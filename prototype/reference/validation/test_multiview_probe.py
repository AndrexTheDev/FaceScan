#!/usr/bin/env python3
"""Synthetische Prüfung der Referenz in multiview_probe.py (keine reale Genauigkeit)."""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multiview_probe import (  # noqa: E402
    ANCHOR_INDICES, ANCHOR_POINTS, ZONE_NAMES, depth_uncertainty_cm, estimate_pose,
    max_pairwise_parallax, project, rodrigues, triangulate, zone_index,
)

WIDTH, HEIGHT = 640, 480
FOCAL = 760.0


def synthetic_scene(yaws=(0.0, -22.0, 24.0), seed=4):
    rng = np.random.default_rng(seed)
    truth = np.zeros((468, 3))
    is_anchor = np.zeros(468, dtype=bool)
    is_anchor[ANCHOR_INDICES] = True
    truth[ANCHOR_INDICES] = ANCHOR_POINTS
    truth[~is_anchor] = rng.uniform([-6, -8, 0], [6, 8, 8], size=(int((~is_anchor).sum()), 3))
    views = []
    for yaw in yaws:
        rotation = rodrigues(np.array([0.02, math.radians(yaw), -0.01]))
        translation = np.array([0.0, 1.0, 55.0])
        uv, _ = project(truth, rotation, translation, FOCAL, FOCAL, WIDTH / 2, HEIGHT / 2)
        landmarks = np.column_stack([(uv[:, 0] + 0.5) / WIDTH, (uv[:, 1] + 0.5) / HEIGHT, np.zeros(468)])
        views.append({"width": WIDTH, "height": HEIGHT, "landmarks": landmarks.tolist()})
    return truth, views


KOTLIN_ANCHOR_FILE = (Path(__file__).resolve().parents[2] / "android/app/src/main/java/"
                      "com/andrexthedev/facescan/scan/CanonicalAnchorData.kt")


def read_kotlin_anchors(path=KOTLIN_ANCHOR_FILE):
    """Liest Indizes und Punkte aus der Kotlin-Datei, ohne sie zu kompilieren."""
    import re
    text = path.read_text(encoding="utf-8")
    indices_block = re.search(r"val indices = intArrayOf\(([^)]*)\)", text)
    points_block = re.search(r"val points: DoubleArray = doubleArrayOf\(([^)]*)\)", text)
    if not indices_block or not points_block:
        raise AssertionError("Ankerblöcke nicht gefunden")
    indices = [int(v) for v in re.findall(r"\d+", indices_block.group(1))]
    cleaned = re.sub(r"//[^\n]*", "", points_block.group(1))
    values = [float(v) for v in re.findall(r"-?\d+\.\d+", cleaned)]
    return indices, np.asarray(values).reshape(-1, 3)


class ZoneAndUncertaintyTest(unittest.TestCase):
    def test_zone_boundaries_match_kotlin_order(self):
        self.assertEqual(zone_index(5.5), 0)
        self.assertEqual(zone_index(5.499), 1)
        self.assertEqual(zone_index(-6.5), 3)
        self.assertEqual(zone_index(-6.51), 4)
        self.assertIsNone(zone_index(float("nan")))
        self.assertIsNone(zone_index(float("inf")))
        # Ankerzahlen je Zone: aus den kanonischen Höhen, nicht geraten.
        counts = [0] * len(ZONE_NAMES)
        for y in ANCHOR_POINTS[:, 1]:
            counts[zone_index(float(y))] += 1
        self.assertEqual(counts, [2, 7, 14, 4, 3])
        self.assertEqual(sum(counts), len(ANCHOR_INDICES))

    def test_depth_uncertainty_formula_and_guards(self):
        expected = 1.0 / (760.0 * math.sin(math.radians(10.0))) * 60.0
        self.assertAlmostEqual(depth_uncertainty_cm(60.0, 1.0, 10.0, 760.0), expected, places=12)
        self.assertLess(depth_uncertainty_cm(60.0, 0.5, 20.0, 760.0), expected)
        for args in ((None, 1.0, 10.0, 760.0), (-1.0, 1.0, 10.0, 760.0),
                     (60.0, float("nan"), 10.0, 760.0), (60.0, 1.0, 0.0, 760.0),
                     (60.0, 1.0, 90.0, 760.0), (60.0, 1.0, 10.0, 0.0)):
            self.assertIsNone(depth_uncertainty_cm(*args), args)

    def test_parallax_between_views_is_measured_from_rays(self):
        rotation = np.eye(3)
        same = [(rotation, np.array([0.0, 0.0, 60.0]), None)] * 2
        self.assertAlmostEqual(max_pairwise_parallax(np.zeros(3), same), 0.0, places=9)
        moved = [(rotation, np.array([0.0, 0.0, 60.0]), None),
                 (rotation, np.array([30.0, 0.0, 60.0]), None)]
        angle = max_pairwise_parallax(np.zeros(3), moved)
        self.assertGreater(angle, 20.0)
        self.assertLess(angle, 40.0)

    def test_report_contains_zone_counts_and_uncertainty_without_truth(self):
        truth, views = synthetic_scene()
        scene = {"camera": {"fx": FOCAL, "fy": FOCAL, "cx": WIDTH / 2, "cy": HEIGHT / 2},
                 "views": views}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scene.json"
            path.write_text(json.dumps(scene), encoding="utf-8")
            output = subprocess.run([sys.executable, str(Path(__file__).with_name("multiview_probe.py")),
                                     str(path)], check=True, capture_output=True, text=True)
        report = json.loads(output.stdout)
        self.assertEqual(sum(report["points_by_zone"].values()), len(report["points"]))
        self.assertEqual(set(report["points_by_zone"]), set(ZONE_NAMES))
        uncertainty = report["depth_uncertainty_cm"]
        self.assertGreater(uncertainty["samples"], 400)
        self.assertGreater(uncertainty["high"], uncertainty["median"])
        # Ohne Rauschen ist die Schätzung praktisch null, aber nicht negativ.
        self.assertGreaterEqual(uncertainty["median"], 0.0)
        self.assertIn("validierte Genauigkeit", uncertainty["note"])


class MultiviewProbeTest(unittest.TestCase):
    def test_anchors_match_canonical_model(self):
        self.assertEqual(len(ANCHOR_INDICES), len(ANCHOR_POINTS))
        self.assertEqual(len(set(ANCHOR_INDICES)), len(ANCHOR_INDICES))
        # Referenzpunkte aus canonical_face_model.obj v0.10.14.
        self.assertAlmostEqual(ANCHOR_POINTS[ANCHOR_INDICES.index(4)][2], 7.586580, places=6)
        self.assertAlmostEqual(ANCHOR_POINTS[ANCHOR_INDICES.index(152)][1], -9.403378, places=6)
        # Dreidimensionale Verteilung: alle drei Achsen müssen streuen.
        self.assertTrue(np.all(np.ptp(ANCHOR_POINTS, axis=0) > 5.0))

    def test_kotlin_anchor_data_matches_python_reference_exactly(self):
        indices, points = read_kotlin_anchors()
        self.assertEqual(indices, ANCHOR_INDICES)
        self.assertEqual(points.shape, ANCHOR_POINTS.shape)
        # Beide Werte stammen aus derselben Modellversion und müssen exakt
        # übereinstimmen; sonst rechnen App und Referenz unterschiedlich.
        np.testing.assert_allclose(points, ANCHOR_POINTS, rtol=0, atol=1e-6)

    def test_pose_and_triangulation_recover_synthetic_truth(self):
        truth, views = synthetic_scene()
        poses = []
        for view in views:
            landmarks = np.asarray(view["landmarks"]).reshape(-1, 3)
            pixels = landmarks[ANCHOR_INDICES, :2] * np.array([WIDTH, HEIGHT]) - 0.5
            estimate = estimate_pose(ANCHOR_POINTS, pixels, FOCAL, FOCAL, WIDTH / 2, HEIGHT / 2)
            self.assertIsNotNone(estimate)
            rotation, translation, rms = estimate
            self.assertLess(rms, 1e-3)
            poses.append((rotation, translation, landmarks))
        worst = 0.0
        for index in range(468):
            observations = [(r, t, lm[index, 0] * WIDTH - 0.5, lm[index, 1] * HEIGHT - 0.5)
                            for r, t, lm in poses]
            point, residual = triangulate(observations, FOCAL, FOCAL, WIDTH / 2, HEIGHT / 2)
            self.assertLess(residual, 1e-6)
            worst = max(worst, float(np.linalg.norm(point - truth[index])))
        self.assertLess(worst, 1e-6)

    def test_requires_two_views_and_valid_camera(self):
        truth, views = synthetic_scene()
        landmarks = np.asarray(views[0]["landmarks"]).reshape(-1, 3)
        observations = [(np.eye(3), np.array([0.0, 0.0, 60.0]), landmarks[0, 0] * WIDTH - 0.5,
                         landmarks[0, 1] * HEIGHT - 0.5)]
        # Eine einzelne Ansicht ist rangdefizient und darf keinen 3D-Punkt liefern.
        self.assertIsNone(triangulate(observations, FOCAL, FOCAL, WIDTH / 2, HEIGHT / 2))

    def test_cli_reports_synthetic_error_and_rejects_single_view(self):
        truth, views = synthetic_scene()
        payload = {
            "camera": {"fx": FOCAL, "fy": FOCAL, "cx": WIDTH / 2, "cy": HEIGHT / 2},
            "views": views,
            "truth": {str(i): truth[i].tolist() for i in range(468)},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scene.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = subprocess.run([sys.executable, str(Path(__file__).with_name("multiview_probe.py")), str(path)],
                                    capture_output=True, text=True, check=True)
            report = json.loads(output.stdout)
            self.assertEqual(report["accepted"], 3)
            self.assertLess(report["truth_error_cm"]["max"], 1e-6)
            path.write_text(json.dumps({**payload, "views": views[:1]}), encoding="utf-8")
            failure = subprocess.run([sys.executable, str(Path(__file__).with_name("multiview_probe.py")), str(path)],
                                     capture_output=True, text=True)
            self.assertNotEqual(failure.returncode, 0)


if __name__ == "__main__":
    unittest.main()

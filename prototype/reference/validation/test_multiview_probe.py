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
    ANCHOR_INDICES, ANCHOR_POINTS, estimate_pose, project, rodrigues, triangulate,
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


class MultiviewProbeTest(unittest.TestCase):
    def test_anchors_match_canonical_model(self):
        self.assertEqual(len(ANCHOR_INDICES), len(ANCHOR_POINTS))
        self.assertEqual(len(set(ANCHOR_INDICES)), len(ANCHOR_INDICES))
        # Referenzpunkte aus canonical_face_model.obj v0.10.14.
        self.assertAlmostEqual(ANCHOR_POINTS[ANCHOR_INDICES.index(4)][2], 7.586580, places=6)
        self.assertAlmostEqual(ANCHOR_POINTS[ANCHOR_INDICES.index(152)][1], -9.403378, places=6)
        # Dreidimensionale Verteilung: alle drei Achsen müssen streuen.
        self.assertTrue(np.all(np.ptp(ANCHOR_POINTS, axis=0) > 5.0))

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

#!/usr/bin/env python3
"""Ableitung von Posen, Triangulation und Teilnetz aus Bildlandmarks.

Reine Referenzrechnung ohne Android/MediaPipe: Der Aufrufer liefert die
normalisierten Landmarks einer oder mehrerer Ansichten sowie die angenommene
Kamera. Das Werkzeug dient dazu, die Kotlin-Implementierung gegen eine
unabhängige Umsetzung zu prüfen (Fehler in Pixeln und Zentimetern), NICHT zur
Angabe einer realen Genauigkeit an Personen.

Alle Schwellen sind dieselben wie in der App und unkalibriert.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

# 30 kanonische Anker in cm (canonical_face_model.obj v0.10.14).
ANCHOR_INDICES = [1, 4, 5, 6, 9, 10, 33, 45, 61, 105, 122, 133, 151, 152, 168,
                  175, 195, 197, 199, 234, 263, 266, 275, 291, 308, 351, 362, 405, 425, 447]
ANCHOR_POINTS = np.array([
    [0.000000, -1.126865, 7.475604], [0.000000, -0.463170, 7.586580],
    [0.000000, 0.365669, 7.242870], [0.000000, 2.473255, 5.788627],
    [0.000000, 4.885979, 5.385258], [0.000000, 8.261778, 4.481535],
    [-4.445859, 2.663991, 3.173422], [-0.496396, -0.475659, 7.440358],
    [-2.456206, -4.342621, 4.283884], [-3.986562, 5.109487, 4.466315],
    [-0.563221, 2.307693, 5.566789], [-1.856432, 2.585245, 3.757904],
    [0.000000, 6.545390, 5.027311], [0.000000, -9.403378, 4.264492],
    [0.000000, 3.271027, 5.236015], [0.000000, -8.765243, 4.891441],
    [0.000000, 1.059413, 6.774605], [0.000000, 1.728369, 6.316750],
    [0.000000, -7.942194, 5.181173], [-7.664182, 0.673132, -2.435867],
    [4.445859, 2.663991, 3.173422], [2.844939, -0.720868, 4.433130],
    [0.496396, -0.475659, 7.440358], [2.456206, -4.342621, 4.283884],
    [2.153084, -4.276322, 4.038093], [0.563221, 2.307693, 5.566789],
    [1.856432, 2.585245, 3.757904], [1.325085, -5.106507, 5.205010],
    [3.832928, -1.537326, 4.137731], [7.297331, 0.763172, -0.048769],
], dtype=np.float64)


def rodrigues(omega):
    omega = np.asarray(omega, dtype=np.float64)
    theta = float(np.linalg.norm(omega))
    if theta < 1e-15:
        return np.eye(3)
    k = omega / theta
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(theta) * kx + (1 - math.cos(theta)) * (kx @ kx)


def project(points, rotation, translation, fx, fy, cx, cy):
    """Projektion mit Blickrichtung +Z; liefert Pixel und Tiefen."""
    camera = points @ rotation.T + translation
    if np.any(camera[:, 2] <= 1e-9):
        raise ValueError("Punkt hinter der Kamera")
    u = fx * camera[:, 0] / camera[:, 2] + cx
    v = fy * camera[:, 1] / camera[:, 2] + cy
    return np.column_stack([u, v]), camera[:, 2]


def estimate_pose(anchors, pixels, fx, fy, cx, cy, iterations=30, huber=1.5):
    """Nichtlineare Gauss-Newton-Pose (R,t) mit Huber-Gewichten.

    Startwert: skaliert-orthographische Naeherung. Dies ist eine unabhaengige
    Referenz, kein Beweis fuer die Guete der Kotlin-Implementierung.
    """
    anchors = np.asarray(anchors, dtype=np.float64)
    pixels = np.asarray(pixels, dtype=np.float64)
    center3 = anchors.mean(axis=0)
    center2 = pixels.mean(axis=0)
    a = anchors - center3
    b = pixels - center2
    # Startwert: Identitaetsrotation, Tiefe aus dem Verhaeltnis der Ausdehnungen.
    # Bewusst anderer Startwert als die POSIT-Initialisierung der Kotlin-App,
    # damit die Referenz nicht denselben Rechenweg kopiert.
    focal = 0.5 * (fx + fy)
    span3 = float(np.mean(np.linalg.norm(a, axis=1)))
    span2 = float(np.mean(np.linalg.norm(b, axis=1)))
    if span3 <= 1e-9 or span2 <= 1e-9:
        return None
    tz = focal * span3 / span2
    rotation = np.eye(3)
    translation = np.array([0.0, 0.0, tz]) - center3
    translation = np.array([-(rotation @ center3)[0], -(rotation @ center3)[1], tz - (rotation @ center3)[2]])
    translation[0] += (center2[0] - cx) * tz / fx
    translation[1] += (center2[1] - cy) * tz / fy

    def residuals(r, t):
        camera = anchors @ r.T + t
        depth = camera[:, 2]
        if np.any(depth <= 1e-9):
            return None, None
        pred = np.column_stack([fx * camera[:, 0] / depth + cx,
                               fy * camera[:, 1] / depth + cy])
        return (pred - pixels).reshape(-1), depth

    def apply(rotation, translation, delta):
        return rodrigues(delta[:3]) @ rotation, translation + delta[3:]

    for _ in range(iterations):
        res, _ = residuals(rotation, translation)
        if res is None:
            return None
        sigma = 1.4826 * np.median(np.abs(res - np.median(res))) + 1e-9
        weights = np.ones_like(res)
        ratio = np.abs(res) / (huber * sigma)
        mask = ratio > 1
        weights[mask] = 1.0 / ratio[mask]
        # Numerische Jacobi-Matrix: absichtlich anderer Rechenweg als die
        # analytischen Ableitungen in der Kotlin-App.
        jacobian = np.zeros((res.size, 6))
        step = 1e-7
        for k in range(6):
            delta = np.zeros(6)
            delta[k] = step
            plus, _ = residuals(*apply(rotation, translation, delta))
            minus, _ = residuals(*apply(rotation, translation, -delta))
            if plus is None or minus is None:
                return None
            jacobian[:, k] = (plus - minus) / (2 * step)
        jw = jacobian * weights[:, None]
        lhs = jw.T @ jacobian + 1e-9 * np.eye(6)
        rhs = -(jw.T @ res)
        try:
            delta = np.linalg.solve(lhs, rhs)
        except np.linalg.LinAlgError:
            return None
        if not np.all(np.isfinite(delta)):
            return None
        rotation, translation = apply(rotation, translation, delta)
        if float(np.linalg.norm(delta)) < 1e-10:
            break
    res, _ = residuals(rotation, translation)
    if res is None:
        return None
    rms = float(np.sqrt(np.mean(res ** 2)))
    return rotation, translation, rms


def triangulate(observations, fx, fy, cx, cy):
    """Kleinste Quadrate zu den Strahlen; None bei ungueltiger Geometrie."""
    a = np.zeros((3, 3))
    b = np.zeros(3)
    for rotation, translation, u, v in observations:
        origin = -rotation.T @ translation
        ray = rotation.T @ np.array([(u - cx) / fx, (v - cy) / fy, 1.0])
        ray = ray / np.linalg.norm(ray)
        a += np.eye(3) - np.outer(ray, ray)
        b += (np.eye(3) - np.outer(ray, ray)) @ origin
    if np.linalg.det(a) < 1e-9:
        return None
    point = np.linalg.solve(a, b)
    residuals = []
    for rotation, translation, u, v in observations:
        camera = rotation @ point + translation
        if camera[2] <= 1e-9:
            return None
        residuals.append([fx * camera[0] / camera[2] + cx - u,
                          fy * camera[1] / camera[2] + cy - v])
    return point, float(np.max(np.abs(residuals)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON mit Kamera, Ansichten und optionaler Wahrheit")
    parser.add_argument("--max-rms-px", type=float, default=6.0)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    camera = data["camera"]
    fx, fy, cx, cy = (float(camera[k]) for k in ("fx", "fy", "cx", "cy"))
    views = data["views"]
    if len(views) > 8:
        raise SystemExit("Maximal 8 Ansichten")
    width, height = int(views[0]["width"]), int(views[0]["height"])
    if any((int(v["width"]), int(v["height"])) != (width, height) for v in views):
        raise SystemExit("Alle Ansichten brauchen dieselbe Bildgroesse")
    poses = []
    for view in views:
        landmarks = np.asarray(view["landmarks"], dtype=np.float64).reshape(-1, 3)
        pixels = landmarks[ANCHOR_INDICES, :2] * np.array([width, height]) - 0.5
        estimate = estimate_pose(ANCHOR_POINTS, pixels, fx, fy, cx, cy)
        if estimate is None:
            continue
        rotation, translation, rms = estimate
        if rms > args.max_rms_px:
            continue
        poses.append((rotation, translation, landmarks))
    if len(poses) < 2:
        raise SystemExit("Weniger als zwei akzeptierte Ansichten")
    report = {"views": len(views), "accepted": len(poses), "points": {}}
    truth = data.get("truth")
    errors = []
    for index in range(int(data.get("landmark_count", 468))):
        observations = [(rotation, translation,
                         landmarks[index, 0] * width - 0.5,
                         landmarks[index, 1] * height - 0.5)
                        for rotation, translation, landmarks in poses]
        result = triangulate(observations, fx, fy, cx, cy)
        if result is None:
            continue
        point, worst = result
        if worst > 2.0:
            continue
        report["points"][str(index)] = [float(x) for x in point]
        if truth is not None and str(index) in truth:
            errors.append(float(np.linalg.norm(np.asarray(truth[str(index)]) - point)))
    if errors:
        report["truth_error_cm"] = {
            "count": len(errors),
            "mean": float(np.mean(errors)),
            "max": float(np.max(errors)),
            "note": "Nur gegen synthetische Wahrheit; keine reale Genauigkeit.",
        }
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

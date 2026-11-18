#!/usr/bin/env python3
"""Vergleich eines FaceScan-OBJ mit externen 3D-Referenzpunkten; vollständig offline.

Die Kalibrierung wird nur aus fit-Punkten geschätzt, der Fehler an getrennten
holdout-Punkten gemessen. Das ist KEINE Validierung ohne echte Referenzdaten.
"""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

VERTICES = 468


def read_obj(path):
    vertices = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            fields = line.split()
            if fields and fields[0] == "v":
                if len(fields) != 4:
                    raise ValueError("OBJ-Vertex muss exakt drei Koordinaten haben")
                vertices.append([float(v) for v in fields[1:]])
    result = np.asarray(vertices, dtype=np.float64)
    if result.shape != (VERTICES, 3) or not np.isfinite(result).all():
        raise ValueError("OBJ benötigt 468 endliche Vertices in FaceScan-Reihenfolge")
    return result


def read_reference(path):
    rows = []
    seen = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"landmark", "x_mm", "y_mm", "z_mm", "role"}
        if reader.fieldnames is None or set(reader.fieldnames) != required:
            raise ValueError("CSV-Header: landmark,x_mm,y_mm,z_mm,role")
        for row in reader:
            idx = int(row["landmark"])
            role = row["role"].strip()
            coords = [float(row[k]) for k in ("x_mm", "y_mm", "z_mm")]
            if not 0 <= idx < VERTICES or idx in seen or role not in ("fit", "holdout") or not all(map(math.isfinite, coords)):
                raise ValueError("Ungültiger/duplizierter Index, Rolle oder Koordinate")
            seen.add(idx)
            rows.append((idx, coords, role))
    return rows


def fit_similarity(source, reference):
    """Geschlossene Ähnlichkeit mit Rotation det +1, Translation und positiver Skala."""
    source = np.asarray(source, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    if source.shape != reference.shape or source.ndim != 2 or source.shape[1] != 3 or len(source) < 4:
        raise ValueError("Mindestens vier entsprechende Fit-Punkte erforderlich")
    if not np.isfinite(source).all() or not np.isfinite(reference).all():
        raise ValueError("Nicht-endliche Werte")
    a_center = source.mean(axis=0)
    b_center = reference.mean(axis=0)
    a = source - a_center
    b = reference - b_center
    if np.linalg.matrix_rank(a, tol=1e-10) < 2 or np.linalg.matrix_rank(b, tol=1e-10) < 2:
        raise ValueError("Fit-Punkte sind nicht ausreichend räumlich verteilt")
    u, _, vt = np.linalg.svd(a.T @ b)
    correction = np.eye(3)
    correction[-1, -1] = np.linalg.det(u @ vt)
    rotation = u @ correction @ vt  # Zeilenvektoren: source @ rotation
    variance = float(np.sum(a * a))
    scale = float(np.sum((a @ rotation) * b) / variance)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Skala nicht bestimmbar")
    translation = b_center - scale * (a_center @ rotation)
    return scale, rotation, translation


def summarize(errors):
    return {"count": len(errors), "mean_mm": float(np.mean(errors)), "median_mm": float(np.median(errors)),
            "rms_mm": float(np.sqrt(np.mean(errors * errors))), "p95_mm": float(np.percentile(errors, 95)),
            "max_mm": float(np.max(errors))}


def compare(vertices, rows):
    fit = [r for r in rows if r[2] == "fit"]
    holdout = [r for r in rows if r[2] == "holdout"]
    if len(fit) < 4 or len(holdout) < 3:
        raise ValueError("Mindestens 4 fit- und 3 unabhängige holdout-Punkte erforderlich")
    if len({r[0] for r in rows}) != len(rows):
        raise ValueError("Doppelte Landmark-Indizes")
    fit_src = vertices[[r[0] for r in fit]]
    fit_ref = np.array([r[1] for r in fit])
    scale, rotation, translation = fit_similarity(fit_src, fit_ref)
    def errors(group):
        points = vertices[[r[0] for r in group]]
        truth = np.array([r[1] for r in group])
        return np.linalg.norm(scale * (points @ rotation) + translation - truth, axis=1)
    return {
        "method": "similarity fit on fit points, error on disjoint holdout points",
        "scale_mm_per_eyespace_unit_fitted": scale,
        "fit": summarize(errors(fit)),
        "holdout": summarize(errors(holdout)),
        "caveat": "Scale and pose fitted to reference; reference accuracy and correspondence errors are not assessed. This is not an independently calibrated metric scan.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("obj", help="neutraler FaceScan-OBJ-Export")
    parser.add_argument("reference_csv", help="externe 3D-Referenzpunkte in mm, mit fit/holdout")
    parser.add_argument("--output", help="optionale JSON-Zusammenfassung; keine individuellen Punkte")
    args = parser.parse_args()
    try:
        result = compare(read_obj(args.obj), read_reference(args.reference_csv))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    text = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Zeigt die wasserdichte Variante neben dem offenen Hautnetz.

Reine Anzeige, keine Kennzahl: ein Z-Buffer-Rasterer mit Lambert-Licht,
geschrieben, weil man einem geschlossenen Netz die Geschlossenheit nicht
ansieht und einem offenen die Löcher nur, wenn man schräg darauf blickt.
Drei Ansichten -- von vorn, von der Seite, von schräg hinten. Genau hinten
liegt die Fläche, die das Poisson-Verfahren ergänzt hat, die es in den
Aufnahmen nicht gab.

Aufruf:
    /tmp/qrenv/bin/python prototype/reference/tools/preview_watertight.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "..", "python")
sys.path.insert(0, os.path.abspath(PY))

from facescan_ref import export_more as em                          # noqa: E402
from facescan_ref import meshopt as mo                              # noqa: E402

MESHES = os.path.abspath(os.path.join(HERE, "..", "meshes"))
RESULTS = os.path.abspath(os.path.join(HERE, "..", "results"))
SIZE = 420
LIGHT = np.array([0.35, 0.55, -0.75])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def render(v: np.ndarray, f: np.ndarray, center: np.ndarray,
           radius: float, size: int = SIZE) -> np.ndarray:
    """Z-Buffer mit Lambert-Licht. Rückgabe: (size, size, 3) in 0..1."""
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    p = v[f]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.where(ln > 1e-20, n / np.maximum(ln, 1e-20), 0.0)
    # BEIDE Netze mit demselben Mittelpunkt und demselben Radius
    # normieren. Nimmt man fuer jedes Netz seine eigenen Werte, wird die
    # geschlossene Variante um 1,63x groesser gezeichnet -- nicht, weil
    # sie groesser waere, sondern weil das offene Netz 132 Inseln hat,
    # von denen eine 18 mm weiter herausragt und damit den Massstab
    # bestimmt. Ein Vergleich, bei dem der Massstab mitschwimmt, ist
    # keiner.
    proj = np.zeros((len(v), 2))
    proj[:, 0] = (v[:, 0] - center[0]) / radius
    proj[:, 1] = (v[:, 1] - center[1]) / radius
    px = (proj * 0.44 + 0.5) * size
    depth = np.full((size, size), -np.inf, dtype=np.float64)
    shade = np.zeros((size, size), dtype=np.float64)
    tri = px[f]
    nrm = n
    for t in range(len(f)):
        a, b, cq = tri[t]
        x0 = max(int(np.floor(min(a[0], b[0], cq[0]))), 0)
        x1 = min(int(np.ceil(max(a[0], b[0], cq[0]))) + 1, size)
        y0 = max(int(np.floor(min(a[1], b[1], cq[1]))), 0)
        y1 = min(int(np.ceil(max(a[1], b[1], cq[1]))) + 1, size)
        if x1 <= x0 or y1 <= y0:
            continue
        # Rueckseiten verwerfen. Ohne das sieht man dem offenen Netz
        # ueberhaupt nicht an, dass es offen ist: von hinten blickt man
        # dann in die Innenseite der Schale, und die sieht genauso
        # geschlossen aus wie eine fertige Oberflaeche. Erst wenn die
        # Rueckseiten fehlen, werden die Loecher zu Loechern.
        if nrm[t, 2] <= 0.0:
            continue
        d = (b[0] - a[0]) * (cq[1] - a[1]) - (cq[0] - a[0]) * (b[1] - a[1])
        if abs(d) < 1e-12:
            continue
        xs = np.arange(x0, x1) + 0.5
        ys = np.arange(y0, y1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        w1 = ((gx - a[0]) * (cq[1] - a[1]) - (cq[0] - a[0]) * (gy - a[1])) / d
        w2 = ((b[0] - a[0]) * (gy - a[1]) - (gx - a[0]) * (b[1] - a[1])) / d
        inside = (w1 >= 0) & (w2 >= 0) & (w1 + w2 <= 1)
        if not inside.any():
            continue
        z = (v[f[t, 0], 2] + w1 * (v[f[t, 1], 2] - v[f[t, 0], 2])
             + w2 * (v[f[t, 2], 2] - v[f[t, 0], 2]))
        z = z * (inside)
        nearer = inside & (z > depth[y0:y1, x0:x1])
        if not nearer.any():
            continue
        lam = max(0.0, float(nrm[t] @ LIGHT))
        sub = depth[y0:y1, x0:x1]
        sub[nearer] = z[nearer]
        sh = shade[y0:y1, x0:x1]
        sh[nearer] = 0.15 + 0.85 * lam
    bg = 0.06
    img = np.full((size, size, 3), bg)
    hit = np.isfinite(depth)
    img[hit, 0] = 0.72 * shade[hit] + 0.18
    img[hit, 1] = 0.70 * shade[hit] + 0.16
    img[hit, 2] = 0.66 * shade[hit] + 0.14
    return np.clip(img, 0.0, 1.0)


def view(v: np.ndarray, f: np.ndarray, yaw_deg: float, pitch_deg: float):
    y = np.deg2rad(yaw_deg)
    p = np.deg2rad(pitch_deg)
    ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0],
                   [-np.sin(y), 0, np.cos(y)]])
    rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)],
                   [0, np.sin(p), np.cos(p)]])
    return v @ (ry @ rx).T, f


def panels_to_png(panels: list, cols: int, path: str,
                  background: float = 0.06) -> None:
    """Setzt die Panels zu einem Bild zusammen und schreibt es."""
    rows = (len(panels) + cols - 1) // cols
    h, w = panels[0].shape[0], panels[0].shape[1]
    canvas = np.full((rows * h, cols * w, 3), background)
    for i, pan in enumerate(panels):
        r, c = divmod(i, cols)
        canvas[r * h:(r + 1) * h, c * w:(c + 1) * w] = pan
    mo.write_png(path, (canvas * 255.0 + 0.5).astype(np.uint8))
    print(f"  {path} ({canvas.shape[1]}x{canvas.shape[0]})")


def coverage(panel: np.ndarray) -> float:
    """Anteil der Bildfläche, auf dem etwas liegt (Hintergrund 0,06)."""
    return float((panel[..., 0] > 0.07).mean())


def main() -> int:
    t0 = time.time()
    skin = np.load(os.path.join(MESHES, "watertight_skin.npz"))
    sv, sf = skin["v"], skin["f"]
    stl = em.read_stl(os.path.join(MESHES, "facescan_watertight.stl"))
    wv, wf = stl["vertices"], stl["faces"]
    print(f"  Hautnetz {len(sv):,} Punkte / {len(sf):,} Dreiecke")
    print(f"  wasserdicht {len(wv):,} Punkte / {len(wf):,} Dreiecke")

    # Massstab aus dem geschlossenen Netz: das ist die vollstaendige Form,
    # am offenen Netz fehlen hinten und unten ganze Flaechenstuecke.
    center = np.asarray(wv, dtype=np.float64).mean(axis=0)
    radius = float(np.linalg.norm(np.asarray(wv, dtype=np.float64) - center,
                                  axis=1).max())
    print(f"  gemeinsamer Massstab: Mittelpunkt {np.round(center, 1)}, "
          f"Radius {radius:.1f} mm")

    panels = []
    for name, yaw, pitch in (("vorn", 0.0, 0.0), ("seitlich", 62.0, 8.0),
                             ("hinten", 168.0, 6.0),
                             ("hinten von oben", 168.0, -34.0)):
        a = render(*view(sv, sf, yaw, pitch), center=center, radius=radius)
        b = render(*view(wv, wf, yaw, pitch), center=center, radius=radius)
        # Deckung ist die einzige Zahl, die hier etwas taugt: von vorn
        # muessen beide Bilder fast gleich viel Flaeche zeigen, von hinten
        # die geschlossene Variante deutlich mehr -- dort liegt die
        # Oberflaeche, die es in den Aufnahmen nicht gab.
        ca = float((a[..., 0] > 0.07).mean())
        cb = float((b[..., 0] > 0.07).mean())
        print(f"  {name:>16}: Hautnetz {100 * ca:5.1f} % der Flaeche, "
              f"wasserdicht {100 * cb:5.1f} % -- das offene Netz zeigt "
              f"{100 * (1 - ca / max(cb, 1e-9)):4.1f} % weniger")
        panels.append(np.concatenate([a, b], axis=1))
    cols = 2
    rows = (len(panels) + cols - 1) // cols
    w = panels[0].shape[1]
    h = panels[0].shape[0]
    canvas = np.zeros((rows * h, cols * w, 3))
    for i, pan in enumerate(panels):
        r, c = divmod(i, cols)
        canvas[r * h:(r + 1) * h, c * w:(c + 1) * w] = pan
    out = os.path.join(RESULTS, "watertight_preview.png")
    mo.write_png(out, (canvas * 255.0 + 0.5).astype(np.uint8))
    print(f"  {out} ({canvas.shape[1]}x{canvas.shape[0]}) "
          f"in {time.time() - t0:.0f} s")
    print("  links das offene Hautnetz, rechts die geschlossene Variante;")
    print("  Rueckseiten sind verworfen, deshalb erscheinen die Loecher im")
    print("  linken Bild als Luecken und nicht als Innenseite der Schale.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

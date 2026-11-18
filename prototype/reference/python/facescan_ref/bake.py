"""Globaler Textur-Bake: EINE Textur aus ALLEN Aufnahmen.

Der Unterschied zum bisherigen Weg ist der folgende, und er ist der
eigentliche Grund fuer dieses Modul:

    Bisher: pro Vertex (oder pro Patch) die "beste" Kamera suchen und
    genau deren Pixel nehmen. Ergebnis: harte Kanten zwischen den
    Zustaendigkeitsbereichen der Kameras -- die "Blocken", die man im
    gerenderten Modell sieht. Jede noch so gute Nachbearbeitung
    (3x3-Blur, Mehrheitsentscheid) kann das nur weichzeichnen, nicht
    beheben, weil die Information "wie saehe es aus Kamera 7 aus?"
    an dieser Stelle bereits weggeworfen wurde.

    Jetzt: pro TEXEL werden ALLE Kameras gefragt, die den Punkt sehen,
    und ihre Farben werden mit dem Sichtwinkel gewichtet gemittelt.
    Ueberall dort, wo zwei Kameras zustaendig sind, geht die Gewichtung
    stetig von der einen zur anderen ueber -- es gibt schlicht keine
    Kante mehr, die man weichzeichnen muesste.

Das Gewicht ist cos(Blickwinkel)^2:
    * cos -> je flacher der Blick auf die Flaeche, desto schlechter
      (Streifblick: ein Pixel deckt Millimeter, und Verdeckung ist
      wahrscheinlich).
    * das Quadrat -> eine Kamera, die genau draufschaut, dominiert.
      Ohne das Quadrat bleibt der Streifblick mit 30 % dabei und zieht
      die Farbe sichtbar grau.

Die Verdeckungspruefung ist nicht optional. Ohne sie malt die
rueckwaertige Kamera die Farbe der Wange auf das Ohr, weil beide im
selben Bild liegen -- nur eben hintereinander.
"""

from __future__ import annotations

import numpy as np


# ------------------------------------------------------------------ UV -> Bild --
#
# Zwei Konventionen, die man auseinanderhalten muss:
#   * UV (glTF, USD, xatlas): v = 0 ist UNTEN.
#   * Bildzeilen: Zeile 0 ist OBEN.
# Wer das verwechselt, bekommt eine kopfstehende Textur -- und merkt es
# erst, wenn das Kinn auf der Stirn sitzt.
def uv_to_pixel(uv: np.ndarray, size: int):
    """(u, v) mit v=0 unten -> (x, y) in Pixel mit y=0 oben."""
    uv = np.asarray(uv, dtype=np.float64)
    x = uv[:, 0] * size
    y = (1.0 - uv[:, 1]) * size
    return x, y


def rasterize_uv(uv: np.ndarray, f: np.ndarray, size: int = 2048,
                 min_px: float = 0.0):
    """Legt fuer jedes Texel fest, welches Dreieck es besitzt.

    Rueckgabe:
        tri   (size, size) int32  -- Dreiecksnummer, -1 = unbelegt
        bary  (size, size, 3) float32 -- baryzentrische Koordinaten

    Gesampelt wird an der Pixelmitte (x+0.5, y+0.5). Dreiecke, die
    kleiner als ein Pixel sind, treffen damit kein Zentrum und wuerden
    Loecher hinterlassen -- deshalb wird um einen halben Pixel
    aufgeweitet (`gut >= -eps` statt `>= 0`). Das ist die uebliche
    "conservative rasterization" und vollkommen ausreichend, weil
    xatlas zwischen den Charts einen Abstand laesst: zwei Dreiecke
    streiten also nie um dasselbe Texel.
    """
    uv = np.asarray(uv, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    x, y = uv_to_pixel(uv, size)

    tri = np.full((size, size), -1, dtype=np.int32)
    bary = np.zeros((size, size, 3), dtype=np.float32)

    px = np.stack([x, y], axis=1)[f]              # (M, 3, 2)
    ax, ay = px[:, 0, 0], px[:, 0, 1]
    bx, by = px[:, 1, 0], px[:, 1, 1]
    cx, cy = px[:, 2, 0], px[:, 2, 1]
    det = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)

    x0 = np.maximum(np.floor(np.minimum(np.minimum(ax, bx), cx)).astype(np.int64), 0)
    x1 = np.minimum(np.ceil(np.maximum(np.maximum(ax, bx), cx)).astype(np.int64), size - 1)
    y0 = np.maximum(np.floor(np.minimum(np.minimum(ay, by), cy)).astype(np.int64), 0)
    y1 = np.minimum(np.ceil(np.maximum(np.maximum(ay, by), cy)).astype(np.int64), size - 1)

    order = np.argsort(-np.abs(det))              # grosse Dreiecke zuerst
    for t in order:
        d = det[t]
        if abs(d) < 1e-18:
            continue
        if x1[t] < x0[t] or y1[t] < y0[t]:
            continue
        xa, ya = ax[t], ay[t]
        ex1, ey1 = bx[t] - xa, by[t] - ya
        ex2, ey2 = cx[t] - xa, cy[t] - ya
        xs = np.arange(x0[t], x1[t] + 1) + 0.5
        ys = np.arange(y0[t], y1[t] + 1) + 0.5
        XX, YY = np.meshgrid(xs, ys)
        qx, qy = XX - xa, YY - ya
        # Baryzentrisch im "Edge"-Schema: w1 entlang e1, w2 entlang e2.
        w1 = (qx * ey2 - qy * ex2) / d
        w2 = (qy * ex1 - qx * ey1) / d
        w0 = 1.0 - w1 - w2
        span = max(abs(ex1), abs(ey1), abs(ex2), abs(ey2), 1e-9)
        eps = 0.5 / span                          # Aufweitung um ~1/2 Pixel
        inside = (w0 >= -eps) & (w1 >= -eps) & (w2 >= -eps)
        if not inside.any():
            continue
        sub = tri[y0[t]:y1[t] + 1, x0[t]:x1[t] + 1]
        inside &= (sub < 0)                       # erstes Dreieck gewinnt
        if not inside.any():
            continue
        ww = np.stack([w0, w1, w2], axis=2)
        ww = np.clip(ww, 0.0, 1.0)
        ww /= ww.sum(axis=2, keepdims=True)
        tri[y0[t]:y1[t] + 1, x0[t]:x1[t] + 1][inside] = t
        bary[y0[t]:y1[t] + 1, x0[t]:x1[t] + 1][inside] = ww[inside]
    return tri, bary


def texel_geometry(tri: np.ndarray, bary: np.ndarray, v: np.ndarray,
                   f: np.ndarray, n: np.ndarray):
    """3D-Punkt und Normale pro belegtem Texel.

    Rueckgabe: (idx_y, idx_x, P (K,3), N (K,3)) -- nur die belegten
    Texel, damit der Bake nicht 4 Millionen leere Pixel mit sich
    herumschleppt.
    """
    iy, ix = np.nonzero(tri >= 0)
    t = tri[iy, ix]
    w = bary[iy, ix]
    tri_v = np.asarray(f, dtype=np.int64)[t]
    p = (np.asarray(v, dtype=np.float64)[tri_v] * w[:, :, None]).sum(axis=1)
    nn = (np.asarray(n, dtype=np.float64)[tri_v] * w[:, :, None]).sum(axis=1)
    ln = np.linalg.norm(nn, axis=1, keepdims=True)
    nn = np.where(ln > 1e-12, nn / np.maximum(ln, 1e-12), 0.0)
    return iy, ix, p, nn


# ------------------------------------------------------------------ Bake ----

def bake_texels(p: np.ndarray, nrm: np.ndarray, frames: list,
                fx: float, fy: float, cx: float, cy: float,
                back_tol_mm: float = 4.0, front_tol_mm: float = 25.0,
                min_cos: float = 0.35,
                gamma: float = 2.0, batch: int = 400_000) -> dict:
    """Mischt fuer jeden 3D-Punkt die Farben ALLER sichtbaren Kameras.

    Rueckgabe je Punkt: `rgb` (uint8), `weight` (Summe der Gewichte),
    `views` (Anzahl beitragender Kameras). Punkte, die keine Kamera
    sieht, bekommen Gewicht 0 und Schwarz -- der Aufrufer muss sie
    fuellen (siehe `dilate`).
    """
    p = np.asarray(p, dtype=np.float64)
    nrm = np.asarray(nrm, dtype=np.float64)
    acc = np.zeros((len(p), 3), dtype=np.float64)
    wsum = np.zeros(len(p), dtype=np.float64)
    views = np.zeros(len(p), dtype=np.int16)

    for fr in frames:
        r = np.asarray(fr["R"], dtype=np.float64)
        t = np.asarray(fr["t"], dtype=np.float64)
        depth = fr["depth"]
        color = np.asarray(fr["color"])
        mask = fr["mask"]
        h, w = depth.shape

        for s in range(0, len(p), batch):
            e = min(s + batch, len(p))
            # Kameraposition des Punkts: p_im = R @ p + t  (Blick entlang +z)
            cam = p[s:e] @ r.T + t
            z = cam[:, 2]
            ok = z > 1.0
            zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
            ui = np.rint(fx * cam[:, 0] / zs + cx).astype(np.int64)
            vi = np.rint(fy * cam[:, 1] / zs + cy).astype(np.int64)
            ok &= (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
            idx = np.flatnonzero(ok)
            if len(idx) == 0:
                continue
            d = depth[vi[idx], ui[idx]]
            m = mask[vi[idx], ui[idx]]
            dz = z[idx] - d                      # > 0 = hinter der Messung
            vis = (m & np.isfinite(d)
                   & (dz <= back_tol_mm) & (dz >= -front_tol_mm))
            sel = idx[vis]
            if len(sel) == 0:
                continue

            # Sichtwinkel: Blickrichtung im Weltkoordinatensystem ist die
            # dritte ZEILE von R (Zeilen = Basisvektoren der Kamera).
            # cos = -dot(normale, blickrichtung), weil die Normale nach
            # aussen zeigt und die Blickrichtung nach innen.
            fwd = r[2]
            cang = -(nrm[s:e][sel] @ fwd)
            good = cang > min_cos
            if not good.any():
                continue
            sel = sel[good]
            wgt = cang[good] ** gamma
            acc[s:e][sel] += color[vi[idx][vis][good], ui[idx][vis][good]] * wgt[:, None]
            wsum[s:e][sel] += wgt
            views[s:e][sel] += 1

    out = np.zeros((len(p), 3), dtype=np.uint8)
    seen = wsum > 0
    if seen.any():
        out[seen] = np.clip(acc[seen] / wsum[seen][:, None], 0, 255).astype(np.uint8)
    return {"rgb": out, "weight": wsum, "views": views, "seen": seen}


# ------------------------------------------------------------------ Naht ----

def dilate(img: np.ndarray, mask: np.ndarray, pad: int = 4) -> np.ndarray:
    """Zieht belegte Texel um `pad` Pixel nach aussen.

    Warum noetig:
      1. Chart-Grenzen. Ein Texel, das zur Haelfte im Abstand zwischen
         zwei Charts liegt, gehoert zu keinem Dreieck. Ohne Aufweitung
         waere dort ein schwarzer Strich -- und der wird beim Rendern
         durch den bilinearen Filter zu einem sichtbaren Gitter.
      2. Mip-Maps. Unterhalb der vollen Aufloesung wird ohnehin
         ueber die Chart-Grenze hinaus gelesen.

    Wir machen die Aufweitung texelweise mit vier Verschiebungen je
    Runde (also eine Chebyshev-Metrik). Das ist einfacher als eine
    echte Distanztransformation und richtiger als das uebliche
    "einmal im Kreis herum": nach `pad` Runden ist jeder Texel im
    Abstand `pad` gefuellt, nicht nur `pad/2`.
    """
    img = np.asarray(img, dtype=np.uint8).copy()
    known = np.asarray(mask, dtype=bool).copy()
    for _ in range(int(pad)):
        grew = False
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            src = np.roll(known, (dy, dx), axis=(0, 1))
            srcv = np.roll(img, (dy, dx), axis=(0, 1))
            take = src & (~known)
            if take.any():
                img[take] = srcv[take]
                known |= take
                grew = True
        if not grew:
            break
    return img


def inpaint_from_mesh(img: np.ndarray, mask: np.ndarray, pad: int = 6):
    """Wie `dilate`, liefert aber die Fuell-Maske mit zurueck."""
    filled = dilate(img, mask, pad)
    return filled, np.asarray(mask, dtype=bool).copy()

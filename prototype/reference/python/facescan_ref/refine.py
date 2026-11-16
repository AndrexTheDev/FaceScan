"""Stufe 12 (docs/03): Verfeinerung des Mesh an den Tiefenbildern.

Warum noetig?
  Die TSDF mittelt ihr Abstandsfeld entlang der BLICKSTRAHLEN und auf einem
  Gitter. Beides erzeugt einen systematischen Versatz: das Mesh liegt zwar
  glatt und geschlossen da, aber im Mittel rund 1 mm NEBEN der echten Haut.
  Fuer einen Export, der spaeter in Blender/Maya weiterverarbeitet wird, ist
  das sichtbar ("die Nase sitzt nicht ganz").

Die Gegenmassnahme ist billig und standardmaessig:
  Jeder Vertex wird in jedes Bild zurueckgerechnet, in dem er SICHTBAR ist
  (Tiefenvergleich statt blossem "im Bild"), dort der Tiefenwert gelesen und
  der Vertex auf den Mittelwert dieser echten 3D-Punkte gezogen -- aber nur
  entlang seiner Normalen, damit die Punktverteilung auf der Flaeche nicht
  verklumpt.

Das ist KEIN "Nachjustieren mit der Ground Truth": es benutzt ausschliesslich
die Tiefenbilder, die auch die echte App hat.
"""
from __future__ import annotations

import numpy as np

from .metrics import vertex_normals


def refine_by_depth(v, f, frames, fx, fy, cx, cy, label: int = 1,
                    iters: int = 2, depth_tol_mm: float = 3.0,
                    max_move_mm: float = 1.5, min_views: int = 2):
    """Zieht die Vertices auf die von den Tiefenbildern gemessene Flaeche."""
    v = np.asarray(v, dtype=np.float64).copy()
    f = np.asarray(f, dtype=np.int64)
    if len(v) == 0:
        return v

    for it in range(iters):
        acc = np.zeros_like(v)
        cnt = np.zeros(len(v), dtype=np.int64)
        normals = vertex_normals(v, f)
        for fr in frames:
            r = np.asarray(fr["R"], dtype=np.float64)
            t = np.asarray(fr["t"], dtype=np.float64)
            depth, mask = fr["depth"], fr["mask"]
            h, w = depth.shape
            cam = v @ r.T + t
            z = cam[:, 2]
            ok = z > 1.0
            zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
            u = fx * cam[:, 0] / zs + cx
            vv = fy * cam[:, 1] / zs + cy
            ui = np.rint(u).astype(np.int64)
            vi = np.rint(vv).astype(np.int64)
            ok &= (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
            idx = np.where(ok)[0]
            if not len(idx):
                continue
            d = depth[vi[idx], ui[idx]]
            good = (mask[vi[idx], ui[idx]]
                    & (fr["label"][vi[idx], ui[idx]] == label)
                    & np.isfinite(d) & (d > 0)
                    & (np.abs(d - z[idx]) <= depth_tol_mm))
            sel = idx[good]
            if not len(sel):
                continue
            ray = np.stack([(u[sel] - cx) / fx, (vv[sel] - cy) / fy,
                            np.ones(len(sel))], axis=1)
            pts_cam = ray * d[good][:, None]
            pts_world = (pts_cam - t) @ r        # p = R^T (cam - t)
            acc[sel] += pts_world
            cnt[sel] += 1

        enough = cnt >= min_views
        if not enough.any():
            break
        target = np.zeros_like(v)
        target[enough] = acc[enough] / cnt[enough][:, None]
        move = target - v
        along = np.sum(move * normals, axis=1)[:, None] * normals
        along = np.clip(along, -max_move_mm, max_move_mm)
        v[enough] += along[enough]
    return v

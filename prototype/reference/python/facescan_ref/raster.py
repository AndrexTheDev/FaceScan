"""Z-Buffer-Rasterizer fuer die M1-Referenz (NumPy, rein on-device denkbar).

Warum ein eigener Rasterizer?
  * Fuer Tiefenfusion und Visual-Hull brauchen wir pro Pixel Tiefe UND
    Material-Label (Haut / Haar / Hintergrund). Kein fertiges Paket liefert
    beides so, wie wir es brauchen -- und jedes externe Paket waere eine
    Lizenz- und Abhaengigkeitsfrage (docs/09).
  * Die Operation ist simpel: Dreieck -> Bildschirm, Baryzentrisch, Z-Test.

WICHTIG -- Koordinatkonvention:
  Dieselbe wie im Kotlin-Kern (CameraModel.project):
      u = fx * x_cam / z_cam + cx
      v = fy * y_cam / z_cam + cy
  Bildzeile 0 entspricht also kleinem y (Kopf steht auf dem Kopf). Das ist
  fuer Rekonstruktion und Fusion belanglos, solange ALLES mit derselben
  Formel rechnet -- genau das tun Rendern und Fusion hier. Nur zum Debuggen
  wird das Bild gekippt ausgegeben.

Tiefe = z_cam in Millimeter (positiv vor der Kamera), Hintergrund = inf.
"""
from __future__ import annotations

import numpy as np


class Renderer:
    """Sammelt mehrere Meshes in einem gemeinsamen Z-Buffer."""

    def __init__(self, width: int, height: int, fx: float, fy: float,
                 cx: float, cy: float):
        self.w, self.h = width, height
        self.fx, self.fy, self.cx, self.cy = fx, fy, cx, cy
        self.depth = np.full((height, width), np.inf, dtype=np.float64)
        self.label = np.zeros((height, width), dtype=np.uint8)
        self.color = np.zeros((height, width, 3), dtype=np.float64)
        self.ids = np.full((height, width), -1, dtype=np.int64)

    # ------------------------------------------------------------------
    def project(self, points: np.ndarray, rotation: np.ndarray,
                translation: np.ndarray):
        cam = points @ rotation.T + translation
        z = cam[:, 2]
        zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
        u = self.fx * cam[:, 0] / zs + self.cx
        v = self.fy * cam[:, 1] / zs + self.cy
        return u, v, z

    def draw(self, vertices: np.ndarray, faces: np.ndarray,
             colors: np.ndarray, rotation: np.ndarray, translation: np.ndarray,
             label: int, shading: np.ndarray | None = None) -> None:
        """Rasterisiert ein Mesh in die gemeinsamen Puffer."""
        u, v, z = self.project(vertices, rotation, translation)
        cols = np.asarray(colors, dtype=np.float64)
        if shading is not None:
            cols = cols * np.asarray(shading, dtype=np.float64)[:, None]

        w, h = self.w, self.h
        for fi in range(faces.shape[0]):
            a, b, c = faces[fi]
            za, zb, zc = z[a], z[b], z[c]
            if za <= 1.0 or zb <= 1.0 or zc <= 1.0:
                continue
            ua, ub, uc = u[a], u[b], u[c]
            va, vb, vc = v[a], v[b], v[c]

            u0 = max(0, int(np.floor(min(ua, ub, uc))))
            u1 = min(w - 1, int(np.ceil(max(ua, ub, uc))))
            v0 = max(0, int(np.floor(min(va, vb, vc))))
            v1 = min(h - 1, int(np.ceil(max(va, vb, vc))))
            if u1 < u0 or v1 < v0:
                continue

            # Bildschirmflaeche (Vorzeichen gibt die Orientierung)
            area = (ub - ua) * (vc - va) - (uc - ua) * (vb - va)
            if abs(area) < 1e-12:
                continue
            sign = 1.0 if area > 0 else -1.0

            pu = np.arange(u0, u1 + 1, dtype=np.float64) + 0.5
            pv = np.arange(v0, v1 + 1, dtype=np.float64) + 0.5
            gu, gv = np.meshgrid(pu, pv)

            w0 = sign * ((ub - ua) * (gv - va) - (vb - va) * (gu - ua))
            w1 = sign * ((uc - ub) * (gv - vb) - (vc - vb) * (gu - ub))
            w2 = sign * ((ua - uc) * (gv - vc) - (va - vc) * (gu - uc))
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue

            total = w0 + w1 + w2
            total = np.where(total == 0, 1e-12, total)
            l0 = w0[inside] / total[inside]
            l1 = w1[inside] / total[inside]
            l2 = w2[inside] / total[inside]

            # Perspektivisch korrekt interpolieren: 1/z ist bildlinear
            inv = l0 / za + l1 / zb + l2 / zc
            zp = 1.0 / np.maximum(inv, 1e-12)
            cp = ((l0 / za)[:, None] * cols[a] + (l1 / zb)[:, None] * cols[b]
                  + (l2 / zc)[:, None] * cols[c]) / np.maximum(inv, 1e-12)[:, None]

            sl = self.depth[v0:v1 + 1, u0:u1 + 1][inside]
            hit = zp < sl
            if not hit.any():
                continue
            idx = np.where(inside)
            rows = v0 + idx[0][hit]
            colsx = u0 + idx[1][hit]
            self.depth[rows, colsx] = zp[hit]
            self.label[rows, colsx] = label
            self.color[rows, colsx] = cp[hit]

    # ------------------------------------------------------------------
    def finish(self) -> dict:
        return {
            "depth": self.depth.copy(),
            "label": self.label.copy(),
            "color": np.clip(self.color, 0, 255).astype(np.uint8),
            "mask": np.isfinite(self.depth),
        }


def lambert(vertices: np.ndarray, faces: np.ndarray,
            light_dir: np.ndarray, ambient: float = 0.55) -> np.ndarray:
    """Einfache, glatte Beleuchtung je Vertex (0..1..~1.4).

    Wichtig fuer den Ehrlichkeitstest: verschiedene Bilder zeigen dieselbe
    Hautstelle unterschiedlich hell (weil aus anderer Richtung beleuchtet).
    Die Texturstufe muss das spaeter herausmitteln -- hier messen wir nur,
    wie viel Flaeche ueberhaupt Textur bekommt.
    """
    v0 = vertices[faces[:, 0]]
    v1 = vertices[faces[:, 1]]
    v2 = vertices[faces[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    norms = np.zeros(vertices.shape, dtype=np.float64)
    np.add.at(norms, faces[:, 0], fn)
    np.add.at(norms, faces[:, 1], fn)
    np.add.at(norms, faces[:, 2], fn)
    ln = np.linalg.norm(norms, axis=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        n = np.where(ln > 1e-12, norms / np.maximum(ln, 1e-12), np.array([0.0, 1.0, 0.0]))
    n[:, 0] = np.where(ln[:, 0] > 1e-12, n[:, 0], 0.0)
    n[:, 1] = np.where(ln[:, 0] > 1e-12, n[:, 1], 1.0)
    n[:, 2] = np.where(ln[:, 0] > 1e-12, n[:, 2], 0.0)

    l = light_dir / np.linalg.norm(light_dir)
    diff = np.clip(n @ l, 0.0, 1.0)
    return ambient + (1.0 - ambient) * diff

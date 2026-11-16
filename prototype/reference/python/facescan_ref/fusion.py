"""TSDF-Fusion und Marching-Tetrahedra (M1, Geometrie-Kette).

Stufe 8-11 der Pipeline (docs/03): aus N Tiefenbildern mit bekannter Pose
wird EINE wasserdichte Oberflaeche.

Warum TSDF?
  * Sie mittelt Rauschen ueber beliebig viele Bilder -- der Fehler faellt
    mit 1/sqrt(N). Einzelne Tiefenbilder eines Handys sind zu schlecht.
  * Sie liefert direkt ein Volumen, aus dem sich eine geschlossene
    Oberflaeche schneiden laesst (Marching Cubes / Tetrahedra).
  * Sie laesst sich in Bloecken (Bricks) verarbeiten -> spaeter streaming-
    faehig und speicherarm auf dem Handy.

Warum Marching TETRAHEDRA statt Marching Cubes?
  Marching Cubes hat 15 Grundfaelle, von denen 5 mehrdeutig sind ("ambiguous
  cases"): falsch aufgeloest entstehen LOECHER im Mesh -- der Klassiker.
  Die Zerlegung eines Wuerfels in 6 Tetraeder (Freudenthal/Kuhn) ist
  konform (benachbarte Wuerfel passen exakt zusammen), hat keine
  Mehrdeutigkeiten und ist in ~120 statt ~400 Zeilen vollstaendig korrekt.
  Preis: ~2x so viele Dreiecke. Auf dem Handy wird spaeter entruempelt
  (Quadric Edge Collapse, docs/03 Stufe 13).

Vorzeichenkonvention (wichtig, wird von den Tests geprueft):
    sdf < 0  innen (hinter der gemessenen Oberflaeche)
    sdf > 0  aussen (zwischen Kamera und Oberflaeche)
    Oberflaeche = Niveau 0
"""
from __future__ import annotations

import numpy as np

# Eckpunkte eines Wuerfels, Reihenfolge ist VERBINDLICH (wie Muenz-Notation)
CUBE_CORNERS = np.array([
    [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
    [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1],
], dtype=np.int64)

# Freudenthal-Zerlegung: 6 Tetraeder um die Raumdiagonale 0-7.
# Diese Zerlegung ist KONFORM -- die Dreiecksflaechen benachbarter Wuerfel
# stimmen ueberein, es gibt keine Loecher.
CUBE_TETS = np.array([
    [0, 1, 3, 7],
    [0, 1, 7, 5],
    [0, 5, 7, 4],
    [0, 4, 7, 6],
    [0, 6, 7, 2],
    [0, 2, 7, 3],
], dtype=np.int64)

TET_EDGES = np.array([[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]], dtype=np.int64)


class TsdfVolume:
    """Regulaeres TSDF-Gitter.

    Parameter
    ---------
    bbox_min, bbox_max : untere/obere Ecke des Volumens (mm)
    voxel_mm           : Kantenlaenge eines Voxels
    trunc_mm           : Trunkierungsband (mm); groesser als Rauschen,
                         kleiner als der Abstand zu gegenueberliegenden
                         Oberflaechen (sonst verschmelzen Haut und Haar)
    """

    def __init__(self, bbox_min, bbox_max, voxel_mm: float, trunc_mm: float):
        self.origin = np.asarray(bbox_min, dtype=np.float64)
        self.voxel = float(voxel_mm)
        self.trunc = float(trunc_mm)
        self.dims = np.ceil((np.asarray(bbox_max, dtype=np.float64) - self.origin)
                            / self.voxel).astype(np.int64) + 1
        # Werte sind NORMIERT auf [-1, 1] (Anteil der Trunkierung),
        # 1.0 bedeutet "sicher draussen" -- das ist der Startzustand.
        self.sdf = np.ones(self.dims, dtype=np.float32)
        self.weight = np.zeros(self.dims, dtype=np.float32)
        self.n_updates = 0

    @property
    def shape(self):
        return tuple(int(d) for d in self.dims)

    def voxel_centers(self, k0: int, k1: int):
        """Mittelpunkte der Voxel der z-Schichten [k0, k1)."""
        i = np.arange(self.dims[0])
        j = np.arange(self.dims[1])
        k = np.arange(k0, k1)
        ii, jj, kk = np.meshgrid(i, j, k, indexing="ij")
        idx = np.stack([ii.ravel(), jj.ravel(), kk.ravel()], axis=1)
        pts = self.origin + (idx + 0.5) * self.voxel
        return idx, pts

    @staticmethod
    def incidence_weights(depth, mask, fx, fy, cx, cy, floor: float = 0.15):
        """Gewicht je Pixel aus dem Einfallswinkel (cos zwischen Blickstrahl
        und Oberflaechennormale).

        Warum das noetig ist: die TSDF misst ihren Abstand entlang des
        BLICKSTRAHLS, nicht senkrecht zur Oberflaeche. Bei streifendem Blick
        (Rand des Kopfes) ist der Fehler deshalb um 1/cos groesser. Ohne
        Gewichtung bleibt ein systematischer Versatz von rund 1 mm -- genau
        der Betrag, der hier zwischen "bestanden" und "nicht bestanden"
        steht. Mit Gewichtung sinkt er deutlich.

        Die Normalen kommen aus dem Tiefenbild (np.gradient) -- das ist
        billig und fuer die Gewichtung genau genug.
        """
        h, w = depth.shape
        d = np.where(np.isfinite(depth) & (depth > 0), depth, 0.0)
        zu = np.gradient(d, axis=1)
        zv = np.gradient(d, axis=0)
        nx = -zu * d / fy
        ny = -zv * d / fx
        nz = d * d / (fx * fy)
        ln = np.sqrt(nx * nx + ny * ny + nz * nz)
        ln = np.where(ln < 1e-9, 1e-9, ln)
        uu = (np.arange(w, dtype=np.float64)[None, :] - cx) / fx
        vv = (np.arange(h, dtype=np.float64)[:, None] - cy) / fy
        rl = np.sqrt(uu * uu + vv * vv + 1.0)
        dot = (nx * uu + ny * vv + nz) / (ln * rl)
        wgt = np.clip(np.abs(dot), floor, 1.0)
        return np.where(mask & np.isfinite(depth) & (depth > 0), wgt, 0.0)

    def integrate(self, depth, mask, rotation, translation,
                  fx, fy, cx, cy, max_weight: float = 64.0, slab: int = 16,
                  weights: np.ndarray | None = None):
        """Fuegt EIN Tiefenbild ein.

        depth (H,W) in mm, mask (H,W) = welche Pixel benutzt werden duerfen.
        weights (H,W) optional = Gewicht je Pixel (z. B. Einfallswinkel).
        """
        h, w = depth.shape
        r = np.asarray(rotation, dtype=np.float64)
        t = np.asarray(translation, dtype=np.float64)

        for k0 in range(0, self.dims[2], slab):
            k1 = min(k0 + slab, self.dims[2])
            idx, pts = self.voxel_centers(k0, k1)

            cam = pts @ r.T + t
            z = cam[:, 2]
            good = z > 1.0
            if not good.any():
                continue
            zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
            u = fx * cam[:, 0] / zs + cx          # gleiche Konvention wie raster.py
            v = fy * cam[:, 1] / zs + cy
            ui = np.rint(u).astype(np.int64)
            vi = np.rint(v).astype(np.int64)

            inside = good & (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
            if not inside.any():
                continue

            d = depth[vi[inside], ui[inside]]
            m = mask[vi[inside], ui[inside]]
            ok = m & np.isfinite(d) & (d > 0)
            if not ok.any():
                continue

            zz = z[inside][ok]
            dd = d[ok]
            sdf = dd - zz                          # >0 = vor der Oberflaeche (aussen)
            band = np.abs(sdf) <= self.trunc
            if not band.any():
                continue

            sel = np.where(inside)[0][ok][band]
            sv = np.clip(sdf[band] / self.trunc, -1.0, 1.0)
            if weights is None:
                wgt = np.ones(len(sel), dtype=np.float32)
            else:
                wgt = weights[vi[inside][ok][band], ui[inside][ok][band]]\
                    .astype(np.float32)

            i0, j0, kk = idx[sel][:, 0], idx[sel][:, 1], idx[sel][:, 2]
            flat_prev = self.weight[i0, j0, kk]
            w_new = np.minimum(flat_prev + wgt, max_weight)
            # laufender Mittelwert (Kinect-Fusion-Regel)
            sdf_old = self.sdf[i0, j0, kk]
            sdf_new = np.where(flat_prev > 0,
                               (sdf_old * flat_prev + sv * wgt) / w_new,
                               sv)
            self.sdf[i0, j0, kk] = sdf_new.astype(np.float32)
            self.weight[i0, j0, kk] = w_new
        self.n_updates += 1


# --------------------------------------------------------- Oberflaeche ----

def _tet_surface(sv: np.ndarray, tv: np.ndarray):
    """Dreiecke EINES Tetraeder-Typs fuer einen ganzen Block von Wuerfeln.

    sv  (nc, 4)  : Vorzeichen-behaftete Werte an den 4 Ecken
    tv  (nc,4,3) : Eckpunkte in Weltkoordinaten
    Rueckgabe: (P, 3, 3) Dreiecke (Weltkoordinaten), (P,3) Schwerpunkt
    """
    nc = sv.shape[0]
    inside = sv < 0.0
    m = inside.sum(axis=1)

    out_p = []
    out_g = []

    # ---- Fall 1/3: ein Eckpunkt ist "anders" -> EIN Dreieck ---------------
    for kind in (1, 3):
        sel = np.where(m == kind)[0]
        if len(sel) == 0:
            continue
        # der "andere" Eckpunkt: bei m==1 der innere, bei m==3 der aeussere
        if kind == 1:
            odd = np.argmax(inside[sel], axis=1)
        else:
            odd = np.argmax(~inside[sel], axis=1)
        others = np.array([[a for a in range(4) if a != o] for o in odd], dtype=np.int64)

        va = np.take_along_axis(sv[sel], odd[:, None], axis=1)[:, 0]
        pa = tv[sel, odd, :]
        tri = []
        for c in range(3):
            ob = others[:, c]
            vb = np.take_along_axis(sv[sel], ob[:, None], axis=1)[:, 0]
            pb = tv[sel, ob, :]
            s = va / (va - vb)
            tri.append(pa + s[:, None] * (pb - pa))
        p0, p1, p2 = tri
        cen = (p0 + p1 + p2) / 3.0
        out_p.append(np.stack([p0, p1, p2], axis=1))
        out_g.append(cen)

    # ---- Fall 2/2: vier Kreuzungen -> Viereck -> zwei Dreiecke -----------
    sel = np.where(m == 2)[0]
    if len(sel):
        order = np.argsort(inside[sel].astype(np.int8), axis=1, kind="stable")
        o1, o2, i1, i2 = order[:, 0], order[:, 1], order[:, 2], order[:, 3]

        def cross(a_idx, b_idx):
            va = np.take_along_axis(sv[sel], a_idx[:, None], axis=1)[:, 0]
            vb = np.take_along_axis(sv[sel], b_idx[:, None], axis=1)[:, 0]
            pa = tv[sel, a_idx, :]
            pb = tv[sel, b_idx, :]
            s = va / (va - vb)
            return pa + s[:, None] * (pb - pa)

        # Zyklus: (i1,o1) - (i2,o1) - (i2,o2) - (i1,o2)  (s. Kommentar oben)
        a = cross(i1, o1)
        b = cross(i2, o1)
        c = cross(i2, o2)
        d = cross(i1, o2)
        out_p.append(np.stack([a, b, c], axis=1))
        out_g.append((a + b + c) / 3.0)
        out_p.append(np.stack([a, c, d], axis=1))
        out_g.append((a + c + d) / 3.0)

    if not out_p:
        z = np.zeros((0, 3, 3))
        return z, np.zeros((0, 3))
    return np.concatenate(out_p, axis=0), np.concatenate(out_g, axis=0)


def marching_tetrahedra(volume: TsdfVolume, min_weight: float = 1.0,
                        slab: int = 24):
    """Schneidet die Nullniveauflaeche aus dem TSDF.

    Rueckgabe: (V (N,3), F (M,3)) -- gemeinsam genutzte Punkte, konsistent
    nach aussen orientiert (Normalen zeigen Richtung wachsendem SDF).
    """
    nx, ny, nz = volume.shape
    if min(nx, ny, nz) < 2:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

    tri_list = []
    cen_list = []

    for k0 in range(0, nz - 1, slab):
        k1 = min(k0 + slab, nz - 1)
        nk = k1 - k0
        if nk <= 0:
            continue
        ii, jj, kk = np.meshgrid(
            np.arange(nx - 1), np.arange(ny - 1), np.arange(nk), indexing="ij")
        base = np.stack([ii.ravel(), jj.ravel(), (kk.ravel() + k0)], axis=1)

        # 8 Eckwerte je Wuerfel
        cv = np.empty((base.shape[0], 8), dtype=np.float64)
        cw = np.empty((base.shape[0], 8), dtype=np.float64)
        for c in range(8):
            o = CUBE_CORNERS[c]
            cv[:, c] = volume.sdf[base[:, 0] + o[0], base[:, 1] + o[1], base[:, 2] + o[2]]
            cw[:, c] = volume.weight[base[:, 0] + o[0], base[:, 1] + o[1], base[:, 2] + o[2]]

        # Wuerfel verwerfen, die nie beobachtet wurden oder kein Vorzeichenwechsel haben
        observed = (cw >= min_weight).all(axis=1)
        has_cross = (cv < 0).any(axis=1) & (cv > 0).any(axis=1)
        keep = observed & has_cross
        if not keep.any():
            continue
        base = base[keep]
        cv = cv[keep]
        nc = base.shape[0]

        # Eckpunkte in Weltkoordinaten
        corners = volume.origin + (base[:, None, :] + CUBE_CORNERS[None, :, :]) * volume.voxel

        for tet in CUBE_TETS:
            idx = tet
            sv = cv[:, idx]                                   # (nc,4)
            tv = corners[:, idx, :]                           # (nc,4,3)
            tris, cens = _tet_surface(sv, tv)
            if len(tris):
                tri_list.append(tris)
                cen_list.append(cens)

    if not tri_list:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)

    tris = np.concatenate(tri_list, axis=0).astype(np.float64)
    cens = np.concatenate(cen_list, axis=0)

    # --- Orientierung: Normalen entlang +grad(sdf) (also nach aussen) -----
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    nrm = np.cross(e1, e2)
    grad = _sdf_gradient(volume, cens)
    flip = np.sum(nrm * grad, axis=1) < 0
    tris[flip] = tris[flip][:, [0, 2, 1]]

    # --- Punkte zusammenfuehren ------------------------------------------
    flat = np.round(tris.reshape(-1, 3), 5)
    uniq, inv = np.unique(flat, axis=0, return_inverse=True)
    faces = inv.reshape(-1, 3).astype(np.int64)
    return uniq.astype(np.float64), faces


def _sdf_gradient(volume: TsdfVolume, points: np.ndarray, eps: float = None):
    """Zentraler Differenzenquotient des SDF an beliebigen Punkten."""
    if eps is None:
        eps = volume.voxel
    p = np.asarray(points, dtype=np.float64)
    g = np.empty_like(p)
    for ax in range(3):
        off = np.zeros(3)
        off[ax] = eps
        a = _sample_sdf(volume, p + off)
        b = _sample_sdf(volume, p - off)
        g[:, ax] = a - b
    n = np.linalg.norm(g, axis=1, keepdims=True)
    g = np.where(n > 1e-12, g / np.maximum(n, 1e-12), np.array([0.0, 0.0, 1.0]))
    return g


def _sample_sdf(volume: TsdfVolume, points: np.ndarray):
    """Naechster-Nachbar-Abtastung des SDF (ausreichend fuer Vorzeichen)."""
    idx = np.rint((points - volume.origin) / volume.voxel - 0.5).astype(np.int64)
    for ax in range(3):
        idx[:, ax] = np.clip(idx[:, ax], 0, volume.dims[ax] - 1)
    return volume.sdf[idx[:, 0], idx[:, 1], idx[:, 2]].astype(np.float64)

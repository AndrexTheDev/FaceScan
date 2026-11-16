"""Haare Stufe L1: Volumen aus der Silhouette (Visual Hull).

So in docs/03 beschlossen:
    L1 (v1) = Volumen/"Kappe" aus Silhouetten -- robust, echte Form,
              aber ohne Straehnen.
    L2 (v2) = Hair Cards (texturierte Streifen)
    L3 (v3) = echte Straehnen

Warum Visual Hull und nicht Tiefe?
  Haar-Tiefe ist auf echten Handybildern unzuverlaessig: feine Haare
  verwackeln, die Kanten sind unscharf, und Segmentation liefert eine saubere
  Maske, aber keine verlaessliche Tiefe. Die Silhouette ist dagegen stabil.
  Also: Maske ist vertrauenswuerdig -> Volumen aus der Maske schneiden.

Das Verfahren (klassisch, aber hier mit zwei Zusatzregeln):
  1. Visual Hull  = Schnitt aller Silhouettenkegel. Ein Voxel bleibt, wenn es
     in JEDEM Bild, in dem es sichtbar ist, auf eine Haar-Maske faellt.
  2. Freiraum     = ein Voxel, das in irgendeinem Bild VOR der Silhouette
     liegt (auf Hintergrund), ist sicher Luft -> entfernen.
  3. Innen        = was im Kopf steckt, ist keine Haarspitze -> entfernen.

Bekannte Grenze (und deshalb in der App ehrlich kommuniziert):
  Bei einem Selbstscan ohne Spiegel sieht die Kamera den Hinterkopf NIE.
  Dort ist das Volumen nicht beobachtbar und wird extrapoliert. Der Bericht
  weist die Guete deshalb getrennt aus: "beobachtet" und "extrapoliert".
"""
from __future__ import annotations

import numpy as np


def visual_hull(volume, poses, masks, fx, fy, cx, cy, slab: int = 16):
    """Schnitt der Silhouettenkegel.

    masks: Liste von (H,W) bool -- je Kamerabild eine Maske.
    Rueckgabe: bool-Gitter, True = "koennte zum Objekt gehoeren".
    """
    occ = np.ones(volume.dims, dtype=bool)
    for (r, t), mask in zip(poses, masks):
        h, w = mask.shape
        rr = np.asarray(r, dtype=np.float64)
        tt = np.asarray(t, dtype=np.float64)
        for k0 in range(0, volume.dims[2], slab):
            k1 = min(k0 + slab, volume.dims[2])
            idx, pts = volume.voxel_centers(k0, k1)
            cam = pts @ rr.T + tt
            z = cam[:, 2]
            good = z > 1.0
            zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
            ui = np.rint(fx * cam[:, 0] / zs + cx).astype(np.int64)
            vi = np.rint(fy * cam[:, 1] / zs + cy).astype(np.int64)
            visible = good & (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
            if not visible.any():
                continue
            hit = mask[vi[visible], ui[visible]]
            sel = np.where(visible)[0][~hit]
            if len(sel):
                ii, jj, kk = idx[sel][:, 0], idx[sel][:, 1], idx[sel][:, 2]
                occ[ii, jj, kk] = False
    return occ


def carve_free_space(volume, poses, masks, fx, fy, cx, cy, slab: int = 16):
    """Voxel, die in irgendeinem Bild auf HINTERGRUND fallen, sind Luft.

    masks = Silhouette des GANZEN Objekts (Haar + Haut). Ein Voxel davor
    wuerde das Objekt verdecken -- es kann also nicht dazugehoeren.
    Rueckgabe: True = "sicher Luft" (darf entfernt werden).
    """
    air = np.zeros(volume.dims, dtype=bool)
    for (r, t), mask in zip(poses, masks):
        h, w = mask.shape
        rr = np.asarray(r, dtype=np.float64)
        tt = np.asarray(t, dtype=np.float64)
        for k0 in range(0, volume.dims[2], slab):
            k1 = min(k0 + slab, volume.dims[2])
            idx, pts = volume.voxel_centers(k0, k1)
            cam = pts @ rr.T + tt
            z = cam[:, 2]
            good = z > 1.0
            zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
            ui = np.rint(fx * cam[:, 0] / zs + cx).astype(np.int64)
            vi = np.rint(fy * cam[:, 1] / zs + cy).astype(np.int64)
            visible = good & (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
            if not visible.any():
                continue
            hit = mask[vi[visible], ui[visible]]
            sel = np.where(visible)[0][~hit]
            if len(sel):
                ii, jj, kk = idx[sel][:, 0], idx[sel][:, 1], idx[sel][:, 2]
                air[ii, jj, kk] = True
    return air


def inside_test(volume, points, fn) -> np.ndarray:
    """Wendet eine analytische Innen-Test-Funktion auf Voxelmittelpunkte an."""
    out = np.zeros(volume.dims, dtype=bool)
    for k0 in range(0, volume.dims[2], 16):
        k1 = min(k0 + 16, volume.dims[2])
        idx, pts = volume.voxel_centers(k0, k1)
        res = np.asarray(fn(pts)).reshape(volume.dims[0], volume.dims[1], k1 - k0)
        # voxel_centers liefert das GITTER in C-Ordnung (i, j, k) -- deshalb
        # ist das Reshape exakt der Slice [:, :, k0:k1].
        out[:, :, k0:k1] = res
    return out


def radial_prior(volume, max_thickness_mm: float, radius_fn, thickness_fn,
                 region_fn):
    """Radiale Schranke: Haar kann nicht dicker als `max_thickness` sein.

    Das ist die Extrapolation fuer den nie gesehenen Hinterkopf. Sie ist
    bewusst KONSERVATIV (eher zu duenn als zu dick): ein zu dickes Volumen
    sieht nach Helm aus, ein zu duennes nach Kurzhaarschnitt.
    """
    out = np.zeros(volume.dims, dtype=bool)
    for k0 in range(0, volume.dims[2], 16):
        k1 = min(k0 + 16, volume.dims[2])
        idx, pts = volume.voxel_centers(k0, k1)
        n = np.linalg.norm(pts, axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            d = pts / np.maximum(n, 1e-12)[:, None]
        inner = radius_fn(d)
        ok = (n > inner - 2.0) & (n <= inner + max_thickness_mm) & region_fn(d)
        out[:, :, k0:k1] = ok.reshape(volume.dims[0], volume.dims[1], k1 - k0)
    return out


def occupancy_to_sdf(occ: np.ndarray) -> np.ndarray:
    """Bool-Belegung -> SDF-aehnliches Feld (-1 innen, +1 aussen).

    Fuer Marching-Tetrahedra: die Nullinie liegt dann genau auf der halben
    Voxelkante zwischen "drin" und "draussen".
    """
    return np.where(occ, -1.0, 1.0).astype(np.float32)


def observed_voxels(volume, poses, masks, fx, fy, cx, cy, slab: int = 16):
    """Voxel, die in mindestens einem Bild auf die Maske fallen.

    Damit trennen wir im Bericht "beobachtet" von "extrapoliert": beim
    Selbstscan ohne Spiegel sieht die Kamera den Hinterkopf nie, und genau
    dort darf man die Guete nicht mit dem Rest verrechnen.
    """
    seen = np.zeros(volume.dims, dtype=bool)
    for (r, t), mask in zip(poses, masks):
        h, w = mask.shape
        rr = np.asarray(r, dtype=np.float64)
        tt = np.asarray(t, dtype=np.float64)
        for k0 in range(0, volume.dims[2], slab):
            k1 = min(k0 + slab, volume.dims[2])
            idx, pts = volume.voxel_centers(k0, k1)
            cam = pts @ rr.T + tt
            z = cam[:, 2]
            good = z > 1.0
            zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
            ui = np.rint(fx * cam[:, 0] / zs + cx).astype(np.int64)
            vi = np.rint(fy * cam[:, 1] / zs + cy).astype(np.int64)
            visible = good & (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
            if not visible.any():
                continue
            hit = mask[vi[visible], ui[visible]]
            sel = np.where(visible)[0][hit]
            if len(sel):
                ii, jj, kk = idx[sel][:, 0], idx[sel][:, 1], idx[sel][:, 2]
                seen[ii, jj, kk] = True
    return seen


def thickness_field_prior(volume, observed, radius_fn, region_fn,
                          n_az: int = 48, n_el: int = 24,
                          fallback_mm: float = 25.0, grow_voxels: int = 1):
    """Radiale Schranke mit GESCHAETZTER, richtungsabhaengiger Haardicke.

    Statt einer globalen "Haare sind hoechstens X mm dick"-Schranke wird die
    Dicke dort gemessen, wo man sie sieht, und auf die nicht sichtbaren
    Richtungen (Hinterkopf) mit dem Mittelwert extrapoliert.

    Das ist genau der Unterschied zwischen "Helm" und "Frisur": eine
    konstante Schranke produziert eine Muschel, eine richtungsabhaengige
    folgt der Kontur wenigstens in der Dicke.
    """
    maxth = np.full(n_az * n_el, -np.inf)

    def bin_of(d: np.ndarray):
        az = np.arctan2(d[:, 0], d[:, 2])
        el = np.arcsin(np.clip(d[:, 1], -1.0, 1.0))
        ia = np.clip(((az + np.pi) / (2 * np.pi) * n_az).astype(np.int64), 0, n_az - 1)
        ie = np.clip(((el + np.pi / 2) / np.pi * n_el).astype(np.int64), 0, n_el - 1)
        return ia * n_el + ie

    def radius_of(d: np.ndarray):
        return radius_fn(d)

    # 1) Dicke je Richtung aus den beobachteten Voxeln messen
    for k0 in range(0, volume.dims[2], 16):
        k1 = min(k0 + 16, volume.dims[2])
        idx, pts = volume.voxel_centers(k0, k1)
        sel = observed[idx[:, 0], idx[:, 1], idx[:, 2]]
        if not sel.any():
            continue
        p = pts[sel]
        n = np.linalg.norm(p, axis=1)
        d = p / n[:, None]
        th = n - radius_of(d)
        np.maximum.at(maxth, bin_of(d), th)

    valid = np.isfinite(maxth)
    median_th = float(np.median(maxth[valid])) if valid.any() else fallback_mm
    field = np.where(valid, maxth, median_th)

    # 2) Schranke anwenden
    out = np.zeros(volume.dims, dtype=bool)
    for k0 in range(0, volume.dims[2], 16):
        k1 = min(k0 + 16, volume.dims[2])
        idx, pts = volume.voxel_centers(k0, k1)
        n = np.linalg.norm(pts, axis=1)
        d = pts / np.maximum(n, 1e-12)[:, None]
        inner = radius_of(d)
        allow = field[bin_of(d)] + grow_voxels * volume.voxel
        ok = region_fn(d) & (n > inner - 2.0) & (n <= inner + allow)
        out[:, :, k0:k1] = ok.reshape(volume.dims[0], volume.dims[1], k1 - k0)
    return out, median_th

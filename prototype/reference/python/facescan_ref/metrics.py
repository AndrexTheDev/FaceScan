"""Kennzahlen fuer M1 -- gegen die Ground Truth, nicht gegen Bauchgefuehl.

Drei Zahlen, die in docs/10 als Abnahmekriterien stehen:

  Chamfer-Abstand (Haut)   <= 0,8 mm   "stimmt die Form?"
  Haar-IoU (Volumen)       >= 0,85     "sitzt die Frisur?"
  Textur-Vollstaendigkeit  >= 0,95     "gibt es Loecher in der Farbe?"
"""
from __future__ import annotations

import numpy as np


class PointGrid:
    """Gleichfoermiges Gitter fuer Naechster-Nachbar-Suchen.

    Ohne so ein Gitter waere Chamfer O(N*M) -- bei 50k x 50k Punkten sind
    das 2,5 Milliarden Abstaende. Mit Gitter sind es wenige Millionen.
    """

    def __init__(self, points: np.ndarray, cell: float = 2.0):
        p = np.asarray(points, dtype=np.float64)
        self.cell = float(cell)
        self.origin = p.min(axis=0) - cell
        key = np.floor((p - self.origin) / self.cell).astype(np.int64)
        self.dims = key.max(axis=0) + 1
        lin = ((key[:, 0] * self.dims[1]) + key[:, 1]) * self.dims[2] + key[:, 2]
        n_cells = int(np.prod(self.dims))
        self.counts = np.bincount(lin, minlength=n_cells)
        self.starts = np.concatenate([[0], np.cumsum(self.counts)]).astype(np.int64)
        order = np.argsort(lin, kind="stable")
        self.sorted_points = p[order]
        self.points = p

    def query(self, q: np.ndarray, shells: int = 3) -> np.ndarray:
        """Abstand zum naechsten Gitterpunkt (ggf. np.inf)."""
        q = np.asarray(q, dtype=np.float64)
        nq = len(q)
        best = np.full(nq, np.inf)
        key = np.floor((q - self.origin) / self.cell).astype(np.int64)
        base_lin = ((key[:, 0] * self.dims[1]) + key[:, 1]) * self.dims[2] + key[:, 2]

        # Offsets der Schalen 0..shells (Chebyshev-Radius)
        offs = []
        rng = np.arange(-shells, shells + 1)
        for dx in rng:
            for dy in rng:
                for dz in rng:
                    if max(abs(dx), abs(dy), abs(dz)) <= shells:
                        offs.append((dx, dy, dz))
        offs = np.array(offs, dtype=np.int64)
        step = np.array([self.dims[1] * self.dims[2], self.dims[2], 1], dtype=np.int64)
        off_lin = offs @ step

        for o in off_lin:
            lin = base_lin + o
            lin = np.clip(lin, 0, len(self.counts) - 1)
            cnt = self.counts[lin]
            total = int(cnt.sum())
            if total == 0:
                continue
            rep = np.repeat(np.arange(nq), cnt)
            starts_rep = self.starts[lin][rep]
            within = np.arange(total) - np.repeat(
                np.concatenate([[0], np.cumsum(cnt)])[:-1], cnt)
            gather = starts_rep + within
            cand = self.sorted_points[gather]
            d = np.linalg.norm(q[rep] - cand, axis=1)
            np.minimum.at(best, rep, d)
        return best


def vertex_normals(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    """Flaechengewichtete Vertexnormalen (normiert)."""
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    fn = np.cross(b - a, c - a)
    n = np.zeros_like(v)
    np.add.at(n, f[:, 0], fn)
    np.add.at(n, f[:, 1], fn)
    np.add.at(n, f[:, 2], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    bad = (ln[:, 0] < 1e-12)
    if bad.any():
        n[bad] = np.array([0.0, 1.0, 0.0])
        ln[bad] = 1.0
    return n / ln


def triangle_areas(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    a = v[f[:, 0]]
    b = v[f[:, 1]]
    c = v[f[:, 2]]
    return 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)


def sample_surface(v: np.ndarray, f: np.ndarray, n_points: int,
                   seed: int = 2026) -> np.ndarray:
    """Flaechengewichtet auf der Oberflaeche ziehen (deterministisch)."""
    rng = np.random.default_rng(seed)
    area = triangle_areas(v, f)
    prob = area / max(area.sum(), 1e-12)
    idx = rng.choice(len(f), size=n_points, p=prob)
    a = v[f[idx, 0]]
    b = v[f[idx, 1]]
    c = v[f[idx, 2]]
    u = rng.random((n_points, 1))
    w = rng.random((n_points, 1))
    flip = (u + w) > 1
    u = np.where(flip, 1 - u, u)
    w = np.where(flip, 1 - w, w)
    return a + u * (b - a) + w * (c - a)


def _brute_fill(query: np.ndarray, cloud: np.ndarray, dist: np.ndarray,
                block: int = 32, cloud_block: int = 8192) -> np.ndarray:
    """Exakter Abstand fuer die Punkte, die das Gitter nicht gefunden hat.

    Ohne diesen Schritt steht im Bericht irgendwann "inf" -- und ein inf
    verschluckt jeden Mittelwert. Besser: die paar Punkte exakt nachrechnen.
    Die Bloecke sind klein gewaehlt: 4000 x 60000 x 3 Doubles waeren 5 GB.
    """
    todo = np.where(~np.isfinite(dist))[0]
    if not len(todo):
        return dist
    q = query[todo]
    best = np.full(len(q), np.inf)
    for cs in range(0, len(cloud), cloud_block):
        c = cloud[cs:cs + cloud_block]
        for start in range(0, len(q), block):
            blk = q[start:start + block]
            d = np.linalg.norm(blk[:, None, :] - c[None, :, :], axis=2)
            np.minimum.at(best, np.arange(start, start + len(blk)), d.min(axis=1))
    dist[todo] = best
    return dist


def chamfer(a: np.ndarray, b: np.ndarray, cell: float = 2.0,
            shells: int = 3) -> dict:
    """Symmetrischer Chamfer-Abstand zwischen zwei Punktwolken (mm).

    a = Referenz (Ground Truth), b = Rekonstruktion.
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ga = PointGrid(a, cell)
    gb = PointGrid(b, cell)
    d_ab = ga.query(b, shells)          # Rekonstruktion -> Wahrheit
    d_ba = gb.query(a, shells)          # Wahrheit -> Rekonstruktion
    d_ab = _brute_fill(b, a, d_ab)
    d_ba = _brute_fill(a, b, d_ba)
    both = np.concatenate([d_ab, d_ba])
    return {
        "chamfer_mm": float(0.5 * (np.mean(d_ab) + np.mean(d_ba))),
        "from_recon_mm": float(np.mean(d_ab)),
        "to_recon_mm": float(np.mean(d_ba)),
        "p95_mm": float(np.percentile(both, 95)),
        "max_mm": float(np.max(both)),
        "within_0_8mm": float(np.mean(both <= 0.8)),
        "within_2_0mm": float(np.mean(both <= 2.0)),
    }


def iou(a: np.ndarray, b: np.ndarray) -> dict:
    """Intersection over Union zweier bool-Volumen."""
    a = np.asarray(a, dtype=bool)
    b = np.asarray(b, dtype=bool)
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    denom_a = a.sum()
    return {
        "iou": float(inter / union) if union else float("nan"),
        "precision": float(inter / denom_a) if denom_a else float("nan"),
        "recall": float(inter / b.sum()) if b.sum() else float("nan"),
        "voxels_recon": int(a.sum()),
        "voxels_truth": int(b.sum()),
    }


def texture_completeness(vertices: np.ndarray, frames: list, fx: float, fy: float,
                         cx: float, cy: float, depth_tol_mm: float = 2.5,
                         min_views: int = 3) -> dict:
    """Wie viel der Oberflaeche wurde wie oft farbig gesehen?

    Ein Vertex gilt als "beobachtet", wenn er im Bild liegt UND sein
    Tiefenwert mit dem Tiefenbild uebereinstimmt (also nicht verdeckt ist).
    Das ist der ehrliche Test: Sichtbarkeit zaehlt nur, wenn nichts davor ist.
    """
    v = np.asarray(vertices, dtype=np.float64)
    views = np.zeros(len(v), dtype=np.int64)
    color_sum = np.zeros((len(v), 3), dtype=np.float64)

    for fr in frames:
        r = np.asarray(fr["R"], dtype=np.float64)
        t = np.asarray(fr["t"], dtype=np.float64)
        depth = fr["depth"]
        color = fr["color"]
        mask = fr["mask"]
        h, w = depth.shape
        cam = v @ r.T + t
        z = cam[:, 2]
        ok = z > 1.0
        zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
        ui = np.rint(fx * cam[:, 0] / zs + cx).astype(np.int64)
        vi = np.rint(fy * cam[:, 1] / zs + cy).astype(np.int64)
        ok &= (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
        idx = np.where(ok)[0]
        if len(idx) == 0:
            continue
        d = depth[vi[idx], ui[idx]]
        m = mask[vi[idx], ui[idx]]
        vis = m & np.isfinite(d) & (np.abs(d - z[idx]) <= depth_tol_mm)
        sel = idx[vis]
        if len(sel):
            views[sel] += 1
            color_sum[sel] += color[vi[sel], ui[sel]].astype(np.float64)

    seen = views > 0
    well = views >= min_views
    colors = np.zeros((len(v), 3), dtype=np.uint8)
    if seen.any():
        c = color_sum / np.maximum(views, 1)[:, None]
        colors = np.clip(c, 0, 255).astype(np.uint8)
    return {
        "covered_any": float(seen.mean()),
        "covered_min_views": float(well.mean()),
        "mean_views": float(views.mean()),
        "colors": colors,
        "views": views,
    }


def observed_points(points: np.ndarray, frames: list, fx: float, fy: float,
                    cx: float, cy: float, label: int | None = None,
                    min_views: int = 1, depth_tol_mm: float = 2.5,
                    normals: np.ndarray | None = None,
                    min_cos: float = 0.0) -> np.ndarray:
    """Ist ein Punkt wirklich GESEHEN worden -- und nicht nur im Bild?

    Zwei Bedingungen muessen gelten:
      1. Der Punkt faellt in mindestens `min_views` Bildern auf ein Pixel mit
         dem richtigen Material-Label (None = irgendein Material).
      2. Seine Tiefe stimmt mit dem Tiefenbild ueberein -- sonst steht etwas
         anderes davor (verdeckt).

    Ohne die Tiefenbedingung zaehlt man auch Punkte als "gesehen", die
    hinter dem Kopf liegen. Das ist der haeufigste Fehler in solchen
    Auswertungen.
    """
    v = np.asarray(points, dtype=np.float64)
    views = np.zeros(len(v), dtype=np.int64)
    for fr in frames:
        r = np.asarray(fr["R"], dtype=np.float64)
        t = np.asarray(fr["t"], dtype=np.float64)
        depth, mask = fr["depth"], fr["mask"]
        h, w = depth.shape
        cam_center = -r.T @ t        # Kameraposition in Weltkoordinaten
        cam = v @ r.T + t
        z = cam[:, 2]
        ok = z > 1.0
        zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
        ui = np.rint(fx * cam[:, 0] / zs + cx).astype(np.int64)
        vi = np.rint(fy * cam[:, 1] / zs + cy).astype(np.int64)
        ok &= (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
        idx = np.where(ok)[0]
        if not len(idx):
            continue
        good = mask[vi[idx], ui[idx]] & np.isfinite(depth[vi[idx], ui[idx]])
        good &= np.abs(depth[vi[idx], ui[idx]] - z[idx]) <= depth_tol_mm
        if label is not None:
            good &= fr["label"][vi[idx], ui[idx]] == label
        if normals is not None and min_cos > 0.0:
            # Streifender Blick zaehlt nicht: dort ist die Tiefenmessung
            # ungenau und die TSDF-"Wand" faellt durch den Tiefentest.
            # Ohne diese Bedingung ueberleben genau die Wand-Dreiecke, die
            # den Chamfer-Abstand ruinieren.
            nrm = np.asarray(normals, dtype=np.float64)[idx]
            to_cam = cam_center - v[idx]
            ln = np.linalg.norm(to_cam, axis=1, keepdims=True)
            cos = np.abs(np.sum(nrm * to_cam / np.maximum(ln, 1e-12), axis=1))
            good &= cos >= min_cos
        sel = idx[good]
        if len(sel):
            views[sel] += 1
    return views >= min_views


def drop_unobserved_triangles(v: np.ndarray, f: np.ndarray, seen: np.ndarray,
                              min_seen: int = 2) -> tuple:
    """Entfernt Dreiecke, die nur vom Rand der Beobachtung leben.

    Ein TSDF-Volumen schliesst seine Oberflaeche am Rand des beobachteten
    Bereichs mit einer "Wand" ab. Die Wand ist KEIN Teil des Gesichts, macht
    den Chamfer-Abstand kaputt und faelscht die Texturstatistik. Jede
    ernsthafte Pipeline entfernt sie -- wir auch (docs/03, Stufe 11).

    Regel: ein Dreieck bleibt, wenn mindestens `min_seen` seiner drei Ecken
    wirklich beobachtet wurden. So bleibt die saubere Randkante stehen.
    """
    f = np.asarray(f, dtype=np.int64)
    cnt = seen[f].sum(axis=1)
    keep = cnt >= min_seen
    kept = f[keep]
    if len(kept) == 0:
        return np.asarray(v)[:0], kept
    # unbenutzte Punkte fallenlassen (sonst exportiert man tote Vertices)
    used, inv = np.unique(kept, return_inverse=True)
    new_v = np.asarray(v)[used]
    new_f = inv.reshape(-1, 3).astype(np.int64)
    return new_v, new_f


def mesh_stats(v: np.ndarray, f: np.ndarray) -> dict:
    """Ein paar Zahlen, die man fuer die App-Praxis braucht."""
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f)
    area = triangle_areas(v, f)
    # Kantenlaengen
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    lens = np.linalg.norm(v[e[:, 0]] - v[e[:, 1]], axis=1)
    return {
        "vertices": int(len(v)),
        "triangles": int(len(f)),
        "surface_cm2": float(area.sum() / 100.0),
        "edge_min_mm": float(lens.min()),
        "edge_median_mm": float(np.median(lens)),
        "edge_max_mm": float(lens.max()),
        "degenerate_triangles": int(np.sum(area < 1e-9)),
    }


# ------------------------------------------------- Punkt-zu-Flaeche (exakt) ----


def _dist2_point_triangle(p, a, b, c):
    """Quadrat des Abstands Punkt -> Dreieck (Ericson, Real-Time Collision
    Detection). Vollstaendig vektorisiert über (m, k) Paare.

    Sieben Fallunterscheidungen: drei Eckpunkte, drei Kanten, eine Fläche.
    Alle werden gerechnet und per np.where ausgewählt -- das ist bei
    hunderttausenden Paaren schneller als jede Verzweigung.
    """
    ab = b - a
    ac = c - a
    ap = p - a
    d1 = np.einsum("...i,...i->...", ab, ap)
    d2 = np.einsum("...i,...i->...", ac, ap)
    bp = p - b
    d3 = np.einsum("...i,...i->...", ab, bp)
    d4 = np.einsum("...i,...i->...", ac, bp)
    cp = p - c
    d5 = np.einsum("...i,...i->...", ab, cp)
    d6 = np.einsum("...i,...i->...", ac, cp)

    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2

    # Schutz gegen Division durch 0 -- die betroffenen Faelle werden unten
    # ohnehin nicht ausgewaehlt.
    eps = 1e-300

    def sq(x):
        return np.einsum("...i,...i->...", x, x)

    r_a = sq(ap)
    r_b = sq(bp)
    r_c = sq(cp)
    t_ab = d1 / (d1 - d3 + eps)
    r_ab = sq(ap - t_ab[..., None] * ab)
    t_ac = d2 / (d2 - d6 + eps)
    r_ac = sq(ap - t_ac[..., None] * ac)
    t_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6) + eps)
    r_bc = sq(bp - t_bc[..., None] * (c - b))
    den = va + vb + vc
    v = vb / (den + eps)
    w = vc / (den + eps)
    r_f = sq(ap - v[..., None] * ab - w[..., None] * ac)

    out = r_f
    out = np.where((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0), r_bc, out)
    out = np.where((vb <= 0) & (d2 >= 0) & (d6 <= 0), r_ac, out)
    out = np.where((vc <= 0) & (d1 >= 0) & (d3 <= 0), r_ab, out)
    out = np.where((d6 >= 0) & (d5 <= d6), r_c, out)
    out = np.where((d3 >= 0) & (d4 <= d3), r_b, out)
    out = np.where((d1 <= 0) & (d2 <= 0), r_a, out)
    return np.maximum(out, 0.0)


def point_to_surface(query, v, f, cell: float = 4.0, max_shells: int = 8):
    """Abstand jedes Abfragepunkts zur Dreiecksoberfläche (mm).

    Warum nicht "Abstand zur nächsten Vertex-Wolke"? Weil das die
    **Abtastdichte** misst, nicht die Form. Ein 6k-Dreieck-Netz hat nur 5k
    Vertices -- der nächste Vertex ist im Mittel eine halbe Kantenlänge
    entfernt, obwohl die Fläche direkt daneben liegt. Wer LOD-Güte mit
    Punktwolken-Abständen misst, lügt sich in die Tasche.

    Verfahren: uniformes Gitter über die Dreiecke (jedes Dreieck wird in
    alle Zellen eingetragen, die seine Bounding-Box schneidet). Für jede
    Zelle mit Abfragepunkten werden die Dreiecke der Nachbarzellen
    geprüft. Wichtig ist die Abbruchbedingung: sind wir `s` Schalen weit
    gegangen und der beste Treffer ist höchstens `(s-1)·Zellgröße`
    entfernt, kann nichts näheres übersehen worden sein -- dann sind wir
    fertig. Sonst wird erweitert.
    """
    query = np.asarray(query, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    if len(f) == 0 or len(query) == 0:
        return np.full(len(query), np.inf), np.zeros(len(query), dtype=bool)

    lo = v.min(axis=0)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    tlo = np.minimum(np.minimum(a, b), c)
    thi = np.maximum(np.maximum(a, b), c)

    def cid(p):
        return np.floor((p - lo) / cell).astype(np.int64)

    size = cid(v.max(axis=0)) + 2
    sx, sy, sz = int(size[0]), int(size[1]), int(size[2])

    # --- Gitter aufbauen: Zelle -> Dreiecksnummern -----------------------
    ci_lo = np.floor((tlo - lo) / cell).astype(np.int64)
    ci_hi = np.floor((thi - lo) / cell).astype(np.int64)
    buckets = {}
    for t in range(len(f)):
        x0, y0, z0 = ci_lo[t]
        x1, y1, z1 = ci_hi[t]
        for xx in range(int(x0), int(x1) + 1):
            for yy in range(int(y0), int(y1) + 1):
                for zz in range(int(z0), int(z1) + 1):
                    key = (xx * sy + yy) * sz + zz
                    lst = buckets.get(key)
                    if lst is None:
                        buckets[key] = [t]
                    else:
                        lst.append(t)

    # --- Abfragepunkte nach Zelle gruppieren -----------------------------
    qk = cid(query)
    # Punkte AUSSERHALB der Bounding-Box des Netzes (die LOD schrumpft
    # minimal gegenüber dem Original) würden sonst in Gitterzellen
    # landen, die es gar nicht gibt, und bekämen irgendeinen fernen
    # Treffer als "Abstand" -- deswegen an den Rand klemmen.
    qk = np.clip(qk, 0, np.array([sx - 1, sy - 1, sz - 1], dtype=np.int64))
    qkey = ((qk[:, 0] * sy + qk[:, 1]) * sz + qk[:, 2])
    order = np.argsort(qkey, kind="stable")
    q_sorted = qkey[order]
    uniq, starts, counts = np.unique(q_sorted, return_index=True,
                                     return_counts=True)

    best = np.full(len(query), np.inf)

    def ring(key, s):
        """Dreiecke aus genau der Schale `s` um die Zelle `key`."""
        kx = int(key // (sy * sz))
        rem = int(key % (sy * sz))
        ky = rem // sz
        kz = rem % sz
        out = []
        for dx in range(-s, s + 1):
            ax = kx + dx
            if ax < 0 or ax >= sx:
                continue
            for dy in range(-s, s + 1):
                ay = ky + dy
                if ay < 0 or ay >= sy:
                    continue
                for dz in range(-s, s + 1):
                    az = kz + dz
                    if az < 0 or az >= sz:
                        continue
                    if max(abs(dx), abs(dy), abs(dz)) != s:
                        continue
                    lst = buckets.get((ax * sy + ay) * sz + az)
                    if lst:
                        out.append(lst)
        if not out:
            return np.empty(0, dtype=np.int64)
        return np.unique(np.concatenate([np.asarray(x, dtype=np.int64)
                                         for x in out]))

    for slot in range(len(uniq)):
        idx = order[starts[slot]:starts[slot] + counts[slot]]
        p = query[idx][:, None, :]
        acc = []
        for s in range(0, max_shells + 1):
            tri = ring(int(uniq[slot]), s)
            if len(tri):
                acc.append(tri)
            if not acc:
                continue
            allt = np.unique(np.concatenate(acc))
            d2 = _dist2_point_triangle(p, v[f[allt, 0]][None, :, :],
                                       v[f[allt, 1]][None, :, :],
                                       v[f[allt, 2]][None, :, :])
            m = d2.min(axis=1)
            best[idx] = m
            # Abbruchbedingung: eine Gitterzelle im Index-Abstand k ist
            # mindestens (k-1)*Zellbreite entfernt. Etwas Näheres als der
            # beste Treffer d kann also nur in Zellen mit k <= ceil(d/cell)
            # liegen -- die haben wir alle gesehen, sobald d <= s*cell.
            if float(m.max()) <= s * cell + 1e-9:
                break
            if s == max_shells:
                break
    best = np.sqrt(np.maximum(best, 0.0))
    return best, np.isfinite(best)


def surface_deviation(v_ref, f_ref, v_lod, f_lod, cell: float = 4.0,
                      max_ref_points: int = 40_000) -> dict:
    """Wie weit liegt das vereinfachte Netz vom Original (mm)?

    Beide Richtungen, weil sie Verschiedenes bedeuten:
      * `to_lod`  -- Original -> LOD: das ist der **Formfehler**, den man
        sieht (wie weit steht die echte Oberfläche über das Modell hinaus).
      * `from_lod` -- LOD -> Original: das ist der Fehler, den die LOD
        selbst macht.
    """
    v_ref = np.asarray(v_ref, dtype=np.float64)
    v_lod = np.asarray(v_lod, dtype=np.float64)
    if len(v_ref) > max_ref_points:
        # Gleichmäßiger Stride statt Zufall: reproduzierbar, und der
        # Mittelwert/p95 sind bei 40k Stichpunkten stabil. Nur die
        # ABFRAGEPUNKTE werden dünner -- das Netz selbst bleibt ganz,
        # sonst würden die Dreiecksindizes ins Leere zeigen.
        step = int(np.ceil(len(v_ref) / max_ref_points))
        q_ref = v_ref[::step]
    else:
        q_ref = v_ref
    d1, ok1 = point_to_surface(q_ref, v_lod, f_lod, cell=cell)
    d2, ok2 = point_to_surface(v_lod, v_ref, f_ref, cell=cell)
    both = np.concatenate([d1[ok1], d2[ok2]])
    if len(both) == 0:
        return {"max_mm": float("inf"), "p95_mm": float("inf"),
                "mean_mm": float("inf"), "to_lod_mm": float("inf"),
                "from_lod_mm": float("inf"), "unresolved": int(len(d1))}
    return {
        "to_lod_mm": float(np.mean(d1[ok1])),
        "from_lod_mm": float(np.mean(d2[ok2])),
        "mean_mm": float(both.mean()),
        "p95_mm": float(np.percentile(both, 95)),
        "max_mm": float(both.max()),
        "unresolved": int((~ok1).sum() + (~ok2).sum()),
    }

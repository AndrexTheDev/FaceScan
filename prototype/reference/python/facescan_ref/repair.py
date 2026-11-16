"""Netz-Reparatur und die wasserdichte Variante (docs/03, 6.2).

Drei Dinge, die docs/03 (6.2) nach dem Marching Cubes verlangt und die
bisher fehlten:

1. **Löcher schließen** (< 3 mm Rand → Advancing Front; größer → die
   Poisson-Variante unten).
2. **Taubin-Glättung** (Haut, 3 Iterationen) -- gegen das Treppenmuster,
   das jedes Voxelgitter hinterlässt.
3. **Wasserdichte Variante** für 3D-Druck und Boolesche Operationen.

Zu 3 der wichtigste Satz vorweg: was hier steht, ist **Poisson Surface
Reconstruction** (Kazhdan et al. 2006, [8] in docs/99), gerechnet auf
einem regelmäßigen Gitter statt auf einem Octree. Das Verfahren ist
dasselbe -- aus gerichteten Punkten wird ein Vektorfeld gebaut, dessen
Divergenz die rechte Seite einer Poisson-Gleichung ist; die Isofläche
der Lösung ist die Oberfläche. Nur die Datenstruktur ist einfacher, und
damit auch der Speicherbedarf.

`docs/03` nennt Octree-Tiefe 10-12. Tiefe 10 wären 1024³ Voxel = 4,3
GByte -- auf einem Telefon undenkbar, auf dem Messrechner hier knapp.
Wir rechnen auf 192³ und weisen die Auflösung als Kennzahl aus, statt
eine Tiefe vorzutäuschen, die wir nicht rechnen.
"""

from __future__ import annotations

import numpy as np


# -------------------------------------------------------------- Ränder ----

def boundary_loops(v: np.ndarray, f: np.ndarray) -> list[np.ndarray]:
    """Ketten aller Randkanten zu geschlossenen Schleifen.

    Eine Randkante gehört zu genau einem Dreieck. Ihre Richtung ist die
    UMLAUFRICHTUNG dieses Dreiecks -- und nur deshalb findet man den
    nächsten Kandidaten eindeutig: von a nach b folgt die Kante, die bei
    b BEGINNT. Bei einem Netz mit gemischter Orientierung (siehe
    `meshopt.winding_errors`) funktioniert das nicht; die Schleifen
    enden dann mitten auf der Oberfläche. Also vorher orientieren.

    Rückgabe: Liste von (L,) Arrays mit Punktindizes in Umlaufrichtung.

    Warum das hier mit numpy steht und nicht als Python-Schleife über die
    Kanten: bei 457 k Dreiecken sind das 1,4 Mio. Kanten, und die
    Python-Version stand bei gut fünf Minuten Laufzeit. Dasselbe
    Ergebnis -- nur die Kantenliste wird vorher sortiert.

    Ein Knoten kann MEHRERE ausgehende Randkanten haben (zwei Schleifen,
    die sich in einem Punkt berühren -- bei Voxelnetzen der Normalfall).
    Die erste Fassung hat hier pro Knoten nur eine Kante abgespeichert
    und damit Schleifen verschluckt; jetzt liegt je Knoten eine Liste.
    """
    f = np.asarray(f, dtype=np.int64)
    if len(f) == 0:
        return []
    n_v = int(f.max()) + 1
    mul = n_v + 1
    a = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
    b = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
    fwd = a * mul + b
    rev = b * mul + a
    uni, first = np.unique(fwd, return_index=True)
    have_rev = np.unique(rev)
    if len(have_rev):
        pos = np.clip(np.searchsorted(have_rev, uni), 0, len(have_rev) - 1)
        uni = uni[have_rev[pos] != uni]
    if len(uni) == 0:
        return []
    ba = (uni // mul).astype(np.int64)
    bb = (uni % mul).astype(np.int64)
    order = np.argsort(ba, kind="stable")
    ba, bb = ba[order], bb[order]
    starts = np.flatnonzero(np.concatenate([[True], ba[1:] != ba[:-1]]))
    ends = np.append(starts[1:], len(ba))
    nxt = {int(ba[i]): [int(y) for y in bb[s:e]]
           for i, s, e in zip(starts, starts, ends)}

    loops = []
    while True:
        offen = [x for x in nxt if nxt[x]]
        if not offen:
            break
        s = offen[0]
        loop = [s]
        cur = s
        while nxt.get(cur):
            y = nxt[cur].pop(0)
            if y == s:
                break
            loop.append(y)
            cur = y
        if len(loop) >= 3:
            loops.append(np.asarray(loop, dtype=np.int64))
    return loops


def loop_perimeter(v: np.ndarray, loop: np.ndarray) -> float:
    p = np.asarray(v, dtype=np.float64)[loop]
    return float(np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1).sum())


# ------------------------------------------------------- Loch-Füllung ----

def fill_holes(v: np.ndarray, f: np.ndarray, max_perimeter_mm: float = 3.0,
               colors: np.ndarray | None = None):
    """Füllt Randlöcher mit der Advancing-Front-Methode.

    Ablauf je Loch: solange mehr als drei Punkte übrig sind, wird der
    mit dem **kleinsten Innenwinkel** zum Dreieck geschlossen und aus
    der Schleife entfernt. Das ist die klassische Wahl -- der spitze
    Winkel ist die Stelle, an der ein neues Dreieck am wenigsten
    Verzerrung erzeugt. Wer stattdessen "irgendeinen" nimmt, bekommt
    Nadeldreiecke, die später jeden Lake-Selektor und jeden 3D-Drucker
    stören.

    Löcher, deren Umfang über `max_perimeter_mm` liegt, bleiben offen:
    sie zu schließen hieße, fehlende Oberfläche zu ERFINDEN. docs/03
    (6.2) schickt genau diese Fälle in die Poisson-Variante.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    loops = boundary_loops(v, f)
    if not loops:
        return v, f, colors, {"loops": 0, "filled": 0, "triangles": 0,
                              "too_big": 0, "open_perimeter_mm": 0.0}

    new_tris = []
    filled = 0
    too_big = 0
    open_per = 0.0
    for loop in loops:
        per = loop_perimeter(v, loop)
        if per > max_perimeter_mm:
            too_big += 1
            open_per += per
            continue
        ring = list(loop.tolist())
        p = v
        while len(ring) > 3:
            n = len(ring)
            a = p[np.array(ring)]
            b = p[np.array(ring[1:] + ring[:1])]
            c = p[np.array(ring[2:] + ring[:2])]
            u = a - b
            w = c - b
            cosang = ((u * w).sum(axis=1)
                      / np.maximum(np.linalg.norm(u, axis=1)
                                   * np.linalg.norm(w, axis=1), 1e-18))
            k = int(np.argmax(cosang))          # größter cos = kleinster Winkel
            j = (k + 1) % n
            new_tris.append([ring[k], ring[j], ring[(j + 1) % n]])
            ring.pop(j)
        new_tris.append([ring[0], ring[1], ring[2]])
        filled += 1

    if not new_tris:
        return v, f, colors, {"loops": len(loops), "filled": 0, "triangles": 0,
                              "too_big": too_big, "open_perimeter_mm": open_per}
    add = np.asarray(new_tris, dtype=np.int64)
    f2 = np.vstack([f, add])
    if colors is not None:
        # Neue Dreiecke färben wir aus dem Rand: der Mittelwert der
        # drei Eckfarben ist dort, wo das Loch war, die ehrlichste Wahl.
        colors = np.asarray(colors)
        addc = colors[add].mean(axis=1)
        colors = np.vstack([colors, addc]).astype(colors.dtype)
    return v, f2, colors, {"loops": len(loops), "filled": filled,
                           "triangles": len(add), "too_big": too_big,
                           "open_perimeter_mm": open_per}


# ------------------------------------------------------------ Glättung ----

def _vertex_adjacency(f: np.ndarray, n_v: int):
    """Nachbarlisten als CSR -- einmal gebaut, für alle Iterationen."""
    a = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
    b = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
    src = np.concatenate([a, b])
    dst = np.concatenate([b, a])
    # Doppelte Kanten sind beim Laplaceschen Operator unerwünscht: ein
    # Nachbar, der über zwei Kanten erreicht wird, würde doppelt zählen.
    key = src.astype(np.int64) * (n_v + 1) + dst
    order = np.lexsort((dst, src))
    src, dst, key = src[order], dst[order], key[order]
    keep = np.ones(len(key), dtype=bool)
    keep[1:] = key[1:] != key[:-1]
    src, dst = src[keep], dst[keep]
    o = np.argsort(src, kind="stable")
    indptr = np.concatenate([[0], np.cumsum(np.bincount(src, minlength=n_v))])
    return indptr.astype(np.int64), dst[o].astype(np.int64)


def taubin_smooth(v: np.ndarray, f: np.ndarray, iterations: int = 3,
                  lam: float = 0.5, mu: float = -0.53,
                  fixed: np.ndarray | None = None) -> np.ndarray:
    """Taubin-Glättung (λ|µ) -- glättet, ohne zu schrumpfen.

    Warum nicht einfach Laplace-Glättung: `v += λ · L(v)` mit λ > 0
    zieht das Netz zusammen. Bei genügend Iterationen schrumpft ein Kopf
    sichtbar -- Augen fallen ein, die Nase wird spitz. Taubin (1995)
    lässt deshalb auf jeden Glättungsschritt mit λ einen
    **Schrumpf-Gegenlauf** mit µ < -λ folgen. Beide Schritte zusammen
    sind ein Tiefpass, der das Volumen erhält.

    `lam = 0.5, mu = -0.53` sind die von Taubin selbst angegebenen
    Werte (µ knapp unter -λ).
    """
    v = np.asarray(v, dtype=np.float64).copy()
    f = np.asarray(f, dtype=np.int64)
    if len(f) == 0 or iterations <= 0:
        return v
    indptr, adj = _vertex_adjacency(f, len(v))
    indptr_l = indptr.tolist()
    adj_l = adj.tolist()
    free = np.ones(len(v), dtype=bool) if fixed is None else ~np.asarray(fixed, bool)

    def step(v, factor):
        out = v.copy()
        for i in range(len(v)):
            if not free[i]:
                continue
            s, e = indptr_l[i], indptr_l[i + 1]
            if e <= s:
                continue
            nb = adj_l[s:e]
            m = v[nb].mean(axis=0)
            out[i] = v[i] + factor * (m - v[i])
        return out

    for _ in range(int(iterations)):
        v = step(v, lam)
        v = step(v, mu)
    return v


# ---------------------------------------------------------- Wasserdicht --

def watertight_report(f: np.ndarray) -> dict:
    """Prüft, ob ein Netz geschlossen ist -- und warum nicht.

    Drei Zahlen, die man zusammen lesen muss:
      * `boundary_edges` -- Kanten mit nur einem Nachbarn. Null heißt
        geschlossen.
      * `non_manifold_edges` -- Kanten mit mehr als zwei Nachbarn. Ein
        Netz kann geschlossen und trotzdem nicht wasserdicht sein, wenn
        sich zwei Flächen eine Kante teilen.
      * `components` -- für den 3D-Druck muss jede Schale einzeln
        geschlossen sein, nicht nur die Summe.
    """
    f = np.asarray(f, dtype=np.int64)
    if len(f) == 0:
        return {"boundary_edges": 0, "non_manifold_edges": 0,
                "components": 0, "watertight": False, "euler": 0}
    a = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
    b = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
    n_v = int(f.max()) + 1
    key = np.sort(np.stack([a, b], axis=1), axis=1)
    flat = key[:, 0].astype(np.int64) * (n_v + 1) + key[:, 1]
    _, cnt = np.unique(flat, return_counts=True)
    from . import meshopt
    lab, sizes = meshopt.connected_components(np.zeros((n_v, 3)), f)
    closed = int((cnt == 1).sum())
    bad = int((cnt > 2).sum())
    n_c, n_f, n_e = n_v, len(f), len(cnt)
    return {
        "boundary_edges": closed,
        "non_manifold_edges": bad,
        "components": int(len(np.unique(lab))),
        "watertight": bool(closed == 0 and bad == 0),
        "euler": int(n_v - n_e + n_f),
    }


def remove_degenerate(v: np.ndarray, f: np.ndarray, colors=None, uv=None,
                      min_area_mm2: float = 1e-9):
    """Wirft Dreiecke ohne Fläche heraus.

    Marching-Tetrahedra erzeugt sie, wo der Iso-Wert genau durch einen
    Gitterpunkt läuft: alle drei Ecken fallen auf denselben Punkt. Die
    Dinger sind harmlos für die Anzeige, aber sie erzeugen
    **nicht-manigfaltige Kanten** -- eine Kante, an der sich plötzlich
    vier Dreiecke treffen. Und die wiederum ist der Grund, warum ein
    Slicer "nicht wasserdicht" meldet, obwohl das Netz längst
    geschlossen ist.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    if len(f) == 0:
        return (v, f, colors, uv)
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    keep = 0.5 * np.linalg.norm(n, axis=1) >= float(min_area_mm2)
    if keep.all():
        return (v, f, colors, uv)
    f2 = f[keep]
    used = np.unique(f2)
    remap = np.full(len(v), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    out = [v[used], remap[f2]]
    for arr in (colors, uv):
        out.append(None if arr is None else np.asarray(arr)[used])
    return tuple(out)


def largest_component(v, f, colors=None, uv=None):
    """Behält nur die größte zusammenhängende Insel und wirft den Rest weg.

    Warum das nötig ist, zeigt der erste Lauf deutlich: das Poisson-Feld
    hat überall dort, wo eine Kamera mal ein paar Pixel weit in die Luft
    gemessen hat, eine eigene kleine geschlossene Blase erzeugt. Zehn
    Stück waren es, und jede für sich völlig korrekt geschlossen. Nur
    war neun von ihnen Rauschen.

    Solche Inseln sind der Grund, warum "wasserdicht: False" und
    "Abstand 6 mm" in einem Atemzug auftauchen können, ohne dass mit der
    eigentlichen Form etwas nicht stimmt. Wir trennen die beiden Dinge
    daher: erst aufräumen, dann messen -- und die Kennzahl nur noch auf
    der Insel bestimmen, die auch wirklich der Kopf ist.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    if len(f) == 0:
        return (v, f, colors, uv)
    from . import meshopt as mo
    labels, _ = mo.connected_components(v, f)
    # Die Etiketten kleben an den Punkten, nicht an den Dreiecken; ein
    # Dreieck gehoert zur Insel seiner ersten Ecke.
    comp = labels[f[:, 0]]
    best = int(np.bincount(comp).argmax())
    keep = comp == best
    f2 = f[keep]
    used = np.unique(f2)
    remap = np.full(len(v), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    out = [v[used], remap[f2]]
    for arr in (colors, uv):
        out.append(None if arr is None else np.asarray(arr)[used])
    return tuple(out)


def signed_volume(v: np.ndarray, f: np.ndarray) -> float:
    """Vorzeichenbehaftetes Volumen (Satz von Gauß über die Dreiecke).

    Negativ heißt: die Normalen zeigen nach innen. Beim STL-Export ist
    das der Klassiker -- die Datei öffnet sich, der Slicer rechnet aber
    mit einem negativen Volumen und füllt anschließend das Falsche aus.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def flip_outward(v, f):
    """Dreht die Dreiecke um, wenn das Volumen negativ ist."""
    if signed_volume(v, f) >= 0.0:
        return (np.asarray(v), np.asarray(f))
    return (np.asarray(v), np.asarray(f)[:, ::-1])


def poisson_grid(points: np.ndarray, normals: np.ndarray,
                 bbox_min, bbox_max, res: int = 192,
                 samples_per_axis: int = 1,
                 tie_eps: float = 1e-9) -> dict:
    """Poisson Surface Reconstruction auf einem regelmäßigen Gitter.

    Ablauf (Kazhdan/Hoppe: "Poisson Surface Reconstruction", 2006):

    1. Aus den gerichteten Punkten wird ein **Vektorfeld V** auf dem
       Gitter gebaut: jeder Punkt trägt seine Normale in das Voxel ein,
       in dem er liegt (und per trilinearer Verteilung in die acht
       Nachbarn, sonst wird das Feld klumpig).
    2. Rechte Seite: ``rho = div V``. Wo die Oberfläche ist, krümmt sich
       der Indikator -- mathematisch genau dort, wo das Feld auseinander-
       oder zusammenläuft.
    3. ``Laplace(chi) = rho`` lösen. **Hier im Frequenzraum**, weil das
       Gitter regelmäßig ist: die Fourier-Symbolwerte des 7-Punkt-
       Laplace-Operators sind bekannt, also ist die Lösung eine Division
       pro Frequenz. Ein Jacobi-Verfahren bräuchte für dieselbe
       Genauigkeit Tausende Iterationen, eine FFT-Sekunden.
       Der konstante Anteil (Frequenz 0) wird auf null gesetzt -- sonst
       ist die Lösung nur bis auf eine Konstante bestimmt, und genau die
       bestimmt das Iso-Level.
    4. Isofläche extrahieren. Der Indikator ist INNEN groß, deshalb ist
       ``sdf = level - chi`` das, was Marching Tetrahedra erwartet
       (positiv = außerhalb).

    Vor Schritt 4 noch ein Schritt, der in keinem Paper steht und ohne
    den hier trotzdem nichts wird: **Krawatten brechen**. Trifft der
    Iso-Wert einen Gitterknoten exakt, liegt der Schnittpunkt genau auf
    dem Knoten -- und dann erzeugen mehrere Tetraeder desselben Würfels
    dasselbe Dreieck. Heraus kommen nullflächige Dreiecke und Kanten, an
    denen sich vier statt zwei Flächen treffen. Das Netz sieht geschlossen
    aus und ist es nicht. Wir schieben daher alle Werte, die betragsmäßig
    unter `tie_eps` (relativ zur Feldamplitude) liegen, knapp aus dem
    Nullbereich heraus. In Zahlen, gemessen auf dem Kopf-Netz: vorher 106
    offene Schleifen und 10 nicht-manigfaltige Kanten, nachher null.

    Rückgabe: dict mit `vertices`, `faces`, `level`, `res`, `voxel_mm`,
    `ties` (Anzahl der Gitterknoten, an denen gebrochen werden musste).
    """
    from .fusion import TsdfVolume, marching_tetrahedra

    p = np.asarray(points, dtype=np.float64)
    n = np.asarray(normals, dtype=np.float64)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.where(ln > 1e-12, n / np.maximum(ln, 1e-12), 0.0)

    bbox_min = np.asarray(bbox_min, dtype=np.float64)
    bbox_max = np.asarray(bbox_max, dtype=np.float64)
    span = bbox_max - bbox_min
    # Etwas Luft: das Gitter muss das Objekt mit Abstand umfassen, sonst
    # wirken die periodischen Randbedingungen der FFT auf die Lösung.
    pad = 0.12 * span.max()
    lo = bbox_min - pad
    hi = bbox_max + pad
    d = max(2, int(res))
    h = float((hi - lo).max() / (d - 1))
    hi = lo + h * (d - 1)            # würfelförmig, einheitliche Kante

    g = np.zeros((d, d, d), dtype=np.float32)
    vx = np.zeros_like(g)
    vy = np.zeros_like(g)
    vz = np.zeros_like(g)

    idx = np.floor((p - lo) / h).astype(np.int64)
    for ax in range(3):
        np.clip(idx[:, ax], 0, d - 2, out=idx[:, ax])
    frac = (p - (lo + idx * h)) / h
    # Trilinear verteilen: sonst steht das Feld nur in jedem
    # hundertsten Voxel und die Divergenz ist überall null.
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                wz = frac[:, 2] if dz else (1.0 - frac[:, 2])
                wy = frac[:, 1] if dy else (1.0 - frac[:, 1])
                wx = frac[:, 0] if dx else (1.0 - frac[:, 0])
                w = (wx * wy * wz)[:, None]
                np.add.at(vx, (idx[:, 0] + dx, idx[:, 1] + dy, idx[:, 2] + dz),
                          (n[:, 0] * w[:, 0]))
                np.add.at(vy, (idx[:, 0] + dx, idx[:, 1] + dy, idx[:, 2] + dz),
                          (n[:, 1] * w[:, 0]))
                np.add.at(vz, (idx[:, 0] + dx, idx[:, 1] + dy, idx[:, 2] + dz),
                          (n[:, 2] * w[:, 0]))
                np.add.at(g, (idx[:, 0] + dx, idx[:, 1] + dy, idx[:, 2] + dz),
                          w[:, 0])
    m = g > 1e-9
    vx[m] /= g[m]
    vy[m] /= g[m]
    vz[m] /= g[m]

    # Divergenz mit zentralen Differenzen -- derselbe Operator, dessen
    # Fourier-Symbol unten als Nenner steht. Wer hier eine andere
    # Formel nimmt als im Nenner, löst eine andere Gleichung.
    rho = np.zeros_like(g)
    rho[1:-1, :, :] += (vx[2:, :, :] - vx[:-2, :, :]) / (2.0 * h)
    rho[:, 1:-1, :] += (vy[:, 2:, :] - vy[:, :-2, :]) / (2.0 * h)
    rho[:, :, 1:-1] += (vz[:, :, 2:] - vz[:, :, :-2]) / (2.0 * h)

    rho_f = np.fft.fftn(rho.astype(np.float64))
    k = 2.0 * np.pi * np.fft.fftfreq(d)
    lam = ((2.0 * (np.cos(k) - 1.0) / (h * h))[:, None, None]
           + (2.0 * (np.cos(k) - 1.0) / (h * h))[None, :, None]
           + (2.0 * (np.cos(k) - 1.0) / (h * h))[None, None, :])
    lam[0, 0, 0] = 1.0                       # Konstante: wird zu null gesetzt
    chi = np.real(np.fft.ifftn(rho_f / lam))
    chi -= chi.mean()

    # Iso-Level: der Mittelwert des Indikators an den Stichprobenpunkten.
    # Das ist die Stelle, an der die Punkte TATSÄCHLICH liegen -- ein
    # geratenes Level (etwa 0) verschiebt die Fläche um Millimeter.
    ii = np.clip(np.rint((p[:, 0] - lo[0]) / h).astype(np.int64), 0, d - 1)
    jj = np.clip(np.rint((p[:, 1] - lo[1]) / h).astype(np.int64), 0, d - 1)
    kk = np.clip(np.rint((p[:, 2] - lo[2]) / h).astype(np.int64), 0, d - 1)
    level = float(np.median(chi[ii, jj, kk]))

    # float64 bleibt float64 -- in float32 wären die Werte, die wir unten
    # gerade erst aus dem Nullbereich geholt haben, wieder genau null.
    sdf = level - chi
    amp = float(np.abs(sdf).max())
    eps = float(tie_eps) * max(amp, 1e-30)
    ties = np.abs(sdf) <= eps
    n_ties = int(ties.sum())
    if n_ties:
        sdf = np.where(ties, eps, sdf)

    vol = TsdfVolume(lo, lo + h * d, h, 3.0 * h)
    vol.sdf = sdf
    vol.weight = np.ones(vol.sdf.shape, dtype=np.float32)
    vol.dims = np.asarray(vol.sdf.shape, dtype=np.int64)
    v_out, f_out = marching_tetrahedra(vol, min_weight=0.5)
    return {"vertices": v_out, "faces": f_out, "level": level,
            "res": int(d), "voxel_mm": h, "ties": n_ties}

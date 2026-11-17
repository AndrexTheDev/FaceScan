"""Prüfungen für den 3D-Druck und das Beschneiden des Indikatorfeldes.

`docs/05` (12.2) verlangt für das druckbare STL eine **Sockel- und
Wandstärkenprüfung**. Beides steht hier, und beides sind Messungen, keine
Schätzungen:

* `cross_section_profile` -- Querschnittsfläche je Höhe. Aus ihr folgt, wo
  der Sockel sitzen muss; geraten wird nichts.
* `local_thickness` -- kleinste **lokale Dicke** des Körpers. Für einen
  massiven Druck ist das die Zahl, die über "hält das?" entscheidet: ein
  Nasenflügel, der 1,3 mm dick ist, bricht beim Entstützen ab, egal wie
  sauber das Netz sonst ist.
* `overhang_report` -- Flächenanteil, der steiler als der Grenzwinkel nach
  unten zeigt. Das ist der Anteil, den ein FDM-Drucker stützen muss.
* `stand_report` -- Standfläche, Schwerpunkt und Kippsicherheit.

Dazu fünf Eingriffe ins **Feld** statt ins Netz: `cut_below`, `add_plinth`,
`r_min_in_plane`, `shell_field` und `drill_hole`. Ein Netz zu zerschneiden
heißt, danach Löcher zu flicken und Umlaufrichtungen zu reparieren; ein Feld
zu ändern heißt, denselben Marcher noch einmal laufen zu lassen.
"""

from __future__ import annotations

import numpy as np

from .meshopt import face_normals
from .metrics import sample_surface, triangle_areas


def _unit(n: np.ndarray) -> np.ndarray:
    """Auf Länge 1 bringen.

    `meshopt.face_normals` liefert **flächengewichtete** Normalen (Länge
    = 2 × Fläche). Für eine Winkelprüfung oder für einen Strahl, der um
    `s` Millimeter weiterlaufen soll, ist diese Länge Gift: der Strahl
    kommt nur halb so weit, und die Dicke wird doppelt so groß gemessen.
    Auf der Kugel r = 30 mm hat das 120 statt 60 mm ergeben -- und zwar
    so unauffällig, dass man es leicht für eine echte Messung hält.
    """
    n = np.asarray(n, dtype=np.float64)
    ln = np.linalg.norm(n, axis=1)
    ln[ln < 1e-20] = 1.0
    return n / ln[:, None]


# ------------------------------------------------------------- Feld ------

def _grid_coords(p: np.ndarray, lo: np.ndarray, h: float, shape):
    """Gitterkoordinaten und Achtelanteile für trilineare Interpolation."""
    g = (np.asarray(p, dtype=np.float64) - np.asarray(lo, dtype=np.float64)) / float(h)
    for ax in range(3):
        np.clip(g[:, ax], 0.0, shape[ax] - 1.0 - 1e-9, out=g[:, ax])
    i = np.floor(g).astype(np.int64)
    np.clip(i, 0, shape[0] - 2, out=i)
    t = g - i
    return i, t


def sample_field(field: np.ndarray, lo: np.ndarray, h: float,
                 p: np.ndarray) -> np.ndarray:
    """Trilinear interpolierter Feldwert an den Punkten `p`."""
    field = np.asarray(field, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    if len(p) == 0:
        return np.zeros(0)
    i, t = _grid_coords(p, lo, h, field.shape)
    tx, ty, tz = t[:, 0], t[:, 1], t[:, 2]
    ix, iy, iz = i[:, 0], i[:, 1], i[:, 2]
    c000 = field[ix, iy, iz]
    c100 = field[ix + 1, iy, iz]
    c010 = field[ix, iy + 1, iz]
    c110 = field[ix + 1, iy + 1, iz]
    c001 = field[ix, iy, iz + 1]
    c101 = field[ix + 1, iy, iz + 1]
    c011 = field[ix, iy + 1, iz + 1]
    c111 = field[ix + 1, iy + 1, iz + 1]
    return ((1 - tx) * (1 - ty) * (1 - tz) * c000
            + tx * (1 - ty) * (1 - tz) * c100
            + (1 - tx) * ty * (1 - tz) * c010
            + tx * ty * (1 - tz) * c110
            + (1 - tx) * (1 - ty) * tz * c001
            + tx * (1 - ty) * tz * c101
            + (1 - tx) * ty * tz * c011
            + tx * ty * tz * c111)


def cross_section_profile(field: np.ndarray, lo: np.ndarray, h: float,
                          level: float, axis: int = 2) -> dict:
    """Querschnittsfläche je Schicht, in cm².

    Das Feld ist INNEN kleiner als das Level (Konvention von
    `repair.poisson_grid`). Gezählt werden die Knoten, nicht die Zellen --
    auf 192³ ist der Unterschied kleiner als die Gitterauflösung, und die
    Zählung ist die Zahl, die man nachprüfen kann.
    """
    field = np.asarray(field, dtype=np.float64)
    inside = field < float(level)
    area_mm2 = inside.sum(axis=tuple(a for a in range(3) if a != axis)) * float(h) ** 2
    z = np.asarray(lo, dtype=np.float64)[axis] + float(h) * np.arange(field.shape[axis])
    return {"z_mm": z, "area_cm2": area_mm2 / 100.0, "axis": int(axis),
            "volume_cm3": float(inside.sum()) * float(h) ** 3 / 1000.0}


def slice_axis_radius(v: np.ndarray, z: float, slab_mm: float = 2.0):
    """Achse und größter Radius des Netzes in einer Höhenschicht.

    Rückgabe: `(r_max_mm, (cx, cy))`. Die Achse ist der **Schwerpunkt der
    Schicht**, nicht die Mitte des Gitters -- und das ist kein Detail. Der
    Kopf steht schief im Gitter (die Kamera-Orbitbahn läuft schräg), deshalb
    liegt der Halsausschnitt bei z = 0 gut 40 mm neben der Gittermitte. Wer
    den Sockel auf die Gittermitte stellt, bekommt einen Sockel von 70 mm
    Radius für einen 30 mm dicken Hals -- und einen, der über den
    Gitterrand hinausläuft und damit offen bleibt.

    Gemessen wird am Netz, nicht am Feld: das Feld enthält zu jeder
    Rauschmessung in der Luft eine kleine Insel, und der weiteste
    Innenknoten einer Schicht war beim ersten Lauf so eine Insel.
    """
    v = np.asarray(v, dtype=np.float64)
    band = v[(v[:, 2] >= float(z)) & (v[:, 2] <= float(z) + float(slab_mm))]
    if len(band) < 3:
        return 0.0, (float(v[:, 0].mean()), float(v[:, 1].mean()))
    cx, cy = float(band[:, 0].mean()), float(band[:, 1].mean())
    r = np.sqrt((band[:, 0] - cx) ** 2 + (band[:, 1] - cy) ** 2)
    return float(r.max()), (cx, cy)


def grid_room_mm(field: np.ndarray, lo: np.ndarray, h: float,
                 center_xy) -> float:
    """Wieviel Radius das Gitter um die Achse herum überhaupt hergibt (mm).

    Ein Sockel, der über den Gitterrand hinaus will, wird abgeschnitten --
    und abgeschnitten heißt offen. Also vorher nachrechnen, statt sich
    hinterher über 1.076 offene Kanten zu wundern.
    """
    lo = np.asarray(lo, dtype=np.float64)
    h = float(h)
    hi = np.array([lo[0] + h * (field.shape[0] - 1),
                   lo[1] + h * (field.shape[1] - 1)])
    c = np.asarray(center_xy, dtype=np.float64)
    room = float(min(c[0] - lo[0], hi[0] - c[0], c[1] - lo[1], hi[1] - c[1]))
    return room - 2.0 * h


def extend_field(field: np.ndarray, lo: np.ndarray, h: float, level: float,
                 pad_cells: int):
    """Erweitert das Feld seitlich um `pad_cells` Zellen.

    Der Sockel braucht Platz, und der fehlt im ursprünglichen Gitter,
    weil das Gitter um den KOPF herum gebaut wurde. Das Feld einfach auf
    einem größeren Gitter neu zu rechnen, würde die Kantenlänge vergröbern
    (h = Spanne / (stützstellen - 1)) -- der Kopf würde gröber, nur damit
    unten Platz ist. Die Erweiterung läßt die Rekonstruktion, so wie sie
    ist, und hängt außen Luft an.

    Voraussetzung: am Rand des alten Feldes ist überall AUSSEN. Das wird
    geprüft und gemeldet, nicht angenommen.

    Rückgabe: `(feld, lo)` oder `(feld, lo, anzahl_innen)` -- im dritten
    Wert steht, wie viele Randknoten innen lagen und damit ein Leck
    bedeuten würden.
    """
    field = np.asarray(field, dtype=np.float64)
    lo = np.asarray(lo, dtype=np.float64).copy()
    n = int(pad_cells)
    if n <= 0:
        return field, lo, 0
    shell = np.concatenate([
        field[0].ravel(), field[-1].ravel(),
        field[:, 0].ravel(), field[:, -1].ravel(),
        field[:, :, 0].ravel(), field[:, :, -1].ravel()])
    leak = int((shell < float(level)).sum())
    amp = float(np.abs(field - float(level)).max())
    out = np.full((field.shape[0] + 2 * n, field.shape[1] + 2 * n,
                   field.shape[2]), float(level) + amp)
    out[n:-n, n:-n, :] = field
    lo = lo - np.array([n * float(h), n * float(h), 0.0])
    return out, lo, leak


def cut_below(field: np.ndarray, lo: np.ndarray, h: float, level: float,
              z_cut: float, margin: float = 1.0) -> np.ndarray:
    """Schneidet alles unterhalb `z_cut` weg.

    Nicht durch Zerschneiden des Netzes, sondern indem das Feld dort
    hart auf "außen" gesetzt wird. Der Marcher erzeugt danach von selbst
    eine geschlossene Schnittfläche -- und die liegt bis auf Bruchteile
    eines Voxels genau auf der Ebene, weil der Feldwert unterhalb der
    Ebene konstant ist und der Nulldurchgang damit auf der Kante zwischen
    der letzten freien und der ersten abgeschnittenen Schicht sitzt.

    `margin` ist der Abstand des Ersatzwertes vom Level, in Einheiten der
    Feldamplitude. Kleinere Werte erzeugen einen glatteren Übergang,
    größere eine schärfere Kante.
    """
    field = np.asarray(field, dtype=np.float64).copy()
    amp = float(np.abs(field - float(level)).max())
    k = int(round((float(z_cut) - float(lo[2])) / float(h)))
    k = int(np.clip(k, 0, field.shape[2]))
    field[:, :, :k] = float(level) + margin * max(amp, 1e-30)
    return field


def add_plinth(field: np.ndarray, lo: np.ndarray, h: float, level: float,
               z_top: float, z_base: float, r_top: float, r_bottom: float,
               center_xy, margin: float = 1.0) -> np.ndarray:
    """Setzt einen Kegelstumpf als Sockel unter den Körper.

    Wieder als Änderung am Feld: unterhalb `z_top` gilt nur noch der
    Kegelstumpf als innen. Dadurch verschmelzen Sockel und Kopf zu EINEM
    Körper -- ohne Boolesche Operation, ohne Naht, ohne Netzreparatur.

    Der Radius an der Oberseite muss größer sein als der Kopf dort dick
    ist (`r_max_in_plane` liefert die Zahl), sonst schneidet der Sockel
    in den Kopf.
    """
    field = np.asarray(field, dtype=np.float64).copy()
    amp = float(np.abs(field - float(level)).max())
    m = margin * max(amp, 1e-30)
    d = field.shape[0]
    ax0 = float(lo[0]) + float(h) * np.arange(d)
    ax1 = float(lo[1]) + float(h) * np.arange(d)
    x = (ax0 - float(center_xy[0]))[:, None, None]
    y = (ax1 - float(center_xy[1]))[None, :, None]
    z = float(lo[2]) + float(h) * np.arange(field.shape[2])[None, None, :]
    t = np.clip((float(z_top) - z) / max(float(z_top) - float(z_base), 1e-9),
                0.0, 1.0)
    r = float(r_top) + (float(r_bottom) - float(r_top)) * t
    rad = np.sqrt(x * x + y * y)
    below = (z <= float(z_top)) & (z >= float(z_base))
    replace = below
    ins = replace & (rad <= r)
    out = replace & (rad > r)
    field[ins] = float(level) - m
    field[out] = float(level) + m
    # Unter dem Sockel ist ebenfalls außen, sonst wächst eine Platte unten
    # drunter, die niemand bestellt hat.
    field[:, :, z.ravel() < float(z_base)] = float(level) + m
    return field


def _shift(arr, off):
    """`out[q] = arr[q + off]`, außerhalb des Gitters überall False."""
    out = np.zeros_like(arr)
    src = tuple(slice(max(int(o), 0), arr.shape[k] + min(int(o), 0))
                for k, o in enumerate(off))
    dst = tuple(slice(max(-int(o), 0), arr.shape[k] + min(-int(o), 0))
                for k, o in enumerate(off))
    out[dst] = arr[src]
    return out


def band_distance(field, lo, h, level, max_mm):
    """Abstand zur Oberfläche in Millimetern, aus dem Indikatorfeld.

    Es ist der Abstand zum nächsten **Randknoten** -- also zu einem
    Gitterknoten, der unmittelbar an der Fläche liegt -- plus einer
    halben Gitterkante, denn genau so weit sitzt der Randknoten im Mittel
    vor der Isofläche. Nachgemessen an diesem Feld (Strahl von der
    Oberfläche nach innen, 4.000 Proben): bei 1,0 mm Tiefe liefert der
    reine Knotenabstand 0,54 mm, mit der halben Kante 1,00 mm; bei 2,0 mm
    entsprechend 1,50 und 1,96 mm. Es bleibt eine Streuung von gut
    ±0,3 mm -- wer es genauer braucht, muß das Gitter verfeinern.

    Warum nicht eleganter? Der erste Versuch hat das Feld **gefaltet**
    (`phi = |u + d/2| - d/2`, eine Isofläche im Abstand `d/|grad u|`).
    Das scheitert an diesem Feld: das Poisson-Feld ist bis auf eine
    Übergangsbreite von knapp 1,5 mm gesättigt, `|grad u|` fällt dort
    praktisch auf null. Bei 0,5 mm Tiefe stimmt die Schätzung noch
    (0,59 statt 0,50 mm), bei 2 mm liefert sie 14 mm -- eine Schale von
    2 mm läßt sich als Niveaufläche dieses Feldes also gar nicht
    ausdrücken. Der Abstand über das Gitter ist gröber, aber überall
    brauchbar.

    Gerechnet wird nur bis `max_mm`; was weiter weg liegt, bekommt
    `max_mm` und gilt damit als "tief drinnen" -- mehr braucht der
    Hohlkörper nicht zu wissen.
    """
    inside = np.asarray(field, dtype=np.float64) < float(level)
    # Randknoten: innen mit einem äußeren Nachbarn -- und umgekehrt, damit
    # der Abstand auf beiden Seiten der Fläche gleich gezählt wird.
    bnd = np.zeros_like(inside)
    for ax in range(3):
        for s in (-1, 1):
            off = [0, 0, 0]
            off[ax] = s
            bnd |= (inside & ~_shift(inside, off)) | (~inside
                                                      & _shift(inside, off))
    r_max = float(max_mm) / float(h)
    k_max = int(np.ceil(r_max))
    d = np.full(inside.shape, float(max_mm), dtype=np.float64)
    # Alle Gitterversätze bis r_max, der Länge nach sortiert: der erste
    # Treffer ist der nächste, danach kann man aufhören.
    offs = []
    for i in range(-k_max, k_max + 1):
        for j in range(-k_max, k_max + 1):
            for k in range(-k_max, k_max + 1):
                r = np.hypot(np.hypot(i, j), k)
                if r <= r_max:
                    offs.append((r * float(h), (i, j, k)))
    offs.sort(key=lambda t: t[0])
    done = np.zeros_like(inside)
    for dist, off in offs:
        todo = ~done
        if not todo.any():
            break
        hit = _shift(bnd, off) & todo
        if hit.any():
            d[hit] = dist
            done |= hit
    # Der Randknoten sitzt eine halbe Zelle VOR der Fläche. Bei 2 mm
    # Tiefe fehlten sonst 0,5 mm -- und die Wand wäre um eben die zu dünn.
    return np.minimum(d + 0.5 * float(h), float(max_mm))


def shell_field(field, lo, h, level, wall_mm, z_from=None, z_to=None,
                max_mm=None):
    """Macht aus einem massiven Körper einen Hohlkörper mit der Wand
    `wall_mm` -- als Änderung am Feld, nicht am Netz.

    Die Außenwand bleibt dabei bitgleich die des massiven Körpers. Das
    erreicht die folgende Zusammensetzung über `maximum`:

        phi = max(field - level, abstand - wall_mm)

    Denn außen ist `field - level > 0` und damit `phi` genau das
    ursprüngliche Feld -- die sichtbare Oberfläche fällt also mit der
    gemessenen zusammen und wird nicht etwa nach außen verschoben.
    Innen entscheidet der Abstand: näher als `wall_mm` an der Oberfläche
    bleibt Material, weiter weg entsteht der Hohlraum.

    Ein Netz um `wall_mm` nach innen zu schieben, würde sich an Haaren
    und Ohren selbst überlappen, weil der Versatz dort größer ist als die
    örtliche Dicke. Eine Isofläche eines Feldes kann sich nie selbst
    schneiden: wo kein Platz ist, schnürt der Hohlraum ab und die Stelle
    bleibt massiv -- genau das, was ein Drucker braucht.

    `z_from`/`z_to` begrenzen das Aushöhlen auf einen Höhenbereich (der
    Sockel soll massiv bleiben); außerhalb bleibt das Feld unangetastet.
    """
    field = np.asarray(field, dtype=np.float64)
    level = float(level)
    wall = float(wall_mm)
    max_mm = float(max_mm) if max_mm else wall + 2.0 * float(h)
    d = band_distance(field, lo, h, level, max_mm)
    phi = np.maximum(field - level, d - wall)
    if z_from is None and z_to is None:
        return level + phi
    z = float(lo[2]) + float(h) * np.arange(field.shape[2])[None, None, :]
    keep = np.ones(field.shape[2], dtype=bool)
    if z_from is not None:
        keep &= z.ravel() >= float(z_from)
    if z_to is not None:
        keep &= z.ravel() <= float(z_to)
    return level + np.where(keep[None, None, :], phi, field - level)


def drill_hole(field, lo, h, level, center_xy, radius_mm, z_from, z_to,
               margin=1.0):
    """Bohrt ein senkrechtes Loch durch den Körper -- als Änderung am Feld.

    Warum das nötig ist: ein Hohlraum ohne Ablauf ist beim Druck ein
    Gefäß. Beim Harzdruck bleibt das flüssige Harz darin und das Teil
    reißt später auf; beim Schmelzschichten nützt das Hohlsein nichts,
    weil niemand das Pulver herausbekommt. Ein Loch unten im Sockel
    verbindet den Hohlraum mit der Außenwelt -- erst damit ist der Körper
    ein Hohlkörper und nicht eine geschlossene Blase.
    """
    field = np.asarray(field, dtype=np.float64).copy()
    amp = float(np.abs(field - float(level)).max())
    m = margin * max(amp, 1e-30)
    nx, ny, nz = field.shape
    x = float(lo[0]) + float(h) * np.arange(nx)
    y = float(lo[1]) + float(h) * np.arange(ny)
    z = float(lo[2]) + float(h) * np.arange(nz)
    rad = np.hypot((x - float(center_xy[0]))[:, None, None],
                   (y - float(center_xy[1]))[None, :, None])
    inside = ((rad <= float(radius_mm))
              & (z[None, None, :] >= float(z_from))
              & (z[None, None, :] <= float(z_to)))
    field[inside] = float(level) + m
    return field


# -------------------------------------------------------- Dicke ----------

def local_thickness(v: np.ndarray, f: np.ndarray, field: np.ndarray,
                    lo: np.ndarray, h: float, level: float,
                    n_samples: int = 20_000, step_mm: float | None = None,
                    max_mm: float = 250.0, seed: int = 2026,
                    z_from: float | None = None,
                    artefact_mm: float | None = None,
                    limit_mm: float | None = None) -> dict:
    """Kleinste lokale Dicke des Körpers, gemessen durch den Körper hindurch.

    Verfahren: Stichproben auf der Oberfläche, und von jeder aus ein Strahl
    entlang der INNEN-Normalen. Wo der Strahl den Körper wieder verläßt,
    ist die lokale Dicke. Das ist nicht der Durchmesser und nicht die
    Wandstärke eines Hohlkörpers, sondern das, woran ein Drucker scheitert:
    **dünne Stellen**.

    Der Strahl läuft durch das Indikatorfeld, nicht durch das Netz. Das ist
    schneller (kein BVH nötig) und es mißt genau die Fläche, die nachher
    auch exportiert wird. Die Grenze steckt im Gitter: Strukturen unter
    etwa zwei Voxel Kantenlänge sind im Feld gar nicht enthalten und
    tauchen hier folglich nicht auf.

    Rückgabe: `min_mm`, `p01_mm`, `p05_mm`, `median_mm` und `at_mm`
    (die Stelle der dünnsten Probe).

    `z_from` läßt nur Proben oberhalb dieser Höhe zu -- gebraucht wird
    das beim Hohlkörper: die Wand sitzt am Kopf, und die dicken Proben
    vom massiven Sockel würden jeden Median verschleppen.
    `artefact_mm` setzt die Schwelle, unter der eine Messung für ein
    Nadeldreieck gehalten wird. Vier Gitterkanten (die Voreinstellung)
    passen zu einem MASSIVEN Körper; bei einem Hohlkörper ist die Wand
    selbst dünn, und die Schwelle würde die Hälfte aller Messungen als
    Artefakt wegwerfen.

    `limit_mm` zählt, welcher ANTEIL der Proben unter einer Grenze liegt.
    Das ist die verläßlichere Zahl als das Minimum: ein einziger Strahl,
    der schräg durch eine Haarspitze läuft, liefert ein Minimum, das mit
    dem Schritt des Strahls wandert (0,91 mm bei halber, 0,64 mm bei
    viertel Gitterkante) und von der Wand gar nicht handelt. Der Anteil
    bleibt davon unberührt.
    """
    step = float(step_mm) if step_mm else 0.5 * float(h)
    pts, tri = sample_surface(v, f, int(n_samples), seed=seed,
                              return_index=True)
    fn = _unit(face_normals(v, f)[tri])
    if z_from is not None:
        keep = pts[:, 2] >= float(z_from)
        pts, fn = pts[keep], fn[keep]
    level = float(level)
    # Auf welcher Seite liegt innen? Wir prüfen es, statt es zu glauben:
    # das Netz aus dem Isofeld kommt mit nach INNEN zeigenden Normalen.
    probe = sample_field(field, lo, h, pts + 2.0 * step * fn) - level
    direction = np.where((probe < 0.0)[:, None], fn, -fn)
    p0 = pts + 2.0 * step * direction          # ein Stück INSIDE starten

    thick = np.full(len(p0), np.nan)
    prev = sample_field(field, lo, h, p0) - level
    active = np.ones(len(p0), dtype=bool)
    s = np.zeros(len(p0))
    n_steps = int(np.ceil(max_mm / step))
    for k in range(1, n_steps + 1):
        if not active.any():
            break
        s_now = np.where(active, k * step, s)
        p = p0 + direction * s_now[:, None]
        cur = sample_field(field, lo, h, p) - level
        gone = active & (cur >= 0.0)            # Feld ist innen negativ
        if gone.any():
            # Linear zwischen den letzten beiden Schritten interpolieren:
            # der Nulldurchgang liegt nicht auf dem Raster.
            den = cur - prev
            with np.errstate(divide="ignore", invalid="ignore"):
                frac = (-prev) / np.where(np.abs(den) > 1e-30, den, 1.0)
            frac = np.where(np.abs(den) > 1e-30, frac, 0.0)
            frac = np.clip(frac, 0.0, 1.0)
            thick[gone] = (s_now[gone] - step) + frac[gone] * step + 2.0 * step
        active &= ~gone
        prev = np.where(gone, prev, cur)
        s = s_now
    ok = np.isfinite(thick)
    if not ok.any():
        return {"min_mm": None, "p01_mm": None, "p05_mm": None,
                "median_mm": None, "at_mm": None, "samples": 0,
                "artefacts": 0, "min_solid_mm": None}
    t = thick[ok]
    k = int(np.argmin(t))
    where = np.flatnonzero(ok)[k]
    # Strahlen, die schon nach vier Schritten draußen sind, messen keine
    # Form, sondern ein Nadeldreieck: dort steht die Flächennormale quer
    # zur wirklichen Oberfläche, und der Strahl läuft an der Haut entlang
    # statt in den Körper hinein. Sie werden gezählt und gemeldet, aber
    # nicht als Dicke verkauft.
    arte = t <= (4.0 * step if artefact_mm is None else float(artefact_mm))
    solid = t[~arte]
    below = (None if limit_mm is None
             else float(np.mean(t < float(limit_mm))))
    return {"min_mm": float(t.min()),
            "below_limit_frac": below,
            "below_limit_n": (None if limit_mm is None
                              else int((t < float(limit_mm)).sum())),
            "limit_mm": (None if limit_mm is None else float(limit_mm)),
            "p01_mm": float(np.percentile(t, 1)),
            "p05_mm": float(np.percentile(t, 5)),
            "median_mm": float(np.median(t)),
            "at_mm": [float(x) for x in pts[where]],
            "samples": int(ok.sum()),
            "artefacts": int(arte.sum()),
            "min_solid_mm": float(solid.min()) if len(solid) else None}


# ---------------------------------------------------- Überhänge ----------

def overhang_report(v: np.ndarray, f: np.ndarray, up=(0.0, 0.0, 1.0),
                    limit_deg: float = 45.0) -> dict:
    """Flächenanteil, der steiler als `limit_deg` nach unten zeigt.

    Ein FDM-Drucker kann `limit_deg` weit über die Senkrechte hinaus
    drucken; was flacher als das nach unten hängt, braucht Stützmaterial.
    Gezählt wird Fläche, nicht Dreieckszahl -- ein Dutzend winziger
    Dreiecke an der Nasenspitze ist unkritisch, ein halber Quadrat-
    zentimeter unter dem Kinn nicht.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    n = _unit(face_normals(v, f))
    a = triangle_areas(v, f)
    up = np.asarray(up, dtype=np.float64)
    up = up / np.linalg.norm(up)
    cos_up = n @ up
    # "limit_deg überhängend" heißt: die Normale zeigt um mehr als
    # (90 - limit_deg) Grad aus der Senkrechten nach unten.
    need = -np.cos(np.deg2rad(90.0 - float(limit_deg)))
    bad = cos_up < need
    total = float(a.sum())
    return {"limit_deg": float(limit_deg),
            "area_total_cm2": total / 100.0,
            "area_overhang_cm2": float(a[bad].sum()) / 100.0,
            "fraction": float(a[bad].sum() / max(total, 1e-30)),
            "triangles_overhang": int(bad.sum())}


# -------------------------------------------------------- Stand ---------

def _convex_hull_2d(p: np.ndarray) -> np.ndarray:
    """Monotone-Chain-Hülle in der x-y-Ebene. Rückgabe: (M,2) im Uhrzeigersinn."""
    p = np.unique(np.round(np.asarray(p, dtype=np.float64)[:, :2], 6), axis=0)
    if len(p) < 3:
        return p
    order = np.lexsort((p[:, 1], p[:, 0]))
    p = p[order]

    def half(pts):
        out = []
        for q in pts:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (q[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (q[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(q)
        return out

    lower = half(p)
    upper = half(p[::-1])
    return np.array(lower[:-1] + upper[:-1], dtype=np.float64)


def stand_report(v: np.ndarray, f: np.ndarray, up=(0.0, 0.0, 1.0),
                 tol_mm: float = 0.35, flat_cos: float = 0.985) -> dict:
    """Steht das Ding? Standfläche, Schwerpunkt, Kippabstand.

    Drei Zahlen, die man zusammen lesen muß:
      * `contact_cm2` -- die Fläche, die wirklich auf dem Bett liegt.
      * `com_offset_mm` -- wie weit der Schwerpunkt (Volumenschwerpunkt,
        über den Divergenzsatz gerechnet) neben der Mitte der Standfläche
        sitzt.
      * `tilt_margin_mm` -- Abstand von dieser Mitte bis zum Rand der
        Standfläche. Kleiner als der Versatz heißt: es fällt um.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    up = np.asarray(up, dtype=np.float64)
    up = up / np.linalg.norm(up)
    height = v @ up
    z0 = float(height.min())
    n = _unit(face_normals(v, f))
    a = triangle_areas(v, f)
    cen = v[f].mean(axis=1)
    flat = (n @ up) < -float(flat_cos)          # zeigt nach unten == aufliegend
    near = (cen @ up) <= z0 + float(tol_mm)
    sel = flat & near
    out = {"z_min_mm": z0, "contact_cm2": float(a[sel].sum()) / 100.0,
           "triangles_contact": int(sel.sum())}
    if not sel.any():
        out.update(com_offset_mm=None, tilt_margin_mm=None,
                   contact_center_mm=None, stands=None)
        return out
    # Volumenschwerpunkt über den Divergenzsatz.
    p = v[f]
    cr = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    vol6 = np.einsum("ij,ij->i", p[:, 0], cr)
    com = ((p[:, 0] + p[:, 1] + p[:, 2]) / 4.0 * vol6[:, None]).sum(axis=0) \
        / max(vol6.sum(), 1e-30)
    pts = v[f[sel]].reshape(-1, 3)
    hull = _convex_hull_2d(pts[:, :2] if abs(up[2]) > 0.5 else pts[:, [0, 2]])
    if len(hull) < 3:
        out.update(com_offset_mm=None, tilt_margin_mm=None,
                   contact_center_mm=None, stands=None)
        return out
    # Fläche und Schwerpunkt der Hülle (Satz von Gauß, 2D).
    x, y = hull[:, 0], hull[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cr2 = x * y1 - x1 * y
    area2 = cr2.sum()
    cx = ((x + x1) * cr2).sum() / (3.0 * area2)
    cy = ((y + y1) * cr2).sum() / (3.0 * area2)
    out["contact_center_mm"] = [float(cx), float(cy)]
    com_xy = np.array([com[0], com[1]], dtype=np.float64)
    off = float(np.linalg.norm(com_xy - np.array([cx, cy])))
    # Kippabstand: kleinster Abstand von der Schwerpunktsmitte zum
    # Hüllenrand.
    ex, ey = x1 - x, y1 - y
    tt = np.clip(((com_xy[0] - x) * ex + (com_xy[1] - y) * ey)
                 / np.maximum(ex * ex + ey * ey, 1e-30), 0.0, 1.0)
    d = np.linalg.norm(np.stack([x + tt * ex - com_xy[0],
                                 y + tt * ey - com_xy[1]], axis=1), axis=1)
    out["com_offset_mm"] = off
    out["tilt_margin_mm"] = float(d.min())
    out["stands"] = bool(off < d.min())
    # Ebenheit: eine Standfläche, die sich um einen halben Millimeter
    # wölbt, steht auf dem Druckbett auf drei Punkten und wackelt.
    zh = (pts @ up)
    out["flatness_mm"] = float(zh.max() - zh.min())
    return out

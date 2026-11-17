"""Mesh-Optimierung M2b: Normalen, LOD-Kette, UV-Atlas, Textur backen.

Warum das eigene Modul ist:
  docs/03 (6.2) verlangt eine LOD-Kette per **Quadric-Edge-Collapse nach
  Garland/Heckbert** auf 300k / 80k / 20k / 6k Dreiecke. Ein 257k-Dreieck-
  Mesh direkt aufs Handy zu schieben ist keine Option -- und in einen Export
  zu schreiben auch nicht, weil Blender, Houdini und Unity damit unbrauchbar
  langsam werden.

Der Kern (Garland/Heckbert 1997, "Surface Simplification Using Quadric Error
Metrics") in drei Saetzen:
  1. Jedem Vertex wird eine 4x4-Matrix Q zugeordnet, die die **Summe der
     quadrierten Abstaende** zu allen Ebenen seiner Umgebung angibt.
  2. Das Zusammenfassen der Kante (u,v) nach p kostet  p^T (Q_u + Q_v) p.
     Das ist eine Zahl, kein Gefuehl -- deshalb kann man die Kanten in eine
     Prioritaetswarteschlange legen und immer die billigste zuerst nehmen.
  3. Die optimale Position p ist die Loesung eines 3x3-Gleichungssystems.

Vier Details, die man wissen muss, sonst wird das Ergebnis Muell:
  * **Randkanten** brauchen eine Strafterm-Ebene, sonst zieht sich der
    Algorithmus die Raender ein wie ein zugeknoteter Sack.
  * **Dreiecke duerfen nicht umklappen.** Ohne diese Pruefung entstehen
    innenliegende Flächen, die kein Reparaturwerkzeug mehr heilt.
  * Die Matrix ist oft **singulaer** (flache Stellen). Dann muss man auf
    Mittelpunkt bzw. Endpunkte zurueckfallen.
  * Die Kosten im Heap werden **schlecht**, sobald sich ein Nachbar bewegt.
    Deshalb wird jede Kante beim Herausholen nachgerechnet und bei
    Abweichung neu eingereiht (lazy update).

UV-Atlas: docs/03 (11) sagt "feste UVs des Basiskopfs". Die Registrierung auf
den Basiskopf kommt erst mit dem 3DMM-Morphing, deshalb ist hier ein
**spärischer Atlas** der Platzhalter: eine einzige Chart, Injectivitaet
geschenkt, weil ein Kopf um seinen Mittelpunkt sternfoermig ist. Das ist
ehrlich als Platzhalter benannt -- kein xatlas-Ersatz.
"""
from __future__ import annotations

import heapq
import struct
import zlib

import numpy as np

# ------------------------------------------------------------------ Normale ----


def face_normals(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    """Flächennormalen, Länge = 2 × Fläche (also flächengewichtet)."""
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return np.cross(b - a, c - a)


def vertex_normals(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    """Flächengewichtet auf die Vertices verteilt und normiert.

    Flächengewichtung (statt einfach die Nachbarnormalen zu mitteln) ist
    wichtig: sonst bekommen schmale Dreiecke in langgezogenen Bereichen
    dasselbe Gewicht wie große -- und die Normale kippt sichtbar.
    """
    n = face_normals(v, f)
    out = np.zeros_like(v)
    np.add.at(out, f[:, 0], n)
    np.add.at(out, f[:, 1], n)
    np.add.at(out, f[:, 2], n)
    ln = np.linalg.norm(out, axis=1)
    ln[ln < 1e-20] = 1.0
    return out / ln[:, None]


# ------------------------------------------------------------------ Quadriken --


def _plane_quadrics(v: np.ndarray, f: np.ndarray, area_weight: bool):
    """Für jede Fläche die Ebene (a,b,c,d) mit a²+b²+c²=1."""
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    e1, e2 = b - a, c - a
    nrm = np.cross(e1, e2)
    area2 = np.linalg.norm(nrm, axis=1)
    safe = area2 > 1e-300
    nrm[safe] /= area2[safe, None]
    d = -np.einsum("ij,ij->i", nrm, a)
    w = (0.5 * area2) if area_weight else np.ones(len(f))
    return np.concatenate([nrm, d[:, None]], axis=1), w


# Die 10 unabhängigen Werte einer symmetrischen 4x4-Matrix:
#   q00 q01 q02 q03 | q11 q12 q13 | q22 q23 | q33
# p = (a,b,c,d) -> p p^T
_PP = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 1), (1, 2), (1, 3),
       (2, 2), (2, 3), (3, 3)]


def _k10(p: np.ndarray, w: np.ndarray) -> np.ndarray:
    return np.stack([w * p[:, i] * p[:, j] for i, j in _PP], axis=1)


def _accumulate(n_vert: int, idx: np.ndarray, k: np.ndarray) -> np.ndarray:
    """Summiert (m,10)-Quadriken auf die Vertices in `idx`."""
    out = np.empty((n_vert, 10))
    for c in range(10):
        out[:, c] = np.bincount(idx, weights=k[:, c], minlength=n_vert)
    return out


def build_quadrics(v: np.ndarray, f: np.ndarray, boundary_weight: float = 16.0,
                   area_weight: bool = True) -> np.ndarray:
    """Fehlerquadrik je Vertex als 10 Werte, inklusive Rand-Strafterm.

    Der Randterm ist der Unterschied zwischen "sauber vereinfacht" und
    "zugeknoteter Sack": Zu jeder Randkante (Kante mit nur EINER
    angrenzenden Fläche) wird eine senkrechte Ebene durch die Kante mit
    großem Gewicht ergänzt. Ein Randvertex wird damit teuer, sobald er den
    Rand verlassen will.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    p, w = _plane_quadrics(v, f, area_weight)
    q = _accumulate(len(v), f.reshape(-1), np.repeat(_k10(p, w), 3, axis=0))

    e = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    lo, hi = e.min(axis=1), e.max(axis=1)
    key = lo.astype(np.int64) * (len(v) + 1) + hi
    uniq, cnt = np.unique(key, return_counts=True)
    if not np.any(cnt == 1):
        return q
    bkey = uniq[cnt == 1]
    bu = (bkey // (len(v) + 1)).astype(np.int64)
    bv = (bkey % (len(v) + 1)).astype(np.int64)
    d = v[bv] - v[bu]
    ln = np.linalg.norm(d, axis=1)
    good = ln > 1e-12
    bu, bv, d, ln = bu[good], bv[good], d[good], ln[good]
    if len(bu) == 0:
        return q
    d = d / ln[:, None]
    nrm = np.cross(d, v[bu] - v.mean(axis=0))
    l2 = np.linalg.norm(nrm, axis=1)
    ok = l2 > 1e-12
    nrm[ok] /= l2[ok, None]
    if not np.all(ok):
        basis = np.eye(3)[np.argmin(np.abs(d[~ok]), axis=1)]
        alt = np.cross(d[~ok], basis)
        alt /= np.linalg.norm(alt, axis=1, keepdims=True)
        nrm[~ok] = alt
    pe = np.concatenate([nrm, (-np.einsum("ij,ij->i", nrm, v[bu]))[:, None]],
                        axis=1)
    mean_area = float(np.mean(0.5 * np.linalg.norm(
        np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1)))
    wl = np.full(len(pe), boundary_weight * mean_area * ln)
    # Beide Endpunkte bekommen je die Hälfte; über eine "Fläche" (bu,bv,bv)
    # gebaut, damit dieselbe Akkumulationsschleife greift.
    bf = np.stack([bu, bv, bv], axis=1)
    q += _accumulate(len(v), bf.reshape(-1),
                     np.repeat(_k10(pe, wl), 3, axis=0) * 0.5)
    return q


def _eval_q(qs: np.ndarray, p: np.ndarray) -> np.ndarray:
    """p^T Q p für (m,10)-Quadriken und (m,3)-Positionen."""
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    return (qs[:, 9]
            + 2.0 * (qs[:, 3] * x + qs[:, 6] * y + qs[:, 8] * z)
            + qs[:, 0] * x * x + qs[:, 4] * y * y + qs[:, 7] * z * z
            + 2.0 * (qs[:, 1] * x * y + qs[:, 2] * x * z + qs[:, 5] * y * z))


def batch_edge_cost(q: np.ndarray, v: np.ndarray, e0: np.ndarray,
                    e1: np.ndarray):
    """Kosten und optimale Position für VIELLE Kanten auf einmal.

    Der 3x3-System wird hier über die Adjunkte geschlossen gelöst statt mit
    np.linalg.solve: bei 400k Kanten ist der Aufruf-Aufwand von solve der
    Flaschenhals, nicht die Arithmetik. Singuläre Fälle (flache Stellen,
    dort ist die Matrix nicht invertierbar) fallen auf den Mittelpunkt
    bzw. die Endpunkte zurück -- genau wie es Garland/Heckbert beschreiben.
    """
    qs = q[e0] + q[e1]
    a00, a01, a02, a03 = qs[:, 0], qs[:, 1], qs[:, 2], qs[:, 3]
    a11, a12, a13 = qs[:, 4], qs[:, 5], qs[:, 6]
    a22, a23 = qs[:, 7], qs[:, 8]

    c00 = a11 * a22 - a12 * a12
    c01 = a02 * a12 - a01 * a22
    c02 = a01 * a12 - a11 * a02
    c11 = a00 * a22 - a02 * a02
    c12 = a01 * a02 - a00 * a12
    c22 = a00 * a11 - a01 * a01
    det = a00 * c00 + a01 * c01 + a02 * c02

    ok = np.abs(det) > 1e-12
    safe = np.where(ok, det, 1.0)
    b0, b1, b2 = -a03, -a13, -a23
    xs = (c00 * b0 + c01 * b1 + c02 * b2) / safe
    ys = (c01 * b0 + c11 * b1 + c12 * b2) / safe
    zs = (c02 * b0 + c12 * b1 + c22 * b2) / safe
    p_solve = np.stack([xs, ys, zs], axis=1)
    e_solve = np.where(ok, _eval_q(qs, p_solve), np.inf)

    p_mid = 0.5 * (v[e0] + v[e1])
    cands = [(e_solve, p_solve),
             (_eval_q(qs, p_mid), p_mid),
             (_eval_q(qs, v[e0]), v[e0]),
             (_eval_q(qs, v[e1]), v[e1])]
    best_c, best_p = cands[0]
    for c, pp in cands[1:]:
        take = c < best_c
        best_c = np.where(take, c, best_c)
        best_p = np.where(take[:, None], pp, best_p)
    return np.maximum(best_c, 0.0), best_p


# -------------------------------------------------------------- Vereinfacher --


def canon3(a, b, c):
    """Kanonische Form eines Dreiecks: kleinster Index nach vorn DREHEN.

    Drehen erhaelt die Umlaufrichtung (a,b,c) -> (b,c,a) -> (c,a,b),
    Sortieren wuerde sie zerstoeren. Zwei Dreiecke aus denselben drei
    Punkten bekommen so genau dann denselben Schluessel, wenn sie
    dieselbe Orientierung haben -- und genau das brauchen wir, um
    Zwillingsdreiecke nach dem Zusammenfassen einer Kante zu finden.
    """
    if a <= b and a <= c:
        return (a, b, c)
    if b <= a and b <= c:
        return (b, c, a)
    return (c, a, b)


def canon_rows(f: np.ndarray) -> np.ndarray:
    """`canon3` zeilenweise auf ein (M, 3)-Indexfeld."""
    f = np.asarray(f, dtype=np.int64)
    out = np.empty_like(f)
    for r in range(3):
        m = (f[:, r] <= f[:, (r + 1) % 3]) & (f[:, r] <= f[:, (r + 2) % 3])
        out[m] = np.stack([f[m, r], f[m, (r + 1) % 3], f[m, (r + 2) % 3]], axis=1)
    return out


def _directed_edges(f: np.ndarray, n_v: int):
    """Gerichtete Kanten des Netzes.

    Rueckgabe je Kante: Dreiecksnummer, Slot (0..2), Start, Ziel.
    Die Richtung ist die UMLAUFRICHTUNG des Dreiecks -- genau daran
    erkennt man, ob zwei Nachbarn gleichsinnig orientiert sind.
    """
    m = len(f)
    tri = np.tile(np.arange(m, dtype=np.int64), 3)
    slot = np.concatenate([np.full(m, k, dtype=np.int64) for k in range(3)])
    a = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
    b = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
    return tri, slot, a, b


def winding_errors(f: np.ndarray) -> int:
    """Anzahl der Kanten, die beide Nachbardreiecke GLEICHSINNIG durchlaufen.

    Bei einem sauber orientierten Netz ist das null: teilen sich zwei
    Dreiecke eine Kante, muessen sie sie gegensinnig durchlaufen, sonst
    zeigt eines von beiden nach innen. Kanten am Rand (nur ein
    Nachbar) zaehlen nicht -- die haben keinen Partner, mit dem sie
    streiten koennten.

    Genau diese Zahl hat den Sortier-Fehler in `_MeshState` aufgedeckt,
    den weder der Geometrie- noch der Indexvergleich gesehen hat.
    """
    f = np.asarray(f, dtype=np.int64)
    if len(f) == 0:
        return 0
    _, _, a, b = _directed_edges(f, int(f.max()) + 1)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    uk = lo.astype(np.int64) * (int(f.max()) + 1) + hi
    sgn = (a < b)
    order = np.argsort(uk, kind="stable")
    us, sg = uk[order], sgn[order]
    start = np.searchsorted(us, us, side="left")
    cnt = np.searchsorted(us, us, side="right") - start
    # Jede Kantengruppe genau einmal: der erste Eintrag der Gruppe.
    sel = np.flatnonzero((cnt == 2) & (np.arange(len(us)) == start))
    return int((sg[sel] == sg[sel + 1]).sum())


def orient_mesh(v: np.ndarray, f: np.ndarray):
    """Dreht Dreiecke um, bis das Netz durchgaengig orientiert ist.

    Breitensuche ueber die Kantenachbarschaft: teilen sich zwei
    Dreiecke eine Kante gleichsinnig, wird das spaetere gedreht. Das ist
    der Schritt, den man VOR einem UV-Atlas braucht -- xatlas und
    Konsorten zerlegen ein gemischt orientiertes Netz in tausende
    Einzel-Charts, weil sie die Nachbarschaft nicht mehr erkennen. Bei
    25.000 Dreiecken waren es 20.753 Charts statt 6.
    """
    f = np.asarray(f, dtype=np.int64).copy()
    m = len(f)
    if m == 0:
        return np.asarray(v), f
    n_v = int(f.max()) + 1
    tri, _slot, a, b = _directed_edges(f, n_v)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    uk = lo.astype(np.int64) * (n_v + 1) + hi
    sgn = (a < b)
    order = np.argsort(uk, kind="stable")
    us, sg = uk[order], sgn[order]
    start = np.searchsorted(us, us, side="left")
    cnt = np.searchsorted(us, us, side="right") - start
    sel = np.flatnonzero((cnt == 2) & (np.arange(len(us)) == start))

    t1 = tri[order[sel]]
    t2 = tri[order[sel + 1]]
    par = (sg[sel] == sg[sel + 1]).astype(np.int8)   # 1 = umdrehen

    # Nachbarschaft als CSR.
    # ACHTUNG: nicht ueber einen "fill"-Zeiger je Dreieck aufbauen. Ein
    # Dreieck kann zu demselben Nachbarn ZWEI Kanten haben, dann taucht
    # es in t1 doppelt auf -- und `fill[src] = pos + 1` zaehlt nur
    # einmal weiter. Danach zeigt ein Teil des CSR ins Nirgendwo.
    # Sortieren ist hier nicht langsamer und immer richtig.
    src_all = np.concatenate([t1, t2])
    dst_all = np.concatenate([t2, t1])
    par_all = np.concatenate([par, par])
    o = np.argsort(src_all, kind="stable")
    adj = dst_all[o]
    parity = par_all[o]
    indptr = np.concatenate(
        [[0], np.cumsum(np.bincount(src_all, minlength=m))]).astype(np.int64)

    flip = np.full(m, -1, dtype=np.int8)
    indptr_l = indptr.tolist()
    adj_l = adj.tolist()
    par_l = parity.tolist()
    flip_l = flip.tolist()
    for seed in range(m):
        if flip_l[seed] >= 0:
            continue
        flip_l[seed] = 0
        stack = [seed]
        while stack:
            t = stack.pop()
            ft = flip_l[t]
            for i in range(indptr_l[t], indptr_l[t + 1]):
                o = adj_l[i]
                if flip_l[o] < 0:
                    flip_l[o] = ft ^ par_l[i]
                    stack.append(o)
    flip = np.asarray(flip_l, dtype=bool)
    f[flip] = f[flip][:, ::-1]
    return np.asarray(v), f


class _MeshState:
    """Topologie zum Zusammenlegen von Kanten.

    Buch geführt werden:
      * `tri`   -- Dreiecke als sortierte Index-Tripel, `t_alive` als Maske
      * `e2t`   -- Kante -> Liste der angrenzenden Dreiecke
      * `v2e`   -- Vertex -> Menge seiner Kanten
      * `tkey`  -- kanonisches Tripel -> Dreiecksnummer (zum Entdoppeln)

    ACHTUNG, und das ist der wichtigste Satz in dieser Klasse: Dreiecke
    werden **zyklisch kanonisiert**, nicht sortiert. Ein sortiertes
    Tripel verliert die Umlaufrichtung, und die brauchen wir:
    `cross(p1 - p0, p2 - p0)` muss die AUSSEN-Normale liefern, sonst
    steht hinterher die Haelfte der Dreiecke auf links. Wer hier
    `np.sort` stehen hat, bekommt ein Netz, das in jedem Viewer
    gesprenkelt aussieht -- und das Gemeine ist, dass es geometrisch
    vollkommen korrekt bleibt, also durch jeden Test faellt, der nur
    Koordinaten und Indizes vergleicht.
    """

    def __init__(self, f: np.ndarray):
        self.tri = canon_rows(np.asarray(f, dtype=np.int64)).copy()
        self.n = int(self.tri.max()) + 1
        self.t_alive = np.ones(len(self.tri), dtype=bool)
        self.e2t = {}
        self.v2e = [set() for _ in range(self.n)]
        self.tkey = {}
        for t in range(len(self.tri)):
            k = tuple(self.tri[t])
            self.tkey[k] = t
            self._link(t)

    def _ek(self, a, b):
        return (a, b) if a < b else (b, a)

    def _link(self, t):
        a, b, c = self.tri[t]
        for x, y in ((a, b), (b, c), (c, a)):
            k = self._ek(x, y)
            self.e2t.setdefault(k, []).append(t)
            self.v2e[x].add(k)
            self.v2e[y].add(k)

    def _unlink(self, t):
        a, b, c = self.tri[t]
        for x, y in ((a, b), (b, c), (c, a)):
            k = self._ek(x, y)
            lst = self.e2t.get(k)
            if lst is None:
                continue
            if t in lst:
                lst.remove(t)
            if not lst:
                del self.e2t[k]
                # Erst wenn die Kante WIRKLICH keinem Dreieck mehr gehört,
                # darf sie aus den Nachbarlisten der beiden Punkte
                # verschwinden. Stand das `discard` außerhalb dieses
                # Zweigs, verlor ein Punkt jede Kante, die noch ein
                # anderes Dreieck benutzt -- die Liste der Dreiecke um
                # einen Punkt wurde Stück für Stück kürzer, und beim
                # Zusammenfassen blieben Dreiecke übrig, die niemand mehr
                # kannte. Die hingen danach nur noch an einer Kante am
                # Rest: Randkanten, nicht-manigfaltige Ecken und am Ende
                # 255 Einzelteile aus einem Stück.
                self.v2e[x].discard(k)
                self.v2e[y].discard(k)

    def kill(self, t):
        if not self.t_alive[t]:
            return
        self.t_alive[t] = False
        self.tkey.pop(tuple(self.tri[t]), None)
        self._unlink(t)

    def add(self, t, key):
        self.tri[t] = key
        self.t_alive[t] = True
        self.tkey[key] = t
        self._link(t)


def quadric_decimate(v, f, target_faces, colors=None, boundary_weight=16.0,
                     color_weight=0.0, uv=None, uv_weight=0.0,
                     max_cost=np.inf, flip_cos=-0.2,
                     pass_fraction=0.03, verbose=False,
                     float32_safe=False, locked=None, keepout=None):
    """Vereinfacht ein Dreiecksnetz auf `target_faces` Flächen.

    Rückgabe: (v2, f2, colors2, uv2). Farben und UVs werden gemittelt
    mitgetragen; mit `color_weight > 0` bzw. `uv_weight > 0` wird das
    Zusammenfassen unterschiedlich gefärbter Vertices zusätzlich bestraft
    (wichtig an Materialgrenzen, etwa Haut -> Haar, sonst franst die
    Grenze aus).

    Die UV-Strafe ist der zweite Grund, `uv` hier mitzugeben: in einem
    Atlas liegen die Charts mit Abstand nebeneinander. Würde man eine
    Kante quer über diesen Abstand zusammenfassen, zöge sich die Textur
    über die Lücke -- ein Streifen fremder Farbe mitten im Gesicht. Die
    Strafe macht genau diese Kanten teuer, und sie werden es nie.

    Ablauf: in jedem **Durchgang** werden die Kosten aller Kanten auf einmal
    vektorisiert berechnet, sortiert und die billigsten Kanten
    zusammengefasst. Ein strikter Prioritätswarteschlange-Schritt pro Kante
    wäre in Python rund zehnmal langsamer und bringt hier sichtbar nichts:
    nach `pass_fraction` Anteil Kanten werden die Kosten ohnehin neu
    berechnet.

    Vier Schutzmechanismen, ohne die das Ergebnis unbrauchbar wird:
      * **Umklapp-Prüfung:** kein Dreieck darf seine Orientierung umkehren.
      * **Gültigkeitsprüfung:** tote Vertices und gelöschte Kanten werden
        übersprungen (die sortierte Liste ist innerhalb eines Durchgangs
        teilweise veraltet).
      * **Nachbarschaftsbedingung:** keine Kante darf vier Nachbarn
        bekommen (sonst ist das Netz nicht mehr wasserdicht, s. unten).
      * **max_cost:** bricht ab, bevor aus einem ehrgeizigen Ziel ein
        zerstörtes Netz wird.

    `locked` ist eine boolesche Maske über die Punkte; ein Punkt mit
    `True` darf sich nicht bewegen, und Kanten, an denen er hängt, werden
    nicht zusammengefaßt. Gebraucht wird das für FUNKTIONSFLÄCHEN --
    Flächen also, deren Maß etwas bedeutet und nicht nur deren Form. Ein
    Ablaufloch ist so eine: uniform vereinfacht schrumpft es von 10 mm auf
    gut 4 mm Durchmesser, weil ein Zylinder eine abwickelbare Fläche ist
    und das Zusammenfassen entlang der Achse praktisch nichts kostet. Das
    Loch bleibt offen, aber es entwässert nicht mehr. Solche Stellen
    schützt man, statt zu hoffen.

    `keepout` ist eine achsenparallele Kiste `((x0,y0,z0), (x1,y1,z1))`,
    die kein neues Dreieck schneiden darf. Wozu das gut ist: eine EBENE
    Fläche läßt sich kostenlos vereinfachen -- jedes Dreieck darin liegt
    genau auf ihr, die Quadrik merkt nichts. Hat diese Fläche aber ein
    Loch, wird es zugepflastert: der Boden des Hohlraums ist eine
    waagerechte Scheibe mit dem Ablaufloch in der Mitte, und drei Punkte
    im Abstand von 120° ergeben ein Riesendreieck, das das Loch
    überdeckt. Der Hohlraum ist danach ein geschlossenes Gefäß, und kein
    Wasserdicht-Test der Welt merkt es -- das Netz ist tadellos, es
    entwässert nur nicht mehr. Punkte am Loch festzuhalten hilft nicht
    (die drei Ecken des zudeckenden Dreiecks dürfen weit weg liegen),
    wohl aber diese Kiste: wer sie schneidet, wird abgelehnt.

    `float32_safe` richtet die neuen Punktlagen so aus, daß das Netz auch
    noch **nach dem Export** wasserdicht ist. Warum das nötig ist: STL
    speichert Positionen als 32-Bit-Zahl (7 Ziffern), und das Optimum der
    Quadrik fällt sehr oft fast genau auf einen schon vorhandenen Punkt --
    dann sind zwei Punkte im Speicher um 1e-6 mm verschieden und in der
    Datei IDENTISCH. Jeder Leser, der sie zusammenfaßt, findet danach
    Kanten mit vier Nachbarn: 14 solcher Paare genügten, und ein im
    Speicher tadelloses Netz (0 Randkanten, Euler 2) kam aus der Datei
    mit Euler 17 und `is_watertight = False` zurück. Zusammenfaßen NACH
    dem Runden hilft nicht -- die entstehenden Löcher bekommt man nicht
    mehr sauber gestopft (es blieben 3 Kanten mit vier Nachbarn). Also
    wird die Kollision VERMIEDEN: die neue Lage wird auf 32 Bit gerundet
    und das Zusammenfassen abgelehnt, wenn dort schon ein Punkt liegt.
    """
    v = np.asarray(v, dtype=np.float64).copy()
    f = np.asarray(f, dtype=np.int64)
    if target_faces >= len(f):
        return v, f, (None if colors is None else np.asarray(colors))

    st = _MeshState(f)
    q = build_quadrics(v, f, boundary_weight=boundary_weight)
    alive_v = np.ones(len(v), dtype=bool)
    n_link = 0          # wie oft die Nachbarschaftsbedingung abgelehnt hat
    n_snap = 0          # wie oft die 32-Bit-Prüfung abgelehnt hat
    n_keep = 0          # wie oft das Sperrgebiet abgelehnt hat
    v32 = v.astype(np.float32) if float32_safe else None
    if float32_safe:
        # Bitmuster der 32-Bit-Lage -> wie viele Punkte liegen dort. Ein
        # Eintrag mit 2 wäre eine Kollision, die wir nicht mehr heilen
        # können -- das Ausgangsnetz muß also schon sauber sein.
        uniq, cnt = np.unique(v32, axis=0, return_counts=True)
        spot = {row.tobytes(): int(c) for row, c in zip(uniq, cnt)}
        n_clash0 = int((cnt > 1).sum())
    else:
        spot, n_clash0 = None, 0
    cols = (None if colors is None
            else np.asarray(colors, dtype=np.float64).copy())
    uvs = None if uv is None else np.asarray(uv, dtype=np.float64).copy()
    n_faces = len(f)

    def gather(tri, w, pos):
        """Positionen der Dreiecksecken, wobei Vertex w auf `pos` sitzt."""
        out = np.empty((len(tri), 3, 3))
        for k in range(3):
            col = tri[:, k]
            pp = v[col].copy()
            pp[col == w] = pos
            out[:, k, :] = pp
        return out

    def ring(vert):
        """Nachbarpunkte von `vert` -- wem die Kanten gehören."""
        out = set()
        for kk in st.v2e[vert]:
            if kk in st.e2t:
                out.add(kk[0] if kk[1] == vert else kk[1])
        return out

    def rings_around(u, w):
        """(Dreiecke um u, Dreiecke um u oder w) -- beides nur lebende.

        Der zweite Teil ist für die PRÜFUNGEN (Umklappen, Sperrgebiet),
        der erste für den Umbau: nur die Dreiecke am sterbenden Punkt
        bekommen einen neuen Index, und nur die darf man herauswerfen und
        neu eintragen. Beides in einen Topf zu werfen, zerstört das Netz
        (Euler -4407 nach dem ersten Schritt): ein Dreieck, das bloß
        mitwandert, zweimal zu töten, reißt ein Loch.
        """
        a_u, both = set(), set()
        for kk in st.v2e[u]:
            a_u.update(st.e2t.get(kk, ()))
        both.update(a_u)
        for kk in st.v2e[w]:
            both.update(st.e2t.get(kk, ()))
        a_u = np.fromiter((t for t in a_u if st.t_alive[t]),
                          dtype=np.int64,
                          count=sum(1 for t in a_u if st.t_alive[t]))
        both = np.fromiter((t for t in both if st.t_alive[t]),
                           dtype=np.int64,
                           count=sum(1 for t in both if st.t_alive[t]))
        return a_u, both

    while n_faces > target_faces:
        edges = list(st.e2t.keys())
        if not edges:
            break
        e0 = np.fromiter((a for a, _ in edges), dtype=np.int64, count=len(edges))
        e1 = np.fromiter((b for _, b in edges), dtype=np.int64, count=len(edges))
        cost, pos = batch_edge_cost(q, v, e0, e1)
        if color_weight > 0.0 and cols is not None:
            cost = cost + color_weight * np.sum((cols[e0] - cols[e1]) ** 2,
                                                axis=1)
        if uv_weight > 0.0 and uvs is not None:
            cost = cost + uv_weight * np.sum((uvs[e0] - uvs[e1]) ** 2,
                                             axis=1)
        order = np.argsort(cost, kind="stable")
        if cost[order[0]] > max_cost:
            break
        budget = max(1, int(pass_fraction * len(order)))

        done = 0
        for j in order:
            if n_faces <= target_faces or done >= budget:
                break
            u, w = int(e0[j]), int(e1[j])
            if not (alive_v[u] and alive_v[w]):
                continue
            if locked is not None and (locked[u] or locked[w]):
                continue
            if (u, w) not in st.e2t:
                continue
            p = pos[j]
            if cost[j] > max_cost:
                break

            # ---- Umklappen verhindern ----------------------------------
            # Geprüft wird um BEIDE Punkte herum, nicht nur um den
            # sterbenden: die Dreiecke am überlebenden Punkt wandern mit,
            # wenn er auf `p` rückt, und ändern sich dabei genauso. Wer
            # nur um `u` herum prüft, läßt jedes Dreieck wachsen, das
            # zufällig immer am überlebenden Punkt hängt -- Zug um Zug,
            # unbegrenzt, und keine Prüfung der Welt sieht es. Genau so
            # ist dem Ablaufloch der Boden über den Kopf gezogen worden:
            # das zudeckende Dreieck war nie das neu entstandene, sondern
            # eines, das nur mitwanderte.
            around, touched = rings_around(u, w)
            if len(touched):
                old = st.tri[touched]
                n0 = np.cross(v[old[:, 1]] - v[old[:, 0]],
                              v[old[:, 2]] - v[old[:, 0]])
                new = old.copy()
                new[new == u] = w
                pp = gather(new, w, p)
                n1 = np.cross(pp[:, 1] - pp[:, 0], pp[:, 2] - pp[:, 0])
                l0 = np.linalg.norm(n0, axis=1)
                l1 = np.linalg.norm(n1, axis=1)
                good = (l0 > 1e-18) & (l1 > 1e-18)
                if np.any(good):
                    cs = (np.sum(n0[good] * n1[good], axis=1)
                          / (l0[good] * l1[good]))
                    if np.any(cs < flip_cos):
                        continue

            # ---- Nachbarschaftsbedingung --------------------------------
            # Zusammenlegen darf nur, wenn die Umgebung der Kante (u,w)
            # genau aus den beiden Dreiecken an der Kante besteht -- die
            # "link condition": lk(u) ∩ lk(w) = lk(uw). Sonst entsteht
            # eine Ecke, an der sich zwei Flaechenblaetter nur in einer
            # Kante beruehren, und eine Kante mit VIER Nachbarn. Das Netz
            # sieht danach unveraendert aus, ist aber nicht mehr
            # wasserdicht -- und ein Formfehler, der an den Vertices
            # mißt, merkt es nicht: die liegen ja richtig, es fehlt nur
            # ein Stueck Flaeche daneben. Wer nur die Abweichung misst,
            # haelt ein loechriges Netz fuer ein gutes. Erst der
            # Wasserdicht-Test findet es.
            opp = set()
            for t in st.e2t.get((u, w), ()):
                if st.t_alive[t]:
                    a, b, c = st.tri[t]
                    opp.add(a if (a != u and a != w)
                            else (b if (b != u and b != w) else c))
            ru, rw = ring(u), ring(w)
            if (ru & rw) != opp:
                n_link += 1
                continue

            if keepout is not None:
                klo, khi = keepout
                # Vortest: kein Dreieck aus dieser Nachbarschaft kann die
                # Kiste erreichen, wenn sie als ganzes nicht einmal in
                # ihre Nähe kommt. Das ist der Regelfall -- das Loch ist
                # ein Zylinder von 8 mm in einer Büste von 140 mm --, und
                # ohne diesen Vortest kostet die Prüfung mehr als alles
                # andere zusammen.
                nb = np.fromiter((ru | rw) | {u, w}, dtype=np.int64)
                pn = v[nb]
                a0 = np.minimum(pn.min(axis=0), p)
                a1 = np.maximum(pn.max(axis=0), p)
                if (a1 >= klo).all() and (a0 <= khi).all():
                    tri = st.tri[touched]
                    gone = (((tri == u) | (tri == w)).sum(axis=1) == 2)
                    if not gone.all():
                        # u und w liegen am Ende beide auf p
                        P = np.where(((tri == u) | (tri == w))[:, :, None],
                                     p[None, None, :], v[tri])
                        mn, mx = P.min(axis=1), P.max(axis=1)
                        hit = ((mx >= klo) & (mn <= khi)).all(axis=1) & ~gone
                        if hit.any():
                            n_keep += 1
                            continue

            # ---- Die neue Lage muß auch in der Datei noch eigen sein ---
            if float32_safe:
                # Erst beide alten Lagen abmelden, dann die neue prüfen:
                # u stirbt, w zieht um, also zählt keine von beiden noch.
                ku, kw = v32[u].tobytes(), v32[w].tobytes()
                spot[ku] -= 1
                if spot[ku] == 0:
                    del spot[ku]
                spot[kw] -= 1
                if spot[kw] == 0:
                    del spot[kw]
                p32 = np.asarray(p, dtype=np.float32)
                kp = p32.tobytes()
                if kp in spot:
                    # Ein paar Stellen weiterrücken, statt das
                    # Zusammenfassen wegzuwerfen. Ein ULP sind bei 100 mm
                    # rund 8e-6 mm -- das sieht kein Drucker und kein
                    # Mensch. Ablehnen ist dagegen teuer: genau die
                    # Zusammenlegungen, deren Optimum auf einen schon
                    # vorhandenen Punkt fällt, sind die BILLIGSTEN.
                    alt = p32
                    for _ in range(6):
                        alt = np.nextafter(alt, np.float32(np.inf))
                        kp = alt.tobytes()
                        if kp not in spot:
                            p32 = alt
                            p = alt.astype(np.float64)
                            break
                    else:
                        spot[ku] = spot.get(ku, 0) + 1
                        spot[kw] = spot.get(kw, 0) + 1
                        n_snap += 1
                        continue
                # Gerückt wird NUR, wenn es sein muß. Jedes neue Optimum
                # auf 32 Bit zu runden, sieht harmlos aus (8e-6 mm) und
                # kostet doch 40 % Formfehler -- nicht weil die Rundung
                # so groß wäre, sondern weil sie den ABLAUF ändert: ein
                # anderer Grenzwert in der Umklapp-Prüfung, eine andere
                # Kante, eine andere Kette von Entscheidungen. p95 fiel
                # von 0,118 mm auf 0,084 mm, als die Rundung entfiel.
                v32[w] = p32
                spot[kp] = 1

            # ---- Kante zusammenfassen: u stirbt, w überlebt ------------
            for t in around.tolist():
                a, b, c = st.tri[t]
                st.kill(t)
                n_faces -= 1
                if w in (a, b, c):
                    continue                     # lag auf der Kante
                key = canon3(*(w if x == u else x for x in (a, b, c)))
                if len(set(key)) < 3:
                    continue                     # entartet -> weg
                # Kanonisieren durch DREHEN, nicht durch Sortieren: nur
                # so bleibt die Umlaufrichtung des Dreiecks erhalten.
                other = st.tkey.get(key)
                if other is not None:
                    st.kill(other)               # Zwillinge heben sich auf
                    n_faces -= 1
                    continue
                st.add(t, key)
                n_faces += 1

            v[w] = p
            q[w] = q[u] + q[w]
            if cols is not None:
                cols[w] = 0.5 * (cols[u] + cols[w])
            if uvs is not None:
                uvs[w] = 0.5 * (uvs[u] + uvs[w])
            alive_v[u] = False
            st.v2e[u] = set()
            done += 1
        else:
            if done == 0:
                break
        if done == 0:
            break

    if verbose:
        print("    %7d Zusammenlegungen wegen der Nachbarschaftsbedingung "
              "abgelehnt" % n_link)
        if float32_safe:
            print("    %7d wegen der 32-Bit-Pruefung abgelehnt, "
                  "%d Kollisionen schon im Ausgangsnetz" % (n_snap, n_clash0))
            print("    %7d wegen des Sperrgebiets abgelehnt" % n_keep)

    keep = np.flatnonzero(st.t_alive)
    f2 = st.tri[keep]
    used = np.unique(f2)
    remap = np.full(len(v), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    v2 = v[used]
    f2 = remap[f2]
    c2 = None if cols is None else cols[used]
    u2 = None if uvs is None else uvs[used]
    if verbose:
        print("    %7d -> %7d Dreiecke, %7d Punkte"
              % (len(f), len(f2), len(v2)))
    return v2, f2, c2, u2


def connected_components(v: np.ndarray, f: np.ndarray):
    """Zerlegt das Netz in Zusammenhangskomponenten.

    Rückgabe: (labels, größen) -- `labels[i]` ist die Nummer der
    Komponente, zu der Punkt i gehört. Läuft über die Kanten, nicht über
    eine Nachbarschaftssuche: bei 1,5 M Dreiecken ist der Unterschied
    zwischen "eine Sekunde" und "eine Minute".
    """
    v = np.asarray(v)
    f = np.asarray(f, dtype=np.int64)
    n = len(v)
    a = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
    b = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
    parent = np.arange(n, dtype=np.int64)

    def find(x: np.ndarray) -> np.ndarray:
        while True:
            p = parent[x]
            if np.array_equal(p, x):
                return x
            parent[x] = parent[p]
            x = p

    for _ in range(64):
        ra, rb = find(a), find(b)
        hi = np.maximum(ra, rb)
        lo = np.minimum(ra, rb)
        np.minimum.at(parent, hi, lo)
        if np.array_equal(find(a), find(b)):
            break
    labels = find(np.arange(n))
    uniq, inv = np.unique(labels, return_inverse=True)
    sizes = np.bincount(inv)
    return inv.reshape(-1), sizes[inv]


def drop_small_components(v: np.ndarray, f: np.ndarray, min_faces: int = 500,
                          colors=None, uv=None):
    """Entfernt alle Komponenten mit weniger als `min_faces` Dreiecken.

    docs/03 (6.2) verlangt das ausdrücklich, und es ist keine Kosmetik:
    ein Visual-Hull-Haarnetz besteht zu einem guten Teil aus
    Einzelbeulen, die kein Voxel mit dem Hauptvolumen teilen. Die sind
    geometrisch echt, aber im Export nur Rauschen -- 855 Inseln mit je
    drei Dreiecken blähen jede Szene auf und verstopfen die
    UV-Chart-Zerlegung.
    """
    v = np.asarray(v, dtype=np.float64)
    f = np.asarray(f, dtype=np.int64)
    labels, sizes = connected_components(v, f)
    keep = sizes >= int(min_faces)
    if keep.all():
        return (v, f, colors, uv)
    sel = keep[f].all(axis=1)
    f2 = f[sel]
    used = np.unique(f2)
    remap = np.full(len(v), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    out = [v[used], remap[f2]]
    for arr in (colors, uv):
        out.append(None if arr is None else np.asarray(arr)[used])
    return tuple(out)


def lod_chain(v, f, targets=(300_000, 80_000, 20_000, 6_000), colors=None,
              uv=None, **kw):
    """Baut die LOD-Kette aus docs/03 (6.2).

    Jede Stufe wird aus der vorherigen gerechnet, nicht aus dem vollen
    Netz -- das ist nicht nur schneller, es liefert auch konsistente
    Hierarchien (jede Stufe ist eine echte Vereinfachung der darüber).

    Wird `uv` mitgegeben, wandert der Atlas über alle Stufen mit. Genau
    das ist der Sinn eines globalen Atlas: ALLE LODs teilen EINE Textur,
    deshalb muss man keine zweite backen und keinen Platz verschenken.
    """
    out, cv, cf = [], np.asarray(v, dtype=np.float64), np.asarray(f, dtype=np.int64)
    cc = None if colors is None else np.asarray(colors, dtype=np.float64)
    cu = None if uv is None else np.asarray(uv, dtype=np.float64)
    for t in targets:
        cv, cf, cc, cu = quadric_decimate(cv, cf, t, colors=cc, uv=cu, **kw)
        out.append((cv.copy(), cf.copy(),
                    None if cc is None else cc.copy(),
                    None if cu is None else cu.copy()))
        if len(cf) <= 4:
            break
    return out


# ------------------------------------------------------------------ UV-Atlas --


def spherical_uv(v: np.ndarray, center=None) -> np.ndarray:
    """Kugelatlas: eine einzige Chart, u = Azimut, v = Polarwinkel.

    Platzhalter für die "festen UVs des Basiskopfs" aus docs/03 (11).
    Er funktioniert, weil ein Kopf um seinen Mittelpunkt sternförmig ist --
    jede Sehne vom Mittelpunkt trifft die Oberfläche genau einmal. Kein
    xatlas, aber ausreichend, um Vertexfarben in eine Textur zu backen.
    """
    v = np.asarray(v, dtype=np.float64)
    c = v.mean(axis=0) if center is None else np.asarray(center, dtype=np.float64)
    d = v - c
    r = np.linalg.norm(d, axis=1)
    r[r < 1e-12] = 1e-12
    d = d / r[:, None]
    u = 0.5 + np.arctan2(d[:, 0], d[:, 2]) / (2.0 * np.pi)
    vv = np.arccos(np.clip(d[:, 1], -1.0, 1.0)) / np.pi
    return np.stack([u, 1.0 - vv], axis=1)


def bake_texture(v, f, uv, colors, size=2048, pad=2) -> np.ndarray:
    """Backt Vertexfarben in eine Textur (einfache UV-Rasterisierung).

    bewusst einfach gehalten: Für jedes Dreieck wird die Bounding-Box im
    UV-Raum durchlaufen und baryzentrisch interpoliert. Bei 257k Dreiecken
    und 2048² sind das im Mittel ~16 Pixel pro Dreieck -- schnell genug.

    Am Ende werden unbeschriebene Pixel mit Nachbarfarben aufgefüllt
    ("dilate"). Ohne das blutet beim späteren Texturfiltern der
    Hintergrund in die Kanten.
    """
    v = np.asarray(v, dtype=np.float64)
    uv = np.asarray(uv, dtype=np.float64)
    colors = np.asarray(colors, dtype=np.float64)
    img = np.zeros((size, size, 3), dtype=np.float64)
    seen = np.zeros((size, size), dtype=bool)

    px = (uv[:, 0] * (size - 1)).astype(np.int64)
    py = (uv[:, 1] * (size - 1)).astype(np.int64)
    for tri in np.asarray(f, dtype=np.int64):
        i0, i1, i2 = tri
        x0, y0 = px[i0], py[i0]
        x1, y1 = px[i1], py[i1]
        x2, y2 = px[i2], py[i2]
        minx, maxx = max(0, min(x0, x1, x2)), min(size - 1, max(x0, x1, x2))
        miny, maxy = max(0, min(y0, y1, y2)), min(size - 1, max(y0, y1, y2))
        if maxx < minx or maxy < miny:
            continue
        e0 = np.array([x1 - x0, y1 - y0], dtype=np.float64)
        e1 = np.array([x2 - x0, y2 - y0], dtype=np.float64)
        den = e0[0] * e1[1] - e0[1] * e1[0]
        if abs(den) < 1e-12:
            continue
        c0, c1, c2 = colors[i0], colors[i1], colors[i2]
        for yy in range(miny, maxy + 1):
            ry = yy + 0.5 - y0
            for xx in range(minx, maxx + 1):
                rx = xx + 0.5 - x0
                b1 = (rx * e1[1] - ry * e1[0]) / den
                b2 = (ry * e0[0] - rx * e0[1]) / den
                b0 = 1.0 - b1 - b2
                if b0 < -1e-6 or b1 < -1e-6 or b2 < -1e-6:
                    continue
                img[yy, xx] = b0 * c0 + b1 * c1 + b2 * c2
                seen[yy, xx] = True

    # ---- Lücken füllen (dilate) -----------------------------------------
    for _ in range(pad):
        missing = ~seen
        if not missing.any():
            break
        acc = np.zeros_like(img)
        cnt = np.zeros((size, size), dtype=np.float64)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            sh_src = (slice(max(0, -dy), size - max(0, dy)),
                      slice(max(0, -dx), size - max(0, dx)))
            sh_dst = (slice(max(0, dy), size - max(0, -dy)),
                      slice(max(0, dx), size - max(0, -dx)))
            w = seen[sh_src]
            acc[sh_dst] += img[sh_src] * w[:, :, None]
            cnt[sh_dst] += w
        fill = missing & (cnt > 0)
        if not fill.any():
            break
        img[fill] = acc[fill] / cnt[fill, None]
        seen |= fill
    return np.clip(img, 0, 255).astype(np.uint8)


def write_png(path: str, rgb: np.ndarray):
    """Minimaler PNG-Schreiber (nur stdlib): 8 Bit RGB, kein Filter.

    PNG ist Pflicht, weil GLB und glTF eingebettete Bilder nur als PNG oder
    JPEG akzeptieren -- und wir keine Bildbibliothek im Produkt wollen.
    """
    rgb = np.asarray(rgb, dtype=np.uint8)
    h, w = rgb.shape[0], rgb.shape[1]
    if rgb.ndim == 2:
        rgb = np.repeat(rgb[:, :, None], 3, axis=2)
        color_type = 0
    else:
        color_type = 2
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type,
                                            0, 0, 0)))
        fh.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        fh.write(chunk(b"IEND", b""))
    return path


# -------------------------------------------------------------------- Qualität --


def one_sided_distance(a: np.ndarray, b: np.ndarray, cell: float = 2.0,
                       shells: int = 4):
    """Mittlerer Abstand von a nach b über eine Gittersuche.

    Wiederverwendung derselben Idee wie in metrics.py: ein uniformes Gitter
    über b, erweitert um `shells` Zellen, reicht als Näherung für den
    nächsten Nachbarn -- und ist um Größenordnungen schneller als ein
    KD-Baum in reinem Python.
    """
    from . import metrics as mt
    return mt.chamfer(a, b, cell=cell, shells=shells)

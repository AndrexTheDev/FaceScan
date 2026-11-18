"""Rig: Gelenke und Hautgewichte fuer ein Gesichtsnetz. (M3)

Ein Netz aus Millionen von Dreiecken ist starr. Damit ein Kopf nicken, den
Mund oeffnen oder in eine Richtung schauen kann, braucht er zwei Dinge:

  1. ein Skelett -- wenige Gelenke in einer Hierarchie (Hals -> Kopf -> Kiefer),
  2. Hautgewichte -- je Vertex die Angabe, wie stark welches Gelenk ihn bewegt.

Dieses Modul bestimmt beides *aus dem Netz selbst*, nicht von Hand. Die
einzige Voraussetzung ist das 3D-Modell aus ``headmesh``: ein elliptischer Kopf
mit Nase, Kinn und Ohren. Es liefert die **Richtungen**, in denen die
Gesichtsmerkmale liegen. Wo sie im konkreten Scan sitzen, wird gemessen --
durch Anpassung des Modells an die Oberflaeche.

Warum dieser Weg und nicht "wir suchen die Nase als groessten Ueberstand"?
Weil ein einzelner Ueberstand auf einem vermessenen Kopf nicht eindeutig ist:
Ohren, Haar und Nase ragen aehnlich weit heraus (auf unserem Netz 5..7 mm --
siehe docs/05, Abschnitt 12.1). Das Modell kennt dagegen die *Form* des
Ganzen. Es an die Oberflaeche anzupassen nutzt tausende Punkte gleichzeitig
und ist deshalb wesentlich sicherer.

Zu jeder Achse gibt es bewusst **zwei unabhaengige Schaetzungen**, die sich
gegenseitig pruefen:

  * oben:  (a) die Schnittflaeche unten am Netz -- ein Kopf, der aufrecht
               steht, ist unten plan abgeschnitten (Sockel oder das Ende des
               beobachteten Bereichs);
           (b) die Traegheitshauptachse -- ein Kopf ist laenger als breit,
               die laengste Achse zeigt nach oben.
  * vorn:  (a) der Modell-Fit -- die Anpassung wird systematisch um die
               Hochachse gedreht; die Nase sitzt nur in einer Drehung richtig;
           (b) der groesste radiale Ueberstand im Gesichtsband.

Stimmen beide, ist das Ergebnis belastbar. Stimmen sie nicht, meldet das
Modul die Abweichung statt stillschweigend zu raten (``frame_report``).

Einheiten: Millimeter. Koordinatensystem wie in ``synthetic``: x rechts,
y oben, z zur Kamera hin (die Blickrichtung des Kopfes).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .headmesh import (DIR_CHIN, DIR_EAR_L, DIR_EAR_R, DIR_EYE_L, DIR_EYE_R,
                       DIR_MOUTH, DIR_NOSE, RX, RY, RZ, head_radius)

__all__ = [
    "Frame", "Joint", "Skeleton", "ModelFit",
    "base_plane_up", "inertia_up", "estimate_frame", "fit_model",
    "measure_front_overhang", "landmark_positions", "build_skeleton",
    "skin_weights", "frame_report", "skeleton_to_world",
]


# ---------------------------------------------------------------- Hilfsmittel
def _norm(d: np.ndarray) -> np.ndarray:
    d = np.asarray(d, dtype=float)
    n = np.linalg.norm(d, axis=-1, keepdims=True)
    return d / np.maximum(n, 1e-12)


def _rotation_from_axes(right: np.ndarray, up: np.ndarray, front: np.ndarray) -> np.ndarray:
    """Spalten = (rechts, oben, vorn). Modell -> Welt, wenn orthonormal."""
    R = np.stack([_norm(right), _norm(up), _norm(front)], axis=1)
    # Gram-Schmidt, damit aus leicht schiefen Achsen eine saubere Drehung wird
    R[:, 0] = _norm(R[:, 0])
    R[:, 1] = _norm(R[:, 1] - R[:, 0] * (R[:, 0] @ R[:, 1]))
    R[:, 2] = np.cross(R[:, 0], R[:, 1])
    return R


# ------------------------------------------------------------- Modell-Rahmen
@dataclass
class Frame:
    """Orientierung und Position des Kopfes im Netz-Rahmen.

    Ein Punkt des Modells p_modell liegt im Netz bei
    ``center + scale * (R @ p_modell)``.
    """

    R: np.ndarray            # 3x3, Spalten (rechts, oben, vorn)
    center: np.ndarray       # (3,), Kopfmitte im Netz-Rahmen
    scale: float = 1.0

    def to_world(self, p_model: np.ndarray) -> np.ndarray:
        p = np.asarray(p_model, dtype=float)
        return self.center + self.scale * (p @ self.R.T)

    def to_model(self, p_world: np.ndarray) -> np.ndarray:
        p = np.asarray(p_world, dtype=float)
        return ((p - self.center) @ self.R) / self.scale


@dataclass
class ModelFit:
    """Ergebnis der Modellanpassung -- inklusive der Frage, ob sie gelang."""

    frame: Frame
    residual_mm: float       | None = None   # medianer Betrag des Abstands
    residual_p90_mm: float   | None = None
    n_used: int = 0
    up_source: str = ""
    front_source: str = ""
    up_disagreement_deg: float | None = None
    front_disagreement_deg: float | None = None


# --------------------------------------------------- Achse 1: wo ist "oben"?
def base_plane_up(v: np.ndarray, frac: float = 0.05) -> tuple[np.ndarray, float]:
    """Senkrechte aus der ebenen Schnittflaeche unten.

    Nimmt die untersten ``frac`` der Punkte und legt eine Ebene hindurch
    (kleinster Eigenvektor der Kovarianz). Ein aufrecht stehender Kopf endet
    unten plan -- entweder am Sockel oder dort, wo keine Kamera mehr hinsah.

    Rueckgabe: (Richtung, Ebenendicke in mm). Die Dicke ist ein
    Guetemass: eine echte Schnittflaeche ist duenn (< 5 mm), eine
    abgerundete Kopfwolke ist es nicht.
    """
    v = np.asarray(v, dtype=float)
    y = v[:, 1]
    cut = y.min() + frac * (y.max() - y.min())
    sel = y < cut
    if sel.sum() < 50:
        sel = np.argsort(y)[: max(50, len(v) // 100)]
    P = v[sel]
    X = P - P.mean(axis=0)
    _, s, vt = np.linalg.svd(X, full_matrices=False)
    n = vt[-1]
    if n[1] < 0:
        n = -n
    thickness = float(s[-1] / np.sqrt(max(len(P), 1)))
    return _norm(n), thickness


def inertia_up(v: np.ndarray, f: np.ndarray) -> tuple[np.ndarray, float]:
    """Laengste Achse des Netzes aus dem Traegheitstensor.

    Unabhaengig von der Schnittflaeche: ein Kopf ist in Hochrichtung laenger
    als breit oder tief. Rueckgabe: (Richtung, Streuungsverhaeltnis
    laengste/kuerzeste Achse) -- je groesser, desto eindeutiger.
    """
    v = np.asarray(v, dtype=float)
    X = v - v.mean(axis=0)
    _, s, vt = np.linalg.svd(X, full_matrices=False)
    n = vt[0]
    if n[1] < 0:
        n = -n
    return _norm(n), float(s[0] / max(s[-1], 1e-9))


# --------------------------------------------------- Achse 2: wo ist "vorn"?
def measure_front_overhang(v: np.ndarray, up: np.ndarray,
                           y_lo: float = -30.0, y_hi: float = 30.0,
                           n_bins: int = 36) -> tuple[float, float]:
    """Blickrichtung als groesster radialer Ueberstand im Gesichtsband.

    Der Kopf wird um die Hochachse in Sektoren zerlegt; gesucht ist die
    Richtung, die ueber das geglaettete Mittel der Nachbarrichtungen
    hinausragt. Das ist die Nase -- oder, wenn sie fehlt, das Kinn.

    Rueckgabe: (Winkel in Grad um ``up``, Ueberstand in mm).
    Der Winkel wird gegen die Achsen ``e1, e2`` gemessen, die mit ``up``
    ein Rechtssystem bilden; der Aufrufende muss ihn in Weltkoordinaten
    uebersetzen.
    """
    v = np.asarray(v, dtype=float)
    up = _norm(up)
    e1 = _norm(np.cross(up, [0.0, 0.0, 1.0])) if abs(up[2]) < 0.9 else np.array([1.0, 0, 0])
    e2 = np.cross(up, e1)
    height = v @ up
    band = (height > y_lo) & (height < y_hi)
    if band.sum() < 500:                        # Band zu duenn -- alles nehmen
        band = np.ones(len(v), dtype=bool)
    P = v[band]
    a = P @ e1
    b = P @ e2
    radius = np.hypot(a, b)
    ang = np.degrees(np.arctan2(b, a))
    bins = np.linspace(-180.0, 180.0, n_bins + 1)
    prof = np.zeros(n_bins)
    for i in range(n_bins):
        m = (ang >= bins[i]) & (ang < bins[i + 1])
        prof[i] = np.percentile(radius[m], 99) if m.sum() > 20 else 0.0
    smooth = np.convolve(np.r_[prof[-3:], prof, prof[:3]], np.ones(7) / 7, mode="same")[3:-3]
    over = prof - smooth
    k = int(np.argmax(over))
    return float(0.5 * (bins[k] + bins[k + 1])), float(over[k])


def _fit_residual(v: np.ndarray, R: np.ndarray, center: np.ndarray,
                  scale: float, mask_pts: np.ndarray) -> float:
    """Medianer Betrag des radialen Abstands Modell <-> Netz."""
    d = (mask_pts - center) @ R                       # Modell-Koordinaten
    r_net = np.linalg.norm(d, axis=1)
    r_mod = scale * head_radius(_norm(d))
    return float(np.median(np.abs(r_net - r_mod)))


def _fit_scale(v: np.ndarray, R: np.ndarray, center: np.ndarray,
               mask_pts: np.ndarray) -> float:
    """Bester Massstab bei gegebener Lage (robust: Median des Verhaeltnisses)."""
    d = (mask_pts - center) @ R
    r_net = np.linalg.norm(d, axis=1)
    r_mod = head_radius(_norm(d))
    ok = r_mod > 1.0
    if ok.sum() < 100:
        return 1.0
    return float(np.median(r_net[ok] / r_mod[ok]))


def _face_mask(v: np.ndarray, R: np.ndarray, center: np.ndarray, scale: float,
               y_lo: float = -45.0, y_hi: float = 60.0,
               front_min: float = 0.5) -> np.ndarray:
    """Punkte der vorderen Kopfhaelfte zwischen Kinn und Stirn.

    Nur dort passt das Modell: am Hinterkopf und oben sitzt Haar, das die
    Modellform nicht beschreibt und die Anpassung verzerren wuerde.
    """
    d = (v - center) @ R / max(scale, 1e-6)
    dn = _norm(d)
    return (dn[:, 2] > front_min) & (d[:, 1] > y_lo) & (d[:, 1] < y_hi)



# --------------------------------------------------- Achse 3: Mittelebene
def symmetry_plane(v: np.ndarray, up: np.ndarray, n_punkte: int = 20000,
                   raster: float = 1.5, schritt: float = 0.5,
                   bereich: float = 25.0) -> tuple[float, float]:
    """Mittelebene aus der Spiegelsymmetrie des Kopfes.

    Ein Kopf ist (von kleinen Scan-Ungenauigkeiten abgesehen) spiegelsym-
    metrisch. Die Ebene, an der sich die Punktwolke am besten auf sich
    selbst abbilden laesst, ist die Mittelebene. Das ist eine dritte, vom
    Modell-Fit voellig unabhaengige Schaetzung: sie kennt keine Nase und
    kein Kinn, nur die Symmetrie.

    Gesucht wird entlang der Rechts-Achse (senkrecht zur Hochachse). Die
    Treffer werden ueber einen Raster-Hash gezaehlt -- schnell genug fuer
    hundert Kandidaten.

    Rueckgabe: (Versatz in mm, Anteil getroffener Spiegelpunkte 0..1).
    """
    v = np.asarray(v, dtype=float)
    # Die Referenz muss dicht sein, sonst trifft ein gespiegelter Punkt
    # nur zufaellig auf einen Stichprobenpunkt und die Schaetzung wird
    # unbrauchbar. Gespiegelt wird eine duenne Stichprobe, verglichen wird
    # gegen die volle Wolke.
    P = v[::max(1, len(v) // max(n_punkte, 1))]
    ref = v[::2] if len(v) > 40000 else v
    up = _norm(up)
    # Rechts-Achse: die Netz-x-Achse, senkrecht zur Hochachse gestellt
    a = np.array([1.0, 0.0, 0.0], dtype=float)
    a = _norm(a - up * float(a @ up))

    def code(Q: np.ndarray) -> np.ndarray:
        k = np.round(Q / raster).astype(np.int64) + 4096
        return (k[:, 0] * 65536 + k[:, 1]) * 65536 + k[:, 2]

    base = np.unique(code(ref))
    best = (0.0, -1.0)
    for d in np.arange(-bereich, bereich + 1e-9, schritt):
        P2 = P - 2.0 * (P @ a - d)[:, None] * a
        treffer = float(np.isin(code(P2), base).mean())
        if treffer > best[1]:
            best = (float(d), treffer)
    return best


# ------------------------------------------------- Gittersuche statt Raten
def _front_from(yaw_deg: float, e1: np.ndarray, e2: np.ndarray) -> np.ndarray:
    t = np.radians(yaw_deg)
    return np.cos(t) * e1 + np.sin(t) * e2


def _grob_yaw(sub: np.ndarray, up: np.ndarray, e1: np.ndarray, e2: np.ndarray,
              centre: np.ndarray) -> float:
    """Grobe Blickrichtung: Modell-Fit **ohne** Gesichtsmaske.

    Ohne Maske sitzt der Massstab zwar zu gross (das Haar hebt ihn an), die
    Drehung wird aber trotzdem zuverlaessig gefunden -- die Nase ist die
    einzige Ausbeulung dieser Groesse. Genauigkeit reicht als Startwert.
    """
    best = None
    for a in range(-180, 180, 5):
        fr = _front_from(a, e1, e2)
        R = _rotation_from_axes(np.cross(up, fr), up, fr)
        s = _fit_scale(sub, R, centre, sub)
        r = _fit_residual(sub, R, centre, s, sub)
        if best is None or r < best[0]:
            best = (r, a)
    return float(best[1])


def _gittersuche(v: np.ndarray, sub: np.ndarray, up: np.ndarray,
                 e1: np.ndarray, e2: np.ndarray, yaw0: float,
                 centre0: np.ndarray, verbose: bool = False) -> tuple[float, float, float, float]:
    """Blickrichtung und Kopfmitte durch hierarchische Gittersuche.

    Warum eine Gittersuche und keine Bergwanderung? Weil die Zielfunktion
    Nebenminima hat: wer vom Schwerpunkt aus nur bergab laeuft, bleibt auf
    unserem Netz 4 Grad und 2,4 mm neben der Wahrheit stehen. Ein Gitter
    findet das globale Minimum zuverlaessig, wenn man es von grob nach fein
    verengt -- drei Stufen kosten zusammen nur einen Bruchteil einer durch-
    gehend feinen Suche.

    Gesucht wird ueber (Blickwinkel, Hoehe der Kopfmitte, Tiefe der Kopf-
    mitte). Der Massstab folgt jeweils aus dem Median des Radiusverhaelt-
    nisses; die seitliche Lage kommt aus der Mittelebene. Die Gesichtsmaske
    wird aus dem bisher besten Rahmen bestimmt und dann festgehalten -- das
    Ziel darf sich waehrend einer Stufe nicht bewegen.

    Rueckgabe: (Winkel, y, z, Massstab).
    """
    def wert(P: np.ndarray, yaw: float, cy: float, cz: float) -> tuple[float, float]:
        fr = _front_from(yaw, e1, e2)
        R = _rotation_from_axes(np.cross(up, fr), up, fr)
        d = (P - np.array([centre0[0], cy, cz])) @ R
        rn = np.linalg.norm(d, axis=1)
        rm = head_radius(_norm(d))
        ok = rm > 1.0
        if ok.sum() < 100:
            return 1e9, 1.0
        sc = float(np.median(rn[ok] / rm[ok]))
        return float(np.median(np.abs(rn - sc * rm))), sc

    # Die Suche bleibt bewusst LOKAL um die vorab bestimmte Blickrichtung.
    # Ueber alle 360 Grad gesucht gewinnt naemlich nicht das Gesicht, sondern
    # der Hinterkopf: er ist schoen glatt und passt deshalb besser zum glatten
    # Modell als Nase, Kinn und Augenpartie. Das Vorzeichen (vorn gegen
    # hinten) entscheidet deshalb der maskenfreie Fit in ``_grob_yaw``, der
    # den ganzen Kopf -- inklusive Nase und Kinn -- im Blick hat.
    stufen = [
        dict(n_a=13, span_a=15.0, d_y=8.0, span_y=32.0, n_pkt=4000, n_mask=800),
        dict(n_a=13, span_a=5.0, d_y=2.0, span_y=8.0, n_pkt=8000, n_mask=2000),
        dict(n_a=9, span_a=1.0, d_y=0.5, span_y=2.0, n_pkt=16000, n_mask=2000),
    ]
    best = (yaw0, float(centre0[1]), float(centre0[2]))
    for i, st in enumerate(stufen):
        P = sub[::max(1, len(sub) // st["n_pkt"])]
        fr = _front_from(best[0], e1, e2)
        R = _rotation_from_axes(np.cross(up, fr), up, fr)
        s0 = wert(P, best[0], best[1], best[2])[1]
        Pm = P[_face_mask(P, R, np.array([centre0[0], best[1], best[2]]), max(s0, 1e-6))]
        # Die Maske darf nicht zu duenn werden, sonst verliert der Fit die
        # Forminformation; aber sie muss auch nicht punktreich sein -- tausend
        # gleichmaessig verteilte Gesichtspunkte legen die Kopfmitte auf
        # Zehntelmillimeter fest.
        if Pm.shape[0] >= 150:
            P = Pm[::max(1, Pm.shape[0] // st["n_mask"])]
        achsen = np.arange(-st["span_y"], st["span_y"] + 1e-9, st["d_y"])
        bb = None
        for a in np.linspace(-st["span_a"], st["span_a"], st["n_a"]):
            for cy in achsen:
                for cz in achsen:
                    w, sc = wert(P, best[0] + a, best[1] + cy, best[2] + cz)
                    if bb is None or w < bb[0]:
                        bb = (w, best[0] + a, best[1] + cy, best[2] + cz, sc)
        if bb is not None:
            best = (bb[1], bb[2], bb[3])
        if verbose:
            print(f"    Stufe {i + 1} ({len(P):,} Punkte, Schritt {st['d_y']} mm): "
                  f"Winkel {best[0]:.2f}, Kopfmitte y={best[1]:.2f} z={best[2]:.2f}, "
                  f"Fehler {bb[0]:.3f} mm")
    _, s = wert(sub, best[0], best[1], best[2])
    return best[0], best[1], best[2], s


def fit_model(v: np.ndarray, f: np.ndarray, up: np.ndarray | None = None,
              front: np.ndarray | None = None,
              n_yaw: int = 72, refine: int = 3,
              n_sample: int = 20000, verbose: bool = False) -> ModelFit:
    """Passt das Kopfmodell an das Netz an: Drehung, Lage, Massstab.

    Ablauf:
      1. Hochachse bestimmen -- aus der Schnittflaeche, falls die Flaeche
         duenn genug ist (< 5 mm), sonst aus dem Traegheitstensor.
      2. Blickrichtung durch systematisches Drehen um die Hochachse: fuer
         jeden Winkel wird der Modell-Fehler gemessen; das Minimum gewinnt.
      3. Lage und Massstab in mehreren Runden verfeinern (Koordinatensuche
         ohne Ableitungen -- scipy steht hier nicht zur Verfuegung).

    Rueckgabe: ein ``ModelFit`` mit Rahmen, Restfehler und Guetemass.
    """
    v = np.asarray(v, dtype=float)
    f = np.asarray(f, dtype=np.int64)
    # Der Fit braucht keine Millionen Punkte: Lage und Massstab sind aus
    # wenigen tausend Oberflaechenpunkten ebenso genau bestimmt. Gestrichen
    # wird gleichmaessig ueber die Punktliste, nicht zufaellig -- so bleibt
    # das Ergebnis bei jedem Lauf identisch.
    step = max(1, len(v) // max(n_sample, 1))
    sub = v[::step]

    # --- Schritt 1: oben -------------------------------------------------
    up_plane, thickness = base_plane_up(v)
    up_inertia, ratio = inertia_up(v, f)
    up_src = "Schnittflaeche"
    if thickness > 5.0:                       # keine plane Flaeche -> Traegheit
        up_src = "Traegheit (Schnittflaeche %.1f mm dick)" % thickness
        up_0 = up_inertia
    else:
        up_0 = up_plane
    if up is not None:                        # Vorgang hat Vorrang
        up_0 = _norm(up)
        up_src = "vorgegeben"
    disagreement_up = float(np.degrees(np.arccos(
        np.clip(float(up_plane @ up_inertia), -1.0, 1.0))))

    up_0 = _norm(up_0)
    e1 = _norm(np.cross(up_0, [0.0, 0.0, 1.0])) if abs(up_0[2]) < 0.9 else np.array([1.0, 0, 0])
    e2 = np.cross(up_0, e1)

    # --- Schritt 2: vorn und Kopfmitte ------------------------------------
    # Vorsicht vor der Reihenfolge: die Gesichtsmaske haengt selbst von
    # Rahmen und Lage ab. Wuerde man sie bei jedem Probeschritt neu
    # berechnen, bewegte sich das Ziel mit -- die Optimierung jagte dann
    # eine Funktion, die sich unter ihr veraendert, und bliebe in einem
    # Nebenminimum haengen (auf unserem Netz 4 Grad und 2,4 mm neben der
    # Wahrheit). Darum hier wie bei ICP: erst Korrespondenzen festlegen,
    # dann loesen, dann neu zuordnen.
    e1 = _norm(np.cross(up_0, [0.0, 0.0, 1.0])) if abs(up_0[2]) < 0.9 else np.array([1.0, 0, 0])
    e2 = np.cross(up_0, e1)
    centre0 = np.asarray(v.mean(axis=0), dtype=float)

    if front is not None:                     # Vorgang hat Vorrang
        front = _norm(front)
        a0 = float(np.degrees(np.arctan2(front @ e2, front @ e1)))
        yaw0, front_src = a0, "vorgegeben"
    else:
        yaw0, front_src = _grob_yaw(sub, up_0, e1, e2, centre0), "Modell-Fit"

    # Die Mittelebene ist die dritte unabhaengige Schaetzung: ein Kopf ist
    # spiegelsymmetrisch. Wo die Spiegelachse liegt, sagt nichts ueber die
    # Blickrichtung -- und umgekehrt. Beides zusammen ist belastbar.
    x_sym, sym_quote = symmetry_plane(v, up_0)
    centre0[0] = x_sym

    yaw, y, z, scale = _gittersuche(v, sub, up_0, e1, e2, yaw0, centre0,
                                    verbose=verbose)
    centre = np.array([x_sym, y, z])

    mask = _face_mask(v, _rotation_from_axes(
        np.cross(up_0, _front_from(yaw, e1, e2)), up_0, _front_from(yaw, e1, e2)),
        centre, scale)
    # Der Massstab aus der Gittersuche gilt der ganzen Wolke und wird vom Haar
    # angehoben; fuer das Gesicht muss er neu bestimmt werden.
    scale = _fit_scale(v, _rotation_from_axes(
        np.cross(up_0, _front_from(yaw, e1, e2)), up_0, _front_from(yaw, e1, e2)),
        centre, v[mask])
    R = _rotation_from_axes(np.cross(up_0, _front_from(yaw, e1, e2)),
                            up_0, _front_from(yaw, e1, e2))
    err = np.abs(np.linalg.norm((v - centre) @ R, axis=1)
                 - scale * head_radius(_norm((v - centre) @ R)))
    fit = ModelFit(
        frame=Frame(R=R, center=centre, scale=scale),
        residual_mm=float(np.median(err[mask])),
        residual_p90_mm=float(np.percentile(err[mask], 90)),
        n_used=int(mask.sum()),
        up_source=up_src,
        front_source=front_src,
        up_disagreement_deg=disagreement_up,
    )
    if verbose:
        print(f"  Modell-Fit: Restfehler Median {fit.residual_mm:.2f} mm "
              f"(p90 {fit.residual_p90_mm:.2f}) auf {fit.n_used:,} Gesichtspunkten")
        print(f"  oben aus {up_src} (Abweichung zur Traegheitsachse {disagreement_up:.1f} Grad)")
        print(f"  Mittelebene x={x_sym:.1f} mm (Spiegeluebereinstimmung {100*sym_quote:.0f} %)")
        print(f"  Blickrichtung {yaw:.1f} Grad, Kopfmitte {np.round(centre, 2)}, Massstab {scale:.3f}")
    return fit


def estimate_frame(v: np.ndarray, f: np.ndarray, verbose: bool = False) -> ModelFit:
    """Bestimmt oben, vorn, Kopfmitte und Massstab -- und misst die Guete."""
    return fit_model(v, f, verbose=verbose)


def up_check(v: np.ndarray, fit: ModelFit, winkel: tuple = (8.0, 16.0, 24.0),
             n_pkt: int = 4000) -> tuple[float, float]:
    """Prueft die Hochachse dort, wo es zaehlt: im Optimum des Modell-Fits.

    Die Traegheitsachse taugt fuer einen Kopf nicht als zweite Schaetzung --
    ein Kopf ist fast so breit wie hoch (auf unserem Netz 220 mm zu 213 mm),
    die drei Hauptachsen liegen deshalb eng beieinander und tauschen schon
    bei kleinen Formaenderungen die Plaetze. Gemessen: 78 Grad Abweichung zur
    echten Hochachse.

    Stattdessen wird die gefundene Hochachse geneigt und nachgesehen, ob der
    Modell-Fit dabei schlechter wird. Liegt sie im Optimum, ist sie bestaetigt.

    Rueckgabe: (Winkel der besten Neigung in Grad, Verbesserung des
    Restfehlers in mm). Beides klein = Hochachse sitzt.
    """
    v = np.asarray(v, dtype=float)
    P = v[::max(1, len(v) // n_pkt)]
    R0 = fit.frame.R
    up0 = R0[:, 1]
    front0 = R0[:, 2]
    c, s0 = fit.frame.center, fit.frame.scale

    def fehler(up_neu: np.ndarray) -> float:
        R = _rotation_from_axes(np.cross(up_neu, front0), up_neu, front0)
        m = _face_mask(P, R, c, s0)
        if m.sum() < 100:
            return 1e9
        d = (P[m] - c) @ R
        rn = np.linalg.norm(d, axis=1)
        return float(np.median(np.abs(rn - s0 * head_radius(_norm(d)))))

    basis = fehler(up0)
    # zwei zueinander senkrechte Kipprichtungen in der Ebene senkrecht zu up0
    k1 = _norm(np.cross(up0, front0))
    k2 = _norm(np.cross(up0, k1))
    best = (0.0, basis)
    for w in winkel:
        for achse in (k1, -k1, k2, -k2):
            up_n = _norm(up0 * np.cos(np.radians(w)) + achse * np.sin(np.radians(w)))
            e = fehler(up_n)
            if e < best[1] - 1e-9:
                best = (w, e)
    return best[0], float(basis - best[1])


def frame_report(fit: ModelFit, v: np.ndarray, f: np.ndarray) -> dict:
    """Prueft die Schaetzungen gegeneinander und meldet Abweichungen.

    Ein Rahmen, der nur aus einer Quelle stammt, kann still falsch liegen.
    Hier wird nachgerechnet, was unabhaengig bestimmt werden kann:

      * die Hochachse gegen den Modell-Fit (Traegheit taugt nicht, s. ``up_check``),
      * die Blickrichtung gegen den gemessenen Nasenueberstand,
      * die Mittelebene gegen die Spiegelsymmetrie.

    ``warnung`` ist genau dann gesetzt, wenn eine Gegenprobe mehr als 15 Grad
    abweicht oder die Hochachse erkennbar nicht im Optimum liegt.
    """
    v = np.asarray(v, dtype=float)
    up_fit = fit.frame.R[:, 1]
    up_plane, thickness = base_plane_up(v)
    ang_plane = float(np.degrees(np.arccos(np.clip(float(up_fit @ up_plane), -1, 1))))

    front_fit = fit.frame.R[:, 2]
    up_fit_n = _norm(up_fit)
    e1 = _norm(np.cross(up_fit_n, [0.0, 0.0, 1.0])) if abs(up_fit_n[2]) < 0.9 else np.array([1.0, 0, 0])
    e2 = np.cross(up_fit_n, e1)
    a_meas, over_mm = measure_front_overhang(v, up_fit_n)
    fr_meas = np.cos(np.radians(a_meas)) * e1 + np.sin(np.radians(a_meas)) * e2
    ang_front = float(np.degrees(np.arccos(np.clip(float(front_fit @ fr_meas), -1, 1))))

    up_abw, up_gewinn = up_check(v, fit)
    return {
        "hochachse_vs_schnittflaeche_grad": ang_plane,
        "schnittflaeche_dicke_mm": thickness,
        "hochachse_neigung_bester_grad": up_abw,
        "hochachse_verbesserung_mm": up_gewinn,
        "blickrichtung_vs_nasenueberstand_grad": ang_front,
        "nasenueberstand_mm": over_mm,
        "restfehler_median_mm": fit.residual_mm,
        "warnung": bool(ang_front > 15.0 or up_abw > 8.0),
    }


# ------------------------------------------------------------- Landmarken
def landmark_positions(frame: Frame) -> dict[str, np.ndarray]:
    """Gesichtsmerkmale im Netz-Rahmen, aus dem angepassten Modell.

    Jedes Merkmal ist eine Richtung im Modell (wohin die Nase zeigt) mal dem
    Modellradius in dieser Richtung -- also der Punkt auf der Modelloberflaeche.
    """
    out = {}
    for name, d in (("nase", DIR_NOSE), ("kinn", DIR_CHIN), ("mund", DIR_MOUTH),
                    ("auge_l", DIR_EYE_L), ("auge_r", DIR_EYE_R),
                    ("ohr_l", DIR_EAR_L), ("ohr_r", DIR_EAR_R)):
        dn = _norm(np.asarray(d, dtype=float))
        r = float(head_radius(dn))
        out[name] = frame.to_world(r * dn)
    out["scheitel"] = frame.to_world(np.array([0.0, RY, 0.0]))
    return out


# ---------------------------------------------------------------- Skelett
@dataclass
class Joint:
    name: str
    parent: str | None
    position: np.ndarray          # im Ruhezustand (Welt-/Netz-Rahmen)
    weight_target: str = "auto"   # wie die Hautgewichte entstehen


@dataclass
class Skeleton:
    joints: list[Joint] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        return [j.name for j in self.joints]

    def index(self, name: str) -> int:
        return self.names.index(name)

    def parent_index(self, i: int) -> int:
        p = self.joints[i].parent
        return -1 if p is None else self.index(p)

    def positions(self) -> np.ndarray:
        return np.stack([j.position for j in self.joints])


def build_skeleton(lm: dict[str, np.ndarray], frame: Frame,
                   v: np.ndarray | None = None) -> Skeleton:
    """Baut die Gelenkhierarchie aus den Gesichtsmerkmalen.

    Die Namen sind absichtlich die von VRM (hips, spine, chest, neck, head,
    leftEye, rightEye), damit das Skelett spaater unmittelbar in eine VRM-
    Datei wandern kann. Der Kiefer (jaw) ist in VRM kein Pflichtknochen,
    wird aber von jedem Animationsprogramm verstanden.

    Anatomie, die hier eingebaut ist:
      * Die Halswirbelsaeule liegt **hinten**, nicht in der Kopfmitte -- die
        Gelenke neck/head sitzen deshalb auf einer Achse, die um ein Drittel
        des Kopfradius nach hinten verschoben ist. Wer den Kopf in der Mitte
        anhaengt, bekommt beim Nicken ein Schaukeln statt eines Drehens.
      * Das Kopf-Gelenk (Atlas) liegt auf Hoehe des Kiefergelenks, nicht in
        der Kopfmitte -- dort sitzt das Drehgelenk des Schaedels.
      * Die Augen sitzen als Gelenke dort, wo die Augapfelmitte laege: etwas
        hinter der Oberflaeche. Sie tragen kein Hautgewicht (siehe
        ``skin_weights``), weil der Scan keine Augaepfel enthaelt.
    """
    nase, kinn = lm["nase"], lm["kinn"]
    auge_l, auge_r = lm["auge_l"], lm["auge_r"]
    ohr_l, ohr_r = lm["ohr_l"], lm["ohr_r"]
    scheitel = lm["scheitel"]

    up = frame.R[:, 1]
    front = frame.R[:, 2]
    right = frame.R[:, 0]

    # Halsachse: senkrecht, aber ein Drittel des Kopfradius nach hinten
    radius = 0.5 * float(np.linalg.norm(ohr_l - ohr_r))
    achse_z = -0.33 * radius

    def auf_achse(y: float, z: float | None = None) -> np.ndarray:
        """Punkt auf der Halsachse: Hoehe y, Versatz z nach vorn (Modell-Mass).

        Die seitliche Lage ist immer die Mittelebene -- die Wirbelsaeule
        laeuft in der Mitte, nicht irgendwo daneben.
        """
        return frame.center + frame.R @ np.array(
            [x_mitte - float(frame.center @ frame.R[:, 0]),
             y - float(frame.center @ up),
             achse_z if z is None else z])

    y_kinn = float(kinn @ up)
    y_scheitel = float(scheitel @ up)
    y_ohr = 0.5 * float((ohr_l + ohr_r) @ up)      # Gehoergang: das Ohr sitzt dort
    kopf_laenge = y_scheitel - y_kinn

    # Der Atlas (der erste Halswirbel, um den der Kopf sich dreht) liegt auf
    # der Hoehe des Kieferwinkels -- knapp ein Drittel der Kopflaenge ueber
    # dem Kinn. Wer ihn in die Kopfmitte legt, bekommt beim Nicken ein
    # Schaukeln statt einer Drehung.
    y_atlas = y_kinn + 0.28 * kopf_laenge
    y_neck = y_kinn - 0.16 * kopf_laenge
    # Das Kiefergelenk sitzt unmittelbar VOR dem Gehoergang, nicht am
    # Kieferwinkel unten: dort, wo der Unterkiefer am Schaedel haengt.
    y_jaw = y_ohr - 0.08 * kopf_laenge
    # Bei einer BUESTE gibt es keinen Rumpf. Die VRM-Kette (hips, spine,
    # chest) muss trotzdem vorhanden sein -- sie traegt aber keine Haut.
    # Darum werden sie eng gestaffelt statt ueber einen halben Meter
    # auseinandergezogen; das haelt die Datei klein und die Hierarchie lesbar.
    y_chest = y_neck - 0.14 * kopf_laenge
    y_spine = y_chest - 0.14 * kopf_laenge
    y_hips = y_spine - 0.16 * kopf_laenge

    # Alle Gelenke der Wirbelsaeule liegen auf der Mittelebene
    x_mitte = float(frame.center @ frame.R[:, 0])

    # LINKS UND RECHTS -- hier steckt eine Falle, die man spaeter leicht
    # "verbessert" und dabei kaputt macht. VRM benennt die Seiten aus Sicht
    # des AVATARS: die Spezifikation sagt "Yaw: Z -> X direction => Left",
    # die linke Seite des Avatars ist also +X. Unser Netz-Rahmen ist ein
    # Rechtssystem mit y oben und z vorn (die Blickrichtung), folglich ist
    # +x die linke Seite des Kopfes. Die Richtungen in ``headmesh`` sind
    # dagegen aus Sicht des BETRACHTERS benannt -- sein "linkes" Auge liegt
    # bei -x. Wer die Namen einfach uebernimmt, baut ein Skelett mit
    # vertauschten Augen: der Avatar schaut dann beim Blick nach links nach
    # rechts. Deshalb wird hier nach der POSITION zugeordnet, nicht nach dem
    # Namen, den headmesh dem Merkmal gegeben hat.
    def auge_auf(richtung_x: float) -> np.ndarray:
        """Augenmittelpunkt auf der Seite mit dem Vorzeichen +1 (links)."""
        p = auge_l if auge_l[0] * richtung_x > 0 else auge_r
        return p - front * 0.18 * radius

    knochen = [
        Joint("hips", None, auf_achse(y_hips)),
        Joint("spine", "hips", auf_achse(y_spine)),
        Joint("chest", "spine", auf_achse(y_chest)),
        Joint("neck", "chest", auf_achse(y_neck)),
        Joint("head", "neck", auf_achse(y_atlas)),
        Joint("jaw", "head", auf_achse(y_jaw, achse_z + 0.45 * radius)),
        Joint("leftEye", "head", auge_auf(+1.0)),
        Joint("rightEye", "head", auge_auf(-1.0)),
    ]
    return Skeleton(knochen)


def skeleton_to_world(sk: Skeleton) -> tuple[list[str], list[int], np.ndarray]:
    """(Namen, Elternindex je Gelenk, Ruhepositionen) -- fuer Exporte."""
    return sk.names, [sk.parent_index(i) for i in range(len(sk.joints))], sk.positions()


# ------------------------------------------------------------ Hautgewichte
def _vertex_neighbours(f: np.ndarray, n_v: int) -> tuple[np.ndarray, np.ndarray]:
    """Ungerichtete Kanten als (quelle, ziel) -- doppelt, je Richtung einmal."""
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]], axis=0)
    a = np.concatenate([e[:, 0], e[:, 1]])
    b = np.concatenate([e[:, 1], e[:, 0]])
    keep = a != b
    return a[keep], b[keep]


def blendshape_deltas(v: np.ndarray, frame: Frame,
                      amplitude_mm: float = 5.0) -> tuple[list[np.ndarray], list[str]]:
    """Mimik-Verschiebungen auf dem Netz: sechs Ausdruecke, ARKit-benenannt.

    Die Ausdrucksfelder des 3D-Morph-Modells sind ANALYTISCH -- Gausssche
    Glocken im Modell-Rahmen, keine gespeicherten Zielnetze. Das ist hier
    ein Gluecksfall: damit lassen sie sich fuer jeden Punkt des Scans
    unmittelbar auswerten, ohne Korrespondenzsuche und ohne dass Modell und
    Scan dieselbe Punktzahl haben muessten. Man rechnet den Scan-Punkt in
    den Modell-Rahmen (dafuer war der ganze Aufwand mit dem Kopf-Rahmen),
    wertet das Feld aus und rechnet die Verschiebung zurueck.

    Die sechs Namen sind bewusst die von ARKit, weil Blender, Unity, Godot
    und jede VTuber-App genau diese Bezeichnungen erwarten -- ein Regler
    namens ``jawOpen`` wird von Werkzeugen erkannt, einer namens
    ``kiefer_auf`` nicht.

    Rueckgabe: (Liste von ``(n_punkte, 3)``-Verschiebungen in mm, Namen).

    **Was hier fehlt, sei ausdruecklich gesagt:** ARKit kennt 52 Formen.
    Wirklich liefern kann dieses Modul nur die sechs, zu denen das Modell
    eine Ausdrucksrichtung besitzt. Die restlichen 46 aus den sechs
    "abzuleiten" (etwa ``mouthSmileLeft`` durch Halbieren von
    ``mouthSmile``) waere erfunden -- die linke und die rechte
    Gesichtshaelfte laecheln bei echten Menschen nicht gleich stark, und
    die Pipeline wuerde so tun, als wuesste sie das. 52 Formen brauchen ein
    3DMM mit 52 Ausdrucksbasen; das ist eine Frage des Modells, nicht des
    Exports. Die Struktur hier nimmt sie auf, sobald sie da sind.
    """
    pm = frame.to_model(np.asarray(v, dtype=np.float64))
    x, y, z = pm[:, 0], pm[:, 1], pm[:, 2]
    vorn = (z > 0).astype(float)

    def glocke(cx: float, cy: float, sx: float, sy: float) -> np.ndarray:
        return np.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2)) * vorn

    felder = []
    # Kiefer auf: die untere Gesichtshaelfte wandert nach unten und etwas
    # zurueck -- so dreht ein Kiefer sich wirklich, statt zu sinken.
    w = np.clip(-(y - 10.0) / 90.0, 0.0, 1.0) * vorn
    felder.append(np.stack([np.zeros_like(x), -w, -0.35 * w], axis=1))
    # Lachen: die Mundwinkel nach aussen und oben.
    wl = glocke(-30.0, -40.0, 22.0, 18.0)
    wr = glocke(30.0, -40.0, 22.0, 18.0)
    felder.append(np.stack([(wr - wl) * 0.9, (wr + wl) * 0.6,
                            np.zeros_like(x)], axis=1))
    # Lidschluss: oben und unten zur Lidachse hin, nicht nur von oben.
    w = glocke(0.0, 12.0, 60.0, 14.0)
    felder.append(np.stack([np.zeros_like(x), -w * np.sign(y - 12.0) * 0.8,
                            np.zeros_like(x)], axis=1))
    # Brauen: innen hoch (Sorge) und runter (Aerger) -- getrennte Regler,
    # weil sie in ARKit getrennt sind und ein gemeinsamer Regler beide
    # Richtungen zugleich bedienen muesste.
    w = glocke(0.0, 34.0, 45.0, 12.0)
    felder.append(np.stack([np.zeros_like(x), w, 0.2 * w], axis=1))
    felder.append(np.stack([np.zeros_like(x), -0.7 * w, np.zeros_like(x)], axis=1))
    # Spitzmund: Lippen nach vorn und zur Mitte hin.
    w = glocke(0.0, -42.0, 26.0, 14.0)
    felder.append(np.stack([-x / 70.0 * w,
                            -np.clip(y + 42.0, -30.0, 30.0) / 30.0 * w * 0.4,
                            1.2 * w], axis=1))

    namen = ["jawOpen", "mouthSmile", "eyeBlink",
             "browInnerUp", "browDown", "mouthPucker"]
    deltas = []
    for feld in felder:
        d = feld / (np.abs(feld).max() + 1e-9) * amplitude_mm
        # Zurueck in den Netz-Rahmen: Drehung rueckwaerts, Massstab vor.
        deltas.append(frame.scale * (d @ frame.R.T))
    return deltas, namen


# ------------------------------------------------- VRM: ganzes Skelett
# VRM 1.0 verlangt 15 Pflichtknochen -- auch Arme und Beine. Eine BUESTE
# hat die nicht, und trotzdem muss die Datei sie enthalten, sonst weist
# jeder VRM-1.0-Pruefer sie ab. Sie bekommen deshalb Knoten an
# anatomisch richtiger Stelle, aber KEIN Hautgewicht: dort ist kein Netz,
# also bewegen sie nichts. Der Avatar ist damit gueltig und benimmt sich
# wie eine Bueste -- die Arme bewegen sich, es sieht nur niemand.
#
# Die Masse sind Erwachsenenmasse in Millimetern, abgeleitet von der
# gemessenen Kopfhoehe, nicht feste Zahlen: wer den Scan eines Kindes
# einsetzt, bekommt ein kindlich proportioniertes Skelett.
VRM_PFLICHT = ("hips", "spine", "head",
               "leftUpperLeg", "leftLowerLeg", "leftFoot",
               "rightUpperLeg", "rightLowerLeg", "rightFoot",
               "leftUpperArm", "leftLowerArm", "leftHand",
               "rightUpperArm", "rightLowerArm", "rightHand")


def build_vrm_skeleton(sk: Skeleton, lm: dict, frame: Frame) -> Skeleton:
    """Ergänzt das Kopf-Skelett zu einem vollständigen VRM-Humanoiden.

    Die Kopf-Gelenke (Hals bis Augen) werden **übernommen**, nicht neu
    gerechnet -- sie sitzen bereits vermessen am richtigen Ort. Ergänzt wird
    der Rumpf darunter und die Gliedmaßen, in VRM-T-Pose: aufrecht, Blick
    nach +Z, Arme waagerecht seitlich (`VRMC_vrm-1.0/tpose.md`, Definition
    1.4), Schultern entspannt (1.5).

    Rueckgabe: ein ``Skeleton`` mit 23 Gelenken in Eltern-zuerst-Reihenfolge.
    """
    up = frame.R[:, 1]
    front = frame.R[:, 2]
    links = frame.R[:, 0] * (+1.0)        # +x = linke Seite des Avatars

    y_kopf = float(frame.center @ up)
    scheitel = lm["scheitel"]
    kinn = lm["kinn"]
    kopf_hoehe = float((scheitel - kinn) @ up)      # Kinn bis Scheitel
    # Erwachsene: die Kopfhoehe ist etwa ein Achtel der Koerpergroesse.
    # Erwachsenenproportionen, aus der gemessenen Kopfhoehe abgeleitet
    # (Kopfhoehe = Kinn bis Scheitel). Der Mensch ist rund 7,7 Kopfhoehen
    # gross; die Einzelmasse unten ergeben zusammen etwa diese Zahl.
    rumpf = 2.6 * kopf_hoehe                 # Kopfmitte -> Huefte
    halbe_schulter = 1.2 * kopf_hoehe
    oberarm = 1.3 * kopf_hoehe
    unterarm = 1.2 * kopf_hoehe
    oberschenkel = 2.25 * kopf_hoehe
    unterschenkel = 2.0 * kopf_hoehe
    fuss = 0.4 * kopf_hoehe

    def punkt(y: float, seit: float = 0.0, vor: float = 0.0) -> np.ndarray:
        """Punkt im Netz-Rahmen: Hoehe y, seitlich `seit`, nach vorn `vor`."""
        return frame.center + up * (y - y_kopf) + links * seit + front * vor

    i_neck = sk.index("neck")
    y_huefte = y_kopf - rumpf
    y_neck = float(sk.joints[i_neck].position @ up)
    # Der Rumpf teilt sich von der Huefte bis KNAPP UNTER den Hals auf.
    # Saesse upperChest genau auf Halshoehe, lagen zwei Gelenke am selben
    # Punkt -- das ist ungueltig und bringt manchen Normalisierer aus dem
    # Tritt, weil die Knochenlaenge null wird.
    y_rumpf_oben = y_huefte + 0.85 * (y_neck - y_huefte)
    y_reihe = np.linspace(y_huefte, y_rumpf_oben, 4)

    g = {j.name: j.position for j in sk.joints}
    neu = [
        Joint("hips", None, punkt(y_huefte)),
        Joint("spine", "hips", punkt(y_reihe[1])),
        Joint("chest", "spine", punkt(y_reihe[2])),
        Joint("upperChest", "chest", punkt(y_reihe[3])),
        Joint("neck", "upperChest", g["neck"]),
        Joint("head", "neck", g["head"]),
        Joint("jaw", "head", g["jaw"]),
        Joint("leftEye", "head", g["leftEye"]),
        Joint("rightEye", "head", g["rightEye"]),
    ]
    # Arme in T-Pose: waagerecht seitlich (tpose.md 1.4), Schultern
    # entspannt (1.5). Die Spec setzt `upperArm` an den ANSATZ des
    # Oberarms, `lowerArm` an den Ellbogen und `hand` ans Handgelenk --
    # nicht ans Ende des jeweiligen Knochens.
    y_schulter = float(y_reihe[3])
    for seite, vorz in (("left", +1.0), ("right", -1.0)):
        neu.append(Joint(seite + "Shoulder", "upperChest",
                         punkt(y_schulter, vorz * 0.45 * halbe_schulter)))
        neu.append(Joint(seite + "UpperArm", seite + "Shoulder",
                         punkt(y_schulter, vorz * halbe_schulter)))
        neu.append(Joint(seite + "LowerArm", seite + "UpperArm",
                         punkt(y_schulter, vorz * (halbe_schulter + oberarm))))
        neu.append(Joint(seite + "Hand", seite + "LowerArm",
                         punkt(y_schulter, vorz * (halbe_schulter + oberarm
                                                   + unterarm))))
    # Beine: `upperLeg` an die Leiste, `lowerLeg` ans Knie, `foot` an den
    # Knoechel (so will es die Spec). Der Boden liegt eine Fusshoehe
    # UNTERHALB des Knoechels -- das ist der Unterschied zwischen "Knochen
    # auf Y=0" und "Modell steht auf Y=0" (Definition 1.3).
    for seite, vorz in (("left", +1.0), ("right", -1.0)):
        seit = vorz * 0.35 * halbe_schulter
        neu.append(Joint(seite + "UpperLeg", "hips", punkt(y_huefte, seit)))
        neu.append(Joint(seite + "LowerLeg", seite + "UpperLeg",
                         punkt(y_huefte - oberschenkel, seit)))
        neu.append(Joint(seite + "Foot", seite + "LowerLeg",
                         punkt(y_huefte - oberschenkel - unterschenkel, seit,
                               0.35 * fuss)))

    return Skeleton(neu)


def boden_hoehe(sk: Skeleton, frame: Frame, lm: dict) -> float:
    """Verschiebung nach oben, damit die Fuesse auf Y=0 stehen.

    VRM verlangt, dass das Modell in Y=0 auf dem Boden steht
    (`tpose.md`, Definition 1.3) -- gemessen am AUSSEHEN des Netzes, nicht
    an den Knochen. Da eine Bueste keine Fuesse hat, ist die Aufstandsflaeche
    die Unterkante des Netzes. Rueckgabe in Millimetern.
    """
    up = frame.R[:, 1]
    knoechel = min(float(j.position @ up) for j in sk.joints
                   if j.name.endswith("Foot"))
    # Die SOHLE steht auf Y=0, nicht der Knoechel: eine Fusshoehe tiefer.
    fuss = 0.4 * float((lm["scheitel"] - lm["kinn"]) @ up)
    return fuss - knoechel


def skeleton_to_bvh(sk: Skeleton, frame: Frame, scale: float = 0.001) -> list[dict]:
    """Skelett in die Hierarchie uebersetzt, die ``export_more.write_bvh`` will.

    BVH traegt keine Einheit mit sich -- der Leser entscheidet. Wir
    schreiben **Meter** (docs/05, 6), deshalb ``scale=0.001`` bei Netzen in
    Millimetern. Die Versatze sind GEGENUEBER dem Elterngelenk zu rechnen,
    nicht absolut; das ist der haeufigste Fehler in selbstgebauten BVH-Dateien
    und faellt erst im Leser auf, weil dort alle Gelenke am falschen Ort
    haengen.

    Blattgelenke bekommen ein kurzes ``End Site`` in Blickrichtung. Ohne das
    zeigen sie im Leser als punktfoermige Gelenke ohne Achse -- man sieht
    nicht, wohin der Kiefer oder der Blick weist.
    """
    front = frame.R[:, 2]
    out = []
    for i, jn in enumerate(sk.joints):
        p = sk.parent_index(i)
        offset = jn.position - (sk.joints[p].position if p >= 0 else 0.0)
        kinder = [k for k in range(len(sk.joints)) if sk.parent_index(k) == i]
        if kinder:
            end = None
        else:
            laenge = 0.02 if jn.name == "jaw" else 0.01
            end = laenge * front
        kanaele = (["Xposition", "Yposition", "Zposition",
                    "Zrotation", "Xrotation", "Yrotation"] if p < 0
                   else ["Zrotation", "Xrotation", "Yrotation"])
        out.append(dict(name=jn.name, parent=None if p < 0 else p,
                        offset=np.asarray(offset) * scale,
                        channels=kanaele,
                        end=None if end is None else np.asarray(end) * scale))
    return out


def animation_values(sk: Skeleton, n_frames: int = 120, fps: float = 30.0,
                     amplitude: dict | None = None) -> np.ndarray:
    """Eine Bewegung zum Vorfuehren: Blick, Nicken, Kiefer, Augen.

    Kein kuestlerischer Entwurf, sondern eine Pruefbewegung, die jedes
    Gelenk einmal durch seinen Arbeitsbereich fuehrt -- damit man im
    Leser sofort sieht, ob das Skelett sitzt. Die Amplituden sind in Grad
    und bewegen sich in dem Bereich, den ein Kopf wirklich macht: 14 Grad
    beim Schuetteln sind eine deutliche, aber natuerliche Kopfbewegung.

    Die Vorstellung dahinter: jemand dreht den Kopf zur Seite (schuetteln),
    nickt dazu, neigt ihn ein wenig -- und spricht, waehrend die Augen
    fuer einen Moment an einer Stelle bleiben, statt starr mitzugehen
    (deshalb gegenlaeufig zur Kopfdrehung).

    Rueckgabe: ``(n_frames, n_kanaele)`` passend zur Gelenkreihenfolge.
    """
    amp = dict(neigen=4.0, nicken=7.0, schuetteln=14.0, kiefer=9.0, blick=12.0)
    if amplitude:
        amp.update(amplitude)
    n_k = 6 + 3 * (len(sk.joints) - 1)
    werte = np.zeros((n_frames, n_k))
    # Die Wurzel bleibt in der Ruhepose -- sie traegt nur die Position.
    werte[:, 0:3] = sk.joints[0].position * 0.001
    t = np.arange(n_frames) / float(fps)

    def kanal(i: int) -> int:
        return 6 + 3 * (i - 1)

    # Kanaele je Gelenk: Zrotation (neigen), Xrotation (nicken), Yrotation (schuetteln)
    kopf = sk.index("head")
    werte[:, kanal(kopf) + 0] = amp["neigen"] * np.sin(2 * np.pi * 0.17 * t)
    werte[:, kanal(kopf) + 1] = amp["nicken"] * np.sin(2 * np.pi * 0.5 * t + 0.8)
    werte[:, kanal(kopf) + 2] = amp["schuetteln"] * np.sin(2 * np.pi * 0.25 * t)
    # Der Kiefer schliesst nie ueber die Ruheposition hinaus: 1-cos bleibt >= 0.
    kiefer = sk.index("jaw")
    werte[:, kanal(kiefer) + 1] = amp["kiefer"] * (1.0 - np.cos(2 * np.pi * 0.7 * t)) / 2.0
    for nm in ("leftEye", "rightEye"):
        if nm in sk.names:
            i = sk.index(nm)
            werte[:, kanal(i) + 2] = -0.5 * amp["blick"] * np.sin(2 * np.pi * 0.25 * t)
            werte[:, kanal(i) + 1] = 0.3 * amp["blick"] * np.sin(2 * np.pi * 0.5 * t)
    return werte


def skin_weights(v: np.ndarray, f: np.ndarray, sk: Skeleton,
                 frame: Frame, smooth_iters: int = 40,
                 max_influences: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """Hautgewichte je Vertex: welche Gelenke bewegen ihn, und wie stark.

    Vorgehen in drei Schritten:

      1. **Rohentwurf aus der Geometrie.** Die Wirbelsaeulen-Gelenke
         (hips/spine/chest/neck/head) teilen sich den Koerper nach Hoehe auf,
         mit weichen Uebergangen. Der Kiefer bekommt seinen Anteil aus dem
         unteren Gesicht, begrenzt durch eine glatte Maske.
      2. **Glaetten ueber die Netz-Nachbarschaft.** Das ist der entscheidende
         Schritt: ein rein nach Hoehe gebautes Gewicht schneidet harte Kanten
         in die Oberflaeche, und ein Gewicht, das nur auf euklidischem Abstand
         beruht, "blutet" durch duenne Stellen (etwa vom Kiefer in den Hals).
         Die Glaettung laeuft entlang der echten Netzkanten, dadurch folgen
         die Uebergaenge der Oberflaeche statt der Luftlinie.
      3. **Auf die staerksten Einfluesse beschraenken** und normieren, damit
         die Summe je Vertex genau 1 ist -- das erwarten DAE, GLB und VRM.

    Die Augen bekommen bewusst kein Gewicht: der Scan enthaelt keine
    Augaepfel, die Augen sind nur aufgemalte Textur. Haenge Gewebe an die
    Augenknochen, verschiebt ein Blick die Augenpartie statt zu schauen. Die
    Gelenke existieren trotzdem -- fuer die Blicksteuerung (VRM LookAt), die
    die Knochen dreht, ohne die Haut mitzunehmen.
    """
    v = np.asarray(v, dtype=float)
    f = np.asarray(f, dtype=np.int64)
    names = sk.names
    up = frame.R[:, 1]
    front = frame.R[:, 2]

    h = v @ up                                  # Hoehe je Punkt
    y_neck = float(sk.joints[sk.index("neck")].position @ up)
    y_head = float(sk.joints[sk.index("head")].position @ up)
    y_kinn = float(landmark_positions(frame)["kinn"] @ up)
    y_chest = float(sk.joints[sk.index("chest")].position @ up)
    y_spine = float(sk.joints[sk.index("spine")].position @ up)
    y_hips = float(sk.joints[sk.index("hips")].position @ up)

    def rampe(y: np.ndarray, a: float, b: float) -> np.ndarray:
        """Weicher Uebergang von 0 (bei a) auf 1 (bei b), dazwischen glatt."""
        t = np.clip((y - a) / max(b - a, 1e-6), 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    # Anteile entlang der Kette: jedes Gelenk besitzt ein Hoehenfenster
    w_hips = 1.0 - rampe(h, y_hips, y_spine)
    w_spine = rampe(h, y_hips, y_spine) * (1.0 - rampe(h, y_spine, y_chest))
    w_chest = rampe(h, y_spine, y_chest) * (1.0 - rampe(h, y_chest, y_neck))
    w_neck = rampe(h, y_chest, y_neck) * (1.0 - rampe(h, y_neck, y_kinn))
    # Der Kopf muss ab dem KINN voll tragen, nicht erst ab dem Atlas. Sonst
    # bekommt das Kinn nur einen Bruchteil und der Unterkiefer hat hinterher
    # zu wenig Gewicht, um sich zu bewegen. Unterhalb des Kinns sitzt die
    # Kehle -- dorthin gehoert der weiche Uebergang zum Hals.
    w_head = rampe(h, y_neck, y_kinn)

    # Kiefer: der Unterkiefer, vom Kinn bis knapp ueber den Mund, seitlich bis
    # zu den Kieferwinkeln und nach hinten nur bis vor die Ohren.
    y_nase = float(landmark_positions(frame)["nase"] @ up)
    y_mund = float(landmark_positions(frame)["mund"] @ up)
    seit = np.abs((v - frame.center) @ frame.R[:, 0])
    breite = 0.5 * float(np.linalg.norm(landmark_positions(frame)["ohr_l"]
                                        - landmark_positions(frame)["ohr_r"]))
    tiefe = (v - frame.center) @ front
    maske_kiefer = (
        (1.0 - rampe(h, y_kinn - 0.18 * (y_nase - y_kinn), y_mund + 0.22 * (y_nase - y_kinn)))
        * (1.0 - rampe(seit, 0.62 * breite, 0.98 * breite))
        * rampe(tiefe, -0.10 * breite, 0.35 * breite)
    )
    w_jaw = w_head * np.clip(maske_kiefer, 0.0, 1.0)
    w_head = w_head * (1.0 - np.clip(maske_kiefer, 0.0, 1.0))

    W = np.zeros((len(v), len(names)))
    for name, w in (("hips", w_hips), ("spine", w_spine), ("chest", w_chest),
                    ("neck", w_neck), ("head", w_head), ("jaw", w_jaw)):
        W[:, sk.index(name)] = w

    # --- Glaetten entlang der Netzkanten ---------------------------------
    if smooth_iters > 0:
        a, b = _vertex_neighbours(f, len(v))
        deg = np.bincount(a, minlength=len(v)).astype(float)
        for _ in range(smooth_iters):
            s = np.zeros_like(W)
            for k in range(W.shape[1]):
                s[:, k] = np.bincount(a, weights=W[b, k], minlength=len(v))
            W = (W + s) / (1.0 + deg[:, None])

    # --- beschraenken und normieren --------------------------------------
    n = len(v)
    idx = np.zeros((n, max_influences), dtype=np.int64)
    wts = np.zeros((n, max_influences), dtype=np.float64)
    for k in range(max_influences):
        best = np.argmax(W, axis=1)
        idx[:, k] = best
        wts[:, k] = W[np.arange(n), best]
        W[np.arange(n), best] = -1.0            # diesen Einfluss verbrauchen
    wts = np.clip(wts, 0.0, None)
    s = wts.sum(axis=1)
    s[s < 1e-8] = 1.0
    wts = wts / s[:, None]
    return idx, wts

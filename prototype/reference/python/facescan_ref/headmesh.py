"""Synthetische Ground Truth mit echter Oberflaeche (M1).

M0 hatte nur Punkte. M1 braucht ein geschlossenes Mesh, weil erst daraus
wird, was der Nutzer am Ende exportiert: eine texturierte Oberflaeche.

Aufbau (alles deterministisch, kein Zufall, kein Netz):

    Kopf   = sternfoermige Flaeche  r = f(Richtung)
             + Details, die ein 3D-Modell NICHT ausdruecken kann
               (Ohren, Muttermal, feine Falten) -- genau dafuer braucht es
               die Multi-View-Fusion und nicht nur den Modell-Fit
    Haare  = Schale um den Schaedel, wellig, mit Haaransatz
             (Level 1: Volumen, keine Straehnen -- so in docs/03 beschlossen)

Warum "sternfoermig"? Weil dann "innen/aussen" analytisch und exakt
beantwortbar ist (|p| gegen r(p/|p|)). Damit sind IoU und Volumenfehler
ohne aufwendige Punkt-im-Mesh-Tests exakt berechenbar -- die Ground Truth
kann sich nicht selbst widersprechen.

Einheiten: Millimeter. Farben: 0..255 (Albedo, ohne Beleuchtung).
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------- Kopf ----

# Grundform: Ellipsoid (Halbachsen in mm)
RX, RY, RZ = 71.0, 96.0, 89.0

# Richtungen der Details (Einheitsvektoren, "Blickrichtung" des Kopfes = +z)
DIR_NOSE = np.array([0.0, -0.06, 1.0])
DIR_CHIN = np.array([0.0, -0.80, 0.60])
DIR_EAR_L = np.array([-0.97, -0.02, -0.10])
DIR_EAR_R = np.array([0.97, -0.02, -0.10])
DIR_MOLE = np.array([0.42, -0.18, 0.88])
DIR_EYE_L = np.array([-0.33, 0.10, 0.94])
DIR_EYE_R = np.array([0.33, 0.10, 0.94])
DIR_BROW_L = np.array([-0.31, 0.30, 0.90])
DIR_BROW_R = np.array([0.31, 0.30, 0.90])
DIR_MOUTH = np.array([0.0, -0.45, 0.89])


def _norm(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def _bump(d: np.ndarray, axis: np.ndarray, width: float, amp: float) -> np.ndarray:
    """Glatte radiale Beule entlang einer Richtung (Kosinus-Falloff)."""
    axis = _norm(np.asarray(axis, dtype=float).reshape(1, 3))[0]
    c = np.clip(d @ axis, -1.0, 1.0)
    ang = np.arccos(c)
    return amp * np.exp(-((ang / width) ** 2))


def head_radius(d: np.ndarray) -> np.ndarray:
    """Radius der Kopfoberflaeche in Richtung d (d muss normiert sein).

    Enthaelt absichtlich Details unterhalb der Modellbasis:
      * Falten mit 0,6 mm Amplitude (Pruefstein fuer die Fusion)
      * ein 2 mm Muttermal
      * Ohren als Beulen
    Ein 3DMM-Fit kann das nicht reproduzieren -- die Fusion schon. Genau
    dieser Unterschied ist die Begruendung fuer die MVS-Stufe (docs/03).
    """
    d = _norm(np.asarray(d, dtype=float))
    # Ellipsoid
    r = 1.0 / np.sqrt((d[..., 0] / RX) ** 2 + (d[..., 1] / RY) ** 2 + (d[..., 2] / RZ) ** 2)

    # Kiefer / Kinn: nach unten schmaler werden
    below = np.clip(-d[..., 1], 0.0, 1.0)
    r = r * (1.0 - 0.20 * below ** 1.6)

    # Hinterkopf etwas voller, Stirn etwas flacher
    r = r * (1.0 - 0.05 * np.clip(d[..., 2], 0.0, 1.0))
    r = r * (1.0 + 0.04 * np.clip(-d[..., 2], 0.0, 1.0))

    r = r + _bump(d, DIR_NOSE, 0.16, 15.0)      # Nase
    r = r + _bump(d, DIR_CHIN, 0.30, 6.0)       # Kinn
    r = r + _bump(d, DIR_EAR_L, 0.15, 13.0)     # Ohren (nicht im Modell!)
    r = r + _bump(d, DIR_EAR_R, 0.15, 13.0)
    r = r + _bump(d, DIR_MOLE, 0.035, 2.2)      # Muttermal, 2 mm

    # Stirnfalten: 0,6 mm Amplitude, drei Streifen
    forehead = np.clip(d[..., 1], 0.0, 1.0) ** 2 * np.clip(d[..., 2], 0.0, 1.0)
    r = r + 0.6 * np.sin(26.0 * d[..., 1] - 1.2) * forehead

    # Asymmetrie (jeder Mensch hat eine) -- 1,5 mm
    r = r + 1.5 * np.sin(3.0 * np.arctan2(d[..., 0], d[..., 2]) + 0.7) * np.clip(
        d[..., 2], 0.0, 1.0) ** 2
    return r


# ---------------------------------------------------------------- Haar ----

HAIR_BASE = 21.0          # Grunddicke in mm
NECK_CUT = -0.62          # unterhalb dieser Hoehe sitzen keine Haare


def hair_region(d: np.ndarray) -> np.ndarray:
    """Wo sitzen Haare? True/False je Richtung.

    Ausgespart werden das Gesichtsoval und der Hals. Der Haaransatz ist
    absichtlich gewellt -- eine gerade Kante waere unrealistisch und wuerde
    den Test zu einfach machen.
    """
    d = _norm(np.asarray(d, dtype=float))
    y = d[..., 1]
    x = d[..., 0]
    z = d[..., 2]

    # Gesichtsoval (kein Haar)
    face = (z > 0.30) & (np.abs(x) < 0.60) & (y > -0.55) & (y < 0.40)
    # gewellter Haaransatz: die Grenze wandert mit der Position
    wobble = 0.06 * np.sin(6.0 * np.arctan2(x, z)) + 0.04 * np.sin(9.0 * x + 1.0)
    face = face | ((z > 0.30 - wobble) & (y < 0.40 + wobble) & (np.abs(x) < 0.60 + wobble))

    neck = y < NECK_CUT
    return (~face) & (~neck)


def hair_thickness(d: np.ndarray) -> np.ndarray:
    """Haardicke je Richtung (mm) -- wellig, deterministisch."""
    d = _norm(np.asarray(d, dtype=float))
    a = np.arctan2(d[..., 0], d[..., 2])
    y = d[..., 1]
    t = (HAIR_BASE
         + 9.0 * np.sin(3.1 * a + 1.7)
         + 6.0 * np.sin(4.7 * y * 3.0 + 0.4)
         + 4.0 * np.sin(7.3 * a * 0.5 - 2.1) * np.clip(y, 0.0, 1.0))
    # oben voller, am Ansatz duenner
    t = t * (0.75 + 0.45 * np.clip(y + 0.4, 0.0, 1.0))
    return np.maximum(t, 3.0)


def hair_outer(d: np.ndarray) -> np.ndarray:
    """Aussenradius der Haare (nur im Haarbereich gueltig)."""
    return head_radius(d) + hair_thickness(d)


def inside_head(points: np.ndarray) -> np.ndarray:
    """Exakter Innen-Test des Kopfes (sternfoermig -> analytisch)."""
    p = np.asarray(points, dtype=float)
    n = np.linalg.norm(p, axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = p / np.maximum(n, 1e-12)[..., None]
    return n <= head_radius(d)


def in_hair_volume(points: np.ndarray) -> np.ndarray:
    """Exakter Test: liegt der Punkt im Haar-VOLUMEN (GT)?

    Haarvolumen = zwischen Kopfoberflaeche und Haaraussenseite, im Haarbereich.
    """
    p = np.asarray(points, dtype=float)
    n = np.linalg.norm(p, axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = p / np.maximum(n, 1e-12)[..., None]
    reg = hair_region(d)
    inner = head_radius(d)
    outer = inner + hair_thickness(d)
    return reg & (n > inner) & (n <= outer)


def in_hair_or_head(points: np.ndarray) -> np.ndarray:
    """Alles, was der Scan als Silhouette sieht (Kopf ODER Haar)."""
    p = np.asarray(points, dtype=float)
    n = np.linalg.norm(p, axis=-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = p / np.maximum(n, 1e-12)[..., None]
    reg = hair_region(d)
    outer = np.where(reg, head_radius(d) + hair_thickness(d), head_radius(d))
    return n <= outer


# ------------------------------------------------------------ Vernetzung ---

def uv_sphere(n_lat: int, n_lon: int):
    """Kugelnetz als Dreiecksliste.

    Liefert (richtungen (N,3), dreiecke (M,3), uv (N,2)). Die Pole werden
    als Dreiecke (nicht als Vierecke) behandelt.
    """
    theta = np.linspace(0.0, np.pi, n_lat + 1)      # 0 = Nordpol
    phi = np.linspace(-np.pi, np.pi, n_lon + 1)
    tt, pp = np.meshgrid(theta, phi, indexing="ij")

    dx = np.sin(tt) * np.sin(pp)
    dy = np.cos(tt)
    dz = np.sin(tt) * np.cos(pp)
    dirs = np.stack([dx, dy, dz], axis=-1).reshape(-1, 3)
    uv = np.stack([(pp + np.pi) / (2 * np.pi), tt / np.pi], axis=-1).reshape(-1, 2)

    idx = np.arange((n_lat + 1) * (n_lon + 1)).reshape(n_lat + 1, n_lon + 1)
    faces = []
    for i in range(n_lat):
        for j in range(n_lon):
            a, b = idx[i, j], idx[i, j + 1]
            c, d = idx[i + 1, j], idx[i + 1, j + 1]
            if i == 0:                       # Nordpol: nur ein Dreieck
                faces.append((c, a, d))
            elif i == n_lat - 1:             # Suedpol
                faces.append((a, b, d))
            else:
                faces.append((a, c, d))
                faces.append((a, d, b))
    return dirs, np.array(faces, dtype=np.int64), uv


def _surface_mesh(dirs: np.ndarray, faces: np.ndarray, radius_fn) -> np.ndarray:
    r = radius_fn(dirs)
    return dirs * r[:, None]


def head_mesh(n_lat: int = 96, n_lon: int = 144):
    """Kopf als (V, F, UV, Farben)."""
    dirs, faces, uv = uv_sphere(n_lat, n_lon)
    v = _surface_mesh(dirs, faces, head_radius)
    c = vertex_colors(dirs)
    return v, faces, uv, c


def hair_mesh(n_lat: int = 96, n_lon: int = 144):
    """AEUSSERE Haaroberflaeche (nur der behaarte Teil).

    Das ist die Flaeche, die die Kamera von den Haaren sieht. Sie ist am
    Haaransatz offen -- dort sieht man darunter die Haut, genau wie in echt.
    """
    dirs, faces, uv = uv_sphere(n_lat, n_lon)
    reg = hair_region(dirs)
    # Nur Dreiecke, deren Ecken alle im Haarbereich liegen
    keep = reg[faces].all(axis=1)
    faces = faces[keep]
    used = np.unique(faces)
    remap = -np.ones(len(dirs), dtype=np.int64)
    remap[used] = np.arange(len(used))
    v = _surface_mesh(dirs[used], None, hair_outer)
    c = hair_colors(dirs[used])
    return v, remap[faces], uv[used], c


# --------------------------------------------------------------- Farben ---

SKIN = np.array([206.0, 160.0, 133.0])
LIP = np.array([176.0, 96.0, 88.0])
EYE = np.array([70.0, 62.0, 60.0])
BROW = np.array([62.0, 45.0, 34.0])
MOLE = np.array([122.0, 78.0, 62.0])
HAIR_DARK = np.array([58.0, 41.0, 31.0])


def _mask(d: np.ndarray, axis: np.ndarray, width: float) -> np.ndarray:
    axis = _norm(np.asarray(axis, dtype=float).reshape(1, 3))[0]
    ang = np.arccos(np.clip(d @ axis, -1.0, 1.0))
    return np.clip(1.0 - (ang / width) ** 2, 0.0, 1.0)


def vertex_colors(dirs: np.ndarray) -> np.ndarray:
    """Albedo je Vertex (0..255). Rein analytisch -- keine Texturdatei."""
    d = _norm(dirs)
    col = np.tile(SKIN, (len(d), 1))

    # leichte Hautunruhe (Poren / Roetung), 3 Frequenzen, klein
    n = (np.sin(31.0 * d[:, 0]) * np.sin(27.0 * d[:, 1])
         + 0.6 * np.sin(63.0 * d[:, 2] + 1.3)
         + 0.4 * np.sin(89.0 * d[:, 0] - 0.7))
    col = col + 7.0 * n[:, None]

    def over(mask_w, axis, width, color):
        m = _mask(d, axis, width)[:, None]
        col[:] = col * (1 - m) + np.asarray(color, dtype=float) * m

    over(0, DIR_MOUTH, 0.16, LIP)
    over(0, DIR_EYE_L, 0.085, EYE)
    over(0, DIR_EYE_R, 0.085, EYE)
    over(0, DIR_BROW_L, 0.075, BROW)
    over(0, DIR_BROW_R, 0.075, BROW)
    over(0, DIR_MOLE, 0.030, MOLE)
    return np.clip(col, 0, 255).astype(np.uint8)


def hair_colors(dirs: np.ndarray) -> np.ndarray:
    d = _norm(dirs)
    shade = 1.0 + 0.18 * np.sin(11.0 * d[:, 0]) + 0.12 * np.sin(17.0 * d[:, 1] + 0.9)
    c = HAIR_DARK * shade[:, None]
    return np.clip(c, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- Kamera --

def orbit_poses(n_frames: int, radius: float = 520.0, yaw_deg: float = 72.0,
                pitch_deg: float = 8.0, jitter: float = 0.0, seed: int = 2026):
    """Kameraposen auf einem Bogen um den Kopf (wie beim Selbstscan).

    Liefert (R, t) mit Welt -> Kamera:  p_cam = R p + t
    """
    rng = np.random.default_rng(seed)
    poses = []
    for i in range(n_frames):
        u = -1.0 + 2.0 * (i / max(n_frames - 1, 1))
        yaw = np.radians(yaw_deg) * u
        pitch = np.radians(pitch_deg) * np.sin(1.7 * u)
        if jitter:
            yaw += np.radians(jitter) * rng.normal()
            pitch += np.radians(jitter) * rng.normal()

        # Kameraposition auf dem Bogen (Blickrichtung zeigt zum Ursprung)
        pos = np.array([
            radius * np.sin(yaw) * np.cos(pitch),
            radius * np.sin(pitch) + 12.0,
            radius * np.cos(yaw) * np.cos(pitch),
        ])
        # Kamera schaut auf den Kopf; "oben" ist +y.
        # Rechtshaendiger Kamerarahmen (x = rechts, y = oben, z = Blickrichtung),
        # damit p_cam = R p + t VOR der Kamera ein POSITIVES z hat.
        fwd = -pos / np.linalg.norm(pos)
        up = np.array([0.0, 1.0, 0.0])
        right = np.cross(up, fwd)                 # up x fwd = rechts
        right /= np.linalg.norm(right)
        true_up = np.cross(fwd, right)            # fwd x rechts = oben
        # Zeilen von R sind die Kameraachsen in Weltkoordinaten
        r = np.stack([right, true_up, fwd])
        t = -r @ pos
        poses.append((r, t))
    return poses

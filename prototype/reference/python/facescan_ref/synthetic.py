"""Synthetische Testdaten mit bekannter Ground Truth.

Warum synthetisch? Weil wir fuer M0 (Null Budget) ohne Studio-Scans und ohne
Referenzscanner objektiv messen muessen, ob die Mathematik stimmt. Alles hier ist
deterministisch (Seed) und wird zusaetzlich als Gold-Fixture fuer die
Kotlin-Unit-Tests ausgegeben.

Einheiten: Millimeter. Koordinatensystem: x rechts, y oben, z zur Kamera hin
(OpenGL-Konvention, wie spaeter im Export).
"""
from __future__ import annotations
import numpy as np

from .math3d import make_intrinsics, project_points, rodrigues


# ---------------------------------------------------------------- Basis-Mesh
def make_base_mesh(n_points: int = 120) -> np.ndarray:
    """Kopfaehnliche Punktewolke: Ellipsoid + Nase + Kinnverjuengung.

    Deterministisch (Fibonacci-Kugel), damit Tests reproduzierbar sind.
    """
    idx = np.arange(n_points) + 0.5
    phi = np.arccos(1.0 - 2.0 * idx / n_points)
    theta = np.pi * (1.0 + 5.0 ** 0.5) * idx
    x = np.cos(theta) * np.sin(phi)
    y = np.cos(phi)
    z = np.sin(theta) * np.sin(phi)

    # Ellipsoid (Kopf-Masse in mm): Breite 72, Hoehe 95, Tiefe 85
    p = np.stack([x * 72.0, y * 95.0, z * 85.0], axis=1)

    # Gesicht nach vorn (z > 0) formen: Nase, Kinn, flacherer Hinterkopf
    front = np.clip(p[:, 2] / 85.0, 0.0, 1.0) ** 2
    nose = np.exp(-(((p[:, 0]) ** 2) / 300.0 + ((p[:, 1] - 5.0) ** 2) / 500.0))
    p[:, 2] += 14.0 * nose * front                       # Nase
    p[:, 1] -= 18.0 * np.clip(-p[:, 1] / 95.0, 0.0, 1.0) ** 2 * front   # Kinn
    p[:, 2] *= np.where(p[:, 2] < 0.0, 0.86, 1.0)        # Hinterkopf abflachen
    return p - p.mean(axis=0)


# ------------------------------------------------------------ Identitaet/PCA
def _smooth_random_fields(n_points: int, n_samples: int, rng: np.random.Generator,
                          n_modes: int = 12) -> np.ndarray:
    """Niedrigfrequente Zufallsfelder als 'verschiedene Menschen'."""
    idx = np.arange(n_points)
    basis = []
    for k in range(n_modes):
        a = rng.uniform(-np.pi, np.pi)
        b = rng.uniform(-np.pi, np.pi)
        basis.append(np.sin((k + 1) * idx / n_points * np.pi + a) * np.cos(b + idx * 0.05))
    basis = np.stack(basis)                               # (n_modes, N)
    coeff = rng.normal(size=(n_samples, n_modes))
    return coeff @ basis                                  # (n_samples, N)


def make_identity_basis(base: np.ndarray, n_basis: int = 8, n_samples: int = 60,
                        seed: int = 1337) -> tuple[np.ndarray, np.ndarray]:
    """PCA-Basis fuer Identitaet. Rueckgabe: (A_id (3N,K), sigma (K,))."""
    rng = np.random.default_rng(seed)
    n = base.shape[0]
    fields = _smooth_random_fields(n, n_samples, rng)     # (S,N)
    normals = base / (np.linalg.norm(base, axis=1, keepdims=True) + 1e-9)
    devs = np.einsum("sn,nd->snd", fields, normals) * 6.0   # 6 mm Amplitude
    devs = devs.reshape(n_samples, -1)
    mean = devs.mean(axis=0)
    centered = devs - mean
    u, s, vt = np.linalg.svd(centered, full_matrices=False)
    sigma = s[:n_basis] / np.sqrt(n_samples)
    a = vt[:n_basis].T.copy()                             # (3N,K)
    # Normierung: Spalten = Einheitsvektoren, sigma traecht die Skala
    for k in range(a.shape[1]):
        nrm = np.linalg.norm(a[:, k])
        if nrm > 1e-12:
            a[:, k] /= nrm
    return a, sigma


# --------------------------------------------------------------- Ausdrucksbasis
def make_expression_basis(base: np.ndarray, amplitude_mm: float = 5.0) -> tuple[np.ndarray, list[str]]:
    """Sechs analytische Ausdrucksfelder (wie spaeter die ARKit-Blendshapes)."""
    x, y, z = base[:, 0], base[:, 1], base[:, 2]
    n = base.shape[0]
    fields = []

    def g(center, sigma, extra=None):
        d2 = ((x - center[0]) ** 2) / sigma[0] ** 2 + ((y - center[1]) ** 2) / sigma[1] ** 2
        w = np.exp(-d2) * (z > 0) if extra is None else np.exp(-d2) * extra
        return w

    # jawOpen: untere Gesichtshaelfte nach unten (Kieferrotation)
    w = np.clip(-(y - 10.0) / 90.0, 0.0, 1.0) * (z > 0)
    fields.append(np.stack([np.zeros(n), -w * 1.0, -w * 0.35], axis=1))

    # mouthSmile: Mundwinkel nach aussen/oben
    wl = g((-30.0, -40.0), (22.0, 18.0))
    wr = g((30.0, -40.0), (22.0, 18.0))
    fields.append(np.stack([(wr - wl) * 0.9, (wr + wl) * 0.6, np.zeros(n)], axis=1))

    # eyeBlink: Lider zur Augenlinie
    w = g((0.0, 12.0), (60.0, 14.0))
    fields.append(np.stack([np.zeros(n), -w * np.sign(y - 12.0) * 0.8, np.zeros(n)], axis=1))

    # browInnerUp / browDown (je eine Richtung, getrennt gefuehrt)
    w = g((0.0, 34.0), (45.0, 12.0))
    fields.append(np.stack([np.zeros(n), w * 1.0, w * 0.2], axis=1))
    fields.append(np.stack([np.zeros(n), -w * 0.7, np.zeros(n)], axis=1))

    # mouthPucker: Lippen nach vorn/innen
    w = g((0.0, -42.0), (26.0, 14.0))
    fields.append(np.stack([-x / 70.0 * w, -np.clip(y + 42.0, -30, 30) / 30.0 * w * 0.4, w * 1.2], axis=1))

    names = ["jawOpen", "mouthSmile", "eyeBlink", "browInnerUp", "browDown", "mouthPucker"]
    mats = []
    for f in fields:
        f = f - f.mean(axis=0) * 0.0
        m = np.abs(f).max()
        mats.append((f / (m + 1e-9) * amplitude_mm).reshape(-1))
    return np.stack(mats, axis=1), names


# --------------------------------------------------------------- Szenengenerator
def make_phone_intrinsics(width: int = 1080, height: int = 1920, fov_deg: float = 62.0):
    """Realistische Handy-Intrinsics (1080p, ~62 deg diagonal)."""
    f = 0.5 * np.hypot(width, height) / np.tan(np.radians(fov_deg) * 0.5)
    return make_intrinsics(f, f, width * 0.5, height * 0.5)


def generate_scene(n_frames: int = 8, n_points: int = 120, seed: int = 2026,
                   noise_px: float = 1.0, outlier_ratio: float = 0.05,
                   occlusion_ratio: float = 0.08) -> dict:
    """Erzeugt eine komplette Testszene mit Ground Truth."""
    rng = np.random.default_rng(seed)
    base = make_base_mesh(n_points)
    a_id, sigma_id = make_identity_basis(base, seed=1337)
    a_exp, exp_names = make_expression_basis(base)
    k_id, k_exp = a_id.shape[1], a_exp.shape[1]

    alpha_true = rng.normal(size=k_id) * 0.8                       # "der Mensch"
    k = make_phone_intrinsics()

    frames = []
    beta_true = []
    poses = []
    for f in range(n_frames):
        yaw = np.radians(np.linspace(-60, 60, n_frames)[f])
        pitch = np.radians(12.0 * np.sin(f * 1.1))
        roll = np.radians(6.0 * np.cos(f * 0.7))
        r = rodrigues(np.array([pitch, yaw, roll]))                 # Reihenfolge: x=pitch,y=yaw,z=roll
        dist = 520.0 + 40.0 * np.sin(f * 0.9)
        t = np.array([18.0 * np.sin(f * 0.5), 10.0 * np.cos(f * 0.4), dist])

        beta = np.abs(rng.normal(size=k_exp)) * np.array([0.35, 0.6, 0.5, 0.4, 0.2, 0.3])
        beta_true.append(beta)

        shape = (base.reshape(-1) + a_id @ alpha_true + a_exp @ beta).reshape(-1, 3)
        pts = project_points(k, r, t, shape)
        pts = pts + rng.normal(scale=noise_px, size=pts.shape)

        n_out = int(round(outlier_ratio * n_points))
        outliers = np.zeros(n_points)
        if n_out > 0:
            oi = rng.choice(n_points, n_out, replace=False)
            pts[oi] += rng.normal(scale=25.0, size=(n_out, 2))
            outliers[oi] = 1.0
        n_occ = int(round(occlusion_ratio * n_points))
        vis = np.ones(n_points)
        if n_occ > 0:
            oi = rng.choice(n_points, n_occ, replace=False)
            vis[oi] = 0.0

        frames.append({"K": k, "points2d": pts, "visibility": vis, "outliers": outliers,
                       "R": r, "t": t})
        poses.append((r, t))

    return {
        "base": base,
        "A_id": a_id,
        "sigma_id": sigma_id,
        "A_exp": a_exp,
        "exp_names": exp_names,
        "alpha_true": alpha_true,
        "beta_true": np.stack(beta_true),
        "K": k,
        "frames": frames,
    }

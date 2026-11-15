"""Kleine, vollstaendige 3D-Mathematik fuer den M0-Prototyp.

Referenzimplementierung (Python/NumPy). Die Kotlin-Klassen in
android/core/geometry/... sind 1:1-Ports dieser Datei.
"""
from __future__ import annotations
import numpy as np

EPS = 1e-12


def skew(v: np.ndarray) -> np.ndarray:
    """Skew-Matrix (Kreuzprodukt-Matrix) eines 3-Vektors."""
    x, y, z = v
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def rodrigues(omega: np.ndarray) -> np.ndarray:
    """Rotation aus dem Rotationsvektor (so(3) -> SO(3))."""
    theta = float(np.linalg.norm(omega))
    if theta < 1e-9:
        return np.eye(3) + skew(omega)
    k = omega / theta
    kk = skew(k)
    return np.eye(3) + np.sin(theta) * kk + (1.0 - np.cos(theta)) * (kk @ kk)


def rodrigues_inv(r: np.ndarray) -> np.ndarray:
    """Rotationsmatrix -> Rotationsvektor."""
    cos_t = (np.trace(r) - 1.0) * 0.5
    cos_t = float(np.clip(cos_t, -1.0, 1.0))
    theta = np.arccos(cos_t)
    if theta < 1e-8:
        return np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]]) * 0.5
    return theta / (2.0 * np.sin(theta)) * np.array(
        [r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]]
    )


def project(intrinsics: np.ndarray, r: np.ndarray, t: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Projektion eines 3D-Punkts (3,) in Pixelkoordinaten (2,)."""
    fx, fy, cx, cy = _unpack_k(intrinsics)
    xc = r @ x + t
    if abs(xc[2]) < EPS:
        return np.array([np.nan, np.nan])
    return np.array([fx * xc[0] / xc[2] + cx, fy * xc[1] / xc[2] + cy])


def project_points(intrinsics: np.ndarray, r: np.ndarray, t: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Projektion vieler Punkte: x (N,3) -> (N,2)."""
    fx, fy, cx, cy = _unpack_k(intrinsics)
    xc = (r @ x.T).T + t                      # (N,3)
    z = np.where(np.abs(xc[:, 2]) < EPS, EPS, xc[:, 2])
    return np.stack([fx * xc[:, 0] / z + cx, fy * xc[:, 1] / z + cy], axis=1)


def pose_jacobian(intrinsics: np.ndarray, r: np.ndarray, t: np.ndarray, x: np.ndarray):
    """Analytische Jacobi-Matrix der Projektion nach der 6-DOF-Kamerapose.

    Parametrisierung (muss zur Aktualisierung in pose._gn_refine passen!):
        R_neu = exp(w^) @ R        (Links-Perturbation, w im Kameraraum)
        t_neu = t + dt             (unabhaengig)

    Damit ist  dp/dw = -[R x]_x = -[p - t]_x   und  dp/dt = I.
    ACHTUNG (haeufiger Fehler): der Hebelarm der Rotation ist R*x, NICHT
    p = R*x + t. Wer hier p einsetzt, linearisiert eine Kamerafahrt um den
    Kopfmittelpunkt (Orbit), aber aktualisiert wie eine Objektdrehung. Das
    konvergiert zwar (Levenberg-Abstieg), bleibt aber systematisch schief.

    Rueckgabe: (2N,6).
    """
    fx, fy, cx, cy = _unpack_k(intrinsics)
    xr = (r @ x.T).T                          # (N,3) rotierter Punkt OHNE Translation
    xc = xr + t                               # (N,3) Punkt im Kamerakoordinatensystem
    z = np.where(np.abs(xc[:, 2]) < EPS, EPS, xc[:, 2])
    # d(uv)/d(X_cam): (N,2,3)
    dp = np.zeros((xc.shape[0], 2, 3))
    dp[:, 0, 0] = fx / z
    dp[:, 0, 2] = -fx * xc[:, 0] / (z * z)
    dp[:, 1, 1] = fy / z
    dp[:, 1, 2] = -fy * xc[:, 1] / (z * z)
    # d(X_cam)/d(pose): (-[R x]_x | I)
    dx = np.zeros((xc.shape[0], 3, 6))
    for i in range(xc.shape[0]):
        dx[i, :, :3] = -skew(xr[i])
        dx[i, :, 3:] = np.eye(3)
    return (dp @ dx).reshape(-1, 6)


def _unpack_k(k: np.ndarray):
    return float(k[0, 0]), float(k[1, 1]), float(k[0, 2]), float(k[1, 2])


def make_intrinsics(fx: float, fy: float, cx: float, cy: float) -> np.ndarray:
    return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])


def orthonormalize(r: np.ndarray) -> np.ndarray:
    """Naechste gueltige Rotationsmatrix (SVD-Procrustes)."""
    u, _, vt = np.linalg.svd(r)
    d = np.sign(np.linalg.det(u @ vt))
    return u @ np.diag([1.0, 1.0, d]) @ vt


def rotation_error_deg(r_a: np.ndarray, r_b: np.ndarray) -> float:
    """Winkel zwischen zwei Rotationen in Grad."""
    rel = r_a @ r_b.T
    cos_t = (np.trace(rel) - 1.0) * 0.5
    return float(np.degrees(np.arccos(np.clip(cos_t, -1.0, 1.0))))

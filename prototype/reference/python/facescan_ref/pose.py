"""Kameraposenschaetzung ohne ARCore/SLAM.

Strategie (genau so in Kotlin umgesetzt):
  1. Initialisierung mit POSIT (skaliert-orthographisch, geschlossene Loesung)
     - braucht kein SLAM, keine Korrespondenzsuche, keine Tiefeninformation
  2. Verfeinerung mit Gauss-Newton + Huber-Gewichten unter voller Perspektive
  3. Robuste IRLS-Schleife gegen Ausreisser (verdeckte/fehlerkannte Punkte)

Eingang: 3D-Punkte des (kanonischen) Gesichtsmodells + 2D-Landmarks im Bild.
Ausgang: R (3x3), t (3,) -- metrisch, weil das Modell metrisch ist.
"""
from __future__ import annotations
import numpy as np

from .math3d import project_points, pose_jacobian, rodrigues, rodrigues_inv, orthonormalize

HUBER_K = 1.5  # Sigma-Vielfaches, ab dem linear statt quadratisch gewichtet wird
IRLS_ITERS = 6
GN_ITERS = 12


def posit_init(intrinsics: np.ndarray, points3d: np.ndarray, points2d: np.ndarray,
               iters: int = 12) -> tuple[np.ndarray, np.ndarray, float]:
    """POSIT: skalierte orthographische Initialisierung (DeMenthon & Davis).

    Liefert (R, t, scale). Robust, deterministisch, ~10 Iterationen.
    """
    k_inv = np.linalg.inv(intrinsics)
    ones = np.ones((points2d.shape[0], 1))
    # normalisierte Bildkoordinaten (Strahlen) x~ = K^-1 [u,v,1]
    rays = (k_inv @ np.hstack([points2d, ones]).T).T[:, :2]   # (N,2)
    xh = np.hstack([points3d, ones])                          # (N,4)

    r3 = np.zeros(3)     # geschaetztes r3/tz (Start: 0 = rein orthographisch)
    tz = 1.0
    for _ in range(iters):
        w = points3d @ r3          # (N,) aus der letzten Iteration
        rhs1 = rays[:, 0] * (w + 1.0)
        rhs2 = rays[:, 1] * (w + 1.0)
        p, *_ = np.linalg.lstsq(xh, rhs1, rcond=None)     # p = [r1/tz, tx/tz]
        q, *_ = np.linalg.lstsq(xh, rhs2, rcond=None)     # q = [r2/tz, ty/tz]
        scale = (np.linalg.norm(p[:3]) * np.linalg.norm(q[:3])) ** 0.5
        if scale < 1e-12:
            break
        tz = 1.0 / scale
        r1 = p[:3] * tz
        r2 = q[:3] * tz
        new_r3 = np.cross(r1, r2)
        n3 = np.linalg.norm(new_r3)
        if n3 < 1e-12:
            break
        r3 = new_r3 / n3 / tz                    # wieder auf r3/tz normieren

    r1 = p[:3] * tz
    r2 = q[:3] * tz
    r3 = np.cross(r1, r2)
    r3 = r3 / max(np.linalg.norm(r3), 1e-12)
    r2 = np.cross(r3, r1)
    r2 = r2 / max(np.linalg.norm(r2), 1e-12)
    r = orthonormalize(np.stack([r1, r2, r3]))
    t = np.array([p[3] * tz, q[3] * tz, tz])
    return r, t, tz


def _gn_refine(intrinsics: np.ndarray, points3d: np.ndarray, points2d: np.ndarray,
               r: np.ndarray, t: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Gauss-Newton-Verfeinerung der 6-DOF-Pose (Huber-gewichtet)."""
    omega = np.zeros(3)
    dt = np.zeros(3)
    lam = 1e-4                        # Levenberg-Daempfung
    for _ in range(GN_ITERS):
        r_cur = rodrigues(omega) @ r
        t_cur = t + dt
        proj = project_points(intrinsics, r_cur, t_cur, points3d)
        res = (proj - points2d).reshape(-1)
        err = float(np.sum(weights * res * res))
        j = pose_jacobian(intrinsics, r_cur, t_cur, points3d) * np.sqrt(weights)[:, None]
        jtj = j.T @ j
        g = -j.T @ (res * np.sqrt(weights))
        for _ in range(8):
            try:
                step = np.linalg.solve(jtj + lam * np.diag(np.diag(jtj) + 1e-9), g)
            except np.linalg.LinAlgError:
                lam *= 10.0
                continue
            omega_new = omega + step[:3]
            dt_new = dt + step[3:]
            r_new = rodrigues(omega_new) @ r
            t_new = t + dt_new
            res_new = (project_points(intrinsics, r_new, t_new, points3d) - points2d).reshape(-1)
            err_new = float(np.sum(weights * res_new * res_new))
            if err_new < err:
                omega, dt, err = omega_new, dt_new, err_new
                lam = max(lam * 0.5, 1e-8)
                break
            lam *= 10.0
        else:
            break
        if np.linalg.norm(step) < 1e-9:
            break
    return rodrigues(omega) @ r, t + dt


def estimate_pose(intrinsics: np.ndarray, points3d: np.ndarray, points2d: np.ndarray,
                  init_r: np.ndarray | None = None, init_t: np.ndarray | None = None,
                  huber_k: float = HUBER_K) -> dict:
    """Robuste Posenschaetzung: POSIT-Init + IRLS + Gauss-Newton.

    Rueckgabe: dict mit R, t, rms (px), inlier_ratio, residuals
    """
    if init_r is None or init_t is None:
        r, t, _ = posit_init(intrinsics, points3d, points2d)
    else:
        r, t = init_r, init_t

    weights = np.ones(points2d.shape[0] * 2)
    inliers = np.ones(points2d.shape[0], dtype=bool)
    for _ in range(IRLS_ITERS):
        r, t = _gn_refine(intrinsics, points3d, points2d, r, t, weights)
        res = (project_points(intrinsics, r, t, points3d) - points2d).reshape(-1)
        sigma = 1.4826 * np.median(np.abs(res - np.median(res))) + 1e-6   # MAD-Schaetzer
        a = np.abs(res) / (huber_k * sigma)
        w = np.where(a <= 1.0, 1.0, 1.0 / np.maximum(a, 1e-6))
        weights = w
        inliers = np.sqrt(w.reshape(-1, 2).mean(axis=1)) > 0.5

    res = (project_points(intrinsics, r, t, points3d) - points2d).reshape(-1)
    rms = float(np.sqrt(np.mean(res ** 2)))
    per_point = np.linalg.norm((project_points(intrinsics, r, t, points3d) - points2d), axis=1)
    return {
        "R": r,
        "t": t,
        "rms": rms,
        "median": float(np.median(per_point)),
        "inlier_ratio": float(inliers.mean()),
        "residuals": per_point,
    }

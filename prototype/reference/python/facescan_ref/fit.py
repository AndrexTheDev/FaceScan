"""Multi-Frame-3DMM-Fit (das Herzstueck von M0).

Gegeben: F Bilder mit 2D-Landmarks, Kamera-Intrinsics, ein Basis-Mesh mit
Identitaets- und Ausdrucksbasis.
Gesucht: Identitaet alpha (geteilt!), Ausdruck beta_f und Pose (R_f,t_f) je Frame.

Loesung: abwechselnde Optimierung
  (a) Pose je Frame   : nichtlinear (Gauss-Newton, 6 DOF, Huber-robust)
  (b) Form            : LINEARES Ausgleichsproblem unter skalierter Orthographie
                        um die aktuelle Pose linearisiert
  (c) Regularisierung : PCA-Whitening, lambda_id ||alpha||^2, lambda_exp ||beta||^2

Genau dieselbe Struktur hat spaeter der C++/Kotlin-Kern, nur mit 478 statt 120
Punkten und zusaetzlichem photometrischen Term.
"""
from __future__ import annotations
import numpy as np

from .math3d import project_points, rotation_error_deg
from .pose import estimate_pose

DEFAULT_LAM_ID = 1e-2
DEFAULT_LAM_EXP = 3e-2
OUTER_ITERS = 8


def _shape(base: np.ndarray, a_id: np.ndarray, a_exp: np.ndarray,
           alpha: np.ndarray, beta: np.ndarray) -> np.ndarray:
    return (base.reshape(-1) + a_id @ alpha + a_exp @ beta).reshape(-1, 3)


def _solve_shape(intrinsics: np.ndarray, base: np.ndarray, a_id: np.ndarray, a_exp: np.ndarray,
                 obs: list[np.ndarray], vis: list[np.ndarray], poses: list[tuple],
                 lam_id: float, lam_exp: float,
                 alpha_init: np.ndarray, betas_init: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Gauss-Newton-Schritt in den Formparametern.

    Linearisiert wird um die AKTUELLE Form (nicht um das Mittelgesicht) --
    sonst konvergiert die aeussere Schleife nicht. Die Projektion wird dabei
    skaliert-orthographisch genaehert (Fehler ~1 % bei 62 deg FOV und 50 cm
    Abstand); die volle Perspektive steckt im anschliessenden Posen-Schritt.
    """
    f = len(obs)
    n = base.shape[0]
    k_id, k_exp = a_id.shape[1], a_exp.shape[1]
    nunk = k_id + f * k_exp

    jtj = np.zeros((nunk, nunk))
    jtr = np.zeros(nunk)
    # Regularisierung (Whitening: sigma steckt in den Spalten, daher Einheits-Prior)
    jtj[:k_id, :k_id] += lam_id * np.eye(k_id)
    for fi in range(f):
        sl = slice(k_id + fi * k_exp, k_id + (fi + 1) * k_exp)
        jtj[sl, sl] += lam_exp * np.eye(k_exp)

    base_flat = base.reshape(-1)
    for fi, (r, t) in enumerate(poses):
        z = float(np.mean((r @ base.T).T[:, 2] + t[2]))
        if abs(z) < 1e-6:
            continue
        s = float(intrinsics[0, 0]) / z                     # Skala der Orthographie
        vis_mask = vis[fi].reshape(-1) > 0.5

        shape_cur = (base_flat + a_id @ alpha_init + a_exp @ betas_init[fi]).reshape(-1, 3)
        pred_cur = project_points(intrinsics, r, t, shape_cur)
        res = (obs[fi] - pred_cur).reshape(-1)              # (2N,)

        # Designmatrix: d(u,v)/d(Vertex) = s * [r1; r2] (zeilenweise je Punkt)
        m = np.zeros((2 * n, 3 * n))
        for i in range(n):
            m[2 * i, 3 * i:3 * i + 3] = s * r[0]
            m[2 * i + 1, 3 * i:3 * i + 3] = s * r[1]

        a_all = np.hstack([a_id, np.zeros((3 * n, f * k_exp))])
        a_all[:, k_id + fi * k_exp: k_id + (fi + 1) * k_exp] = a_exp
        j = m @ a_all                                        # (2N, nunk)

        w = np.repeat(vis_mask, 2).astype(float)
        jw = j * w[:, None]
        jtj += jw.T @ j
        jtr += jw.T @ (res * w)

    delta = np.linalg.solve(jtj + 1e-9 * np.eye(nunk), jtr)
    alpha = alpha_init + delta[:k_id]
    betas = betas_init + delta[k_id:].reshape(f, k_exp)
    return alpha, betas


def fit_multiframe(scene: dict, lam_id: float = DEFAULT_LAM_ID,
                   lam_exp: float = DEFAULT_LAM_EXP, iters: int = OUTER_ITERS,
                   verbose: bool = False) -> dict:
    """Fuehrt den kompletten Fit durch und liefert Kennzahlen."""
    base, a_id, a_exp = scene["base"], scene["A_id"], scene["A_exp"]
    k = scene["K"]
    obs = [fr["points2d"] for fr in scene["frames"]]
    vis = [fr["visibility"] for fr in scene["frames"]]

    # --- Schritt 0: Posen gegen das MITTLERE Gesicht schaetzen (wie mit MediaPipe-Pose-Init)
    poses = []
    for fi in range(len(obs)):
        m = vis[fi].reshape(-1) > 0.5
        est = estimate_pose(k, base[m], obs[fi][m])
        poses.append((est["R"], est["t"]))
        if verbose:
            print(f"  init frame {fi}: rms={est['rms']:.2f}px inlier={est['inlier_ratio']:.2f}")

    alpha = np.zeros(a_id.shape[1])
    betas = np.zeros((len(obs), a_exp.shape[1]))
    history = []
    for it in range(iters):
        # (b) Form
        alpha, betas = _solve_shape(k, base, a_id, a_exp, obs, vis, poses,
                                    lam_id, lam_exp, alpha, betas)
        # (a) Posen (mit der neuen Form je Frame)
        for fi in range(len(obs)):
            m = vis[fi].reshape(-1) > 0.5
            shape = _shape(base, a_id, a_exp, alpha, betas[fi])
            est = estimate_pose(k, shape[m], obs[fi][m], init_r=poses[fi][0], init_t=poses[fi][1])
            poses[fi] = (est["R"], est["t"])

        rms = []
        for fi in range(len(obs)):
            m = vis[fi].reshape(-1) > 0.5
            shape = _shape(base, a_id, a_exp, alpha, betas[fi])
            d = project_points(k, poses[fi][0], poses[fi][1], shape[m]) - obs[fi][m]
            rms.append(float(np.sqrt(np.mean(np.sum(d ** 2, axis=1)))))
        history.append(float(np.mean(rms)))
        if verbose and len(history) > 1 and abs(history[-1] - history[-2]) < 1e-4:
            break
        if verbose:
            print(f"  iter {it}: repro rms={history[-1]:.3f} px")

    return {"alpha": alpha, "betas": betas, "poses": poses, "history": history}


def evaluate(scene: dict, result: dict) -> dict:
    """Vergleich gegen die Ground Truth."""
    rot_err, tra_err = [], []
    for fi, fr in enumerate(scene["frames"]):
        r_est, t_est = result["poses"][fi]
        rot_err.append(rotation_error_deg(r_est, fr["R"]))
        tra_err.append(float(np.linalg.norm(t_est - fr["t"])))

    a_true, a_est = scene["alpha_true"], result["alpha"]
    k = min(len(a_true), len(a_est))
    corr = float(np.corrcoef(a_true[:k], a_est[:k])[0, 1]) if k > 1 else float("nan")
    alpha_rmse = float(np.sqrt(np.mean((a_true[:k] - a_est[:k]) ** 2)))

    beta_true, beta_est = scene["beta_true"], result["betas"]
    beta_rmse = float(np.sqrt(np.mean((beta_true - beta_est) ** 2)))

    # Rekonstruktionsfehler der Geometrie (Chamfer-artig, hier Punkt-zu-Punkt)
    shape_true = (scene["base"].reshape(-1)
                  + scene["A_id"] @ scene["alpha_true"]
                  + scene["A_exp"] @ scene["beta_true"][0]).reshape(-1, 3)
    shape_est = (scene["base"].reshape(-1)
                 + scene["A_id"] @ result["alpha"]
                 + scene["A_exp"] @ result["betas"][0]).reshape(-1, 3)
    geom = float(np.mean(np.linalg.norm(shape_true - shape_est, axis=1)))

    # Inlier-RMS: nur sichtbare UND nicht-verrauschte Punkte (die ehrliche
    # Genauigkeitskennzahl; der RMS ueber alle Punkte wird von den injizierten
    # Ausreissern dominiert und sagt ueber das Verfahren nichts aus).
    inlier_rms = []
    for fi, fr in enumerate(scene["frames"]):
        good = (fr["visibility"].reshape(-1) > 0.5) & (fr.get("outliers", np.zeros(
            fr["visibility"].shape[0])).reshape(-1) < 0.5)
        if good.sum() == 0:
            continue
        shape = _shape(scene["base"], scene["A_id"], scene["A_exp"],
                       result["alpha"], result["betas"][fi])
        d = project_points(scene["K"], result["poses"][fi][0], result["poses"][fi][1],
                           shape[good]) - fr["points2d"][good]
        inlier_rms.append(float(np.sqrt(np.mean(np.sum(d ** 2, axis=1)))))

    return {
        "repro_inlier_rms_px": float(np.mean(inlier_rms)) if inlier_rms else float("nan"),
        "rot_err_deg_mean": float(np.mean(rot_err)),
        "rot_err_deg_max": float(np.max(rot_err)),
        "trans_err_mm_mean": float(np.mean(tra_err)),
        "trans_err_mm_max": float(np.max(tra_err)),
        "alpha_corr": corr,
        "alpha_rmse": alpha_rmse,
        "beta_rmse": beta_rmse,
        "geometry_err_mm_mean": geom,
        "repro_rms_final_px": float(result["history"][-1]) if result["history"] else float("nan"),
        "repro_rms_first_px": float(result["history"][0]) if result["history"] else float("nan"),
    }

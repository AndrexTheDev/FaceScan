"""Spiegelbild des Kotlin-Kerns – Validierung OHNE Compiler.

Diese Datei ist KEIN Produktionscode. Sie ist ein 1:1-Nachbau der Kotlin-
Klassen (prototype/android/app/src/main/java/.../geometry/) in reinem Python:
gleiche Index-Arithmetik, gleiche Reihenfolge, gleiche Schleifen, flache
DoubleArrays statt numpy-Matrizen.

Wozu? In dieser Sandbox gibt es kein JDK/Gradle. Der Kotlin-Code kann also
nicht kompiliert werden. Der Spiegel prueft damit die Dinge, die ein Compiler
NICHT prueft und die trotzdem wehtun:

  * Index-Fehler (zeilenweise 3N/2N-Layout, Blockindizes je Frame)
  * falsche Vorzeichen und Hebelarme in den Jacobi-Matrizen
  * vertauschte Reihenfolgen (Regularisierung vor/nach dem Aufsummieren)
  * falsch gesetzte Kreuzterme in J^T J

Wenn der Spiegel dieselben Kennzahlen liefert wie die numpy-Referenz, ist die
Mathematik und die Indexierung des Kotlin-Kerns belegt. Die Syntax bleibt
trotzdem vom ersten echten Gradle-Build zu bestaetigen.

Aufruf:
    /tmp/qrenv/bin/python kotlin_mirror.py
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

# ---------------------------------------------------------------- Mat3 -----

class Mat3:
    """3x3, zeilenweise in einer Liste der Laenge 9 (wie Mat3.kt)."""

    __slots__ = ("m",)

    def __init__(self, m):
        assert len(m) == 9
        self.m = list(m)

    def get(self, r, c):
        return self.m[r * 3 + c]

    def __mul__(self, other):
        out = [0.0] * 9
        for r in range(3):
            for c in range(3):
                out[r * 3 + c] = (
                    self.get(r, 0) * other.get(0, c)
                    + self.get(r, 1) * other.get(1, c)
                    + self.get(r, 2) * other.get(2, c)
                )
        return Mat3(out)

    def times_vec(self, v):
        m = self.m
        return [
            m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
            m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
            m[6] * v[0] + m[7] * v[1] + m[8] * v[2],
        ]

    def transpose(self):
        m = self.m
        return Mat3([m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8]])

    def determinant(self):
        m = self.m
        return (
            m[0] * (m[4] * m[8] - m[5] * m[7])
            - m[1] * (m[3] * m[8] - m[5] * m[6])
            + m[2] * (m[3] * m[7] - m[4] * m[6])
        )

    def inverse(self):
        m = self.m
        d = self.determinant()
        inv = [0.0] * 9
        inv[0] = (m[4] * m[8] - m[5] * m[7]) / d
        inv[1] = (m[2] * m[7] - m[1] * m[8]) / d
        inv[2] = (m[1] * m[5] - m[2] * m[4]) / d
        inv[3] = (m[5] * m[6] - m[3] * m[8]) / d
        inv[4] = (m[0] * m[8] - m[2] * m[6]) / d
        inv[5] = (m[2] * m[3] - m[0] * m[5]) / d
        inv[6] = (m[3] * m[7] - m[4] * m[6]) / d
        inv[7] = (m[1] * m[6] - m[0] * m[7]) / d
        inv[8] = (m[0] * m[4] - m[1] * m[3]) / d
        return Mat3(inv)

    def orthonormalize(self):
        """Newton-Iteration auf den polaren Faktor (wie Mat3.kt)."""
        x = self
        for _ in range(12):
            y = x.inverse().transpose()
            nxt = [0.5 * (x.m[i] + y.m[i]) for i in range(9)]
            delta = sum(abs(nxt[i] - x.m[i]) for i in range(9))
            x = Mat3(nxt)
            if delta < 1e-14:
                break
        return x

    @staticmethod
    def identity():
        return Mat3([1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0])

    @staticmethod
    def skew(v):
        return Mat3([0.0, -v[2], v[1], v[2], 0.0, -v[0], -v[1], v[0], 0.0])

    @staticmethod
    def from_rodrigues(omega):
        theta = math.sqrt(omega[0] ** 2 + omega[1] ** 2 + omega[2] ** 2)
        ident = Mat3.identity()
        if theta < 1e-12:
            s = Mat3.skew(omega)
            return Mat3([ident.m[i] + s.m[i] for i in range(9)])
        k = [omega[0] / theta, omega[1] / theta, omega[2] / theta]
        kk = Mat3.skew(k)
        kk2 = kk * kk
        return Mat3(
            [
                ident.m[i] + math.sin(theta) * kk.m[i] + (1.0 - math.cos(theta)) * kk2.m[i]
                for i in range(9)
            ]
        )

    @staticmethod
    def to_rodrigues(r):
        cos_theta = ((r.get(0, 0) + r.get(1, 1) + r.get(2, 2)) - 1.0) * 0.5
        cos_theta = max(-1.0, min(1.0, cos_theta))
        theta = math.acos(cos_theta)
        raw = [
            r.get(2, 1) - r.get(1, 2),
            r.get(0, 2) - r.get(2, 0),
            r.get(1, 0) - r.get(0, 1),
        ]
        if theta < 1e-8:
            return [raw[0] * 0.5, raw[1] * 0.5, raw[2] * 0.5]
        f = theta / (2.0 * math.sin(theta))
        return [raw[0] * f, raw[1] * f, raw[2] * f]

    @staticmethod
    def rotation_error_deg(a, b):
        rel = a * b.transpose()
        cos_theta = ((rel.get(0, 0) + rel.get(1, 1) + rel.get(2, 2)) - 1.0) * 0.5
        return math.degrees(math.acos(max(-1.0, min(1.0, cos_theta))))


# -------------------------------------------------------------- Linalg -----

def solve_spd(a, b, n):
    """Cholesky (wie Linalg.solveSpd)."""
    l = [0.0] * (n * n)
    for i in range(n):
        for j in range(i + 1):
            s = a[i * n + j]
            for k in range(j):
                s -= l[i * n + k] * l[j * n + k]
            if i == j:
                if s <= 1e-18:
                    return None
                l[i * n + j] = math.sqrt(s)
            else:
                d = l[j * n + j]
                l[i * n + j] = s / (d if d != 0.0 else 1e-18)
    y = [0.0] * n
    for i in range(n):
        s = b[i]
        for k in range(i):
            s -= l[i * n + k] * y[k]
        d = l[i * n + i]
        if d == 0.0:
            return None
        y[i] = s / d
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = y[i]
        for k in range(i + 1, n):
            s -= l[k * n + i] * x[k]
        d = l[i * n + i]
        if d == 0.0:
            return None
        x[i] = s / d
    return x


def least_squares(a, b, rows, cols, damping=1e-9):
    ata = [0.0] * (cols * cols)
    atb = [0.0] * cols
    for r in range(rows):
        off = r * cols
        for i in range(cols):
            avi = a[off + i]
            if avi == 0.0:
                continue
            atb[i] += avi * b[r]
            j = i
            while j < cols:
                ata[i * cols + j] += avi * a[off + j]
                j += 1
    for i in range(cols):
        for j in range(i + 1, cols):
            ata[j * cols + i] = ata[i * cols + j]
        ata[i * cols + i] += damping
    return solve_spd(ata, atb, cols)


def median(values):
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2 == 0:
        return (s[mid - 1] + s[mid]) * 0.5
    return s[mid]


def mad_sigma(values):
    med = median(values)
    dev = [abs(v - med) for v in values]
    return 1.4826 * median(dev) + 1e-6


# ---------------------------------------------------------- CameraModel ----

class CameraModel:
    __slots__ = ("fx", "fy", "cx", "cy")

    def __init__(self, fx, fy, cx, cy):
        self.fx, self.fy, self.cx, self.cy = fx, fy, cx, cy

    def project_all(self, rot, t, points, out):
        n = len(points) // 3
        for i in range(n):
            xc = rot.times_vec([points[3 * i], points[3 * i + 1], points[3 * i + 2]])
            z = xc[2] + t[2]
            if abs(z) < 1e-9:
                z = 1e-9
            out[2 * i] = self.fx * (xc[0] + t[0]) / z + self.cx
            out[2 * i + 1] = self.fy * (xc[1] + t[1]) / z + self.cy
        return out

    def mean_depth(self, rot, t, points):
        n = len(points) // 3
        if n == 0:
            return 0.0
        s = 0.0
        for i in range(n):
            xc = rot.times_vec([points[3 * i], points[3 * i + 1], points[3 * i + 2]])
            s += xc[2] + t[2]
        return s / n


# --------------------------------------------------------- PoseEstimator ----

POSIT_ITERS = 12
GN_ITERS = 12
IRLS_ITERS = 6
HUBER_K = 1.5


class RigidTransform:
    __slots__ = ("rotation", "translation")

    def __init__(self, rotation, translation):
        self.rotation = rotation
        self.translation = list(translation)

    def translation_error_mm(self, other):
        d = [self.translation[i] - other.translation[i] for i in range(3)]
        return math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)

    def rotation_error_deg(self, other):
        return Mat3.rotation_error_deg(self.rotation, other.rotation)


def posit_init(camera, points3d, points2d, iters=POSIT_ITERS):
    n = len(points3d) // 3
    rx = [(points2d[2 * i] - camera.cx) / camera.fx for i in range(n)]
    ry = [(points2d[2 * i + 1] - camera.cy) / camera.fy for i in range(n)]
    design = [0.0] * (n * 4)
    for i in range(n):
        design[4 * i] = points3d[3 * i]
        design[4 * i + 1] = points3d[3 * i + 1]
        design[4 * i + 2] = points3d[3 * i + 2]
        design[4 * i + 3] = 1.0

    r3 = [0.0, 0.0, 0.0]
    tz = 1.0
    p = [0.0] * 4
    q = [0.0] * 4
    for _ in range(iters):
        rhs1 = [0.0] * n
        rhs2 = [0.0] * n
        for i in range(n):
            w = (r3[0] * points3d[3 * i] + r3[1] * points3d[3 * i + 1]
                 + r3[2] * points3d[3 * i + 2])
            rhs1[i] = rx[i] * (w + 1.0)
            rhs2[i] = ry[i] * (w + 1.0)
        p_new = least_squares(design, rhs1, n, 4)
        q_new = least_squares(design, rhs2, n, 4)
        if p_new is None or q_new is None:
            break
        p, q = p_new, q_new
        norm_p = math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2)
        norm_q = math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2)
        scale = math.sqrt(norm_p * norm_q)
        if scale < 1e-12:
            break
        tz = 1.0 / scale
        r1 = [p[0] * tz, p[1] * tz, p[2] * tz]
        r2 = [q[0] * tz, q[1] * tz, q[2] * tz]
        cross = [
            r1[1] * r2[2] - r1[2] * r2[1],
            r1[2] * r2[0] - r1[0] * r2[2],
            r1[0] * r2[1] - r1[1] * r2[0],
        ]
        nrm = math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2)
        if nrm < 1e-12:
            break
        r3 = [cross[0] / nrm / tz, cross[1] / nrm / tz, cross[2] / nrm / tz]

    r1 = [p[0] * tz, p[1] * tz, p[2] * tz]
    r2 = [q[0] * tz, q[1] * tz, q[2] * tz]
    r3n = _normalize([
        r1[1] * r2[2] - r1[2] * r2[1],
        r1[2] * r2[0] - r1[0] * r2[2],
        r1[0] * r2[1] - r1[1] * r2[0],
    ])
    r2n = _normalize([
        r3n[1] * r1[2] - r3n[2] * r1[1],
        r3n[2] * r1[0] - r3n[0] * r1[2],
        r3n[0] * r1[1] - r3n[1] * r1[0],
    ])
    rotation = Mat3([
        r1[0], r1[1], r1[2],
        r2n[0], r2n[1], r2n[2],
        r3n[0], r3n[1], r3n[2],
    ]).orthonormalize()
    return RigidTransform(rotation, [p[3] * tz, q[3] * tz, tz])


def _normalize(v):
    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if n < 1e-12:
        return [0.0, 0.0, 1.0]
    return [v[0] / n, v[1] / n, v[2] / n]


def pose_jacobian_row(camera, x, rotation, translation, out):
    """1:1 zu PoseEstimator.poseJacobianRow (Hebelarm = R*x, ohne Translation)."""
    xr = rotation.times_vec(x)
    px = xr[0] + translation[0]
    py = xr[1] + translation[1]
    pz = xr[2] + translation[2]
    z = pz if abs(pz) >= 1e-9 else 1e-9
    fx, fy = camera.fx, camera.fy
    a00 = fx / z
    a02 = -fx * px / (z * z)
    a11 = fy / z
    a12 = -fy * py / (z * z)

    out[0] = a02 * xr[1]
    out[1] = a00 * xr[2] - a02 * xr[0]
    out[2] = -a00 * xr[1]
    out[3] = a00
    out[4] = 0.0
    out[5] = a02

    out[6] = -a11 * xr[2] + a12 * xr[1]
    out[7] = -a12 * xr[0]
    out[8] = a11 * xr[0]
    out[9] = 0.0
    out[10] = a11
    out[11] = a12


def refine(camera, points3d, points2d, init, weights):
    n = len(points3d) // 3
    proj = [0.0] * (2 * n)
    trial = [0.0] * (2 * n)
    j_row = [0.0] * 12
    omega = [0.0, 0.0, 0.0]
    dt = [0.0, 0.0, 0.0]
    lam = 1e-4
    current_error = float("inf")

    for _ in range(GN_ITERS):
        r_cur = Mat3.from_rodrigues(omega) * init.rotation
        t_cur = [init.translation[0] + dt[0], init.translation[1] + dt[1],
                 init.translation[2] + dt[2]]
        camera.project_all(r_cur, t_cur, points3d, proj)
        err = 0.0
        for i in range(2 * n):
            r = proj[i] - points2d[i]
            err += weights[i] * r * r
        current_error = err

        jtj = [0.0] * 36
        g = [0.0] * 6
        for i in range(n):
            x = [points3d[3 * i], points3d[3 * i + 1], points3d[3 * i + 2]]
            pose_jacobian_row(camera, x, r_cur, t_cur, j_row)
            for a in range(2):
                row = 2 * i + a
                w = weights[row]
                res = proj[row] - points2d[row]
                for rr in range(6):
                    jr = j_row[a * 6 + rr]
                    g[rr] -= w * jr * res
                    for c in range(rr, 6):
                        jtj[rr * 6 + c] += w * jr * j_row[a * 6 + c]
        for rr in range(6):
            for c in range(rr):
                jtj[rr * 6 + c] = jtj[c * 6 + rr]
            jtj[rr * 6 + rr] *= (1.0 + lam)
            jtj[rr * 6 + rr] += lam * 1e-9

        accepted = False
        for _trial in range(8):
            step = solve_spd(jtj, g, 6)
            if step is None:
                lam *= 10.0
                continue
            omega_new = [omega[0] + step[0], omega[1] + step[1], omega[2] + step[2]]
            dt_new = [dt[0] + step[3], dt[1] + step[4], dt[2] + step[5]]
            r_new = Mat3.from_rodrigues(omega_new) * init.rotation
            t_new = [init.translation[0] + dt_new[0], init.translation[1] + dt_new[1],
                     init.translation[2] + dt_new[2]]
            camera.project_all(r_new, t_new, points3d, trial)
            err_new = 0.0
            for i in range(2 * n):
                r = trial[i] - points2d[i]
                err_new += weights[i] * r * r
            if err_new < current_error:
                omega, dt = omega_new, dt_new
                lam = max(lam * 0.5, 1e-8)
                accepted = True
                break
            lam *= 10.0
        if not accepted:
            break

    r_final = Mat3.from_rodrigues(omega) * init.rotation
    t_final = [init.translation[0] + dt[0], init.translation[1] + dt[1],
               init.translation[2] + dt[2]]
    return RigidTransform(r_final, t_final)


def estimate_pose(camera, points3d, points2d, init=None):
    n = len(points3d) // 3
    pose = init if init is not None else posit_init(camera, points3d, points2d)
    weights = [1.0] * (2 * n)
    inliers = 0

    for _ in range(IRLS_ITERS):
        pose = refine(camera, points3d, points2d, pose, weights)
        proj = [0.0] * (2 * n)
        camera.project_all(pose.rotation, pose.translation, points3d, proj)
        residuals = [proj[i] - points2d[i] for i in range(2 * n)]
        sigma = mad_sigma(residuals)
        for i in range(2 * n):
            a = abs(residuals[i]) / (HUBER_K * sigma)
            weights[i] = 1.0 if a <= 1.0 else 1.0 / max(a, 1e-6)

    proj = [0.0] * (2 * n)
    camera.project_all(pose.rotation, pose.translation, points3d, proj)
    sum_sq = 0.0
    per_point = [0.0] * n
    inliers = 0
    for i in range(n):
        du = proj[2 * i] - points2d[2 * i]
        dv = proj[2 * i + 1] - points2d[2 * i + 1]
        per_point[i] = math.sqrt(du * du + dv * dv)
        sum_sq += du * du + dv * dv
        if 0.5 * (weights[2 * i] + weights[2 * i + 1]) > 0.5:
            inliers += 1
    return {
        "transform": pose,
        "rms_px": math.sqrt(sum_sq / n),
        "median_px": median(per_point),
        "inlier_ratio": inliers / n,
    }


# ---------------------------------------------------------- ModelFitter ----

class MorphableModel:
    def __init__(self, mean_vertices, identity_basis, expression_basis, k_id, k_exp):
        self.mean_vertices = list(mean_vertices)
        self.identity_basis = list(identity_basis)
        self.expression_basis = list(expression_basis)
        self.k_id, self.k_exp = k_id, k_exp
        self.n_vertices = len(mean_vertices) // 3

    def shape(self, alpha, beta, out=None):
        """Komponentenweises Layout: basis[komponente * k_anzahl + k]."""
        n3 = len(self.mean_vertices)
        if out is None:
            out = [0.0] * n3
        k_id, k_exp = self.k_id, self.k_exp
        for i in range(n3):
            acc = self.mean_vertices[i]
            id_off = i * k_id
            for k in range(k_id):
                a = alpha[k]
                if a != 0.0:
                    acc += a * self.identity_basis[id_off + k]
            exp_off = i * k_exp
            for k in range(k_exp):
                b = beta[k]
                if b != 0.0:
                    acc += b * self.expression_basis[exp_off + k]
            out[i] = acc
        return out


def _visible_subset(points3d, landmarks, visibility):
    n = len(points3d) // 3
    p3, p2 = [], []
    for i in range(n):
        if visibility[i] < 0.5:
            continue
        p3 += [points3d[3 * i], points3d[3 * i + 1], points3d[3 * i + 2]]
        p2 += [landmarks[2 * i], landmarks[2 * i + 1]]
    return p3, p2


def fit_multiframe(camera, model, observations,
                   lam_id=1e-2, lam_exp=3e-2, outer_iterations=8, convergence_px=1e-4,
                   verbose=False):
    """observations: Liste aus (landmarks 2N, visibility N)."""
    f = len(observations)
    n = model.n_vertices
    n3 = n * 3
    k_id, k_exp = model.k_id, model.k_exp
    n_unknowns = k_id + f * k_exp

    poses = []
    for index in range(f):
        landmarks, visibility = observations[index]
        p3, p2 = _visible_subset(model.mean_vertices, landmarks, visibility)
        poses.append(estimate_pose(camera, p3, p2)["transform"])

    alpha = [0.0] * k_id
    betas = [[0.0] * k_exp for _ in range(f)]

    jtj = [0.0] * (n_unknowns * n_unknowns)
    jtr = [0.0] * n_unknowns
    pred = [0.0] * (2 * n)
    shape = [0.0] * n3
    history = []

    local_n = k_id + k_exp
    ju = [0.0] * local_n
    jv = [0.0] * local_n
    global_index = [0] * local_n

    previous_error = float("inf")

    for outer in range(outer_iterations):
        jtj = [0.0] * (n_unknowns * n_unknowns)
        jtr = [0.0] * n_unknowns
        for u in range(k_id):
            jtj[u * n_unknowns + u] = lam_id
        for fi in range(f):
            base = k_id + fi * k_exp
            for u in range(k_exp):
                jtj[(base + u) * n_unknowns + (base + u)] = lam_exp

        for fi in range(f):
            landmarks, visibility = observations[fi]
            pose = poses[fi]
            r = pose.rotation
            mean_z = camera.mean_depth(pose.rotation, pose.translation, model.mean_vertices)
            if mean_z < 1e-6:
                continue
            s = camera.fx / mean_z
            model.shape(alpha, betas[fi], shape)
            camera.project_all(pose.rotation, pose.translation, shape, pred)

            for k in range(k_id):
                global_index[k] = k
            for k in range(k_exp):
                global_index[k_id + k] = k_id + fi * k_exp + k

            for i in range(n):
                if visibility[i] < 0.5:
                    continue
                i3 = 3 * i
                for k in range(k_id):
                    off = i3 * k_id + k
                    ju[k] = s * (r.get(0, 0) * model.identity_basis[off]
                                 + r.get(0, 1) * model.identity_basis[off + k_id]
                                 + r.get(0, 2) * model.identity_basis[off + 2 * k_id])
                    jv[k] = s * (r.get(1, 0) * model.identity_basis[off]
                                 + r.get(1, 1) * model.identity_basis[off + k_id]
                                 + r.get(1, 2) * model.identity_basis[off + 2 * k_id])
                for k in range(k_exp):
                    off = i3 * k_exp + k
                    ju[k_id + k] = s * (r.get(0, 0) * model.expression_basis[off]
                                        + r.get(0, 1) * model.expression_basis[off + k_exp]
                                        + r.get(0, 2) * model.expression_basis[off + 2 * k_exp])
                    jv[k_id + k] = s * (r.get(1, 0) * model.expression_basis[off]
                                        + r.get(1, 1) * model.expression_basis[off + k_exp]
                                        + r.get(1, 2) * model.expression_basis[off + 2 * k_exp])

                res_u = landmarks[2 * i] - pred[2 * i]
                res_v = landmarks[2 * i + 1] - pred[2 * i + 1]

                for c in range(local_n):
                    jtr[global_index[c]] += ju[c] * res_u + jv[c] * res_v
                for a in range(local_n):
                    ga = global_index[a]
                    for b in range(a, local_n):
                        jtj[ga * n_unknowns + global_index[b]] += ju[a] * ju[b] + jv[a] * jv[b]

        for i in range(n_unknowns):
            for j in range(i):
                jtj[i * n_unknowns + j] = jtj[j * n_unknowns + i]
            jtj[i * n_unknowns + i] += 1e-9

        delta = solve_spd(jtj, jtr, n_unknowns)
        if delta is not None:
            for k in range(k_id):
                alpha[k] += delta[k]
            for fi in range(f):
                for k in range(k_exp):
                    betas[fi][k] += delta[k_id + fi * k_exp + k]

        for fi in range(f):
            landmarks, visibility = observations[fi]
            model.shape(alpha, betas[fi], shape)
            p3, p2 = _visible_subset(shape, landmarks, visibility)
            poses[fi] = estimate_pose(camera, p3, p2, poses[fi])["transform"]

        sum_per_frame = 0.0
        for fi in range(f):
            landmarks, visibility = observations[fi]
            model.shape(alpha, betas[fi], shape)
            camera.project_all(poses[fi].rotation, poses[fi].translation, shape, pred)
            sum_sq = 0.0
            count = 0
            for i in range(n):
                if visibility[i] < 0.5:
                    continue
                du = pred[2 * i] - landmarks[2 * i]
                dv = pred[2 * i + 1] - landmarks[2 * i + 1]
                sum_sq += du * du + dv * dv
                count += 1
            if count > 0:
                sum_per_frame += math.sqrt(sum_sq / count)
        rms = sum_per_frame / f
        history.append(rms)
        if verbose:
            print(f"  iter {outer}: repro rms={rms:.4f} px")
        if abs(previous_error - rms) < convergence_px:
            break
        previous_error = rms

    final_shape = model.shape(alpha, [0.0] * k_exp)
    return {"alpha": alpha, "betas": betas, "poses": poses,
            "history": history, "final_shape": final_shape}


# ---------------------------------------------------------------- Test -----

def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    scene = json.loads((root / "fixtures" / "m0_fixtures.json").read_text())
    report = json.loads((root / "results" / "m0_report.json").read_text())

    k = scene["intrinsics"]                      # 3x3-Matrix im JSON
    camera = CameraModel(fx=k[0][0], fy=k[1][1], cx=k[0][2], cy=k[1][2])
    model = MorphableModel(
        mean_vertices=[v for xyz in scene["base"] for v in xyz],
        identity_basis=[v for row in scene["A_id"] for v in row],
        expression_basis=[v for row in scene["A_exp"] for v in row],
        k_id=len(scene["A_id"][0]),
        k_exp=len(scene["A_exp"][0]),
    )
    # JSON ist verschachtelt ([N,2], [N,3]) -- der Kotlin-Kern arbeitet auf
    # flachen Arrays, also wird hier genauso "geplattet" wie beim Erzeugen
    # der Kotlin-Fixtures (numpy reshape(-1)).
    def flat(x):
        out = []
        for row in x:
            if isinstance(row, list):
                out.extend(row)
            else:
                out.append(row)
        return [float(v) for v in out]

    frames = []
    for fr in scene["frames"]:
        frames.append({
            "R_gt": flat(fr["R_gt"]),
            "t_gt": flat(fr["t_gt"]),
            "visibility": flat(fr["visibility"]),
            "points2d": flat(fr["points2d"]),
            "outliers": flat(fr.get("outliers", [])),
        })
    observations = [(fr["points2d"], fr["visibility"]) for fr in frames]

    print("=" * 74)
    print("Kotlin-Spiegel: gleiche Algorithmen, gleiche Index-Arithmetik")
    print("=" * 74)

    # --- F1: Pose -------------------------------------------------------
    rot, tra, ratios = [], [], []
    for fi, fr in enumerate(frames):
        p3, p2 = _visible_subset(model.mean_vertices, fr["points2d"], fr["visibility"])
        est = estimate_pose(camera, p3, p2)
        truth = RigidTransform(Mat3(fr["R_gt"]), fr["t_gt"])
        rot.append(est["transform"].rotation_error_deg(truth))
        tra.append(est["transform"].translation_error_mm(truth))
        ratios.append(est["inlier_ratio"])
    f1_rot = sum(rot) / len(rot)
    f1_tra = sum(tra) / len(tra)
    print(f"F1 Pose : rot={f1_rot:.4f} deg (max {max(rot):.4f})  "
          f"trans={f1_tra:.4f} mm (max {max(tra):.4f})  "
          f"inlier={min(ratios):.2f}-{max(ratios):.2f}")

    # --- F2: Multi-Frame-Fit -------------------------------------------
    res = fit_multiframe(camera, model, observations, verbose=True)

    def mean_dist(a, b):
        return sum(math.dist(a[3 * i:3 * i + 3], b[3 * i:3 * i + 3])
                   for i in range(model.n_vertices)) / model.n_vertices

    # (1) genau wie die numpy-Referenz: wahre Form von Frame 0 (Identitaet +
    #     Mimik) gegen die geschaetzte Form von Frame 0
    shape_true_f0 = model.shape(scene["alpha_true"], scene["beta_true"][0])
    shape_est_f0 = model.shape(res["alpha"], res["betas"][0])
    geom = mean_dist(shape_true_f0, shape_est_f0)
    # (2) zusaetzlich: die NEUTRALE Kopfform (die spaeter exportiert wird)
    shape_true_neutral = model.shape(scene["alpha_true"], [0.0] * model.k_exp)
    geom_neutral = mean_dist(shape_true_neutral, res["final_shape"])

    n = model.n_vertices
    inlier_rms = []
    for fi, fr in enumerate(frames):
        good = [i for i in range(n)
                if fr["visibility"][i] > 0.5 and fr.get("outliers", [0.0] * n)[i] < 0.5]
        if not good:
            continue
        shp = model.shape(res["alpha"], res["betas"][fi])
        proj = [0.0] * (2 * n)
        camera.project_all(res["poses"][fi].rotation, res["poses"][fi].translation, shp, proj)
        acc = 0.0
        for i in good:
            acc += (proj[2 * i] - fr["points2d"][2 * i]) ** 2 + \
                   (proj[2 * i + 1] - fr["points2d"][2 * i + 1]) ** 2
        inlier_rms.append(math.sqrt(acc / len(good)))
    f2_inlier = sum(inlier_rms) / len(inlier_rms)

    rot_f = []
    tra_f = []
    for fi, fr in enumerate(frames):
        truth = RigidTransform(Mat3(fr["R_gt"]), fr["t_gt"])
        rot_f.append(res["poses"][fi].rotation_error_deg(truth))
        tra_f.append(res["poses"][fi].translation_error_mm(truth))

    a_true = scene["alpha_true"][:model.k_id]
    a_est = res["alpha"]
    mean_t = sum(a_true) / len(a_true)
    mean_e = sum(a_est) / len(a_est)
    num = sum((a_true[i] - mean_t) * (a_est[i] - mean_e) for i in range(len(a_true)))
    den = math.sqrt(sum((v - mean_t) ** 2 for v in a_true) *
                   sum((v - mean_e) ** 2 for v in a_est))
    corr = num / den if den > 0 else float("nan")

    print(f"F2 Fit  : repro {res['history'][0]:.4f} -> {res['history'][-1]:.4f} px  "
          f"inlier={f2_inlier:.4f} px")
    print(f"         Geometrie Frame 0 = {geom:.4f} mm | "
          f"neutrale Kopfform = {geom_neutral:.4f} mm")
    print(f"         rot={sum(rot_f)/len(rot_f):.4f} deg  trans={sum(tra_f)/len(tra_f):.4f} mm  "
          f"geom={geom:.4f} mm  alpha_corr={corr:.4f}")

    # --- Vergleich gegen die numpy-Referenz ------------------------------
    ref = report["multiframe"]
    ref_pose = report["pose_only"]
    print("-" * 74)
    print(f"{'Kennzahl':38s}{'numpy-Referenz':>18s}{'Kotlin-Spiegel':>18s}")
    print("-" * 74)
    rows = [
        ("F1 Rotation Mittel (deg)", ref_pose["rot_deg_mean"], f1_rot),
        ("F1 Rotation Max (deg)", ref_pose["rot_deg_max"], max(rot)),
        ("F1 Translation Mittel (mm)", ref_pose["trans_mm_mean"], f1_tra),
        ("F1 Translation Max (mm)", ref_pose["trans_mm_max"], max(tra)),
        ("F2 Repro Start (px)", ref["repro_rms_first_px"], res["history"][0]),
        ("F2 Repro Ende (px)", ref["repro_rms_final_px"], res["history"][-1]),
        ("F2 Inlier-RMS (px)", ref["repro_inlier_rms_px"], f2_inlier),
        ("F2 Rotation Mittel (deg)", ref["rot_err_deg_mean"], sum(rot_f) / len(rot_f)),
        ("F2 Translation Mittel (mm)", ref["trans_err_mm_mean"], sum(tra_f) / len(tra_f)),
        ("F2 Geometrie Frame 0 (mm)", ref["geometry_err_mm_mean"], geom),
        ("F2 Identitaet Korrelation", ref["alpha_corr"], corr),
    ]
    ok = True
    for name, a, b in rows:
        diff = abs(a - b)
        tol = max(0.02 * max(abs(a), 1e-9), 1e-3)
        flag = "OK " if diff <= tol else "ABW"
        ok = ok and diff <= tol
        print(f"{name:38s}{a:18.5f}{b:18.5f}  {flag}")
    print("-" * 74)
    print("ERGEBNIS:", "Spiegel stimmt mit der Referenz ueberein."
          if ok else "Abweichung -> Index-/Formelfehler im Kotlin-Kern suchen.")

    # --- Zuordnung der Kotlin-Konstanten ---------------------------------
    # Der Generator schreibt FUENF F2-Konstanten und VIER F1-Konstanten in
    # M0Fixtures.kt. Ein Test hat einmal die F2-Zahlen gegen ein F1-Ergebnis
    # geprueft; der Fehler fiel erst in der CI auf. Darum wird hier die
    # Zuordnung selbst geprueft: jede Konstante muss zu der Kennzahl passen,
    # die unter diesem Namen gemessen wird.
    fx = _kotlin_constants(root.parent / "android" / "app" / "src" / "main" / "java"
                           / "com" / "andrexthedev" / "facescan" / "geometry"
                           / "M0Fixtures.kt")
    pairs = [
        ("F1 Rotation Mittel", fx.get("expectedPoseOnlyRotDegMean"), f1_rot),
        ("F1 Rotation Max", fx.get("expectedPoseOnlyRotDegMax"), max(rot)),
        ("F1 Translation Mittel", fx.get("expectedPoseOnlyTransMmMean"), f1_tra),
        ("F1 Translation Max", fx.get("expectedPoseOnlyTransMmMax"), max(tra)),
        ("F2 Rotation Mittel", fx.get("expectedRotDegMean"), sum(rot_f) / len(rot_f)),
        ("F2 Translation Mittel", fx.get("expectedTransMmMean"), sum(tra_f) / len(tra_f)),
        ("F2 Geometrie", fx.get("expectedGeometryMm"), geom),
        ("F2 Inlier-RMS", fx.get("expectedInlierRmsPx"), f2_inlier),
        ("F2 Repro Ende", fx.get("expectedReproFinalPx"), res["history"][-1]),
    ]
    print()
    print("Zuordnung der Kotlin-Konstanten (F1 = Pose je Frame, F2 = Gesamtfit)")
    paired = True
    for name, want, got in pairs:
        if want is None:
            print(f"  {name:26s} FEHLT in M0Fixtures.kt")
            paired = False
            continue
        diff = abs(want - got)
        tol = max(0.02 * max(abs(want), 1e-9), 1e-3)
        good = diff <= tol
        paired = paired and good
        print(f"  {name:26s} Konstante {want:10.6f}  Spiegel {got:10.6f}  "
              f"{'OK ' if good else 'FALSCH ZUGEORDNET'}")
    print("  ->", "Konstanten passen zu ihren Kennzahlen." if paired
          else "Konstante gehoert zu einer anderen Kennzahl (F1/F2 verwechselt?).")
    return 0 if (ok and paired) else 1


def _kotlin_constants(path):
    """Liest 'const val NAME = ZAHL' aus einer Kotlin-Quelldatei."""
    import re
    out = {}
    for m in re.finditer(r"const\s+val\s+(\w+)\s*=\s*(-?[\d.eE+-]+)", path.read_text()):
        try:
            out[m.group(1)] = float(m.group(2))
        except ValueError:
            pass
    return out


if __name__ == "__main__":
    sys.exit(main())

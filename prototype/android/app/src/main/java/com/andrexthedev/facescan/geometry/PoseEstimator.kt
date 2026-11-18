package com.andrexthedev.facescan.geometry

import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Starre Kameratransformation: Rotation + Translation (Welt -> Kamera).
 * Translation in der Einheit der vom Aufrufer bereitgestellten 3D-Anker.
 */
data class RigidTransform(val rotation: Mat3, val translation: DoubleArray) {
    fun translationErrorMm(other: RigidTransform): Double {
        val dx = translation[0] - other.translation[0]
        val dy = translation[1] - other.translation[1]
        val dz = translation[2] - other.translation[2]
        return sqrt(dx * dx + dy * dy + dz * dz)
    }

    fun rotationErrorDeg(other: RigidTransform): Double =
        Mat3.rotationErrorDeg(rotation, other.rotation)
}

data class PoseEstimate(
    val transform: RigidTransform,
    val rmsPx: Double,
    val medianPx: Double,
    val inlierRatio: Double
)

/**
 * Kameraposenschaetzung OHNE ARCore, OHNE SLAM, OHNE Tiefensensor.
 *
 * Rezept (in Python gegen Ground Truth validiert, siehe
 * prototype/reference/python/run_m0.py):
 *   1. POSIT-Initialisierung (skaliert-orthographisch, geschlossene Loesung)
 *   2. Gauss-Newton-Verfeinerung unter voller Perspektive
 *   3. IRLS mit Huber-Gewichten gegen Ausreisser (verdeckte/verkannte Punkte)
 *
 * Eingang: 3D-Anker (N*3, gemeinsame Einheit) und entzerrte 2D-Pixel (N*2).
 * Ausgang: Pose in der Einheit der Eingabeanker. Eine metrische Pose ergibt sich
 * nur bei korrekten metrischen Ankern und kalibrierter Kamera; synthetische
 * Tests belegen keine reale Genauigkeit. Nicht im Scanablauf angeschlossen.
 *
 * Referenz: DeMenthon & Davis, "Model-Based Object Pose in 25 Lines of Code".
 */
object PoseEstimator {

    private const val POSIT_ITERS = 12
    private const val GN_ITERS = 12
    private const val IRLS_ITERS = 6
    private const val HUBER_K = 1.5

    /**
     * POSIT: Startwert aus der skaliert-orthographischen Naeherung.
     * Benoetigt kein RANSAC und keine Korrespondenzsuche – wir haben die
     * Korrespondenzen (Landmark-Index <-> Modellvertex) bereits.
     */
    fun positInit(
        camera: CameraModel,
        points3d: DoubleArray,
        points2d: DoubleArray,
        iters: Int = POSIT_ITERS
    ): RigidTransform {
        val n = points3d.size / 3
        require(points2d.size == 2 * n) { "Anzahl 2D- und 3D-Punkte passt nicht" }

        // Normalisierte Bildstrahlen: x~ = K^-1 [u,v,1]
        val rx = DoubleArray(n)
        val ry = DoubleArray(n)
        for (i in 0 until n) {
            rx[i] = (points2d[2 * i] - camera.cx) / camera.fx
            ry[i] = (points2d[2 * i + 1] - camera.cy) / camera.fy
        }

        // Designzeile je Punkt: [X, Y, Z, 1]
        val design = DoubleArray(n * 4)
        for (i in 0 until n) {
            design[4 * i] = points3d[3 * i]
            design[4 * i + 1] = points3d[3 * i + 1]
            design[4 * i + 2] = points3d[3 * i + 2]
            design[4 * i + 3] = 1.0
        }

        var r3 = doubleArrayOf(0.0, 0.0, 0.0)
        var tz = 1.0
        var p = DoubleArray(4)
        var q = DoubleArray(4)

        repeat(iters) {
            // w_i = r3 · X_i  (aus der vorigen Iteration; Start: rein orthographisch)
            val rhs1 = DoubleArray(n)
            val rhs2 = DoubleArray(n)
            for (i in 0 until n) {
                val w = r3[0] * points3d[3 * i] + r3[1] * points3d[3 * i + 1] + r3[2] * points3d[3 * i + 2]
                rhs1[i] = rx[i] * (w + 1.0)
                rhs2[i] = ry[i] * (w + 1.0)
            }
            val pNew = Linalg.leastSquares(design, rhs1, n, 4) ?: return@repeat
            val qNew = Linalg.leastSquares(design, rhs2, n, 4) ?: return@repeat
            p = pNew
            q = qNew

            val normP = sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2])
            val normQ = sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2])
            val scale = sqrt(normP * normQ)
            if (scale < 1e-12) return@repeat
            tz = 1.0 / scale

            val r1 = doubleArrayOf(p[0] * tz, p[1] * tz, p[2] * tz)
            val r2 = doubleArrayOf(q[0] * tz, q[1] * tz, q[2] * tz)
            val cross = doubleArrayOf(
                r1[1] * r2[2] - r1[2] * r2[1],
                r1[2] * r2[0] - r1[0] * r2[2],
                r1[0] * r2[1] - r1[1] * r2[0]
            )
            val nrm = sqrt(cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2])
            if (nrm < 1e-12) return@repeat
            r3 = doubleArrayOf(cross[0] / nrm / tz, cross[1] / nrm / tz, cross[2] / nrm / tz)
        }

        val r1 = doubleArrayOf(p[0] * tz, p[1] * tz, p[2] * tz)
        val r2 = doubleArrayOf(q[0] * tz, q[1] * tz, q[2] * tz)
        val r3n = normalize(
            doubleArrayOf(
                r1[1] * r2[2] - r1[2] * r2[1],
                r1[2] * r2[0] - r1[0] * r2[2],
                r1[0] * r2[1] - r1[1] * r2[0]
            )
        )
        val r2n = normalize(
            doubleArrayOf(
                r3n[1] * r1[2] - r3n[2] * r1[1],
                r3n[2] * r1[0] - r3n[0] * r1[2],
                r3n[0] * r1[1] - r3n[1] * r1[0]
            )
        )
        val rotation = Mat3(
            doubleArrayOf(
                r1[0], r1[1], r1[2],
                r2n[0], r2n[1], r2n[2],
                r3n[0], r3n[1], r3n[2]
            )
        ).orthonormalize()
        val translation = doubleArrayOf(p[3] * tz, q[3] * tz, tz)
        return RigidTransform(rotation, translation)
    }

    /**
     * Analytische Jacobi-Matrix der Projektion nach der 6-DOF-Pose (2x6 je Punkt).
     *
     * Parametrisierung – MUSS zur Aktualisierung in [refine] passen:
     *     R_neu = exp(w^) * R     (Links-Perturbation, w im Kameraraum)
     *     t_neu = t + dt          (unabhaengig)
     *
     * Daraus folgt:
     *     dp/dw = -[R x]_x   (Hebelarm ist der ROTIERTE Punkt, OHNE Translation)
     *     dp/dt = I
     *
     * ACHTUNG (haeufiger und folgenreicher Fehler): Wer hier p = R*x + t als
     * Hebelarm einsetzt, linearisiert eine Kamerafahrt um den Kopfmittelpunkt
     * (Orbit), aktualisiert aber wie eine Objektdrehung. Der Fehler ist nicht
     * klein (in unseren Szenarien ueber 300 % relativ) und erzeugt eine
     * systematische Schiefe, die auch mit mehr Iterationen nicht verschwindet.
     * Gegen finite Differenzen geprueft: max. Abweichung 1.4e-10 relativ.
     */
    internal fun poseJacobianRow(
        camera: CameraModel,
        x: DoubleArray,
        rotation: Mat3,
        translation: DoubleArray,
        out: DoubleArray
    ) {
        val xr = rotation.times(x)                        // Hebelarm der Rotation
        val px = xr[0] + translation[0]                   // Punkt im Kameraraum
        val py = xr[1] + translation[1]
        val pz = xr[2] + translation[2]
        val z = if (abs(pz) < 1e-9) 1e-9 else pz
        val fx = camera.fx
        val fy = camera.fy

        // d(uv)/d(X_cam)   (2x3)
        val a00 = fx / z
        val a02 = -fx * px / (z * z)
        val a11 = fy / z
        val a12 = -fy * py / (z * z)

        // -skew(xr) = [[0, xr_z, -xr_y], [-xr_z, 0, xr_x], [xr_y, -xr_x, 0]]
        out[0] = a02 * xr[1]                              // d u / d wx
        out[1] = a00 * xr[2] - a02 * xr[0]                // d u / d wy
        out[2] = -a00 * xr[1]                             // d u / d wz
        out[3] = a00                                      // d u / d tx
        out[4] = 0.0
        out[5] = a02                                      // d u / d tz

        out[6] = -a11 * xr[2] + a12 * xr[1]               // d v / d wx
        out[7] = -a12 * xr[0]                             // d v / d wy
        out[8] = a11 * xr[0]                              // d v / d wz
        out[9] = 0.0
        out[10] = a11                                     // d v / d ty
        out[11] = a12                                     // d v / d tz
    }

    /**
     * Gauss-Newton-Verfeinerung (Levenberg-Daempfung, Huber-Gewichte).
     * [weights] hat 2N Eintraege (je Punkt eine Gewichtung fuer u und v).
     */
    fun refine(
        camera: CameraModel,
        points3d: DoubleArray,
        points2d: DoubleArray,
        init: RigidTransform,
        weights: DoubleArray
    ): RigidTransform {
        val n = points3d.size / 3
        val proj = DoubleArray(2 * n)
        val trial = DoubleArray(2 * n)
        val jRow = DoubleArray(12)

        var omega = DoubleArray(3)
        var dt = DoubleArray(3)
        var lambda = 1e-4
        var currentError = Double.POSITIVE_INFINITY

        repeat(GN_ITERS) {
            val rCur = Mat3.fromRodrigues(omega) * init.rotation
            val tCur = doubleArrayOf(
                init.translation[0] + dt[0],
                init.translation[1] + dt[1],
                init.translation[2] + dt[2]
            )
            camera.projectAll(rCur, tCur, points3d, proj)
            var err = 0.0
            for (i in 0 until 2 * n) {
                val r = proj[i] - points2d[i]
                err += weights[i] * r * r
            }
            currentError = err

            // Normalgleichungen (6x6)
            val jtj = DoubleArray(36)
            val g = DoubleArray(6)
            for (i in 0 until n) {
                val x = doubleArrayOf(points3d[3 * i], points3d[3 * i + 1], points3d[3 * i + 2])
                poseJacobianRow(camera, x, rCur, tCur, jRow)
                for (a in 0 until 2) {
                    val rowIdx = 2 * i + a
                    val w = weights[rowIdx]
                    val res = proj[rowIdx] - points2d[rowIdx]
                    for (r in 0 until 6) {
                        val jr = jRow[a * 6 + r]
                        g[r] -= w * jr * res
                        for (c in r until 6) {
                            jtj[r * 6 + c] += w * jr * jRow[a * 6 + c]
                        }
                    }
                }
            }
            for (r in 0 until 6) {
                for (c in 0 until r) jtj[r * 6 + c] = jtj[c * 6 + r]
                jtj[r * 6 + r] *= (1.0 + lambda)
                jtj[r * 6 + r] += lambda * 1e-9
            }

            var accepted = false
            repeat(8) {
                val step = Linalg.solveSpd(jtj, g, 6)
                if (step == null) {                 // singulaer -> staerker daempfen, nochmal
                    lambda *= 10.0
                    return@repeat
                }
                val omegaNew = doubleArrayOf(omega[0] + step[0], omega[1] + step[1], omega[2] + step[2])
                val dtNew = doubleArrayOf(dt[0] + step[3], dt[1] + step[4], dt[2] + step[5])
                val rNew = Mat3.fromRodrigues(omegaNew) * init.rotation
                val tNew = doubleArrayOf(
                    init.translation[0] + dtNew[0],
                    init.translation[1] + dtNew[1],
                    init.translation[2] + dtNew[2]
                )
                camera.projectAll(rNew, tNew, points3d, trial)
                var errNew = 0.0
                for (i in 0 until 2 * n) {
                    val r = trial[i] - points2d[i]
                    errNew += weights[i] * r * r
                }
                if (errNew < currentError) {
                    omega = omegaNew
                    dt = dtNew
                    lambda = (lambda * 0.5).coerceAtLeast(1e-8)
                    accepted = true
                    return@repeat
                }
                lambda *= 10.0                      // Schritt abgelehnt -> kuerzer treten
            }
            if (!accepted) return@repeat            // kein Fortschritt mehr -> fertig
        }

        val rFinal = Mat3.fromRodrigues(omega) * init.rotation
        val tFinal = doubleArrayOf(
            init.translation[0] + dt[0],
            init.translation[1] + dt[1],
            init.translation[2] + dt[2]
        )
        return RigidTransform(rFinal, tFinal)
    }

    /** Robuste Schaetzung: POSIT (oder gegebener Startwert) + IRLS + GN. */
    fun estimate(
        camera: CameraModel,
        points3d: DoubleArray,
        points2d: DoubleArray,
        init: RigidTransform? = null
    ): PoseEstimate {
        val n = points3d.size / 3
        var pose = init ?: positInit(camera, points3d, points2d)
        val weights = DoubleArray(2 * n) { 1.0 }

        repeat(IRLS_ITERS) {
            pose = refine(camera, points3d, points2d, pose, weights)
            val proj = DoubleArray(2 * n)
            camera.projectAll(pose.rotation, pose.translation, points3d, proj)
            val residuals = DoubleArray(2 * n)
            for (i in 0 until 2 * n) residuals[i] = proj[i] - points2d[i]
            val sigma = Linalg.madSigma(residuals)
            for (i in 0 until 2 * n) {
                val a = abs(residuals[i]) / (HUBER_K * sigma)
                weights[i] = if (a <= 1.0) 1.0 else 1.0 / a.coerceAtLeast(1e-6)
            }
        }

        // Kennzahlen
        val proj = DoubleArray(2 * n)
        camera.projectAll(pose.rotation, pose.translation, points3d, proj)
        var sumSq = 0.0
        var inliers = 0
        val perPoint = DoubleArray(n)
        for (i in 0 until n) {
            val du = proj[2 * i] - points2d[2 * i]
            val dv = proj[2 * i + 1] - points2d[2 * i + 1]
            perPoint[i] = sqrt(du * du + dv * dv)
            sumSq += du * du + dv * dv
            val w = 0.5 * (weights[2 * i] + weights[2 * i + 1])
            if (w > 0.5) inliers++
        }
        return PoseEstimate(
            transform = pose,
            rmsPx = sqrt(sumSq / n),
            medianPx = Linalg.median(perPoint),
            inlierRatio = inliers.toDouble() / n
        )
    }

    private fun normalize(v: DoubleArray): DoubleArray {
        val n = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        return if (n < 1e-12) doubleArrayOf(0.0, 0.0, 1.0)
        else doubleArrayOf(v[0] / n, v[1] / n, v[2] / n)
    }
}

package com.andrexthedev.facescan.geometry

import kotlin.math.sqrt

/** Eine Beobachtung: 2D-Landmarks (2N, px) + Sichtbarkeit je Punkt (N, 1.0/0.0). */
data class Observation(
    val landmarks: DoubleArray,
    val visibility: DoubleArray,
    /** Optionaler Startwert der Pose, z. B. aus der MediaPipe-Transformationsmatrix. */
    val initialPose: RigidTransform? = null
)

data class FitOptions(
    val lambdaIdentity: Double = 1e-2,
    val lambdaExpression: Double = 3e-2,
    val outerIterations: Int = 8,
    val convergencePx: Double = 1e-4
)

data class FitResult(
    val alpha: DoubleArray,               // geteilte Identitaet (alle Frames)
    val betas: List<DoubleArray>,         // Mimik je Frame
    val poses: List<RigidTransform>,      // Kamerapose je Frame
    val reproHistory: DoubleArray,        // Reprojektionsfehler je aeusserer Iteration (px)
    val finalShape: DoubleArray           // neutrale Form (alpha, beta = 0)
)

/**
 * Multi-Frame-Fit: geteilte Identitaet, Pose und Mimik je Frame.
 *
 * Abwechselnde Optimierung (1:1 zur validierten Python-Referenz
 * prototype/reference/python/facescan_ref/fit.py):
 *
 *   (0) Posen gegen das MITTLERE Gesicht schaetzen
 *   (a) Form  : ein Gauss-Newton-Schritt, skaliert-orthographisch um die
 *               aktuelle Form und Pose linearisiert
 *   (b) Pose  : nichtlinear, 6 DOF, Huber-robust, warm gestartet ([PoseEstimator])
 *   (c) Ende, wenn sich der Reprojektionsfehler kaum noch aendert
 *
 * Zwei Fallen, die hier bewusst vermieden sind und die man beim Nachbauen
 * unbedingt kennen sollte:
 *   1. Linearisiert werden muss um die AKTUELLE Form, nicht um das
 *      Mittelgesicht – sonst faellt die aeussere Schleife auf einen
 *      flachen Punkt und "konvergiert" im ersten Schritt.
 *   2. J^T J braucht die VOLLEN Kreuzterme (Identitaet x Ausdruck). Nur die
 *      Diagonale zu fuellen sieht harmlos aus, ist aber ein anderes
 *      (Jacobi-)Verfahren und liefert andere Ergebnisse als die Referenz.
 */
object ModelFitter {

    fun fit(
        camera: CameraModel,
        model: MorphableModel,
        observations: List<Observation>,
        options: FitOptions = FitOptions()
    ): FitResult {
        val f = observations.size
        require(f > 0) { "Mindestens eine Beobachtung noetig" }
        val n = model.nVertices
        val n3 = n * 3
        val kId = model.kIdentity
        val kExp = model.kExpression
        val nUnknowns = kId + f * kExp

        // --- (0) Posen gegen das mittlere Gesicht initialisieren ------------
        val poses = MutableList(f) { index ->
            val (p3, p2) = visibleSubset(model.meanVertices, observations[index])
            val start = observations[index].initialPose
            PoseEstimator.estimate(camera, p3, p2, start).transform
        }

        var alpha = DoubleArray(kId)
        val betas = MutableList(f) { DoubleArray(kExp) }

        val jtj = DoubleArray(nUnknowns * nUnknowns)
        val jtr = DoubleArray(nUnknowns)
        val pred = DoubleArray(2 * n)
        val shape = DoubleArray(n3)
        val history = ArrayList<Double>()

        // Lokale Spalten je Frame: [Identitaet(kId) | Ausdruck des Frames(kExp)]
        val localN = kId + kExp
        val jU = DoubleArray(localN)
        val jV = DoubleArray(localN)
        val globalIndex = IntArray(localN)

        var previousError = Double.POSITIVE_INFINITY

        repeat(options.outerIterations) {

            // --- (a) Form-Schritt ------------------------------------------
            jtj.fill(0.0)
            jtr.fill(0.0)
            for (u in 0 until kId) jtj[u * nUnknowns + u] = options.lambdaIdentity
            for (fi in 0 until f) {
                val base = kId + fi * kExp
                for (u in 0 until kExp) jtj[(base + u) * nUnknowns + (base + u)] = options.lambdaExpression
            }

            for (fi in 0 until f) {
                val obs = observations[fi]
                val pose = poses[fi]
                val r = pose.rotation

                // Skala der Orthographie: Brennweite / mittlere Tiefe des
                // MITTELGESICHTS (genau wie in der Referenz – Abweichung ~1 %
                // bei 62 deg FOV und 50 cm Abstand; die volle Perspektive
                // steckt im anschliessenden Posen-Schritt).
                val meanZ = camera.meanDepth(pose.rotation, pose.translation, model.meanVertices)
                if (meanZ < 1e-6) continue
                val s = camera.fx / meanZ

                model.shape(alpha, betas[fi], shape)
                camera.projectAll(pose.rotation, pose.translation, shape, pred)

                for (k in 0 until kId) globalIndex[k] = k
                for (k in 0 until kExp) globalIndex[kId + k] = kId + fi * kExp + k

                for (i in 0 until n) {
                    if (obs.visibility[i] < 0.5) continue

                    // Komponentenweises Layout: die drei Komponenten eines
                    // Vertex liegen je Mode hintereinander.
                    val i3 = 3 * i
                    for (k in 0 until kId) {
                        val off = i3 * kId + k
                        jU[k] = s * (r[0, 0] * model.identityBasis[off] +
                            r[0, 1] * model.identityBasis[off + kId] +
                            r[0, 2] * model.identityBasis[off + 2 * kId])
                        jV[k] = s * (r[1, 0] * model.identityBasis[off] +
                            r[1, 1] * model.identityBasis[off + kId] +
                            r[1, 2] * model.identityBasis[off + 2 * kId])
                    }
                    for (k in 0 until kExp) {
                        val off = i3 * kExp + k
                        jU[kId + k] = s * (r[0, 0] * model.expressionBasis[off] +
                            r[0, 1] * model.expressionBasis[off + kExp] +
                            r[0, 2] * model.expressionBasis[off + 2 * kExp])
                        jV[kId + k] = s * (r[1, 0] * model.expressionBasis[off] +
                            r[1, 1] * model.expressionBasis[off + kExp] +
                            r[1, 2] * model.expressionBasis[off + 2 * kExp])
                    }

                    val resU = obs.landmarks[2 * i] - pred[2 * i]
                    val resV = obs.landmarks[2 * i + 1] - pred[2 * i + 1]

                    for (c in 0 until localN) {
                        jtr[globalIndex[c]] += jU[c] * resU + jV[c] * resV
                    }
                    for (a in 0 until localN) {
                        val ga = globalIndex[a]
                        for (b in a until localN) {
                            jtj[ga * nUnknowns + globalIndex[b]] += jU[a] * jU[b] + jV[a] * jV[b]
                        }
                    }
                }
            }
            symmetrize(jtj, nUnknowns)
            val delta = Linalg.solveSpd(jtj, jtr, nUnknowns)
            if (delta != null) {
                for (k in 0 until kId) alpha[k] += delta[k]
                for (fi in 0 until f) {
                    for (k in 0 until kExp) betas[fi][k] += delta[kId + fi * kExp + k]
                }
            }

            // --- (b) Posen-Schritt (warm gestartet) -------------------------
            for (fi in 0 until f) {
                model.shape(alpha, betas[fi], shape)
                val (p3, p2) = visibleSubset(shape, observations[fi])
                poses[fi] = PoseEstimator.estimate(camera, p3, p2, poses[fi]).transform
            }

            // --- Fehlerverlauf: RMS je Frame, dann gemittelt ----------------
            var sumPerFrame = 0.0
            for (fi in 0 until f) {
                model.shape(alpha, betas[fi], shape)
                camera.projectAll(poses[fi].rotation, poses[fi].translation, shape, pred)
                var sumSq = 0.0
                var count = 0
                for (i in 0 until n) {
                    if (observations[fi].visibility[i] < 0.5) continue
                    val du = pred[2 * i] - observations[fi].landmarks[2 * i]
                    val dv = pred[2 * i + 1] - observations[fi].landmarks[2 * i + 1]
                    sumSq += du * du + dv * dv
                    count++
                }
                if (count > 0) sumPerFrame += sqrt(sumSq / count)
            }
            val rms = sumPerFrame / f
            history.add(rms)
            if (kotlin.math.abs(previousError - rms) < options.convergencePx) {
                previousError = rms
                return@repeat
            }
            previousError = rms
        }

        val finalShape = model.shape(alpha, DoubleArray(kExp))
        return FitResult(alpha, betas, poses, history.toDoubleArray(), finalShape)
    }

    /** Reduziert Punkte/Landmarks auf die sichtbaren Korrespondenzen. */
    private fun visibleSubset(points3d: DoubleArray, obs: Observation): Pair<DoubleArray, DoubleArray> {
        val n = points3d.size / 3
        var count = 0
        for (i in 0 until n) if (obs.visibility[i] >= 0.5) count++
        val p3 = DoubleArray(count * 3)
        val p2 = DoubleArray(count * 2)
        var w = 0
        for (i in 0 until n) {
            if (obs.visibility[i] < 0.5) continue
            p3[3 * w] = points3d[3 * i]
            p3[3 * w + 1] = points3d[3 * i + 1]
            p3[3 * w + 2] = points3d[3 * i + 2]
            p2[2 * w] = obs.landmarks[2 * i]
            p2[2 * w + 1] = obs.landmarks[2 * i + 1]
            w++
        }
        return p3 to p2
    }

    /** Spiegelt das obere Dreieck nach unten und daempft die Diagonale minimal. */
    private fun symmetrize(a: DoubleArray, n: Int) {
        for (i in 0 until n) {
            for (j in 0 until i) a[i * n + j] = a[j * n + i]
            a[i * n + i] += 1e-9
        }
    }
}

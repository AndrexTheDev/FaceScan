package com.andrexthedev.facescan.geometry

import java.util.Locale
import kotlin.math.abs
import kotlin.math.sqrt

/** M0-Referenzprüfung mit rein synthetischen Daten, nicht mit dem Gesicht des Nutzers. */
object GeometrySelfTest {
    data class Result(val passed: Boolean, val details: String)

    fun run(): Result {
        val start = System.nanoTime()
        val camera = TestData.camera()
        var sumRot = 0.0
        var sumTrans = 0.0
        var maxRot = 0.0
        var maxTrans = 0.0
        for (f in 0 until M0Fixtures.N_FRAMES) {
            val (p3, p2) = TestData.visibleCorrespondences(f, M0Fixtures.baseVertices)
            val pose = PoseEstimator.estimate(camera, p3, p2).transform
            val truth = TestData.groundTruth(f)
            val rot = pose.rotationErrorDeg(truth)
            val trans = pose.translationErrorMm(truth)
            sumRot += rot
            sumTrans += trans
            maxRot = maxOf(maxRot, rot)
            maxTrans = maxOf(maxTrans, trans)
        }
        val f1Rot = sumRot / M0Fixtures.N_FRAMES
        val f1Trans = sumTrans / M0Fixtures.N_FRAMES
        val f1Ok = f1Rot.isFinite() && f1Trans.isFinite() &&
            abs(f1Rot - M0Fixtures.expectedPoseOnlyRotDegMean) < 0.05 &&
            abs(f1Trans - M0Fixtures.expectedPoseOnlyTransMmMean) < 0.05 &&
            maxRot < M0Fixtures.expectedPoseOnlyRotDegMax * 1.1 &&
            maxTrans < M0Fixtures.expectedPoseOnlyTransMmMax * 1.1

        val model = TestData.model()
        val fit = ModelFitter.fit(camera, model, TestData.observations())
        var fitRot = 0.0
        var fitTrans = 0.0
        for (f in 0 until M0Fixtures.N_FRAMES) {
            val truth = TestData.groundTruth(f)
            fitRot += fit.poses[f].rotationErrorDeg(truth)
            fitTrans += fit.poses[f].translationErrorMm(truth)
        }
        fitRot /= M0Fixtures.N_FRAMES
        fitTrans /= M0Fixtures.N_FRAMES
        val trueShape = model.shape(M0Fixtures.alphaTrue, M0Fixtures.betaTrueFrame0)
        val fittedShape = model.shape(fit.alpha, fit.betas[0])
        val geometry = model.meanVertexDistance(trueShape, fittedShape)
        val repro = fit.reproHistory.last()
        var sumSq = 0.0
        var inlierCount = 0
        val projection = DoubleArray(2 * model.nVertices)
        for (f in 0 until M0Fixtures.N_FRAMES) {
            val shape = model.shape(fit.alpha, fit.betas[f])
            camera.projectAll(fit.poses[f].rotation, fit.poses[f].translation, shape, projection)
            val points = TestData.landmarks(f)
            val visible = TestData.visibility(f)
            val outliers = TestData.outliers(f)
            for (i in 0 until model.nVertices) {
                if (visible[i] < 0.5 || outliers[i] > 0.5) continue
                val du = projection[2 * i] - points[2 * i]
                val dv = projection[2 * i + 1] - points[2 * i + 1]
                sumSq += du * du + dv * dv
                inlierCount++
            }
        }
        val inlierRms = if (inlierCount > 0) sqrt(sumSq / inlierCount) else Double.NaN
        val f2Ok = fitRot.isFinite() && fitTrans.isFinite() && geometry.isFinite() && repro.isFinite() && inlierRms.isFinite() &&
            abs(fitRot - M0Fixtures.expectedRotDegMean) < 0.05 &&
            abs(fitTrans - M0Fixtures.expectedTransMmMean) < 0.05 &&
            abs(geometry - M0Fixtures.expectedGeometryMm) < 0.05 &&
            abs(repro - M0Fixtures.expectedReproFinalPx) < 0.05 &&
            abs(inlierRms - M0Fixtures.expectedInlierRmsPx) < 0.05 &&
            repro <= fit.reproHistory.first() + 1e-9
        val elapsedMs = (System.nanoTime() - start) / 1_000_000
        val details = String.format(Locale.US,
            "F1 %s (Rotation %.4f deg, Translation %.4f mm); F2 %s (Rotation %.4f deg, Translation %.4f mm, Geometrie %.4f mm, Reprojektion %.4f px, Inlier-RMS %.4f px); %d ms",
            if (f1Ok) "bestanden" else "fehlgeschlagen", f1Rot, f1Trans,
            if (f2Ok) "bestanden" else "fehlgeschlagen", fitRot, fitTrans, geometry, repro, inlierRms, elapsedMs)
        return Result(f1Ok && f2Ok, details)
    }
}

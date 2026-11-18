package com.andrexthedev.facescan.geometry

import kotlin.math.abs

/** Schätzt eine Kamerapose aus bekannten starren 3D-Ankern und entzerrten Pixeln. */
object ValidatedAnchorPose {
    data class Anchor(val world: DoubleArray, val u: Double, val v: Double)
    enum class Failure { INVALID_INPUT, DEGENERATE_ANCHORS, ESTIMATION_FAILED, BEHIND_CAMERA, HIGH_RESIDUAL }
    sealed class Result {
        data class Pose(val transform: RigidTransform, val rmsPixels: Double, val inlierRatio: Double) : Result()
        data class Rejected(val reason: Failure) : Result()
    }

    /**
     * Die Anker müssen im selben Weltkoordinatensystem wie die zu rekonstruierenden
     * Punkte liegen. Die Translation erhält ausschließlich die Einheit der Anker.
     * Kleine Fit-Reste garantieren keine richtigen Anker oder metrische Genauigkeit.
     */
    fun estimate(camera: CameraModel, anchors: List<Anchor>, maxRmsPixels: Double = 3.0,
                 minInlierRatio: Double = 0.7): Result {
        fun reject(reason: Failure): Result = Result.Rejected(reason)
        if (anchors.size !in 6..128 || !camera.fx.isFinite() || !camera.fy.isFinite() ||
            camera.fx <= 0 || camera.fy <= 0 || !camera.cx.isFinite() || !camera.cy.isFinite() ||
            !maxRmsPixels.isFinite() || maxRmsPixels <= 0 || !minInlierRatio.isFinite() || minInlierRatio !in 0.0..1.0 ||
            anchors.any { it.world.size != 3 || it.world.any { v -> !v.isFinite() } || !it.u.isFinite() || !it.v.isFinite() })
            return reject(Failure.INVALID_INPUT)
        val center = DoubleArray(3) { axis -> anchors.sumOf { it.world[axis] / anchors.size } }
        if (center.any { !it.isFinite() }) return reject(Failure.INVALID_INPUT)
        val covariance = DoubleArray(9)
        for (a in anchors) for (row in 0..2) for (col in 0..2)
            covariance[3*row+col] += (a.world[row]-center[row]) * (a.world[col]-center[col]) / anchors.size
        val trace = covariance[0] + covariance[4] + covariance[8]
        if (!trace.isFinite() || trace <= 1e-18) return reject(Failure.DEGENERATE_ANCHORS)
        val normalized = Mat3(DoubleArray(9) { covariance[it] / trace })
        if (!normalized.determinant().isFinite() || normalized.determinant() < 1e-8) return reject(Failure.DEGENERATE_ANCHORS)
        val world = DoubleArray(anchors.size * 3) { anchors[it / 3].world[it % 3] }
        val image = DoubleArray(anchors.size * 2) { if (it % 2 == 0) anchors[it / 2].u else anchors[it / 2].v }
        val estimate = try { PoseEstimator.estimate(camera, world, image) }
            catch (_: Exception) { return reject(Failure.ESTIMATION_FAILED) }
        val transform = estimate.transform
        if (transform.translation.size != 3 || transform.translation.any { !it.isFinite() } ||
            transform.rotation.m.any { !it.isFinite() } || abs(transform.rotation.determinant() - 1.0) > 1e-5 ||
            !estimate.rmsPx.isFinite() || !estimate.inlierRatio.isFinite()) return reject(Failure.ESTIMATION_FAILED)
        for (anchor in anchors) {
            val depth = transform.rotation.times(anchor.world)[2] + transform.translation[2]
            if (!depth.isFinite() || depth <= 1e-9) return reject(Failure.BEHIND_CAMERA)
        }
        if (estimate.rmsPx > maxRmsPixels || estimate.inlierRatio < minInlierRatio) return reject(Failure.HIGH_RESIDUAL)
        return Result.Pose(transform, estimate.rmsPx, estimate.inlierRatio)
    }
}

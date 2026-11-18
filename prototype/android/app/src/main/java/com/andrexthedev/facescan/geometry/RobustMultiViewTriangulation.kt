package com.andrexthedev.facescan.geometry

/** Kleine, deterministische Konsenssuche für wenige Ansichten; keine Identitätsprüfung. */
object RobustMultiViewTriangulation {
    sealed class Result {
        data class Point(val fit: MultiViewTriangulation.Result.Point, val inliers: List<Int>) : Result()
        data class Rejected(val reason: MultiViewTriangulation.Failure) : Result()
    }

    /**
     * Nur mindestens drei und strikt mehr als die Hälfte aller Beobachtungen
     * dürfen einen Konsens bilden. Aus allen Paaren erzeugte Hypothesen werden
     * mittels Pixelrest bewertet und der Konsens wird neu trianguliert.
     * Maximal 32 Beobachtungen; keine statistische Genauigkeitsgarantie.
     */
    fun triangulate(
        observations: List<MultiViewTriangulation.Observation>,
        minParallaxDegrees: Double = 1.0,
        maxReprojectionPixels: Double = 2.0
    ): Result {
        if (observations.size !in 3..32) return Result.Rejected(MultiViewTriangulation.Failure.INVALID_INPUT)
        val all = MultiViewTriangulation.triangulate(observations, minParallaxDegrees, maxReprojectionPixels)
        if (all is MultiViewTriangulation.Result.Point) return Result.Point(all, observations.indices.toList())
        if (all is MultiViewTriangulation.Result.Rejected && all.reason == MultiViewTriangulation.Failure.INVALID_INPUT)
            return Result.Rejected(all.reason)
        val minInliers = maxOf(3, observations.size / 2 + 1)
        fun residual(point: DoubleArray, obs: MultiViewTriangulation.Observation): Double {
            val p = obs.worldToCamera.times(point)
            for (axis in 0..2) p[axis] += obs.translation[axis]
            if (p.any { !it.isFinite() } || p[2] <= 1e-9) return Double.POSITIVE_INFINITY
            return Math.hypot(obs.camera.fx * p[0] / p[2] + obs.camera.cx - obs.u,
                obs.camera.fy * p[1] / p[2] + obs.camera.cy - obs.v)
        }
        fun members(point: DoubleArray): List<Int> = observations.indices.filter {
            val e = residual(point, observations[it])
            e.isFinite() && e <= maxReprojectionPixels
        }
        var best: Result.Point? = null
        for (i in observations.indices) for (j in 0 until i) {
            val seed = MultiViewTriangulation.triangulate(listOf(observations[j], observations[i]), minParallaxDegrees, maxReprojectionPixels)
            if (seed !is MultiViewTriangulation.Result.Point) continue
            var indices = members(seed.xyz)
            var fit: MultiViewTriangulation.Result.Point? = null
            // Die finalen Inlier müssen auch nach dem Refit dieselben bleiben.
            repeat(5) {
                if (fit == null && indices.size >= minInliers) {
                    val refined = MultiViewTriangulation.triangulate(indices.map { observations[it] }, minParallaxDegrees, maxReprojectionPixels)
                    if (refined is MultiViewTriangulation.Result.Point) {
                        val updated = members(refined.xyz)
                        if (updated == indices) fit = refined else indices = updated
                    } else indices = emptyList()
                }
            }
            val accepted = fit ?: continue
            val candidate = Result.Point(accepted, indices)
            val old = best
            if (old == null || indices.size > old.inliers.size ||
                (indices.size == old.inliers.size && accepted.rmsPixels < old.fit.rmsPixels)) best = candidate
        }
        return best ?: Result.Rejected(MultiViewTriangulation.Failure.NO_CONSENSUS)
    }
}

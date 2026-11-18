package com.andrexthedev.facescan.geometry

/** Punktweise Mehransicht-Rekonstruktion aus bereitgestellten, festen Korrespondenzen.
 * Kein Mesh, keine Vervollständigung und keine Ermittlung von Kameraposen.
 */
object MultiViewPointCloud {
    data class Pixel(val u: Double, val v: Double)
    data class View(
        val camera: CameraModel,
        val worldToCamera: Mat3,
        val translation: DoubleArray,
        // Gemeinsamer Index je physischem Punkt, null wenn nicht beobachtet.
        val pixels: List<Pixel?>
    )
    data class Result(val points: List<MultiViewTriangulation.Result>, val acceptedCount: Int)

    fun reconstruct(views: List<View>, minParallaxDegrees: Double = 1.0, maxReprojectionPixels: Double = 2.0): Result {
        require(views.size in 2..32)
        val count = views.first().pixels.size
        require(count in 1..2048 && views.all { it.pixels.size == count })
        require(minParallaxDegrees.isFinite() && minParallaxDegrees > 0.0 && minParallaxDegrees < 90.0 &&
            maxReprojectionPixels.isFinite() && maxReprojectionPixels >= 0.0)
        val points = (0 until count).map { index ->
            val observations = views.mapNotNull { view ->
                view.pixels[index]?.let { p -> MultiViewTriangulation.Observation(view.camera, view.worldToCamera, view.translation, p.u, p.v) }
            }
            if (observations.size < 2) MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS)
            else MultiViewTriangulation.triangulate(observations, minParallaxDegrees, maxReprojectionPixels)
        }
        return Result(points, points.count { it is MultiViewTriangulation.Result.Point })
    }
    /** Jede Inlier-Liste enthält Indizes der ursprünglichen Ansichten, nicht der Teilmenge. */
    data class RobustResult(val points: List<RobustMultiViewTriangulation.Result>, val acceptedCount: Int)
    fun reconstructRobust(views: List<View>, minParallaxDegrees: Double = 1.0, maxReprojectionPixels: Double = 2.0): RobustResult {
        require(views.size in 3..32)
        val count = views.first().pixels.size
        require(count in 1..2048 && views.all { it.pixels.size == count })
        require(minParallaxDegrees.isFinite() && minParallaxDegrees > 0.0 && minParallaxDegrees < 90.0 &&
            maxReprojectionPixels.isFinite() && maxReprojectionPixels >= 0.0)
        val points = (0 until count).map { index ->
            val seen = views.indices.filter { views[it].pixels[index] != null }
            if (seen.size < 3) RobustMultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS)
            else {
                val observations = seen.map { i ->
                    val view = views[i]; val p = view.pixels[index]!!
                    MultiViewTriangulation.Observation(view.camera, view.worldToCamera, view.translation, p.u, p.v)
                }
                when (val result = RobustMultiViewTriangulation.triangulate(observations, minParallaxDegrees, maxReprojectionPixels)) {
                    is RobustMultiViewTriangulation.Result.Point -> result.copy(inliers = result.inliers.map { seen[it] })
                    is RobustMultiViewTriangulation.Result.Rejected -> result
                }
            }
        }
        return RobustResult(points, points.count { it is RobustMultiViewTriangulation.Result.Point })
    }

}

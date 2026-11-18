package com.andrexthedev.facescan.geometry

import kotlin.math.abs

/** Künstliche Kameraposen und 3D-Punkte; kein Test für echte Gerätekalibrierung. */
object TriangulationSelfTest {
    fun run(): Boolean {
        val camera = CameraModel(800.0, 810.0, 320.0, 240.0)
        val truth = doubleArrayOf(22.0, -15.0, 550.0)
        val rotations = listOf(Mat3.identity(), Mat3.fromRodrigues(doubleArrayOf(0.0, -0.12, 0.03)))
        val translations = listOf(doubleArrayOf(0.0, 0.0, 0.0), doubleArrayOf(-90.0, 3.0, 0.0))
        val observations = rotations.indices.map { i ->
            val pixel = DoubleArray(2)
            camera.project(rotations[i], translations[i], truth, pixel)
            MultiViewTriangulation.Observation(camera, rotations[i], translations[i], pixel[0], pixel[1])
        }
        val result = MultiViewTriangulation.triangulate(observations) as? MultiViewTriangulation.Result.Point ?: return false
        if ((0..2).any { abs(result.xyz[it] - truth[it]) > 1e-6 } || result.maxPixels > 1e-7) return false
        val mapping = CalibratedPixelMapping(100.0, 200.0, 4100.0, 3200.0, 800, 600, 90,
            1200.0, 1250.0, 2100.0, 1700.0, 12.0)
        val mapped = listOf(0.0, -100.0).map { tx ->
            val y = truth[1] / truth[2]
            val pixel = CalibratedPixelMapping.Pixel(mapping.fx * (truth[0] + tx) / truth[2] + mapping.skew * y + mapping.cx,
                mapping.fy * y + mapping.cy)
            mapping.toObservation(mapping.sensorToUpright(pixel), Mat3.identity(), doubleArrayOf(tx, 0.0, 0.0))
        }
        val mappedResult = MultiViewTriangulation.triangulate(mapped) as? MultiViewTriangulation.Result.Point ?: return false
        if ((0..2).any { abs(mappedResult.xyz[it] - truth[it]) > 1e-6 }) return false
        val noBaseline = MultiViewTriangulation.triangulate(listOf(observations[0], observations[0]))
        if (noBaseline != MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_PARALLAX)) return false
        val extra = listOf(doubleArrayOf(80.0, 0.0, 0.0), doubleArrayOf(-150.0, 0.0, 0.0), doubleArrayOf(150.0, 0.0, 0.0))
            .map { t ->
                val pixel = DoubleArray(2); camera.project(Mat3.identity(), t, truth, pixel)
                MultiViewTriangulation.Observation(camera, Mat3.identity(), t, pixel[0], pixel[1])
            }.toMutableList()
        extra[1] = extra[1].copy(v = extra[1].v + 45.0)
        val consensus = RobustMultiViewTriangulation.triangulate(observations + extra) as? RobustMultiViewTriangulation.Result.Point ?: return false
        return consensus.inliers == listOf(0, 1, 2, 4) && (0..2).all { abs(consensus.fit.xyz[it] - truth[it]) < 1e-6 }
    }
}

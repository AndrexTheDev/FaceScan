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
        val noBaseline = MultiViewTriangulation.triangulate(listOf(observations[0], observations[0]))
        return noBaseline == MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_PARALLAX)
    }
}

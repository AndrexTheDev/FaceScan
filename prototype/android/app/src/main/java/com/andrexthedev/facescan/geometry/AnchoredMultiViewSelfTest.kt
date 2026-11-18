package com.andrexthedev.facescan.geometry

import kotlin.math.abs
import kotlin.random.Random

/** Keine Kamera oder reale Person: künstliche Anker, Posen und unabhängiger Punkt. */
object AnchoredMultiViewSelfTest {
    fun run(): Boolean {
        val camera = CameraModel(900.0, 910.0, 320.0, 240.0)
        val random = Random(123)
        val anchors = List(30) { doubleArrayOf(random.nextDouble(-80.0, 80.0),
            random.nextDouble(-90.0, 90.0), random.nextDouble(-35.0, 35.0)) }
        val truth = doubleArrayOf(15.0, -8.0, 10.0)
        fun view(rotation: Mat3, translation: DoubleArray): AnchoredMultiView.View {
            fun pixel(point: DoubleArray): MultiViewPointCloud.Pixel {
                val output = DoubleArray(2); camera.project(rotation, translation, point, output)
                return MultiViewPointCloud.Pixel(output[0], output[1])
            }
            return AnchoredMultiView.View(camera, anchors.map { a ->
                val p = pixel(a); ValidatedAnchorPose.Anchor(a, p.u, p.v)
            }, listOf(pixel(truth)))
        }
        val first = view(Mat3.identity(), doubleArrayOf(0.0, 0.0, 600.0))
        val second = view(Mat3.fromRodrigues(doubleArrayOf(.03, -.12, .02)), doubleArrayOf(-100.0, 4.0, 610.0))
        val result = AnchoredMultiView.reconstruct(listOf(first, second))
        val point = result.cloud?.points?.firstOrNull() as? MultiViewTriangulation.Result.Point ?: return false
        if (result.acceptedViewIndices != listOf(0, 1) || (0..2).any { abs(point.xyz[it] - truth[it]) > .01 }) return false
        val invalid = first.copy(anchors = first.anchors.map { it.copy(world = doubleArrayOf(it.world[0], it.world[1], 0.0)) })
        return AnchoredMultiView.reconstruct(listOf(first, invalid)).cloud == null
    }
}

package com.andrexthedev.facescan.geometry

import org.junit.Assert.*
import org.junit.Test
import kotlin.random.Random

class AnchoredMultiViewTest {
    private val camera = CameraModel(900.0, 910.0, 320.0, 240.0)
    private val anchors = Random(123).let { random -> List(30) {
        doubleArrayOf(random.nextDouble(-80.0, 80.0), random.nextDouble(-90.0, 90.0), random.nextDouble(-35.0, 35.0))
    } }
    private val target = listOf(doubleArrayOf(15.0, -8.0, 10.0), doubleArrayOf(-25.0, 12.0, -10.0))
    private fun view(rotation: Mat3, translation: DoubleArray): AnchoredMultiView.View {
        fun project(p: DoubleArray): MultiViewPointCloud.Pixel {
            val out = DoubleArray(2); camera.project(rotation, translation, p, out)
            return MultiViewPointCloud.Pixel(out[0], out[1])
        }
        return AnchoredMultiView.View(camera, anchors.map { p ->
            val q = project(p); ValidatedAnchorPose.Anchor(p, q.u, q.v)
        }, target.map(::project))
    }
    @Test fun syntheticOnDevicePipelineTest() { assertTrue(AnchoredMultiViewSelfTest.run()) }
    @Test fun estimatesPoseAndTriangulatesSeparateSyntheticHoldoutPoints() {
        val views = listOf(
            view(Mat3.identity(), doubleArrayOf(0.0, 0.0, 600.0)),
            view(Mat3.fromRodrigues(doubleArrayOf(0.03, -0.12, 0.02)), doubleArrayOf(-100.0, 4.0, 610.0)),
            view(Mat3.fromRodrigues(doubleArrayOf(-0.03, 0.1, -0.02)), doubleArrayOf(80.0, -3.0, 590.0)))
        val result = AnchoredMultiView.reconstruct(views)
        assertEquals(listOf(0,1,2), result.acceptedViewIndices)
        assertTrue(result.poses.all { it is ValidatedAnchorPose.Result.Pose && it.rmsPixels < 0.01 })
        val cloud = result.cloud!!
        assertEquals(2, cloud.acceptedCount)
        for (i in target.indices) assertArrayEquals(target[i], (cloud.points[i] as MultiViewTriangulation.Result.Point).xyz, 0.01)
    }
    @Test fun unusableViewsAreExcludedAndMissingPointsAreNotInvented() {
        val one = view(Mat3.identity(), doubleArrayOf(0.0, 0.0, 600.0))
        val two = view(Mat3.identity(), doubleArrayOf(-100.0, 0.0, 600.0)).let { it.copy(points = listOf(it.points[0], null)) }
        val bad = one.copy(anchors = one.anchors.map { it.copy(world = doubleArrayOf(it.world[0], it.world[1], 0.0)) })
        val result = AnchoredMultiView.reconstruct(listOf(one, bad, two))
        assertEquals(listOf(0, 2), result.acceptedViewIndices)
        assertEquals(ValidatedAnchorPose.Result.Rejected(ValidatedAnchorPose.Failure.DEGENERATE_ANCHORS), result.poses[1])
        assertEquals(1, result.cloud!!.acceptedCount)
        assertEquals(MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS), result.cloud.points[1])
        assertNull(AnchoredMultiView.reconstruct(listOf(one, bad)).cloud)
    }
    @Test fun invalidAndInconsistentAnchorsFailClosed() {
        val input = view(Mat3.identity(), doubleArrayOf(0.0, 0.0, 600.0))
        assertEquals(ValidatedAnchorPose.Result.Rejected(ValidatedAnchorPose.Failure.INVALID_INPUT),
            ValidatedAnchorPose.estimate(camera, input.anchors.take(5)))
        assertEquals(ValidatedAnchorPose.Result.Rejected(ValidatedAnchorPose.Failure.INVALID_INPUT),
            ValidatedAnchorPose.estimate(camera, input.anchors.mapIndexed { i, a -> if (i == 0) a.copy(u = Double.NaN) else a }))
        val bad = input.anchors.mapIndexed { i, a -> a.copy(u = a.u + if (i % 2 == 0) 80 else -80) }
        assertTrue(ValidatedAnchorPose.estimate(camera, bad) is ValidatedAnchorPose.Result.Rejected)
    }
}

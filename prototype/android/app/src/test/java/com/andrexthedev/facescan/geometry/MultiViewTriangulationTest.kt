package com.andrexthedev.facescan.geometry

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.abs
import kotlin.random.Random

class MultiViewTriangulationTest {
    private val camera = CameraModel(800.0, 810.0, 320.0, 240.0)
    private fun obs(point: DoubleArray, rotation: Mat3, translation: DoubleArray): MultiViewTriangulation.Observation {
        val p = DoubleArray(2)
        camera.project(rotation, translation, point, p)
        return MultiViewTriangulation.Observation(camera, rotation, translation, p[0], p[1])
    }
    private fun accepted(observations: List<MultiViewTriangulation.Observation>) =
        MultiViewTriangulation.triangulate(observations) as MultiViewTriangulation.Result.Point
    private fun reason(observations: List<MultiViewTriangulation.Observation>) =
        (MultiViewTriangulation.triangulate(observations) as MultiViewTriangulation.Result.Rejected).reason

    @Test fun syntheticDeviceTest() { assertTrue(TriangulationSelfTest.run()) }

    @Test fun recoversManyPointsFromRotatedTranslatedCameras() {
        val random = Random(42)
        val rotations = listOf(Mat3.identity(), Mat3.fromRodrigues(doubleArrayOf(.03, -.2, .05)),
            Mat3.fromRodrigues(doubleArrayOf(-.1, .12, -.03)))
        val translations = listOf(doubleArrayOf(0.0, 0.0, 0.0), doubleArrayOf(-100.0, 5.0, 3.0), doubleArrayOf(75.0, -8.0, 4.0))
        repeat(100) {
            val truth = doubleArrayOf(random.nextDouble(-60.0, 60.0), random.nextDouble(-80.0, 80.0), random.nextDouble(400.0, 800.0))
            val result = accepted(rotations.indices.map { obs(truth, rotations[it], translations[it]) })
            for (i in 0..2) assertEquals(truth[i], result.xyz[i], 1e-7)
            assertTrue(result.maxParallaxDegrees > 1.0)
            assertTrue(result.rmsPixels < 1e-8 && result.maxPixels < 1e-8)
        }
    }

    @Test fun unitsComeFromPoseScale() {
        val point = doubleArrayOf(20.0, -10.0, 600.0)
        val r = Mat3.identity()
        val a = obs(point, r, doubleArrayOf(0.0, 0.0, 0.0))
        val b = obs(point, r, doubleArrayOf(-100.0, 0.0, 0.0))
        val scaled = b.copy(translation = b.translation.map { it * 2 }.toDoubleArray())
        val reconstructed = accepted(listOf(a, scaled))
        for (i in 0..2) assertEquals(2 * point[i], reconstructed.xyz[i], 1e-7)
    }

    @Test fun detectsInsufficientParallaxAndPureRotation() {
        val point = doubleArrayOf(10.0, 20.0, 600.0)
        val a = obs(point, Mat3.identity(), doubleArrayOf(0.0, 0.0, 0.0))
        val rotated = obs(point, Mat3.fromRodrigues(doubleArrayOf(.2, -.3, .1)), doubleArrayOf(0.0, 0.0, 0.0))
        val tinyBaseline = obs(point, Mat3.identity(), doubleArrayOf(-0.01, 0.0, 0.0))
        assertEquals(MultiViewTriangulation.Failure.INSUFFICIENT_PARALLAX, reason(listOf(a, rotated)))
        assertEquals(MultiViewTriangulation.Failure.INSUFFICIENT_PARALLAX, reason(listOf(a, tinyBaseline)))
    }

    @Test fun rejectsPointBehindCameraAndInconsistentPixels() {
        val behind = doubleArrayOf(10.0, 20.0, -600.0)
        val r = Mat3.identity()
        val a = obs(behind, r, doubleArrayOf(0.0, 0.0, 0.0))
        val b = obs(behind, r, doubleArrayOf(-100.0, 0.0, 0.0))
        assertEquals(MultiViewTriangulation.Failure.BEHIND_CAMERA, reason(listOf(a, b)))
        val point = doubleArrayOf(0.0, 0.0, 500.0)
        val first = obs(point, r, doubleArrayOf(0.0, 0.0, 0.0))
        val second = obs(point, r, doubleArrayOf(-80.0, 0.0, 0.0))
        val third = obs(point, r, doubleArrayOf(60.0, 0.0, 0.0)).let { it.copy(v = it.v + 80.0) }
        assertEquals(MultiViewTriangulation.Failure.REPROJECTION_ERROR, reason(listOf(first, second, third)))
    }

    @Test fun noiseAcceptedWithHonestResidual() {
        val point = doubleArrayOf(10.0, -12.0, 500.0)
        val r = Mat3.identity()
        val observations = listOf(obs(point, r, doubleArrayOf(0.0, 0.0, 0.0)),
            obs(point, r, doubleArrayOf(-100.0, 0.0, 0.0)).let { it.copy(v = it.v + 1.0) },
            obs(point, r, doubleArrayOf(80.0, 0.0, 0.0)))
        val result = accepted(observations)
        assertTrue(result.rmsPixels > 0.0 && result.maxPixels <= 2.0)
        assertTrue(abs(result.xyz[2] - point[2]) < 5.0)
    }

    @Test fun reconstructsPartialPointCloudWithoutInventingMissingPoints() {
        val r = Mat3.identity()
        val t1 = doubleArrayOf(0.0, 0.0, 0.0)
        val t2 = doubleArrayOf(-100.0, 0.0, 0.0)
        val truth = listOf(doubleArrayOf(10.0, 20.0, 600.0), doubleArrayOf(-20.0, 5.0, 500.0))
        fun pixel(p: DoubleArray, t: DoubleArray): MultiViewPointCloud.Pixel {
            val o = obs(p, r, t)
            return MultiViewPointCloud.Pixel(o.u, o.v)
        }
        val cloud = MultiViewPointCloud.reconstruct(listOf(
            MultiViewPointCloud.View(camera, r, t1, listOf(pixel(truth[0], t1), pixel(truth[1], t1), null)),
            MultiViewPointCloud.View(camera, r, t2, listOf(pixel(truth[0], t2), null, null))))
        assertEquals(1, cloud.acceptedCount)
        assertArrayEquals(truth[0], (cloud.points[0] as MultiViewTriangulation.Result.Point).xyz, 1e-7)
        assertEquals(MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS), cloud.points[1])
        assertEquals(MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS), cloud.points[2])
        try {
            MultiViewPointCloud.reconstruct(listOf(
                MultiViewPointCloud.View(camera, r, t1, listOf(null)),
                MultiViewPointCloud.View(camera, r, t2, listOf(null, null))))
            fail("mismatched point indices accepted")
        } catch (_: IllegalArgumentException) { }
    }

    @Test fun rejectsMalformedCalibrationAndThresholds() {
        val point = doubleArrayOf(0.0, 0.0, 500.0)
        val a = obs(point, Mat3.identity(), doubleArrayOf(0.0, 0.0, 0.0))
        val b = obs(point, Mat3.identity(), doubleArrayOf(-100.0, 0.0, 0.0))
        val bad = listOf(a.copy(camera = camera.copy(fx = 0.0)), a.copy(u = Double.NaN),
            a.copy(translation = doubleArrayOf(0.0)), a.copy(worldToCamera = Mat3(doubleArrayOf(-1.0,0.0,0.0, 0.0,1.0,0.0, 0.0,0.0,1.0))),
            a.copy(worldToCamera = Mat3(doubleArrayOf(2.0,0.0,0.0, 0.0,.5,0.0, 0.0,0.0,1.0))))
        for (o in bad) assertEquals(MultiViewTriangulation.Failure.INVALID_INPUT, reason(listOf(o, b)))
        assertEquals(MultiViewTriangulation.Failure.INVALID_INPUT, reason(listOf(a)))
        assertEquals(MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INVALID_INPUT),
            MultiViewTriangulation.triangulate(listOf(a, b), maxReprojectionPixels = Double.NaN))
    }
}

package com.andrexthedev.facescan.geometry

import org.junit.Assert.*
import org.junit.Test

class RobustMultiViewTriangulationTest {
    private val camera = CameraModel(800.0, 810.0, 320.0, 240.0)
    private val rotation = Mat3.identity()
    private val truth = doubleArrayOf(10.0, -20.0, 550.0)
    private fun observation(offset: Double): MultiViewTriangulation.Observation {
        val t = doubleArrayOf(offset, 0.0, 0.0)
        val pixel = DoubleArray(2)
        camera.project(rotation, t, truth, pixel)
        return MultiViewTriangulation.Observation(camera, rotation, t, pixel[0], pixel[1])
    }
    @Test fun rejectsOneWrongMatchWithoutInventingData() {
        val all = listOf(observation(0.0), observation(-80.0), observation(70.0),
            observation(-150.0).let { it.copy(v = it.v + 45.0) }, observation(140.0))
        assertTrue(MultiViewTriangulation.triangulate(all) is MultiViewTriangulation.Result.Rejected)
        val result = RobustMultiViewTriangulation.triangulate(all) as RobustMultiViewTriangulation.Result.Point
        assertEquals(listOf(0, 1, 2, 4), result.inliers)
        assertArrayEquals(truth, result.fit.xyz, 1e-7)
        assertTrue(result.fit.maxPixels < 1e-7)
    }
    @Test fun threeViewsWithOneOutlierAreRejectedInsteadOfGuessed() {
        val three = listOf(observation(0.0), observation(-100.0), observation(100.0).let { it.copy(v = it.v + 50) })
        // Mit nur drei Ansichten lässt sich ein Ausreißer nicht sicher erkennen;
        // die Rekonstruktion wird deshalb abgelehnt statt geraten.
        assertEquals(RobustMultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.NO_CONSENSUS),
            RobustMultiViewTriangulation.triangulate(three))
        val agreeing = listOf(observation(0.0), observation(-100.0), observation(100.0))
        val result = RobustMultiViewTriangulation.triangulate(agreeing) as RobustMultiViewTriangulation.Result.Point
        assertEquals(listOf(0, 1, 2), result.inliers)
        assertArrayEquals(truth, result.fit.xyz, 1e-7)
        val noParallax = List(5) { observation(0.0) }
        assertEquals(RobustMultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.NO_CONSENSUS),
            RobustMultiViewTriangulation.triangulate(noParallax))
        assertEquals(RobustMultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INVALID_INPUT),
            RobustMultiViewTriangulation.triangulate(three.take(2)))
    }
    @Test fun badCalibrationIsNeverSilentlyDroppedAsOutlier() {
        val all = listOf(observation(0.0), observation(-80.0), observation(70.0),
            observation(140.0).let { it.copy(camera = camera.copy(fx = 0.0)) })
        assertEquals(RobustMultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INVALID_INPUT),
            RobustMultiViewTriangulation.triangulate(all))
    }
    @Test fun cloudPreservesOriginalViewIndicesAcrossMissingPixels() {
        val observations = listOf(observation(0.0), observation(20.0), observation(-80.0),
            observation(70.0), observation(-150.0).let { it.copy(v = it.v + 60.0) }, observation(140.0))
        val views = observations.mapIndexed { i, o ->
            MultiViewPointCloud.View(o.camera, o.worldToCamera, o.translation,
                listOf(if (i == 1) null else MultiViewPointCloud.Pixel(o.u, o.v), if (i < 2) MultiViewPointCloud.Pixel(o.u, o.v) else null))
        }
        val cloud = MultiViewPointCloud.reconstructRobust(views)
        assertEquals(1, cloud.acceptedCount)
        val point = cloud.points[0] as RobustMultiViewTriangulation.Result.Point
        assertArrayEquals(truth, point.fit.xyz, 1e-7)
        assertEquals(listOf(0, 2, 3, 5), point.inliers)
        assertEquals(RobustMultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS), cloud.points[1])
    }
}

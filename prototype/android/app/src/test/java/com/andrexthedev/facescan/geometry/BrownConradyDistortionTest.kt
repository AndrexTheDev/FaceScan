package com.andrexthedev.facescan.geometry

import org.junit.Assert.*
import org.junit.Test

class BrownConradyDistortionTest {
    private val lens = BrownConradyDistortion(-0.19, 0.045, -0.005, 0.001, -0.002)

    @Test fun syntheticPointsRoundTripAcrossImage() {
        for (i in -10..10) for (j in -10..10) {
            val point = BrownConradyDistortion.Point(i * .07, j * .06)
            val distorted = lens.distort(point)!!
            val restored = lens.undistort(distorted)!!
            assertEquals(point.x, restored.x, 1e-8)
            assertEquals(point.y, restored.y, 1e-8)
        }
    }

    @Test fun identityAndCenterRemainUnchanged() {
        val identity = BrownConradyDistortion(0.0, 0.0, 0.0, 0.0, 0.0)
        val p = BrownConradyDistortion.Point(.3, -.7)
        assertEquals(p, identity.distort(p))
        assertEquals(p, identity.undistort(p))
        assertEquals(BrownConradyDistortion.Point(0.0, 0.0), lens.undistort(BrownConradyDistortion.Point(0.0, 0.0)))
    }

    @Test fun invalidAndSingularConditionsFailClosed() {
        try { lens.copy(k1 = Double.NaN); fail() } catch (_: IllegalArgumentException) { }
        assertNull(lens.distort(BrownConradyDistortion.Point(Double.POSITIVE_INFINITY, 0.0)))
        assertNull(lens.undistort(BrownConradyDistortion.Point(4.0, 0.0)))
        // At x = 1, the radial map's radial derivative is zero; reject even a zero residual.
        val singular = BrownConradyDistortion(-1.0 / 3.0, 0.0, 0.0, 0.0, 0.0)
        assertNull(singular.undistort(BrownConradyDistortion.Point(1.0, 0.0)))
    }

    @Test fun mappedLensCorrectionFeedsTwoViewReconstruction() {
        val truth = doubleArrayOf(110.0, -80.0, 500.0)
        val model = CalibratedPixelMapping(0.0, 0.0, 4000.0, 3000.0, 800, 600, 90,
            1200.0, 1250.0, 2000.0, 1500.0, 12.0)
        val offsets = listOf(0.0, -100.0, 130.0)
        val obs = offsets.map { offset ->
            val distorted = lens.distort(BrownConradyDistortion.Point((truth[0] + offset) / truth[2], truth[1] / truth[2]))!!
            val sensor = CalibratedPixelMapping.Pixel(model.fx * distorted.x + model.skew * distorted.y + model.cx,
                model.fy * distorted.y + model.cy)
            model.toObservation(model.sensorToUpright(sensor), Mat3.identity(), doubleArrayOf(offset, 0.0, 0.0), lens)
        }
        val result = MultiViewTriangulation.triangulate(obs) as MultiViewTriangulation.Result.Point
        assertArrayEquals(truth, result.xyz, 1e-6)
        assertTrue(result.maxPixels < 1e-6)
    }
}

package com.andrexthedev.facescan.geometry

import org.junit.Assert.*
import org.junit.Test

class CalibratedPixelMappingTest {
    private fun mapping(rotation: Int) = CalibratedPixelMapping(100.0, 200.0, 4100.0, 3200.0, 800, 600, rotation,
        1200.0, 1250.0, 2100.0, 1700.0, 12.0)
    @Test fun cropsScalesRotatesAndInvertsInContinuousEdgeCoordinates() {
        for (rotation in listOf(0, 90, 180, 270)) {
            val map = mapping(rotation)
            assertEquals(if (rotation == 90 || rotation == 270) 600 else 800, map.uprightWidth)
            assertEquals(if (rotation == 90 || rotation == 270) 800 else 600, map.uprightHeight)
            for (p in listOf(CalibratedPixelMapping.Pixel(100.0, 200.0), CalibratedPixelMapping.Pixel(4100.0, 3200.0), CalibratedPixelMapping.Pixel(777.5, 1111.5))) {
                val roundtrip = map.uprightToSensor(map.sensorToUpright(p))
                assertEquals(p.x, roundtrip.x, 1e-10)
                assertEquals(p.y, roundtrip.y, 1e-10)
            }
        }
        assertEquals(CalibratedPixelMapping.Pixel(600.0, 0.0), mapping(90).sensorToUpright(CalibratedPixelMapping.Pixel(100.0, 200.0)))
        assertEquals(CalibratedPixelMapping.Pixel(0.0, 800.0), mapping(270).sensorToUpright(CalibratedPixelMapping.Pixel(100.0, 200.0)))
    }
    @Test fun mappedAndDeskewedPixelsReconstructKnownPoint() {
        val truth = doubleArrayOf(30.0, -25.0, 600.0)
        val rotation = Mat3.identity()
        val views = listOf(mapping(90) to doubleArrayOf(0.0, 0.0, 0.0), mapping(270) to doubleArrayOf(-100.0, 0.0, 0.0))
        val observations = views.map { (m, translation) ->
            val xc = truth[0] + translation[0]; val yc = truth[1] + translation[1]; val zc = truth[2] + translation[2]
            val sensor = CalibratedPixelMapping.Pixel(m.fx * xc / zc + m.skew * yc / zc + m.cx, m.fy * yc / zc + m.cy)
            m.toObservation(m.sensorToUpright(sensor), rotation, translation)
        }
        val point = MultiViewTriangulation.triangulate(observations) as MultiViewTriangulation.Result.Point
        assertArrayEquals(truth, point.xyz, 1e-7)
    }
    @Test fun refusesInvalidOrOutOfCropInputRatherThanGuessing() {
        try { mapping(45); fail() } catch (_: IllegalArgumentException) { }
        try { mapping(0).copy(sensorRight = 100.0); fail() } catch (_: IllegalArgumentException) { }
        try { mapping(0).copy(fx = 0.0); fail() } catch (_: IllegalArgumentException) { }
        try { mapping(0).toObservation(CalibratedPixelMapping.Pixel(-1.0, 0.0), Mat3.identity(), doubleArrayOf(0.0, 0.0, 0.0)); fail() } catch (_: IllegalArgumentException) { }
        try { mapping(0).uprightToSensor(CalibratedPixelMapping.Pixel(Double.NaN, 0.0)); fail() } catch (_: IllegalArgumentException) { }
    }
}

package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test

class ImageQualityTest {
    @Test fun syntheticDeviceSmokeTest() { assertTrue(ImageQualitySelfTest.run()) }

    @Test fun pixelStatisticsAreCorrectAndContrastIsStandardDeviation() {
        val flat = ByteArray(64*64) { 128.toByte() }
        val result = ImageQuality.analyze(flat, 64, 64, 64)
        assertEquals(128.0, result.meanLuma, 0.0)
        assertEquals(0.0, result.darkFraction, 0.0)
        assertEquals(0.0, result.brightFraction, 0.0)
        assertEquals(0.0, result.laplacianStdDev, 0.0)
        assertEquals(ImageQuality.Hint.POSSIBLY_BLURRY, result.hint)
    }

    @Test fun borderOutsideEllipseDoesNotControlHint() {
        val gray = ByteArray(64*64) { 128.toByte() }
        for (y in 0 until 64) for (x in 0 until 64) {
            if (x < 4 || y < 4 || x >= 60 || y >= 60) gray[y*64+x] = 255.toByte()
        }
        val result = ImageQuality.analyze(gray, 64, 64, 64)
        assertEquals(128.0, result.meanLuma, 0.0)
        assertEquals(0.0, result.brightFraction, 0.0)
    }

    @Test fun stridePaddingDoesNotChangeResults() {
        val width = 64; val height = 64; val stride = 80
        val packed = ByteArray(width*height) { i -> if ((i / width + i % width) % 2 == 0) 75.toByte() else 185.toByte() }
        val padded = ByteArray(stride*height) { 255.toByte() }
        for (y in 0 until height) packed.copyInto(padded, y*stride, y*width, y*width + width)
        assertEquals(ImageQuality.analyze(packed, width, height, width), ImageQuality.analyze(padded, width, height, stride))
    }

    @Test fun invalidDimensionsAndTruncatedDataRejected() {
        val bad = listOf(Triple(7, 64, 64), Triple(64, 64, 63), Triple(257, 64, 257), Triple(64, 64, Int.MAX_VALUE))
        for ((width, height, stride) in bad) {
            try { ImageQuality.analyze(ByteArray(64*64), width, height, stride); fail() } catch (_: IllegalArgumentException) { }
        }
        try { ImageQuality.analyze(ByteArray(10), 64, 64, 64); fail() } catch (_: IllegalArgumentException) { }
    }
}

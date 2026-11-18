package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs

class FaceScanTest {
    private fun points(offset: Float = 0f): FloatArray = FloatArray(468 * 3) { i ->
        val p = i / 3
        when (i % 3) {
            0 -> (0.2f + (p % 20) * 0.025f + offset)
            1 -> (0.2f + (p / 20) * 0.02f)
            else -> ((p % 7) * -0.001f)
        }
    }.apply {
        this[33 * 3] = 0.3f + offset; this[33 * 3 + 1] = 0.4f
        this[263 * 3] = 0.7f + offset; this[263 * 3 + 1] = 0.4f
    }

    @Test fun onDeviceScanSmokeTestPasses() { assertTrue(ScanSelfTest.run()) }

    @Test fun bufferRequiresRecentFramesAndResetsOnFaceLoss() {
        val buffer = FaceFrameBuffer()
        buffer.add(FaceFrame(points(), 640, 480, 1000))
        buffer.add(FaceFrame(points(), 640, 480, 1200))
        assertNull(buffer.snapshot(1200))
        buffer.add(FaceFrame(points(), 640, 480, 1400))
        val snapshot = buffer.snapshot(1500)!!
        assertEquals(3, snapshot.samples)
        assertTrue(snapshot.jitterPx < 0.001)
        assertNull(buffer.snapshot(4100))
        buffer.add(null)
        assertNull(buffer.snapshot(1500))
    }

    @Test fun imageTranslationDoesNotChangeEyeRelativeShape() {
        val a = FaceSnapshot(points(), 640, 480, 0.0, 3)
        val b = FaceSnapshot(points(0.05f), 640, 480, 0.0, 3)
        val result = FaceSurfaceBuilder.build(a, b)
        assertTrue(result.neutral.indices.all { abs(result.neutral[it] - result.expression[it]) < 1e-5 })
    }

    @Test fun rejectsInvalidPointsAndDegenerateEyes() {
        val invalid = points().apply { this[0] = Float.NaN }
        val good = FaceSnapshot(points(), 640, 480, 0.0, 3)
        try { FaceSurfaceBuilder.build(good, FaceSnapshot(invalid, 640, 480, 0.0, 3)); fail() } catch (_: IllegalArgumentException) { }
        val badEyes = points().apply { this[263 * 3] = this[33 * 3]; this[263 * 3 + 1] = this[33 * 3 + 1] }
        try { FaceSurfaceBuilder.build(FaceSnapshot(badEyes, 640, 480, 0.0, 3), good); fail() } catch (_: IllegalArgumentException) { }
    }

    @Test fun glbContainsIndexedMeshAndAnimatedMorphTarget() {
        val neutral = FaceSnapshot(points(), 640, 480, 0.0, 3)
        val expressionPoints = points().apply { this[13 * 3 + 1] += 0.03f }
        val expression = FaceSnapshot(expressionPoints, 640, 480, 0.0, 3)
        val glb = GlbWriter.write(FaceSurfaceBuilder.build(neutral, expression))
        val input = ByteBuffer.wrap(glb).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(0x46546c67, input.int)
        assertEquals(2, input.int)
        assertEquals(glb.size, input.int)
        val jsonSize = input.int
        assertEquals(0x4e4f534a, input.int)
        assertEquals(0, jsonSize % 4)
        val jsonBytes = ByteArray(jsonSize); input.get(jsonBytes)
        val json = String(jsonBytes, Charsets.UTF_8)
        assertTrue(json.contains("\"targets\""))
        assertTrue(json.contains("\"animations\""))
        assertTrue(json.contains("\"path\":\"weights\""))
        assertTrue(json.contains("uncalibrated"))
        val binarySize = input.int
        assertEquals(0x004e4942, input.int)
        assertEquals(0, binarySize % 4)
        assertEquals(binarySize, input.remaining())
        // CI lässt diesen ausschließlich synthetischen Export zusätzlich vom
        // unabhängigen Khronos glTF-Validator prüfen.
        System.getenv("RUNNER_TEMP")?.let { File(it, "facescan-synthetic.glb").writeBytes(glb) }
    }
}

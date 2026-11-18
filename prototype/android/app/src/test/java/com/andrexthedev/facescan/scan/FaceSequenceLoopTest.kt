package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class FaceSequenceLoopTest {
    private val size = FaceTopology.VERTEX_COUNT * 3
    private fun sequence(): FaceSurface {
        val keys = (0..16).map { i -> FaceKeyframe(i * 0.25f, FloatArray(size) { i * 0.01f }) }
        return FaceSurface(keys.first().points.copyOf(), keys.last().points.copyOf(), 0.0, 0.0, keys)
    }
    @Test fun returnsToNeutralInHalfSecondWithoutModifyingRecording() {
        val raw = sequence()
        val loop = FaceSequenceLoop.close(raw)
        assertEquals(17, raw.keyframes().size)
        assertEquals(18, loop.keyframes().size)
        assertEquals(4.5f, loop.keyframes().last().seconds, 0f)
        assertArrayEquals(raw.neutral, loop.keyframes().last().points, 0f)
        assertArrayEquals(raw.keyframes().last().points, FaceSequencePlayback.sample(loop, 4f), 0f)
        assertEquals(0.08f, FaceSequencePlayback.sample(loop, 4.25f)[0], 1e-6f)
        assertArrayEquals(raw.neutral, FaceSequencePlayback.sample(loop, 4.5f), 0f)
        assertNotSame(raw.neutral, loop.keyframes().last().points)
        assertArrayEquals(ObjWriter.write(raw), ObjWriter.write(loop))
    }
    @Test fun glbEncodesAddedKeyframeAndZeroNeutralDelta() {
        val loop = FaceSequenceLoop.close(sequence())
        val buffer = ByteBuffer.wrap(GlbWriter.write(loop)).order(ByteOrder.LITTLE_ENDIAN)
        val jsonLen = buffer.getInt(12)
        val json = String(buffer.array(), 20, jsonLen, Charsets.UTF_8)
        assertTrue(json.contains("\"frame_17\""))
        assertTrue(json.contains("\"count\":306"))
        val binaryStart = 20 + jsonLen + 8
        val indexBytes = (FaceTopology.triangles.size * 2 + 3) and -4
        val lastDelta = binaryStart + size * 4 + indexBytes + 16 * size * 4
        for (i in 0 until size) assertEquals(0f, buffer.getFloat(lastDelta + i * 4), 0f)
        val weightStart = binaryStart + size * 4 + indexBytes + 17 * size * 4 + 18 * 4
        for (i in 0 until 17) assertEquals(if (i == 16) 1f else 0f, buffer.getFloat(weightStart + (17 * 17 + i) * 4), 0f)
    }
    @Test fun smoothingAndLoopCanBeCombinedAndInvalidInputsAreRejected() {
        val smooth = FaceSequenceSmoothing.smooth(sequence())
        val loop = FaceSequenceLoop.close(smooth)
        assertArrayEquals(smooth.neutral, loop.keyframes().last().points, 0f)
        assertEquals(898, MeshIntegrity.inspect(loop).neutral.totalTriangles)
        try { FaceSequenceLoop.close(loop); fail() } catch (_: IllegalArgumentException) { }
        val raw = sequence()
        val bad = raw.copy(sequence = listOf(FaceKeyframe(0f, raw.neutral), FaceKeyframe(Float.NaN, raw.expression)))
        try { FaceSequenceLoop.close(bad); fail() } catch (_: IllegalArgumentException) { }
    }
}

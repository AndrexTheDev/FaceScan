package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs

class FaceSequenceSmoothingTest {
    private val size = FaceTopology.VERTEX_COUNT * 3
    private fun surface(values: List<Float>, times: List<Float>): FaceSurface {
        val keys = values.mapIndexed { i, v -> FaceKeyframe(times[i], FloatArray(size) { v }) }
        return FaceSurface(keys.first().points.copyOf(), keys.last().points.copyOf(), 0.0, 0.0, keys)
    }

    @Test fun constantSequenceIsUnchangedAndInputIsNotMutated() {
        val raw = surface(listOf(0.25f, 0.25f, 0.25f), listOf(0f, 0.2f, 0.8f))
        val smoothed = FaceSequenceSmoothing.smooth(raw)
        assertEquals(raw.keyframes().map { it.seconds }, smoothed.keyframes().map { it.seconds })
        assertTrue(smoothed.keyframes().all { it.points.all { p -> abs(p - 0.25f) < 1e-7f } })
        assertNotSame(raw.keyframes()[1].points, smoothed.keyframes()[1].points)
        smoothed.keyframes()[1].points[0] = 99f
        assertEquals(0.25f, raw.keyframes()[1].points[0], 0f)
        assertArrayEquals(raw.neutral, smoothed.keyframes().first().points, 0f)
    }

    @Test fun reducesAlternatingNoiseButDelaysExpression() {
        val raw = surface(listOf(0f, 1f, -1f, 1f), listOf(0f, 0.25f, 0.5f, 0.75f))
        val keys = FaceSequenceSmoothing.smooth(raw).keyframes()
        val alpha = 0.25 / (0.12 + 0.25)
        assertEquals(alpha, keys[1].points[0].toDouble(), 1e-6)
        assertTrue(keys[2].points[0] > -1f && keys[2].points[0] < keys[1].points[0])
        assertTrue(abs(keys[3].points[0] - keys[2].points[0]) < 2f)
        assertEquals(1f, raw.keyframes()[3].points[0], 0f)
    }

    @Test fun timeStepControlsResponseAndNeverExtrapolates() {
        val fast = FaceSequenceSmoothing.smooth(surface(listOf(0f, 1f), listOf(0f, 0.02f)))
        val slow = FaceSequenceSmoothing.smooth(surface(listOf(0f, 1f), listOf(0f, 1f)))
        assertTrue(fast.keyframes().last().points[0] < slow.keyframes().last().points[0])
        assertTrue(slow.keyframes().last().points[0] in 0f..1f)
        val extreme = FaceSequenceSmoothing.smooth(surface(listOf(-Float.MAX_VALUE, Float.MAX_VALUE), listOf(0f, 0.25f)))
        assertTrue(extreme.keyframes().last().points.all { it.isFinite() })
    }

    @Test fun glbContainsTheSelectedFilteredShapeAndObjStaysNeutral() {
        val raw = surface(listOf(0f, 1f, 0f), listOf(0f, 0.25f, 0.5f))
        val filtered = FaceSequenceSmoothing.smooth(raw)
        val bytes = GlbWriter.write(filtered)
        val header = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        val jsonLength = header.getInt(12)
        val binaryStart = 12 + 8 + jsonLength + 8
        val deltaStart = binaryStart + size * 4 + ((FaceTopology.triangles.size * 2 + 3) and -4)
        assertEquals(filtered.keyframes()[1].points[0] - filtered.neutral[0], header.getFloat(deltaStart), 1e-6f)
        assertNotEquals(raw.keyframes()[1].points[0], header.getFloat(deltaStart), 1e-6f)
        assertArrayEquals(ObjWriter.write(raw), ObjWriter.write(filtered))
        assertEquals((filtered.keyframes()[1].points[0] + filtered.keyframes()[2].points[0]) / 2f,
            FaceSequencePlayback.sample(filtered, 0.375f)[0], 1e-6f)
    }

    @Test fun invalidSequencesAreRejected() {
        val valid = surface(listOf(0f, 1f, 2f), listOf(0f, 0.25f, 0.5f))
        val bad = listOf(
            valid.copy(sequence = listOf(FaceKeyframe(0f, valid.neutral), FaceKeyframe(0f, valid.expression))),
            valid.copy(sequence = listOf(FaceKeyframe(0f, valid.neutral), FaceKeyframe(Float.NaN, valid.expression))),
            valid.copy(sequence = listOf(FaceKeyframe(0f, valid.neutral), FaceKeyframe(1f, FloatArray(3)))),
            valid.copy(sequence = listOf(FaceKeyframe(0f, FloatArray(size) { 2f }), FaceKeyframe(1f, valid.expression))),
            valid.copy(sequence = listOf(FaceKeyframe(0f, valid.neutral), FaceKeyframe(1f, FloatArray(size) { Float.NaN })))
        )
        for (s in bad) {
            try { FaceSequenceSmoothing.smooth(s); fail("invalid sequence accepted") } catch (_: IllegalArgumentException) { }
        }
    }
}

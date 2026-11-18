package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test

class FaceFrameContinuityTest {
    private fun points(scale: Float = 1f, shift: Float = 0f): FloatArray = FloatArray(468 * 3) { i ->
        when (i % 3) {
            0 -> (.2f + (i / 3 % 20) * .025f - .5f) * scale + .5f + shift
            1 -> (.2f + (i / 3 / 20) * .02f - .5f) * scale + .5f
            else -> -.01f
        }
    }.apply {
        this[33*3] = (.3f-.5f)*scale+.5f+shift; this[33*3+1] = (.4f-.5f)*scale+.5f
        this[263*3] = (.7f-.5f)*scale+.5f+shift; this[263*3+1] = (.4f-.5f)*scale+.5f
    }
    private fun frame(t: Long, scale: Float = .5f, shift: Float = 0f) = FaceFrame(points(scale, shift), 640, 480, t)

    @Test fun toleratesSmallMotionButRejectsLargeJumpScaleAndGap() {
        val a = frame(1000)
        assertTrue(FaceFrameContinuity.isContinuous(a, frame(1250, shift = .03f)))
        assertFalse(FaceFrameContinuity.isContinuous(a, frame(1250, shift = .3f)))
        assertFalse(FaceFrameContinuity.isContinuous(a, frame(1250, scale = 1f)))
        assertFalse(FaceFrameContinuity.isContinuous(a, frame(2501)))
        assertFalse(FaceFrameContinuity.isContinuous(a, frame(1000)))
        assertFalse(FaceFrameContinuity.isContinuous(a, FaceFrame(a.points, 480, 640, 1250)))
    }
    @Test fun previousNeutralCannotBeUsedAfterJumpAndFreshSessionCanRecover() {
        val buffer = FaceFrameBuffer()
        assertFalse(buffer.add(frame(1000)))
        assertFalse(buffer.add(frame(1200)))
        assertFalse(buffer.add(frame(1400)))
        val old = buffer.snapshot(1400)!!
        assertTrue(buffer.isCurrent(old, 1400))
        assertTrue(buffer.add(frame(1600, shift = .3f)))
        assertFalse(buffer.isCurrent(old, 1600))
        assertNull(buffer.snapshot(1600))
        assertFalse(buffer.add(frame(1800, shift = .3f)))
        assertFalse(buffer.add(frame(2000, shift = .3f)))
        val fresh = buffer.snapshot(2000)!!
        assertTrue(buffer.isCurrent(fresh, 2000))
        assertFalse(buffer.isCurrent(old, 2000))
    }
    @Test fun invalidAndMissingFramesInvalidateButAreNotPersonRecognition() {
        val buffer = FaceFrameBuffer()
        buffer.add(frame(1000))
        assertTrue(buffer.add(FaceFrame(points().apply { this[0] = 0f }, 640, 480, 1200)))
        assertFalse(buffer.hasRecentFace(1200))
        assertFalse(buffer.add(null))
        buffer.add(frame(1300))
        assertTrue(buffer.add(null))
    }
}

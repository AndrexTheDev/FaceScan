package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.cos
import kotlin.math.sin

class FaceFrontalGuidanceTest {
    private fun points(offset: Float): FloatArray = FloatArray(468 * 3) { if (it % 3 == 2) 0f else 0.5f }.apply {
        this[33 * 3] = .3f; this[33 * 3 + 1] = .5f
        this[263 * 3] = .7f; this[263 * 3 + 1] = .5f
        this[3] = .5f + offset; this[4] = .5f
    }
    @Test fun givesOnlyAnAdvisoryForLargeNoseEyeAsymmetry() {
        assertEquals(false, FaceFrontalGuidance.possiblyTurned(points(0f), 640, 480))
        assertEquals(true, FaceFrontalGuidance.possiblyTurned(points(.1f), 640, 480))
        assertEquals(true, FaceFrontalGuidance.possiblyTurned(points(-.1f), 640, 480))
    }
    @Test fun rollAndImageAspectAreHandledInPixelCoordinates() {
        val p = points(.1f); val angle = .5; val c = cos(angle); val s = sin(angle)
        for (i in 0 until 468) {
            val x = (p[3*i] - .5f) * 640; val y = (p[3*i+1] - .5f) * 480
            p[3*i] = (.5 + (x*c-y*s)/640).toFloat()
            p[3*i+1] = (.5 + (x*s+y*c)/480).toFloat()
        }
        assertEquals(true, FaceFrontalGuidance.possiblyTurned(p, 640, 480))
    }
    @Test fun noAdviceForInvalidTooSmallOrClippedFaces() {
        assertNull(FaceFrontalGuidance.possiblyTurned(FloatArray(3), 640, 480))
        assertNull(FaceFrontalGuidance.possiblyTurned(points(0f).apply { this[0] = Float.NaN }, 640, 480))
        assertNull(FaceFrontalGuidance.possiblyTurned(points(0f).apply { this[0] = 0f }, 640, 480))
        assertNull(FaceFrontalGuidance.possiblyTurned(points(0f).apply { this[263*3] = this[33*3] }, 640, 480))
    }
}

package com.andrexthedev.facescan.scan

import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt
import org.junit.Assert.*
import org.junit.Test

class FaceAlignmentTest {
    private fun shape() = FloatArray(468 * 3) { i ->
        val v = i / 3.0
        when (i % 3) {
            0 -> sin(v * 0.47).toFloat()
            1 -> (cos(v * 0.19) * 0.7).toFloat()
            else -> (sin(v * 0.13) * 0.4).toFloat()
        }
    }

    private fun rotate(points: FloatArray, angle: Double, axis: Int): FloatArray {
        val result = points.copyOf(); val c = cos(angle); val s = sin(angle)
        for (i in 0 until points.size / 3) {
            val x = points[3*i]; val y = points[3*i+1]; val z = points[3*i+2]
            when (axis) {
                0 -> { result[3*i] = x; result[3*i+1] = (c*y-s*z).toFloat(); result[3*i+2] = (s*y+c*z).toFloat() }
                1 -> { result[3*i] = (c*x+s*z).toFloat(); result[3*i+1] = y; result[3*i+2] = (-s*x+c*z).toFloat() }
                else -> { result[3*i] = (c*x-s*y).toFloat(); result[3*i+1] = (s*x+c*y).toFloat(); result[3*i+2] = z }
            }
            result[3*i] += 0.4f; result[3*i+1] -= 0.3f; result[3*i+2] += 0.2f
        }
        return result
    }

    @Test fun rotationTranslationRecoveredAroundAllAxesIncludingHalfTurn() {
        val neutral = shape()
        for (axis in 0..2) for (angle in listOf(0.0, 0.25, -0.6, Math.PI)) {
            val moving = rotate(neutral, angle, axis)
            val fit = FaceAlignment.align(neutral, moving)
            assertTrue("axis=$axis angle=$angle rms=${fit.anchorRms}", fit.anchorRms < 1e-5)
            for (i in neutral.indices) assertEquals("axis=$axis angle=$angle index=$i", neutral[i], fit.points[i], 1e-5f)
        }
    }

    @Test fun deformationAwayFromAnchorsIsPreservedNotAbsorbed() {
        val neutral = shape()
        val expressive = neutral.copyOf().apply { this[13 * 3 + 1] += 0.3f }
        val fit = FaceAlignment.align(neutral, rotate(expressive, 0.6, 1))
        assertTrue(fit.anchorRms < 1e-5)
        assertEquals(0.3f, fit.points[13 * 3 + 1] - neutral[13 * 3 + 1], 1e-5f)
    }

    @Test fun degeneracyAndInvalidInputsRejected() {
        val good = shape()
        for (bad in listOf(FloatArray(good.size), good.copyOf().apply { this[0] = Float.NaN }, FloatArray(3))) {
            try { FaceAlignment.align(good, bad); fail("Invalid alignment accepted") } catch (_: IllegalArgumentException) { }
        }
    }

    @Test fun nonRigidAnchorDeformationHasMeasurableResidual() {
        val neutral = shape()
        val moving = neutral.copyOf().apply { this[10 * 3] += 0.8f }
        val fit = FaceAlignment.align(neutral, moving)
        assertTrue(fit.anchorRms > 0.1)
        assertTrue(fit.anchorRms < sqrt(0.8 * 0.8 / 13))
    }
}

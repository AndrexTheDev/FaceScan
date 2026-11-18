package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.sqrt

class MeshNormalsTest {
    @Test fun planarAndReversedWindingProduceUnitNormals() {
        val p = floatArrayOf(0f, 0f, 0f, 1f, 0f, 0f, 0f, 1f, 0f)
        val forward = MeshNormals.calculate(p, intArrayOf(0, 1, 2))
        val backward = MeshNormals.calculate(p, intArrayOf(0, 2, 1))
        for (i in 0..2) {
            assertEquals(1f, forward[3*i+2], 0f)
            assertEquals(-1f, backward[3*i+2], 0f)
        }
    }
    @Test fun areaWeightedSharedNormalsAndDegenerateFallbackAreFinite() {
        // A big +Z triangle and a smaller +X triangle meet at vertex 0.
        val p = floatArrayOf(0f,0f,0f, 2f,0f,0f, 0f,2f,0f, 0f,1f,0f, 0f,0f,1f, 3f,3f,3f)
        val n = MeshNormals.calculate(p, intArrayOf(0,1,2, 0,3,4, 5,5,5))
        assertEquals(1.0 / sqrt(17.0), n[0].toDouble(), 1e-6)
        assertEquals(4.0 / sqrt(17.0), n[2].toDouble(), 1e-6)
        assertEquals(1f, n[5*3+2], 0f)
        for (i in p.indices step 3) {
            val norm = sqrt((n[i]*n[i] + n[i+1]*n[i+1] + n[i+2]*n[i+2]).toDouble())
            assertEquals(1.0, norm, 1e-6)
        }
    }
    @Test fun invalidTopologyAndNonfinitePointsAreRejected() {
        try { MeshNormals.calculate(floatArrayOf(0f, 0f, 0f), intArrayOf(0, 1, 0)); fail() } catch (_: IllegalArgumentException) { }
        try { MeshNormals.calculate(floatArrayOf(Float.NaN, 0f, 0f), intArrayOf()); fail() } catch (_: IllegalArgumentException) { }
        try { MeshNormals.calculate(floatArrayOf(0f, 0f, 0f), intArrayOf(0, 0)); fail() } catch (_: IllegalArgumentException) { }
    }
    @Test fun largeFiniteCoordinatesDoNotOverflowCrossProducts() {
        val big = Float.MAX_VALUE
        val n = MeshNormals.calculate(floatArrayOf(0f,0f,0f, big,0f,0f, 0f,big,0f), intArrayOf(0,1,2))
        assertTrue(n.all { it.isFinite() })
        assertEquals(1f, n[2], 0f)
    }
}

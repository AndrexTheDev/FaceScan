package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test

class MeshIntegrityTest {
    @Test fun countsZeroAreaAndLongEdgesWithoutRejectingMesh() {
        val p = floatArrayOf(0f,0f,0f, .1f,0f,0f, 0f,.1f,0f, 2f,0f,0f)
        val result = MeshIntegrity.inspect(p, intArrayOf(0,1,2, 0,0,1, 0,1,3))
        assertEquals(3, result.totalTriangles)
        assertEquals(2, result.tinyTriangles)
        assertEquals(1, result.longEdgeTriangles)
    }
    @Test fun thresholdMeasuresAreInEyeDistanceUnits() {
        val p = floatArrayOf(0f,0f,0f, .4f,0f,0f, 0f,.4f,0f)
        assertEquals(0, MeshIntegrity.inspect(p, intArrayOf(0,1,2)).longEdgeTriangles)
        assertEquals(1, MeshIntegrity.inspect(FloatArray(p.size) { 2 * p[it] }, intArrayOf(0,1,2)).longEdgeTriangles)
    }
    @Test fun summariesIncludeTheWorstAnimatedShape() {
        val neutral = FloatArray(FaceTopology.VERTEX_COUNT * 3) { i ->
            when (i % 3) { 0 -> (i / 3 % 20) * .01f; 1 -> (i / 3 / 20) * .01f; else -> 0f }
        }
        val broken = neutral.copyOf().apply { this[0] = 100f }
        val surface = FaceSurface(neutral, broken, 0.0, 0.0,
            listOf(FaceKeyframe(0f, neutral), FaceKeyframe(1f, broken)))
        val result = MeshIntegrity.inspect(surface)
        assertEquals(898, result.neutral.totalTriangles)
        assertTrue(result.maxLongEdgeTriangles > result.neutral.longEdgeTriangles)
        assertTrue(result.maxTinyTriangles >= result.neutral.tinyTriangles)
    }
    @Test fun nonfiniteAndInvalidTopologyAreRejected() {
        try { MeshIntegrity.inspect(floatArrayOf(Float.NaN,0f,0f), intArrayOf(0,0,0)); fail() } catch (_: IllegalArgumentException) { }
        try { MeshIntegrity.inspect(floatArrayOf(0f,0f,0f), intArrayOf(0,0,1)); fail() } catch (_: IllegalArgumentException) { }
        try { MeshIntegrity.inspect(floatArrayOf(0f,0f,0f), intArrayOf()); fail() } catch (_: IllegalArgumentException) { }
    }
}

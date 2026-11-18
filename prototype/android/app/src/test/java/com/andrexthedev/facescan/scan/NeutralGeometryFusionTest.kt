package com.andrexthedev.facescan.scan

import kotlin.math.cos
import kotlin.math.sin
import org.junit.Assert.*
import org.junit.Test

class NeutralGeometryFusionTest {
    private fun shape() = FloatArray(FaceTopology.VERTEX_COUNT * 3) { i ->
        val p = i / 3.0
        when (i % 3) {
            0 -> sin(p * 0.47).toFloat()
            1 -> (cos(p * 0.19) * 0.7).toFloat()
            else -> (sin(p * 0.13) * 0.4).toFloat()
        }
    }
    private fun transform(points: FloatArray): FloatArray = points.copyOf().also { result ->
        val angle = 0.35; val c = cos(angle); val s = sin(angle)
        for (i in 0 until FaceTopology.VERTEX_COUNT) {
            val x = points[3*i]; val z = points[3*i+2]
            result[3*i] = (c*x + s*z + 0.2).toFloat()
            result[3*i+1] = points[3*i+1] - 0.1f
            result[3*i+2] = (-s*x + c*z + 0.3).toFloat()
        }
    }

    @Test fun alignsRigidMotionRejectsBadAnchorsAndSuppressesLocalOutlier() {
        val base = shape()
        val oneBadLandmark = base.copyOf().apply { this[13*3+1] += 0.6f }
        val badAnchors = base.copyOf().apply { for (i in listOf(10, 151, 9, 168, 6, 197)) this[3*i] += 1f }
        val result = NeutralGeometryFusion.fuse(listOf(base, base.copyOf(), oneBadLandmark, badAnchors, transform(base)))!!
        assertArrayEquals(intArrayOf(0, 1, 2, 4), result.accepted)
        val backToBase = FaceAlignment.align(base, result.points)
        assertTrue(backToBase.anchorRms < 1e-5)
        for (i in base.indices) assertEquals("index $i", base[i], backToBase.points[i], 1e-5f)
    }

    @Test fun requiresConsensusAndRejectsInvalidAndDegenerateInput() {
        val base = shape()
        assertNull(NeutralGeometryFusion.fuse(listOf(base, base)))
        val bad = base.copyOf().apply { this[0] = Float.NaN }
        assertNull(NeutralGeometryFusion.fuse(listOf(base, bad, FloatArray(base.size))))
        assertNotNull(NeutralGeometryFusion.fuse(listOf(base, base, bad, base)))
    }

    @Test fun medianReducesIndependentSyntheticLandmarkNoiseOnAverage() {
        val base = shape()
        val random = kotlin.random.Random(734)
        var singleSquared = 0.0
        var fusionSquared = 0.0
        for (trial in 0 until 8) {
            val samples = List(5) {
                FloatArray(base.size) { i -> base[i] + (random.nextFloat() - 0.5f) * 0.03f }
            }
            val fusion = NeutralGeometryFusion.fuse(samples)!!
            val first = FaceAlignment.align(base, samples.first()).points
            val combined = FaceAlignment.align(base, fusion.points).points
            for (i in base.indices) {
                val a = (first[i] - base[i]).toDouble()
                val b = (combined[i] - base[i]).toDouble()
                singleSquared += a * a; fusionSquared += b * b
            }
        }
        assertTrue("synthetic fusion error $fusionSquared should be below one-frame error $singleSquared", fusionSquared < singleSquared)
    }

    @Test fun bufferRejectsStaleFaceAndOutOfOrderTimestamps() {
        val points = FloatArray(468 * 3) { i ->
            when (i % 3) {
                0 -> 0.2f + (i / 3 % 20) * 0.025f
                1 -> 0.2f + (i / 3 / 20) * 0.02f
                else -> -0.01f
            }
        }.apply {
            this[33*3] = 0.3f; this[33*3+1] = 0.4f
            this[263*3] = 0.7f; this[263*3+1] = 0.4f
        }
        val buffer = FaceFrameBuffer()
        for (t in listOf(100L, 200L, 300L)) buffer.add(FaceFrame(points, 640, 480, t))
        assertTrue(buffer.hasRecentFace(300))
        assertFalse(buffer.hasRecentFace(2801))
        val sample = buffer.snapshot(300)!!
        assertEquals(3, sample.samples)
        assertNotNull(sample.fusedPoints)
        assertTrue(sample.fusionAnchorRms!! < 0.0001)
        assertNull(buffer.snapshot(2801))
        buffer.add(FaceFrame(points, 640, 480, 250))
        assertNull(buffer.snapshot(300))
        assertFalse(buffer.hasRecentFace(300))
    }

    @Test fun invalidFusedGeometryIsNotUsedForScan() {
        val base = shape()
        val invalid = FaceSnapshot(base, 640, 480, 0.0, 3, fusedPoints = base.copyOf().apply { this[0] = Float.NaN })
        try { FaceSurfaceBuilder.neutralPoints(invalid); fail() } catch (_: IllegalArgumentException) { }
    }
}

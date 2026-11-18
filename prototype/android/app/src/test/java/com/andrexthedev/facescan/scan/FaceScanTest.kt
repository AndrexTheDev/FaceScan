package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.Executors
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

    @Test fun neutralSessionCannotBeReusedAfterTrackingLossOrDimensionsChange() {
        val buffer = FaceFrameBuffer()
        for (t in listOf(1000L, 1200L, 1400L)) buffer.add(FaceFrame(points(), 640, 480, t))
        val first = buffer.snapshot(1400)!!
        assertTrue(buffer.isCurrent(first, 1400))
        assertFalse(buffer.isCurrent(first, 3901))
        buffer.add(null)
        for (t in listOf(1500L, 1700L, 1900L)) buffer.add(FaceFrame(points(), 640, 480, t))
        assertTrue(buffer.hasRecentFace(1900))
        assertFalse(buffer.isCurrent(first, 1900))
        val second = buffer.snapshot(1900)!!
        assertTrue(buffer.isCurrent(second, 1900))
        for (t in listOf(2100L, 2300L, 2500L)) buffer.add(FaceFrame(points(), 480, 640, t))
        assertFalse(buffer.isCurrent(second, 2500))
        assertFalse(buffer.isCurrent(second.copy(sessionEpoch = null), 2500))
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

    private fun recordSequence(): FaceSurface {
        val recorder = FaceSequenceRecorder()
        recorder.start(1000)
        for (i in 0 until 16) {
            val sample = points().apply { this[13 * 3 + 1] += i * 0.002f }
            recorder.add(FaceFrame(sample, 640, 480, 1200L + i * 250))
        }
        return recorder.finish(5000, FaceSnapshot(points(), 640, 480, 0.0, 3))!!
    }

    @Test fun sequenceHasBoundedTimedFramesAndPlaybackInterpolates() {
        val sequence = recordSequence()
        val keys = sequence.keyframes()
        assertEquals(17, keys.size)
        assertEquals(0f, keys.first().seconds, 0f)
        assertEquals(3.95f, keys.last().seconds, 0.0001f)
        assertTrue(keys.zipWithNext().all { (a, b) -> b.seconds > a.seconds })
        val a = keys[5]; val b = keys[6]
        val mid = FaceSequencePlayback.sample(sequence, (a.seconds + b.seconds) / 2f)
        for (i in mid.indices) assertEquals((a.points[i] + b.points[i]) / 2, mid[i], 0.00001f)
        assertArrayEquals(keys.first().points, FaceSequencePlayback.sample(sequence, -1f), 0f)
        assertArrayEquals(keys.last().points, FaceSequencePlayback.sample(sequence, 99f), 0f)
    }

    @Test fun recorderRejectsLostFaceAndGapsAndCanCancelAndRestart() {
        val neutral = FaceSnapshot(points(), 640, 480, 0.0, 3)
        val r = FaceSequenceRecorder()
        r.start(1000)
        r.add(FaceFrame(points(), 640, 480, 1200)); r.add(null)
        for (i in 0 until 10) r.add(FaceFrame(points(), 640, 480, 1500L + 250 * i))
        assertNull(r.finish(5000, neutral))
        r.start(1000); r.add(FaceFrame(points(), 640, 480, 1200)); r.add(FaceFrame(points(), 640, 480, 3000))
        assertNull(r.finish(5000, neutral))
        r.start(1000); r.add(FaceFrame(points(), 640, 480, 1200)); r.cancel()
        assertNull(r.finish(5000, neutral))
        assertNotNull(recordSequence())
    }

    @Test fun recordingCopiesFramesRejectsDimensionChangeAndStaleStart() {
        val r = FaceSequenceRecorder()
        val neutral = FaceSnapshot(points(), 640, 480, 0.0, 3)
        r.start(1000)
        r.add(FaceFrame(points(), 640, 480, 900)) // vor Nutzerstart
        val mutable = points().apply { this[13 * 3 + 1] += 0.1f }
        r.add(FaceFrame(mutable, 640, 480, 1200))
        mutable[13 * 3 + 1] = 0.9f
        for (i in 1..15) r.add(FaceFrame(points(), 640, 480, 1200L + i * 250))
        val surface = r.finish(5000, neutral)!!
        assertEquals(0.2f, surface.keyframes()[1].seconds, 0.0001f)
        assertTrue(abs(surface.keyframes()[1].points[13 * 3 + 1] - surface.keyframes()[2].points[13 * 3 + 1]) > 0.01f)
        r.start(1000)
        r.add(FaceFrame(points(), 640, 480, 1200))
        r.add(FaceFrame(points(), 480, 640, 1450))
        assertNull(r.finish(5000, neutral))
    }

    @Test fun cancellationDuringAlignmentIsNonBlockingAndDiscardsOldResult() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val recorder = FaceSequenceRecorder { a, b ->
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            FaceAlignment.align(a, b)
        }
        val neutral = FaceSnapshot(points(), 640, 480, 0.0, 3)
        recorder.start(1000)
        for (i in 0 until 16) recorder.add(FaceFrame(points(), 640, 480, 1200L + 250 * i))
        val pool = Executors.newFixedThreadPool(2)
        try {
            val old = pool.submit<FaceSurface?> { recorder.finish(5000, neutral) }
            assertTrue(entered.await(5, TimeUnit.SECONDS))
            val cancel = pool.submit { recorder.cancel(); recorder.start(6000) }
            cancel.get(2, TimeUnit.SECONDS) // alignment cannot hold the recorder monitor
            release.countDown()
            assertNull(old.get(5, TimeUnit.SECONDS))
            for (i in 0 until 16) recorder.add(FaceFrame(points(), 640, 480, 6200L + 250 * i))
            assertNotNull(recorder.finish(10000, neutral))
        } finally { release.countDown(); pool.shutdownNow() }
    }

    @Test fun recordingRejectsClippedFramesAndNonRigidAnchors() {
        val neutral = FaceSnapshot(points(), 640, 480, 0.0, 3)
        val r = FaceSequenceRecorder()
        r.start(1000)
        r.add(FaceFrame(points().apply { this[0] = 0f }, 640, 480, 1200))
        assertNull(r.finish(5000, neutral))
        assertFalse(r.wasAlignmentFailure())
        r.start(1000)
        for (i in 0 until 16) {
            val deformed = points().apply { for (anchor in listOf(10, 151, 9, 168, 6, 197)) this[3 * anchor] += 0.25f }
            r.add(FaceFrame(deformed, 640, 480, 1200L + i * 250))
        }
        assertNull(r.finish(5000, neutral))
        assertTrue(r.wasAlignmentFailure())
    }

    @Test fun neutralQualityChecksScaleEdgesAndMotionWithoutClaimingAccuracy() {
        val p = points()
        assertTrue(NeutralCaptureQuality.isUsable(FaceSnapshot(p, 640, 480, 2.0, 3)))
        assertFalse(NeutralCaptureQuality.isUsable(FaceSnapshot(p, 640, 480, 40.0, 3)))
        assertFalse(NeutralCaptureQuality.isUsable(FaceSnapshot(p.copyOf().apply { this[0] = 0f }, 640, 480, 0.0, 3)))
        assertFalse(NeutralCaptureQuality.isUsable(FaceSnapshot(p.copyOf().apply { this[263*3] = this[33*3] }, 640, 480, 0.0, 3)))
    }

    @Test fun glbContainsIndexedMeshAndAnimatedMorphTarget() {
        val surface = recordSequence()
        val glb = GlbWriter.write(surface)
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
        assertTrue(json.contains("\"NORMAL\""))
        assertTrue(json.contains("uncalibrated"))
        assertTrue(json.contains("\"frame_16\""))
        assertTrue(json.contains("\"count\":272"))
        val binarySize = input.int
        assertEquals(0x004e4942, input.int)
        assertEquals(0, binarySize % 4)
        assertEquals(binarySize, input.remaining())
        // Ein Einheitsgewicht je Keyframe muss exakt die aufgenommenen Formen ergeben.
        val binaryStart = input.position()
        val trianglesBytes = FaceTopology.triangles.size * 2
        val deltaStart = binaryStart + 468 * 12 + ((trianglesBytes + 3) and -4)
        for (k in 1 until surface.keyframes().size) {
            val point = 13 * 3 + 1
            val delta = input.getFloat(deltaStart + (k - 1) * 468 * 12 + point * 4)
            assertEquals(surface.keyframes()[k].points[point], surface.neutral[point] + delta, 1e-6f)
        }
        val weightsStart = deltaStart + 16 * 468 * 12 + 17 * 4
        for (k in 0 until 17) for (target in 0 until 16) {
            assertEquals(if (k == target + 1) 1f else 0f, input.getFloat(weightsStart + (k * 16 + target) * 4), 0f)
        }
        // Normale und Morph-Normalen liegen hinter den Animationsgewichten.
        val normalsStart = weightsStart + 272 * 4
        val baseNormals = MeshNormals.calculate(surface.neutral, FaceTopology.triangles)
        val targetNormals = MeshNormals.calculate(surface.keyframes()[7].points, FaceTopology.triangles)
        var changedNormals = 0
        for (i in baseNormals.indices) {
            val base = input.getFloat(normalsStart + i * 4)
            val delta = input.getFloat(normalsStart + 468 * 12 + 6 * 468 * 12 + i * 4)
            assertEquals(baseNormals[i], base, 1e-6f)
            assertEquals(targetNormals[i], base + delta, 1e-6f)
            if (abs(delta) > 1e-5f) changedNormals++
        }
        assertTrue(changedNormals > 0)
        // CI lässt diesen ausschließlich synthetischen Export zusätzlich vom
        // unabhängigen Khronos glTF-Validator prüfen.
        System.getenv("RUNNER_TEMP")?.let {
            File(it, "facescan-synthetic.glb").writeBytes(glb)
            File(it, "facescan-synthetic-loop.glb").writeBytes(GlbWriter.write(FaceSequenceLoop.close(surface)))
        }
    }
    @Test fun texturedGlbContainsEmbeddedJpegAndUvWithoutChangingMeshAnimation() {
        val surface = recordSequence()
        // Vollständig künstliches, lokal erzeugtes 16x16-Farbmuster.
        val jpeg = javaClass.getResourceAsStream("/synthetic-gradient.jpg")!!.use { it.readBytes() }
        val uv = FloatArray(468 * 2) { i -> if (i % 2 == 0) (i / 2 % 20) / 20f else (i / 2 / 20) / 24f }
        val glb = GlbWriter.write(surface.copy(texture = FaceTexture(jpeg, uv)))
        val input = ByteBuffer.wrap(glb).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(0x46546c67, input.int); assertEquals(2, input.int); assertEquals(glb.size, input.int)
        val jsonSize = input.int; assertEquals(0x4e4f534a, input.int)
        val jsonBytes = ByteArray(jsonSize); input.get(jsonBytes)
        val json = String(jsonBytes, Charsets.UTF_8)
        assertTrue(json.contains("\"TEXCOORD_0\""))
        assertTrue(json.contains("\"mimeType\":\"image/jpeg\""))
        assertTrue(json.contains("\"baseColorTexture\""))
        assertTrue(json.contains("\"animations\""))
        val binarySize = input.int; assertEquals(0x004e4942, input.int); assertEquals(binarySize, input.remaining())
        val binStart = input.position()
        val trianglesBytes = FaceTopology.triangles.size * 2
        val uvOffset = 468 * 12 + ((trianglesBytes + 3) and -4) + 16 * 468 * 12 + 17 * 4 + 272 * 4
        for (i in uv.indices) assertEquals(uv[i], input.getFloat(binStart + uvOffset + i * 4), 0f)
        val actualJpeg = ByteArray(jpeg.size)
        input.position(binStart + uvOffset + uv.size * 4); input.get(actualJpeg)
        assertArrayEquals(jpeg, actualJpeg)
        System.getenv("RUNNER_TEMP")?.let { File(it, "facescan-synthetic-textured.glb").writeBytes(glb) }
    }

    @Test fun syntheticMultiviewPartialObjIsExportedForIndependentParsing() {
        val clouds = (0 until FaceTopology.VERTEX_COUNT).map { i ->
            if (i % 97 == 0) MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS)
            else MultiViewTriangulation.Result.Point(
                doubleArrayOf((i % 26 - 12.5) * 0.3, (i / 26 - 9.0) * 0.3, 1.0 + (i % 7) * 0.1), 8.0, 0.0, 0.0)
        }
        val cloud = MultiViewPointCloud.Result(clouds, clouds.count { it is MultiViewTriangulation.Result.Point })
        val mesh = PartialFaceMesh.build(cloud).mesh
        assertNotNull(mesh)
        val bytes = PartialFaceMesh.writeObj(mesh!!)
        System.getenv("RUNNER_TEMP")?.let { dir ->
            File(dir, "facescan-synthetic-partial.obj").writeBytes(bytes)
            val vertices = mesh.vertices.joinToString(",", "[", "]") { row -> row.joinToString(",", "[", "]") }
            val faces = mesh.triangles.toList().chunked(3).joinToString(",", "[", "]") { row -> row.joinToString(",", "[", "]") }
            File(dir, "facescan-synthetic-partial-reference.json").writeText(
                "{\"vertices\":$vertices,\"faces\":$faces,\"sourceIndices\":${mesh.sourceIndices.toList()}}")
        }
        val obj = String(bytes, Charsets.UTF_8).lines()
        assertEquals(mesh.vertices.size, obj.count { it.startsWith("v ") })
        assertEquals(mesh.triangles.size / 3, obj.count { it.startsWith("f ") })
        // Kollineare Gitterpunkte dürfen keine degenerierten Dreiecke erzeugen.
        assertTrue(mesh.vertices.size in 400 until FaceTopology.VERTEX_COUNT)
        assertTrue(mesh.triangles.isNotEmpty())
        assertTrue(obj.any { it.contains("not validated") })
    }

    @Test fun badTextureFailsAndObjHasOneBasedTrianglesAndNoPhoto() {
        val surface = recordSequence()
        for (texture in listOf(FaceTexture(byteArrayOf(1, 2), FloatArray(936)),
            FaceTexture(byteArrayOf(-1, -40, -1, -39), FloatArray(936) { Float.NaN }))) {
            try { GlbWriter.write(surface.copy(texture = texture)); fail("invalid texture accepted") } catch (_: IllegalArgumentException) { }
        }
        val objBytes = ObjWriter.write(surface)
        System.getenv("RUNNER_TEMP")?.let { dir ->
            File(dir, "facescan-synthetic.obj").writeBytes(objBytes)
            val normals = MeshNormals.calculate(surface.neutral, FaceTopology.triangles)
            fun vectors(values: FloatArray) = values.toList().chunked(3).joinToString(",", "[", "]") { row -> row.joinToString(",", "[", "]") }
            val faces = FaceTopology.triangles.toList().chunked(3).joinToString(",", "[", "]") { row -> row.joinToString(",", "[", "]") }
            File(dir, "facescan-synthetic-obj-reference.json").writeText("{\"vertices\":${vectors(surface.neutral)},\"normals\":${vectors(normals)},\"faces\":$faces}")
        }
        val obj = String(objBytes, Charsets.UTF_8).lines()
        assertEquals(468, obj.count { it.startsWith("v ") })
        assertEquals(898, obj.count { it.startsWith("f ") })
        assertEquals(468, obj.count { it.startsWith("vn ") })
        val first = obj.first { it.startsWith("f ") }.split(" ").drop(1).map { it.split("//").map(String::toInt) }
        assertEquals(FaceTopology.triangles.take(3).map { listOf(it + 1, it + 1) }, first)
        assertTrue(obj.any { it.contains("Uncalibrated") })
        assertFalse(obj.any { it.startsWith("mtllib ") })
    }

    @Test fun photoRequestIsExplicitOneShotAndCancellable() {
        val request = FaceTextureRequest()
        assertEquals(0L, request.take())
        val id = request.request(); assertEquals(id, request.take()); assertEquals(0L, request.take())
        val cancelled = request.request(); request.cancel(); assertEquals(0L, request.take())
        assertTrue(request.request() > cancelled)
    }

    @Test fun textureAndNeutralRequireMatchingCameraAndSimilarLandmarks() {
        val base = FaceSnapshot(points(), 640, 480, 0.0, 3)
        assertTrue(FaceTextureMatch.isConsistent(base, FaceFrame(points(0.01f), 640, 480, 100)))
        assertFalse(FaceTextureMatch.isConsistent(base, FaceFrame(points(0.1f), 640, 480, 100)))
        assertFalse(FaceTextureMatch.isConsistent(base, FaceFrame(points(), 480, 640, 100)))
    }

}

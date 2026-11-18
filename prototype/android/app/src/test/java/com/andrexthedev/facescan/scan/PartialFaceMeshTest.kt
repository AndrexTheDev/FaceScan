package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.AnchoredMultiView
import com.andrexthedev.facescan.geometry.CameraModel
import com.andrexthedev.facescan.geometry.Mat3
import com.andrexthedev.facescan.geometry.MultiViewPointCloud
import com.andrexthedev.facescan.geometry.MultiViewTriangulation
import com.andrexthedev.facescan.geometry.ValidatedAnchorPose
import org.junit.Assert.*
import org.junit.Test
import kotlin.math.sin
import kotlin.random.Random

class PartialFaceMeshTest {
    private fun world(i: Int) = doubleArrayOf((i % 26 - 12.5) * 3.0, (i / 26 - 9.0) * 3.0, sin(i * .3) * 3.0)
    private fun cloud(missing: Set<Int> = emptySet()): MultiViewPointCloud.Result {
        val p = (0 until 468).map { i ->
            if (i in missing) MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS)
            else MultiViewTriangulation.Result.Point(world(i), 8.0, 0.0, 0.0)
        }
        return MultiViewPointCloud.Result(p, 468 - missing.size)
    }
    @Test fun syntheticDeviceTest() { assertTrue(PartialFaceMeshSelfTest.run()) }
    @Test fun excludesMissingTrianglesAndPreservesSourceMapping() {
        val missing = setOf(0, 5, 100)
        val result = PartialFaceMesh.build(cloud(missing))
        val mesh = result.mesh!!
        assertEquals(465, result.acceptedPoints)
        val expectedFaces = FaceTopology.triangles.toList().chunked(3).count { triangle -> triangle.any { it in missing } }
        assertTrue(result.skippedTriangles >= expectedFaces)
        assertTrue(mesh.sourceIndices.none { it in missing })
        assertTrue(mesh.triangles.all { it in mesh.vertices.indices })
        for (i in mesh.vertices.indices) assertArrayEquals(world(mesh.sourceIndices[i]), mesh.vertices[i], 0.0)
        val obj = String(PartialFaceMesh.writeObj(mesh), Charsets.UTF_8).lines()
        assertEquals(mesh.vertices.size, obj.count { it.startsWith("v ") })
        assertEquals(mesh.triangles.size / 3, obj.count { it.startsWith("f ") })
        assertTrue(obj.any { it.contains("not validated") })
    }
    @Test fun lengthLimitAndDegenerateInputNeverInventSurface() {
        val limited = PartialFaceMesh.build(cloud(), maxEdgeLength = .001)
        assertNull(limited.mesh)
        assertEquals(898, limited.skippedTriangles)
        val allMissing = PartialFaceMesh.build(cloud((0 until 468).toSet()))
        assertNull(allMissing.mesh)
        try { PartialFaceMesh.build(cloud(), 0.0); fail() } catch (_: IllegalArgumentException) { }
    }
    @Test fun knownAnchorPoseToPartialFaceObjEndToEnd() {
        val camera = CameraModel(900.0, 910.0, 320.0, 240.0)
        val random = Random(123)
        val anchors = List(30) { doubleArrayOf(random.nextDouble(-80.0,80.0), random.nextDouble(-90.0,90.0), random.nextDouble(-35.0,35.0)) }
        val missing = setOf(0, 5, 100)
        fun view(rotation: Mat3, translation: DoubleArray, hide: Boolean): AnchoredMultiView.View {
            fun project(p: DoubleArray): MultiViewPointCloud.Pixel {
                val q = DoubleArray(2); camera.project(rotation, translation, p, q)
                return MultiViewPointCloud.Pixel(q[0], q[1])
            }
            return AnchoredMultiView.View(camera, anchors.map { a ->
                val p = project(a); ValidatedAnchorPose.Anchor(a, p.u, p.v)
            }, (0 until 468).map { i -> if (hide && i in missing) null else project(world(i)) })
        }
        val views = listOf(view(Mat3.identity(), doubleArrayOf(0.0,0.0,600.0), true),
            view(Mat3.fromRodrigues(doubleArrayOf(.03,-.12,.02)), doubleArrayOf(-100.0,4.0,610.0), true),
            view(Mat3.fromRodrigues(doubleArrayOf(-.03,.1,-.02)), doubleArrayOf(80.0,-3.0,590.0), false))
        val result = AnchoredFaceReconstruction.reconstruct(views)
        assertEquals(listOf(0,1,2), result.reconstruction.acceptedViewIndices)
        val partial = result.surface!!
        assertEquals(465, partial.acceptedPoints)
        assertTrue(partial.skippedTriangles > 0)
        val mesh = partial.mesh!!
        for (i in mesh.vertices.indices) assertArrayEquals(world(mesh.sourceIndices[i]), mesh.vertices[i], .01)
        assertTrue(String(PartialFaceMesh.writeObj(mesh), Charsets.UTF_8).contains("f "))
    }
}

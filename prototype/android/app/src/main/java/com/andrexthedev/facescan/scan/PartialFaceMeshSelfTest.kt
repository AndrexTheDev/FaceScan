package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.MultiViewPointCloud
import com.andrexthedev.facescan.geometry.MultiViewTriangulation
import kotlin.math.sin

/** Künstliche Punktwolke, keine echte Person. */
object PartialFaceMeshSelfTest {
    fun run(): Boolean {
        val data = (0 until FaceTopology.VERTEX_COUNT).map { i ->
            if (i == 0) MultiViewTriangulation.Result.Rejected(MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS)
            else MultiViewTriangulation.Result.Point(doubleArrayOf((i%26-12.5)*3, (i/26-9.0)*3, sin(i*.3)*3), 8.0, 0.0, 0.0)
        }
        val result = PartialFaceMesh.build(MultiViewPointCloud.Result(data, data.size-1))
        val mesh = result.mesh ?: return false
        if (result.acceptedPoints != 467 || result.skippedTriangles == 0 || mesh.sourceIndices.any { it == 0 }) return false
        val obj = String(PartialFaceMesh.writeObj(mesh), Charsets.UTF_8)
        return obj.lineSequence().count { it.startsWith("v ") } == mesh.vertices.size &&
            obj.lineSequence().count { it.startsWith("f ") } == mesh.triangles.size / 3 && obj.contains("not validated")
    }
}

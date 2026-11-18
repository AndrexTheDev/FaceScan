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
        if (obj.lineSequence().count { it.startsWith("v ") } != mesh.vertices.size ||
            obj.lineSequence().count { it.startsWith("f ") } != mesh.triangles.size / 3 ||
            !obj.contains("not validated")) return false
        // Strukturzählung: das künstliche Gitter ist offen, aber zusammenhängend.
        val topology = PartialMeshTopology.inspect(mesh)
        if (topology.triangleCount != mesh.triangles.size / 3 || topology.components != 1 ||
            topology.boundaryEdges <= 0 || topology.nonManifoldEdges != 0) return false
        if (!obj.contains("# topology ${PartialMeshTopology.describe(topology)}")) return false
        if (topology.largestComponentTriangles != topology.triangleCount) return false
        // Statischer GLB-Export: Kopf, Binärteil und dieselben Dreiecke wie im Mesh.
        val glb = PartialGlbWriter.write(mesh)
        if (glb.size < 20 || glb[0] != 'g'.code.toByte() || glb[1] != 'l'.code.toByte() ||
            glb[2] != 'T'.code.toByte() || glb[3] != 'F'.code.toByte()) return false
        val glbJson = String(glb, Charsets.ISO_8859_1)
        if (!glbJson.contains("\"count\":${mesh.triangles.size}") ||
            !glbJson.contains("open partial surface")) return false
        val dense = MultiViewSurface.densePoints(MultiViewPointCloud.Result(data, data.size - 1))
        if (dense[0].isFinite() || !dense[3].isFinite() || kotlin.math.abs(MultiViewSurface.coverage(dense) - 467.0 / 468.0) > 1e-9) return false
        return MultiViewSessionSelfTest.run()
    }
}

package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.MultiViewPointCloud
import com.andrexthedev.facescan.geometry.MultiViewTriangulation

/** Nur gemessene/triangulierte Punkte; fehlende Bereiche werden nicht ergänzt. */
object PartialFaceMesh {
    data class Mesh(val vertices: List<DoubleArray>, val sourceIndices: IntArray, val triangles: IntArray)
    data class Result(val mesh: Mesh?, val acceptedPoints: Int, val skippedTriangles: Int)

    /**
     * Gibt ausschließlich Originaldreiecke aus, deren drei Eckpunkte vorliegen
     * und nicht exakt kollabiert sind. Optional können zu lange Kanten in der
     * Einheit der eingegebenen Posen ausgeschlossen werden. Keine Gewähr, dass
     * sichtbare oder triangulierte Punkte anatomisch korrekt sind.
     */
    fun build(cloud: MultiViewPointCloud.Result, maxEdgeLength: Double? = null): Result {
        require(cloud.points.size == FaceTopology.VERTEX_COUNT)
        require(maxEdgeLength == null || (maxEdgeLength.isFinite() && maxEdgeLength > 0.0))
        val points = cloud.points.map { value ->
            when (value) {
                is MultiViewTriangulation.Result.Point -> value.xyz.also { require(it.size == 3 && it.all(Double::isFinite)) }
                is MultiViewTriangulation.Result.Rejected -> null
            }
        }
        val accepted = points.count { it != null }
        val selected = mutableListOf<Int>()
        val indices = FaceTopology.triangles
        for (i in indices.indices step 3) {
            val a = points[indices[i]] ?: continue
            val b = points[indices[i+1]] ?: continue
            val c = points[indices[i+2]] ?: continue
            val ab = DoubleArray(3) { b[it] - a[it] }; val ac = DoubleArray(3) { c[it] - a[it] }
            val bc = DoubleArray(3) { c[it] - b[it] }
            val cross = doubleArrayOf(ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
            val area2 = Math.hypot(Math.hypot(cross[0], cross[1]), cross[2])
            if (!area2.isFinite() || area2 <= 0.0) continue
            if (maxEdgeLength != null && listOf(ab, ac, bc).any {
                    val length = Math.hypot(Math.hypot(it[0], it[1]), it[2])
                    !length.isFinite() || length > maxEdgeLength
                }) continue
            selected.add(indices[i]); selected.add(indices[i+1]); selected.add(indices[i+2])
        }
        val skipped = indices.size / 3 - selected.size / 3
        if (selected.isEmpty()) return Result(null, accepted, skipped)
        // Nur tatsächlich referenzierte Punkte; deterministische Originalreihenfolge.
        val used = selected.toSet().sorted()
        val remap = IntArray(points.size) { -1 }
        used.forEachIndexed { index, original -> remap[original] = index }
        val mesh = Mesh(used.map { points[it]!!.copyOf() }, used.toIntArray(), selected.map { remap[it] }.toIntArray())
        return Result(mesh, accepted, skipped)
    }

    /**
     * Kompakte Float-Punkte (3N) für die bestehende Vorschau. Nicht belegte
     * Slots werden mit NaN markiert; der Renderer prüft auf endliche Werte und
     * zeichnet solche Daten nicht.
     */
    fun densePoints(mesh: Mesh): FloatArray {
        val out = FloatArray(FaceTopology.VERTEX_COUNT * 3) { Float.NaN }
        for (i in mesh.sourceIndices.indices) {
            val target = mesh.sourceIndices[i]
            out[3 * target] = mesh.vertices[i][0].toFloat()
            out[3 * target + 1] = mesh.vertices[i][1].toFloat()
            out[3 * target + 2] = mesh.vertices[i][2].toFloat()
        }
        return out
    }

    /**
     * Offenes, untexturiertes OBJ mit Flächennormalen je Vertex; Einheit stammt
     * aus den Ankern. Normalen verbessern nur die Beleuchtung im Viewer und
     * sind kein Genauigkeitsbeleg.
     */
    fun writeObjWithNormals(mesh: Mesh): ByteArray {
        require(mesh.vertices.isNotEmpty() && mesh.vertices.all { it.size == 3 && it.all(Double::isFinite) })
        require(mesh.sourceIndices.size == mesh.vertices.size && mesh.triangles.isNotEmpty() &&
            mesh.triangles.size % 3 == 0 && mesh.triangles.all { it in mesh.vertices.indices })
        val flat = FloatArray(mesh.vertices.size * 3) { i -> mesh.vertices[i / 3][i % 3].toFloat() }
        val normals = MeshNormals.calculate(flat, mesh.triangles)
        val out = StringBuilder("# FaceScan partial multiview surface\n" +
            "# Scale and units derive from supplied anchors; not validated.\n" +
            "# Missing points and faces are omitted; no completion, texture or animation.\n")
        for (vertex in mesh.vertices) out.append("v ").append(vertex[0]).append(' ')
            .append(vertex[1]).append(' ').append(vertex[2]).append('\n')
        for (i in mesh.vertices.indices) out.append("vn ").append(normals[3 * i]).append(' ')
            .append(normals[3 * i + 1]).append(' ').append(normals[3 * i + 2]).append('\n')
        for (i in mesh.triangles.indices step 3) {
            out.append('f')
            for (j in 0..2) {
                val index = mesh.triangles[i + j] + 1
                out.append(' ').append(index).append("//").append(index)
            }
            out.append('\n')
        }
        return out.toString().toByteArray(Charsets.UTF_8)
    }

    /** Offenes, untexturiertes OBJ; Koordinateneinheit stammt aus den Ankern. */
    fun writeObj(mesh: Mesh): ByteArray {
        require(mesh.vertices.isNotEmpty() && mesh.vertices.all { it.size == 3 && it.all(Double::isFinite) })
        require(mesh.sourceIndices.size == mesh.vertices.size && mesh.triangles.isNotEmpty() && mesh.triangles.size % 3 == 0 &&
            mesh.triangles.all { it in mesh.vertices.indices })
        val out = StringBuilder("# FaceScan partial multiview surface\n# Scale and units derive from supplied anchors; not validated.\n# Missing points and faces are omitted; no completion, texture or animation.\n")
        for (vertex in mesh.vertices) out.append("v ").append(vertex[0]).append(' ').append(vertex[1]).append(' ').append(vertex[2]).append('\n')
        for (i in mesh.triangles.indices step 3) out.append("f ").append(mesh.triangles[i]+1).append(' ')
            .append(mesh.triangles[i+1]+1).append(' ').append(mesh.triangles[i+2]+1).append('\n')
        return out.toString().toByteArray(Charsets.UTF_8)
    }
}

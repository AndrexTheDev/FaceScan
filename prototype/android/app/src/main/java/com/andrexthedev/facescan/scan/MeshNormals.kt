package com.andrexthedev.facescan.scan

/** Flächengewichtete Vertexnormalen für Beleuchtung, keine zusätzliche Geometrie. */
object MeshNormals {
    /**
     * Konsistente Dreiecksreihenfolge vorausgesetzt. Degenerierte Flächen tragen
     * nichts bei; isolierte/ausgelöschte Normalen erhalten die feste Richtung +Z.
     */
    fun calculate(points: FloatArray, triangles: IntArray): FloatArray {
        require(points.isNotEmpty() && points.size % 3 == 0 && points.all { it.isFinite() })
        val vertices = points.size / 3
        require(triangles.size % 3 == 0 && triangles.all { it in 0 until vertices })
        val sums = DoubleArray(points.size)
        for (t in triangles.indices step 3) {
            val a = triangles[t] * 3; val b = triangles[t + 1] * 3; val c = triangles[t + 2] * 3
            val abx = points[b].toDouble() - points[a]; val aby = points[b + 1].toDouble() - points[a + 1]; val abz = points[b + 2].toDouble() - points[a + 2]
            val acx = points[c].toDouble() - points[a]; val acy = points[c + 1].toDouble() - points[a + 1]; val acz = points[c + 2].toDouble() - points[a + 2]
            val x = aby * acz - abz * acy; val y = abz * acx - abx * acz; val z = abx * acy - aby * acx
            sums[a] += x; sums[a + 1] += y; sums[a + 2] += z
            sums[b] += x; sums[b + 1] += y; sums[b + 2] += z
            sums[c] += x; sums[c + 1] += y; sums[c + 2] += z
        }
        val normals = FloatArray(points.size)
        for (i in 0 until vertices) {
            val p = 3 * i
            val length = Math.hypot(Math.hypot(sums[p], sums[p + 1]), sums[p + 2])
            if (length > 0.0 && length.isFinite()) {
                normals[p] = (sums[p] / length).toFloat()
                normals[p + 1] = (sums[p + 1] / length).toFloat()
                normals[p + 2] = (sums[p + 2] / length).toFloat()
            } else normals[p + 2] = 1f
        }
        return normals
    }
}

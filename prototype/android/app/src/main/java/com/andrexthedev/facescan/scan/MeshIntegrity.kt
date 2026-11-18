package com.andrexthedev.facescan.scan

/** Interne Netz-Auffälligkeiten; keine Prüfung anatomischer oder metrischer Richtigkeit. */
object MeshIntegrity {
    // Nicht anhand realer Geräte/Gesichter kalibrierte Startwerte in Augenabständen.
    const val SMALL_DOUBLE_AREA = 1e-8
    const val LONG_EDGE = 0.75
    data class Counts(val tinyTriangles: Int, val longEdgeTriangles: Int, val totalTriangles: Int)
    data class Summary(val neutral: Counts, val maxTinyTriangles: Int, val maxLongEdgeTriangles: Int)

    fun inspect(points: FloatArray, triangles: IntArray): Counts {
        require(points.isNotEmpty() && points.size % 3 == 0 && points.all { it.isFinite() })
        require(triangles.isNotEmpty() && triangles.size % 3 == 0 && triangles.all { it in 0 until points.size / 3 })
        var tiny = 0; var long = 0
        for (i in triangles.indices step 3) {
            val a = 3 * triangles[i]; val b = 3 * triangles[i + 1]; val c = 3 * triangles[i + 2]
            val abx = points[b].toDouble() - points[a]; val aby = points[b+1].toDouble() - points[a+1]; val abz = points[b+2].toDouble() - points[a+2]
            val acx = points[c].toDouble() - points[a]; val acy = points[c+1].toDouble() - points[a+1]; val acz = points[c+2].toDouble() - points[a+2]
            val bcx = points[c].toDouble() - points[b]; val bcy = points[c+1].toDouble() - points[b+1]; val bcz = points[c+2].toDouble() - points[b+2]
            val nx = aby*acz - abz*acy; val ny = abz*acx - abx*acz; val nz = abx*acy - aby*acx
            if (Math.hypot(Math.hypot(nx, ny), nz) <= SMALL_DOUBLE_AREA) tiny++
            if (maxOf(Math.hypot(Math.hypot(abx, aby), abz), Math.hypot(Math.hypot(acx, acy), acz),
                    Math.hypot(Math.hypot(bcx, bcy), bcz)) > LONG_EDGE) long++
        }
        return Counts(tiny, long, triangles.size / 3)
    }

    fun inspect(surface: FaceSurface): Summary {
        val keys = surface.keyframes()
        require(keys.size in 2..FaceSequenceRecorder.MAX_EXPORT_KEYFRAMES && surface.neutral.size == FaceTopology.VERTEX_COUNT * 3)
        require(keys.all { it.points.size == surface.neutral.size })
        val neutral = inspect(surface.neutral, FaceTopology.triangles)
        var maxTiny = neutral.tinyTriangles; var maxLong = neutral.longEdgeTriangles
        for (key in keys) {
            val count = inspect(key.points, FaceTopology.triangles)
            maxTiny = maxOf(maxTiny, count.tinyTriangles); maxLong = maxOf(maxLong, count.longEdgeTriangles)
        }
        return Summary(neutral, maxTiny, maxLong)
    }
}

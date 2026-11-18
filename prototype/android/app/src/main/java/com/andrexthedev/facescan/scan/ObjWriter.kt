package com.andrexthedev.facescan.scan

/** Statisches neutrales, offenes Flächennetz; keine Animation oder Fototextur. */
object ObjWriter {
    fun write(surface: FaceSurface): ByteArray {
        val points = surface.neutral
        require(points.size == FaceTopology.VERTEX_COUNT * 3 && points.all { it.isFinite() })
        val triangles = FaceTopology.triangles
        require(triangles.size % 3 == 0 && triangles.all { it in 0 until FaceTopology.VERTEX_COUNT })
        val normals = MeshNormals.calculate(points, triangles)
        val text = StringBuilder()
        text.append("# FaceScan experimental face surface\n")
        text.append("# Uncalibrated units: 1 unit is the eye distance. No metric accuracy.\n")
        text.append("# Single view; open surface, no hair, back of head, texture or animation.\n")
        text.append("o FaceSurface\n")
        for (i in 0 until FaceTopology.VERTEX_COUNT) {
            text.append("v ").append(points[3*i]).append(' ').append(points[3*i+1]).append(' ').append(points[3*i+2]).append('\n')
        }
        for (i in 0 until FaceTopology.VERTEX_COUNT) {
            text.append("vn ").append(normals[3*i]).append(' ').append(normals[3*i+1]).append(' ').append(normals[3*i+2]).append('\n')
        }
        for (i in triangles.indices step 3) {
            text.append("f")
            for (j in 0..2) {
                val index = triangles[i + j] + 1
                text.append(' ').append(index).append("//").append(index)
            }
            text.append('\n')
        }
        return text.toString().toByteArray(Charsets.UTF_8)
    }
}

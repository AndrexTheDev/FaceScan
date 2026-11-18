package com.andrexthedev.facescan.scan

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Statisches, untexturiertes glTF 2.0 (GLB) für das offene Mehransichten-Teilnetz.
 *
 * Was die Datei enthält: genau die triangulierten Punkte und Flächen aus
 * [PartialFaceMesh] mit Flächennormalen. Keine Animation, keine Fototextur,
 * keine Ergänzung fehlender Bereiche.
 *
 * Was sie NICHT belegt: Die Einheit stammt aus kanonischen Durchschnittsankern
 * und ist keine Vermessung der aufgenommenen Person. Fehlende Punkte bleiben
 * fehlend; offene Ränder sind beabsichtigt.
 */
object PartialGlbWriter {
    /** glTF erlaubt 16-Bit-Indizes nur bis 65535 Vertices; das Teilnetz liegt weit darunter. */
    private const val MAX_VERTICES = 65535

    fun write(mesh: PartialFaceMesh.Mesh): ByteArray {
        require(mesh.vertices.isNotEmpty() && mesh.vertices.all { it.size == 3 && it.all(Double::isFinite) })
        require(mesh.sourceIndices.size == mesh.vertices.size)
        require(mesh.triangles.isNotEmpty() && mesh.triangles.size % 3 == 0 &&
            mesh.triangles.all { it in mesh.vertices.indices })
        val count = mesh.vertices.size
        require(count <= MAX_VERTICES)
        val positions = FloatArray(count * 3) { i -> mesh.vertices[i / 3][i % 3].toFloat() }
        require(positions.all(Float::isFinite))
        val normals = MeshNormals.calculate(positions, mesh.triangles)
        val indices = mesh.triangles

        val binary = ByteArrayOutputStream()
        fun floats(values: FloatArray) {
            val buffer = ByteBuffer.allocate(values.size * 4).order(ByteOrder.LITTLE_ENDIAN)
            values.forEach { buffer.putFloat(it) }
            binary.write(buffer.array())
        }
        fun shorts(values: IntArray) {
            val buffer = ByteBuffer.allocate(values.size * 2).order(ByteOrder.LITTLE_ENDIAN)
            values.forEach { buffer.putShort(it.toShort()) }
            binary.write(buffer.array())
        }
        fun align() { while (binary.size() % 4 != 0) binary.write(0) }
        fun bounds(values: FloatArray): Pair<String, String> {
            val min = FloatArray(3) { Float.POSITIVE_INFINITY }
            val max = FloatArray(3) { Float.NEGATIVE_INFINITY }
            for (i in values.indices) {
                val axis = i % 3
                min[axis] = minOf(min[axis], values[i])
                max[axis] = maxOf(max[axis], values[i])
            }
            return min.joinToString(",", "[", "]") to max.joinToString(",", "[", "]")
        }

        val positionOffset = binary.size(); floats(positions)
        val normalOffset = binary.size(); floats(normals)
        val indexOffset = binary.size(); shorts(indices)
        align()
        val bytes = binary.toByteArray()
        val (min, max) = bounds(positions)

        val json = """{
"asset":{"version":"2.0","generator":"FaceScan prototype","extras":{"units":"centimetres derived from canonical average anchors; not a measurement of the subject","limitations":"open partial surface, no completion, no texture, no animation, no real-device accuracy validation"}},
"scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0,"name":"PartialFaceMesh"}],
"meshes":[{"name":"PartialFaceMesh","primitives":[{"attributes":{"POSITION":0,"NORMAL":1},"indices":2,"material":0,"mode":4}]}],
"materials":[{"name":"Partial","doubleSided":true,"pbrMetallicRoughness":{"baseColorFactor":[0.75,0.62,0.55,1],"metallicFactor":0,"roughnessFactor":1}}],
"buffers":[{"byteLength":${bytes.size}}],
"bufferViews":[
{"buffer":0,"byteOffset":$positionOffset,"byteLength":${positions.size * 4},"target":34962},
{"buffer":0,"byteOffset":$normalOffset,"byteLength":${normals.size * 4},"target":34962},
{"buffer":0,"byteOffset":$indexOffset,"byteLength":${indices.size * 2},"target":34963}],
"accessors":[
{"bufferView":0,"componentType":5126,"count":$count,"type":"VEC3","min":$min,"max":$max},
{"bufferView":1,"componentType":5126,"count":$count,"type":"VEC3"},
{"bufferView":2,"componentType":5123,"count":${indices.size},"type":"SCALAR"}]}""".toByteArray(Charsets.UTF_8)

        // glTF verlangt: JSON mit Leerzeichen, BIN mit Nullen auf 4 Byte auffüllen.
        val jsonLength = (json.size + 3) and -4
        val total = 12 + 8 + jsonLength + 8 + bytes.size
        val out = ByteBuffer.allocate(total).order(ByteOrder.LITTLE_ENDIAN)
        out.putInt(0x46546c67).putInt(2).putInt(total)
        out.putInt(jsonLength).putInt(0x4e4f534a).put(json)
        repeat(jsonLength - json.size) { out.put(0x20.toByte()) }
        out.putInt(bytes.size).putInt(0x004e4942).put(bytes)
        return out.array()
    }
}

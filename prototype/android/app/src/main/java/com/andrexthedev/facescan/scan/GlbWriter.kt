package com.andrexthedev.facescan.scan

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** glTF 2.0 GLB mit Gesichtsdreiecken und einer aufgezeichneten Mimik als Morph-Animation. */
object GlbWriter {
    fun write(surface: FaceSurface): ByteArray {
        val n = FaceTopology.VERTEX_COUNT
        require(surface.neutral.size == n * 3 && surface.expression.size == n * 3)
        require(surface.neutral.all { it.isFinite() } && surface.expression.all { it.isFinite() })
        val deltas = FloatArray(n * 3) { surface.expression[it] - surface.neutral[it] }
        require(deltas.all { it.isFinite() })
        val indices = FaceTopology.triangles
        require(indices.isNotEmpty() && indices.size % 3 == 0 && indices.all { it in 0 until n })

        val binary = ByteArrayOutputStream()
        fun floats(values: FloatArray) {
            val b = ByteBuffer.allocate(values.size * 4).order(ByteOrder.LITTLE_ENDIAN)
            values.forEach { b.putFloat(it) }
            binary.write(b.array())
        }
        fun shorts(values: IntArray) {
            val b = ByteBuffer.allocate(values.size * 2).order(ByteOrder.LITTLE_ENDIAN)
            values.forEach { b.putShort(it.toShort()) }
            binary.write(b.array())
        }
        fun align() { while (binary.size() % 4 != 0) binary.write(0) }
        fun bounds(values: FloatArray): Pair<String, String> {
            val min = FloatArray(3) { Float.POSITIVE_INFINITY }
            val max = FloatArray(3) { Float.NEGATIVE_INFINITY }
            for (i in values.indices) { val axis = i % 3; min[axis] = minOf(min[axis], values[i]); max[axis] = maxOf(max[axis], values[i]) }
            return min.joinToString(",", "[", "]") to max.joinToString(",", "[", "]")
        }
        val positionsOffset = binary.size(); floats(surface.neutral); align()
        val indicesOffset = binary.size(); shorts(indices); align()
        val deltaOffset = binary.size(); floats(deltas); align()
        val timesOffset = binary.size(); floats(floatArrayOf(0f, 1f, 2f)); align()
        val weightsOffset = binary.size(); floats(floatArrayOf(0f, 1f, 0f)); align()
        val bytes = binary.toByteArray()
        val (min, max) = bounds(surface.neutral)
        val (deltaMin, deltaMax) = bounds(deltas)
        val json = """{
"asset":{"version":"2.0","generator":"FaceScan prototype","extras":{"scale":"uncalibrated; one unit is eye distance","limitations":"single-view face surface; no texture, hair, back of head or validated metric accuracy"}},
"scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0,"name":"Face"}],
"meshes":[{"name":"FaceSurface","weights":[0],"extras":{"targetNames":["expression"]},"primitives":[{"attributes":{"POSITION":0},"indices":1,"material":0,"targets":[{"POSITION":2}]}]}],
"materials":[{"name":"Face","doubleSided":true,"pbrMetallicRoughness":{"baseColorFactor":[0.75,0.62,0.55,1],"metallicFactor":0,"roughnessFactor":1}}],
"animations":[{"name":"Expression","samplers":[{"input":3,"output":4,"interpolation":"LINEAR"}],"channels":[{"sampler":0,"target":{"node":0,"path":"weights"}}]}],
"buffers":[{"byteLength":${bytes.size}}],
"bufferViews":[
{"buffer":0,"byteOffset":$positionsOffset,"byteLength":${n * 12},"target":34962},
{"buffer":0,"byteOffset":$indicesOffset,"byteLength":${indices.size * 2},"target":34963},
{"buffer":0,"byteOffset":$deltaOffset,"byteLength":${n * 12},"target":34962},
{"buffer":0,"byteOffset":$timesOffset,"byteLength":12},
{"buffer":0,"byteOffset":$weightsOffset,"byteLength":12}],
"accessors":[
{"bufferView":0,"componentType":5126,"count":$n,"type":"VEC3","min":$min,"max":$max},
{"bufferView":1,"componentType":5123,"count":${indices.size},"type":"SCALAR"},
{"bufferView":2,"componentType":5126,"count":$n,"type":"VEC3","min":$deltaMin,"max":$deltaMax},
{"bufferView":3,"componentType":5126,"count":3,"type":"SCALAR","min":[0],"max":[2]},
{"bufferView":4,"componentType":5126,"count":3,"type":"SCALAR"}]}
""".toByteArray(Charsets.UTF_8)
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

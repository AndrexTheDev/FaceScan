package com.andrexthedev.facescan.scan

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** glTF 2.0: zeitgestempelte Mimik als Morph-Targets mit linearen Gewichtskurven. */
object GlbWriter {
    fun write(surface: FaceSurface): ByteArray {
        val n = FaceTopology.VERTEX_COUNT
        val keys = surface.keyframes()
        require(keys.size in 2..(FaceSequenceRecorder.MAX_FRAMES + 1))
        require(surface.neutral.size == n * 3 && keys.first().seconds == 0f && keys.first().points.contentEquals(surface.neutral))
        keys.forEachIndexed { i, key ->
            require(key.points.size == n * 3 && key.points.all { it.isFinite() } && key.seconds.isFinite())
            if (i > 0) require(key.seconds > keys[i - 1].seconds)
        }
        val deltas = keys.drop(1).map { key ->
            FloatArray(n * 3) { key.points[it] - surface.neutral[it] }.also { require(it.all(Float::isFinite)) }
        }
        val indices = FaceTopology.triangles
        require(indices.isNotEmpty() && indices.size % 3 == 0 && indices.all { it in 0 until n })

        val binary = ByteArrayOutputStream()
        fun floats(values: FloatArray) {
            val b = ByteBuffer.allocate(values.size * 4).order(ByteOrder.LITTLE_ENDIAN)
            values.forEach { b.putFloat(it) }; binary.write(b.array())
        }
        fun shorts(values: IntArray) {
            val b = ByteBuffer.allocate(values.size * 2).order(ByteOrder.LITTLE_ENDIAN)
            values.forEach { b.putShort(it.toShort()) }; binary.write(b.array())
        }
        fun align() { while (binary.size() % 4 != 0) binary.write(0) }
        fun bounds(values: FloatArray): Pair<String, String> {
            val min = FloatArray(3) { Float.POSITIVE_INFINITY }; val max = FloatArray(3) { Float.NEGATIVE_INFINITY }
            for (i in values.indices) { val axis = i % 3; min[axis] = minOf(min[axis], values[i]); max[axis] = maxOf(max[axis], values[i]) }
            return min.joinToString(",", "[", "]") to max.joinToString(",", "[", "]")
        }
        val positionsOffset = binary.size(); floats(surface.neutral); align()
        val indicesOffset = binary.size(); shorts(indices); align()
        val deltaOffsets = deltas.map { val offset = binary.size(); floats(it); align(); offset }
        val timesOffset = binary.size(); floats(keys.map { it.seconds }.toFloatArray()); align()
        val targetCount = deltas.size
        val weights = FloatArray(keys.size * targetCount)
        for (i in 1 until keys.size) weights[i * targetCount + i - 1] = 1f
        val weightsOffset = binary.size(); floats(weights); align()
        val bytes = binary.toByteArray()
        val (min, max) = bounds(surface.neutral)
        val views = mutableListOf(
            "{\"buffer\":0,\"byteOffset\":$positionsOffset,\"byteLength\":${n * 12},\"target\":34962}",
            "{\"buffer\":0,\"byteOffset\":$indicesOffset,\"byteLength\":${indices.size * 2},\"target\":34963}"
        )
        views.addAll(deltaOffsets.map { "{\"buffer\":0,\"byteOffset\":$it,\"byteLength\":${n * 12},\"target\":34962}" })
        views.add("{\"buffer\":0,\"byteOffset\":$timesOffset,\"byteLength\":${keys.size * 4}}")
        views.add("{\"buffer\":0,\"byteOffset\":$weightsOffset,\"byteLength\":${weights.size * 4}}")
        val accessors = mutableListOf(
            "{\"bufferView\":0,\"componentType\":5126,\"count\":$n,\"type\":\"VEC3\",\"min\":$min,\"max\":$max}",
            "{\"bufferView\":1,\"componentType\":5123,\"count\":${indices.size},\"type\":\"SCALAR\"}"
        )
        deltas.forEachIndexed { i, delta ->
            val (dmin, dmax) = bounds(delta)
            accessors.add("{\"bufferView\":${i + 2},\"componentType\":5126,\"count\":$n,\"type\":\"VEC3\",\"min\":$dmin,\"max\":$dmax}")
        }
        val timesAccessor = accessors.size
        accessors.add("{\"bufferView\":$timesAccessor,\"componentType\":5126,\"count\":${keys.size},\"type\":\"SCALAR\",\"min\":[0],\"max\":[${keys.last().seconds}]}")
        val weightsAccessor = accessors.size
        accessors.add("{\"bufferView\":$weightsAccessor,\"componentType\":5126,\"count\":${weights.size},\"type\":\"SCALAR\"}")
        val targetJson = deltas.indices.joinToString(",") { "{\"POSITION\":${it + 2}}" }
        val targetNames = deltas.indices.joinToString(",") { "\"frame_${it + 1}\"" }
        val zeros = deltas.indices.joinToString(",") { "0" }
        val json = """{
"asset":{"version":"2.0","generator":"FaceScan prototype","extras":{"scale":"uncalibrated; one unit is eye distance","limitations":"single-view face surface; no texture, hair, back of head or validated metric accuracy"}},
"scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0,"name":"Face"}],
"meshes":[{"name":"FaceSurface","weights":[$zeros],"extras":{"targetNames":[$targetNames]},"primitives":[{"attributes":{"POSITION":0},"indices":1,"material":0,"targets":[$targetJson]}]}],
"materials":[{"name":"Face","doubleSided":true,"pbrMetallicRoughness":{"baseColorFactor":[0.75,0.62,0.55,1],"metallicFactor":0,"roughnessFactor":1}}],
"animations":[{"name":"RecordedExpression","samplers":[{"input":$timesAccessor,"output":$weightsAccessor,"interpolation":"LINEAR"}],"channels":[{"sampler":0,"target":{"node":0,"path":"weights"}}]}],
"buffers":[{"byteLength":${bytes.size}}],"bufferViews":[${views.joinToString(",")}],"accessors":[${accessors.joinToString(",")}]}""".toByteArray(Charsets.UTF_8)
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

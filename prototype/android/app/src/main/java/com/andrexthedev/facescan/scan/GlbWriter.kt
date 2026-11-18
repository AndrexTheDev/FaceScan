package com.andrexthedev.facescan.scan

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** glTF 2.0: zeitgestempelte Mimik als Morph-Targets mit linearen Gewichtskurven. */
object GlbWriter {
    fun write(surface: FaceSurface): ByteArray {
        val n = FaceTopology.VERTEX_COUNT
        val keys = surface.keyframes()
        require(keys.size in 2..FaceSequenceRecorder.MAX_EXPORT_KEYFRAMES)
        require(surface.neutral.size == n * 3 && keys.first().seconds == 0f && keys.first().points.contentEquals(surface.neutral))
        keys.forEachIndexed { i, key ->
            require(key.points.size == n * 3 && key.points.all { it.isFinite() } && key.seconds.isFinite())
            if (i > 0) require(key.seconds > keys[i - 1].seconds)
        }
        val deltas = keys.drop(1).map { key ->
            FloatArray(n * 3) { key.points[it] - surface.neutral[it] }.also { require(it.all(Float::isFinite)) }
        }
        val texture = surface.texture
        if (texture != null) {
            require(texture.jpeg.size in 1..FaceTextureCapture.MAX_JPEG_BYTES)
            require(texture.jpeg.size >= 4 && texture.jpeg[0] == 0xff.toByte() && texture.jpeg[1] == 0xd8.toByte() &&
                texture.jpeg[texture.jpeg.size - 2] == 0xff.toByte() && texture.jpeg.last() == 0xd9.toByte())
            require(texture.uv.size == n * 2 && texture.uv.all { it.isFinite() && it in 0f..1f })
        }
        val indices = FaceTopology.triangles
        require(indices.isNotEmpty() && indices.size % 3 == 0 && indices.all { it in 0 until n })
        val baseNormals = MeshNormals.calculate(surface.neutral, indices)
        val normalDeltas = keys.drop(1).map { key ->
            val normals = MeshNormals.calculate(key.points, indices)
            FloatArray(n * 3) { normals[it] - baseNormals[it] }
        }

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
        val uvOffset = if (texture != null) binary.size().also { floats(texture.uv); align() } else null
        val imageOffset = if (texture != null) binary.size().also { binary.write(texture.jpeg); align() } else null
        // Am Ende angehängt: bestehende Positions-/UV-Puffer bleiben unverändert.
        val normalOffset = binary.size(); floats(baseNormals); align()
        val normalDeltaOffsets = normalDeltas.map { val offset = binary.size(); floats(it); align(); offset }
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
        val textureAccessor = if (texture != null) {
            val uvView = views.size
            views.add("{\"buffer\":0,\"byteOffset\":$uvOffset,\"byteLength\":${n * 8},\"target\":34962}")
            val imageView = views.size
            views.add("{\"buffer\":0,\"byteOffset\":$imageOffset,\"byteLength\":${texture.jpeg.size}}")
            val accessor = accessors.size
            accessors.add("{\"bufferView\":$uvView,\"componentType\":5126,\"count\":$n,\"type\":\"VEC2\"}")
            accessor to imageView
        } else null
        val normalView = views.size
        views.add("{\"buffer\":0,\"byteOffset\":$normalOffset,\"byteLength\":${n * 12},\"target\":34962}")
        val normalAccessor = accessors.size
        accessors.add("{\"bufferView\":$normalView,\"componentType\":5126,\"count\":$n,\"type\":\"VEC3\"}")
        val normalTargetAccessors = normalDeltaOffsets.map { offset ->
            val view = views.size
            views.add("{\"buffer\":0,\"byteOffset\":$offset,\"byteLength\":${n * 12},\"target\":34962}")
            val accessor = accessors.size
            accessors.add("{\"bufferView\":$view,\"componentType\":5126,\"count\":$n,\"type\":\"VEC3\"}")
            accessor
        }
        val targetJson = deltas.indices.joinToString(",") { "{\"POSITION\":${it + 2},\"NORMAL\":${normalTargetAccessors[it]}}" }
        val targetNames = deltas.indices.joinToString(",") { "\"frame_${it + 1}\"" }
        val zeros = deltas.indices.joinToString(",") { "0" }
        val texAttr = textureAccessor?.let { ",\"TEXCOORD_0\":${it.first}" } ?: ""
        val texData = textureAccessor?.let { ",\"images\":[{\"bufferView\":${it.second},\"mimeType\":\"image/jpeg\"}],\"textures\":[{\"source\":0,\"sampler\":0}],\"samplers\":[{\"wrapS\":33071,\"wrapT\":33071}]" } ?: ""
        val baseColor = if (texture != null) "[1,1,1,1]" else "[0.75,0.62,0.55,1]"
        val texMaterial = if (texture != null) ",\"baseColorTexture\":{\"index\":0}" else ""
        val json = """{
"asset":{"version":"2.0","generator":"FaceScan prototype","extras":{"scale":"uncalibrated; one unit is eye distance","limitations":"single-view face surface; optional single-view photograph, no hair, back of head or validated metric accuracy"}},
"scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0,"name":"Face"}],
"meshes":[{"name":"FaceSurface","weights":[$zeros],"extras":{"targetNames":[$targetNames]},"primitives":[{"attributes":{"POSITION":0,"NORMAL":$normalAccessor$texAttr},"indices":1,"material":0,"targets":[$targetJson]}]}],
"materials":[{"name":"Face","doubleSided":true,"pbrMetallicRoughness":{"baseColorFactor":$baseColor,"metallicFactor":0,"roughnessFactor":1$texMaterial}}],
"animations":[{"name":"RecordedExpression","samplers":[{"input":$timesAccessor,"output":$weightsAccessor,"interpolation":"LINEAR"}],"channels":[{"sampler":0,"target":{"node":0,"path":"weights"}}]}],
"buffers":[{"byteLength":${bytes.size}}],"bufferViews":[${views.joinToString(",")}],"accessors":[${accessors.joinToString(",")}]$texData}""".toByteArray(Charsets.UTF_8)
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

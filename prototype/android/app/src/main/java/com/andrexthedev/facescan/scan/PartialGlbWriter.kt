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

    /**
     * @param completeness optionaler Bericht aus [MultiViewCompleteness]; er
     *   wird nur als Text in `extras` abgelegt und ändert keine Geometrie.
     */
    fun write(
        mesh: PartialFaceMesh.Mesh,
        completeness: MultiViewCompleteness.Report? = null,
        redundancy: MultiViewRedundancy.Report? = null,
        pointLoss: MultiViewPointLoss.Report? = null,
        focalConsistency: MultiViewFocalConsistency.Report? = null,
        viewUse: MultiViewViewUse.Report? = null
    ): ByteArray {
        require(mesh.vertices.isNotEmpty() && mesh.vertices.all { it.size == 3 && it.all(Double::isFinite) })
        require(mesh.sourceIndices.size == mesh.vertices.size)
        require(mesh.triangles.isNotEmpty() && mesh.triangles.size % 3 == 0 &&
            mesh.triangles.all { it in mesh.vertices.indices })
        val count = mesh.vertices.size
        require(count <= MAX_VERTICES)
        val positions = FloatArray(count * 3) { i -> mesh.vertices[i / 3][i % 3].toFloat() }
        require(positions.all(Float::isFinite))
        // Ein Dreieck, das in Double noch Fläche hat, kann beim Runden auf
        // Float32 kollabieren. Im GLB steht Float32; deshalb wird hier gegen
        // die geschriebenen Werte gefiltert, nicht gegen die Double-Quelle.
        val indices = floatSafeTriangles(positions, mesh.triangles)
        require(indices.isNotEmpty())
        val dropped = mesh.triangles.size / 3 - indices.size / 3
        val normals = MeshNormals.calculate(positions, indices)

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
        // Struktur der tatsächlich geschriebenen Flächen, nicht der Double-Quelle.
        val topology = PartialMeshTopology.inspect(count, indices)
        // Vorberechnet, damit im JSON-Text keine Lambda-Klammern stehen.
        val agreeingViews = focalConsistency?.let { MultiViewFocalConsistency.agreeingViews(it) } ?: 0
        val focalConsistent = focalConsistency?.consistent?.toString() ?: "null"
        val viewUseReasons = AnchorPoseDropReason.entries.joinToString(",") { reason ->
            "\"" + reason.key + "\":" + (viewUse?.reason(reason) ?: 0)
        }
        val viewUseComplete = viewUse?.complete?.toString() ?: "null"

        val json = """{
"asset":{"version":"2.0","generator":"FaceScan prototype","extras":{"units":"centimetres derived from canonical average anchors; not a measurement of the subject","limitations":"open partial surface, no completion, no texture, no animation, no real-device accuracy validation","droppedDegenerateTriangles":$dropped,"topology":{"vertices":${topology.vertexCount},"triangles":${topology.triangleCount},"boundaryEdges":${topology.boundaryEdges},"nonManifoldEdges":${topology.nonManifoldEdges},"components":${topology.components},"largestComponentTriangles":${topology.largestComponentTriangles},"note":"structure only, not a quality or accuracy measure"},"zoneCoverage":"${zoneText(completeness)}","depthUncertaintyCm":{"median":${number(completeness?.medianDepthUncertaintyCm)},"high":${number(completeness?.highDepthUncertaintyCm)},"samples":${completeness?.uncertaintySamples ?: 0},"note":"first-order estimate from reprojection residual and parallax, not validated"},"viewSupport":{"medianUsedViews":${number(redundancy?.medianUsedViews)},"fractionThreePlus":${number(redundancy?.fractionWithThreeOrMore)},"twoViewOnly":${redundancy?.supportedByTwoViews ?: 0},"triangulated":${redundancy?.triangulatedPoints ?: 0},"note":"how many views support each point, not accuracy"},"pointLoss":{"triangulated":${pointLoss?.triangulated ?: 0},"missing":${pointLoss?.missing ?: 0},"tooFewViews":${pointLoss?.count(MultiViewPointLoss.TOO_FEW_VIEWS) ?: 0},"insufficientParallax":${pointLoss?.count(MultiViewPointLoss.INSUFFICIENT_PARALLAX) ?: 0},"behindCamera":${pointLoss?.count(MultiViewPointLoss.BEHIND_CAMERA) ?: 0},"unstableGeometry":${pointLoss?.count(MultiViewPointLoss.UNSTABLE) ?: 0},"noConsensus":${pointLoss?.count(MultiViewPointLoss.NO_CONSENSUS) ?: 0},"unknown":${pointLoss?.count(MultiViewPointLoss.UNKNOWN) ?: 0},"note":"rejection reasons of missing landmarks, one category each"},"viewUse":{"stored":${viewUse?.storedViews ?: 0},"used":${viewUse?.usedViews ?: 0},"notStored":${viewUse?.attemptsNotStored ?: 0},"dropped":${viewUse?.storedNotUsed ?: 0},"reasons":{$viewUseReasons},"complete":$viewUseComplete,"note":"which captured views contributed, not accuracy"}}},
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

    /**
     * Zonenabdeckung als kompakter Text, z. B. `forehead=2/2,eyes=7/7,...`.
     * Leer, wenn kein Bericht vorliegt; es werden keine Zahlen erfunden.
     */
    fun zoneText(report: MultiViewCompleteness.Report?): String =
        report?.zoneCoverages?.joinToString(",") { "${it.name}=${it.anchorsTriangulated}/${it.anchorsInZone}" } ?: ""

    private fun number(value: Double?): String =
        if (value == null || !value.isFinite()) "null"
        else "%.3f".format(java.util.Locale.ROOT, value)

    /**
     * Verwirft Dreiecke, deren Fläche in Float32 exakt null wird. Das ist kein
     * Qualitätsurteil über die Form, sondern verhindert ungültige Flächen in
     * der geschriebenen Datei.
     */
    fun floatSafeTriangles(positions: FloatArray, triangles: IntArray): IntArray {
        require(positions.isNotEmpty() && positions.size % 3 == 0)
        require(triangles.size % 3 == 0 && triangles.all { it in 0 until positions.size / 3 })
        val kept = ArrayList<Int>(triangles.size)
        for (t in triangles.indices step 3) {
            val a = triangles[t] * 3
            val b = triangles[t + 1] * 3
            val c = triangles[t + 2] * 3
            val abx = positions[b] - positions[a]
            val aby = positions[b + 1] - positions[a + 1]
            val abz = positions[b + 2] - positions[a + 2]
            val acx = positions[c] - positions[a]
            val acy = positions[c + 1] - positions[a + 1]
            val acz = positions[c + 2] - positions[a + 2]
            val x = aby * acz - abz * acy
            val y = abz * acx - abx * acz
            val z = abx * acy - aby * acx
            val area = Math.sqrt((x * x + y * y + z * z).toDouble())
            if (area > 0.0) { kept.add(triangles[t]); kept.add(triangles[t + 1]); kept.add(triangles[t + 2]) }
        }
        return kept.toIntArray()
    }
}

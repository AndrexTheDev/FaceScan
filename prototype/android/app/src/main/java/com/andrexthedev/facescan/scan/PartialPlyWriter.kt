package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.MultiViewTriangulation
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Binäres Stanford-PLY des offenen Mehransichten-Teilnetzes.
 *
 * Was die Datei enthält: exakt die Punkte und Dreiecke aus
 * [PartialFaceMesh], dazu je Vertex die Tiefenunsicherheit als Grauwert in
 * `red/green/blue`. Kein Foto, keine UV-Koordinaten, keine Animation, keine
 * Ergänzung fehlender Bereiche.
 *
 * Was sie NICHT belegt: Die Einheit stammt aus kanonischen Durchschnittsankern
 * und ist keine Vermessung der Person. Der Grauwert ist eine Schätzung erster
 * Ordnung aus Reprojektionsrest und Parallaxe; er ist keine validierte
 * Genauigkeit. Punkte ohne belastbare Schätzung werden als schwarz geschrieben
 * und im Kommentarkopf als `unknown` gezählt – es wird kein Wert erfunden.
 */
object PartialPlyWriter {
    /** Helligkeit 0 = keine Angabe, 255 = größte im Mesh geschätzte Unsicherheit. */
    const val UNKNOWN_SHADE = 0

    data class UncertaintyColors(
        val colors: ByteArray,
        /** Anzahl der Vertices mit einer echten Schätzung. */
        val known: Int,
        /** Anzahl der Vertices ohne Schätzung. */
        val unknown: Int,
        /** Maximum der geschätzten Unsicherheit in cm, auf das skaliert wurde. */
        val maxCm: Double?
    ) {
        val vertexCount: Int get() = colors.size / 3
    }

    /**
     * Skaliert die Unsicherheit je Vertex auf 25..255. Lineare Skala relativ zum
     * Maximum im Mesh, damit ein Viewer die Unterschiede überhaupt zeigt; das
     * ist eine Darstellungsentscheidung, keine Messung. Unbekannte Werte
     * bleiben schwarz (0) und sind damit von "sehr sicher" (25) unterscheidbar.
     */
    fun uncertaintyColors(
        mesh: PartialFaceMesh.Mesh,
        cloud: com.andrexthedev.facescan.geometry.MultiViewPointCloud.Result,
        referenceRotation: com.andrexthedev.facescan.geometry.Mat3,
        referenceTranslation: DoubleArray,
        focalPixels: Double
    ): UncertaintyColors {
        require(mesh.sourceIndices.size == mesh.vertices.size)
        require(cloud.points.size == CanonicalAnchors.LANDMARK_COUNT)
        require(referenceTranslation.size == 3 && referenceTranslation.all { it.isFinite() })
        val values = DoubleArray(mesh.vertices.size) { Double.NaN }
        var max = 0.0
        for (i in mesh.vertices.indices) {
            val point = cloud.points[mesh.sourceIndices[i]]
            if (point !is MultiViewTriangulation.Result.Point) continue
            val depth = MultiViewCompleteness.depthInReference(point.xyz, referenceRotation, referenceTranslation)
            val value = MultiViewCompleteness.depthUncertaintyCm(
                depth, point.rmsPixels, point.maxParallaxDegrees, focalPixels) ?: continue
            values[i] = value
            if (value > max) max = value
        }
        val colors = ByteArray(mesh.vertices.size * 3)
        var known = 0
        for (i in values.indices) {
            val value = values[i]
            if (value.isNaN() || !value.isFinite() || value < 0.0) continue
            known++
            // 25..255: 0 bleibt für "keine Schätzung" reserviert.
            val fraction = if (max > 0.0) (value / max).coerceIn(0.0, 1.0) else 0.0
            val shade = (25.0 + fraction * 230.0).toInt().coerceIn(25, 255).toByte()
            colors[3 * i] = shade; colors[3 * i + 1] = shade; colors[3 * i + 2] = shade
        }
        return UncertaintyColors(colors, known, mesh.vertices.size - known,
            if (known > 0 && max > 0.0) max else null)
    }

    /** Binäres PLY mit Positionen, Flächen und optional Vertexfarben. */
    fun write(mesh: PartialFaceMesh.Mesh, colors: UncertaintyColors? = null): ByteArray {
        require(mesh.vertices.isNotEmpty() && mesh.vertices.all { it.size == 3 && it.all(Double::isFinite) })
        require(mesh.sourceIndices.size == mesh.vertices.size)
        require(mesh.triangles.isNotEmpty() && mesh.triangles.size % 3 == 0)
        require(mesh.triangles.all { it in mesh.vertices.indices })
        // PLY speichert Float32; Dreiecke, die dabei flächenlos würden, würden
        // eine ungültige Datei erzeugen. Deshalb dieselbe Filterung wie im GLB.
        val positions = FloatArray(mesh.vertices.size * 3) { i -> mesh.vertices[i / 3][i % 3].toFloat() }
        require(positions.all(Float::isFinite))
        val indices = PartialGlbWriter.floatSafeTriangles(positions, mesh.triangles)
        require(indices.isNotEmpty())
        val dropped = mesh.triangles.size / 3 - indices.size / 3
        val topology = PartialMeshTopology.inspect(mesh.vertices.size, indices)
        val shaded = colors != null && colors.vertexCount == mesh.vertices.size
        val body = ByteArrayOutputStream()
        fun floats(values: FloatArray) {
            val buffer = ByteBuffer.allocate(values.size * 4).order(ByteOrder.LITTLE_ENDIAN)
            values.forEach { buffer.putFloat(it) }
            body.write(buffer.array())
        }
        floats(positions)
        if (shaded) body.write(colors!!.colors)
        // Binäres PLY schreibt Flächen als list: 1 Byte Anzahl + n Indizes.
        val faceHeader = "property list uchar int vertex_indices"
        for (t in indices.indices step 3) {
            require(indices[t] in 0..255 && indices[t + 1] in 0..255 && indices[t + 2] in 0..255)
            body.write(3)
            val buffer = ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN)
            for (j in 0..2) buffer.putInt(indices[t + j])
            body.write(buffer.array())
        }
        val header = buildString {
            append("ply\nformat binary_little_endian 1.0\n")
            append("comment FaceScan partial multiview surface\n")
            append("comment Scale and units derive from canonical average anchors; not validated.\n")
            append("comment Missing points and faces are omitted; no completion, photo, texture or animation.\n")
            append("comment topology: ${PartialMeshTopology.describe(topology)} (structure only, not quality)\n")
            append("comment droppedDegenerateTriangles $dropped\n")
            if (shaded) {
                append("comment vertex colours encode the first-order depth uncertainty, ")
                append("scaled to 25..255; 0 means no estimate. Not a validated accuracy.\n")
                append("comment uncertaintyKnown ${colors!!.known} uncertaintyUnknown ${colors.unknown}\n")
            } else {
                append("comment no colour channel: no uncertainty estimate available\n")
            }
            append("element vertex ${mesh.vertices.size}\n")
            append("property float x\nproperty float y\nproperty float z\n")
            if (shaded) append("property uchar red\nproperty uchar green\nproperty uchar blue\n")
            append("element face ${indices.size / 3}\n")
            append("$faceHeader\n")
            append("end_header\n")
        }
        return header.toByteArray(Charsets.US_ASCII) + body.toByteArray()
    }

    /** Nur zum Prüfen: Punktkoordinaten als Float32, wie sie in der Datei stehen. */
    fun positions(mesh: PartialFaceMesh.Mesh): FloatArray =
        FloatArray(mesh.vertices.size * 3) { i -> mesh.vertices[i / 3][i % 3].toFloat() }
}

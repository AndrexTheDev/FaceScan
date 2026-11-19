package com.andrexthedev.facescan.scan

/**
 * Exportformate für das rekonstruierte Teilnetz. Beide enthalten ausschließlich
 * triangulierte Punkte und Flächen; OBJ zusätzlich eine Kommentarzeile mit den
 * Fit-Zahlen, GLB stattdessen einen festen JSON-Block.
 */
enum class MeshExportFormat(val mimeType: String, val fileName: String) {
    OBJ("model/obj", "facescan-multiview.obj"),
    GLB("model/gltf-binary", "facescan-multiview.glb"),
    /** Binäres PLY mit Unsicherheit als Vertexfarbe; setzt eine Referenzpose voraus. */
    PLY("application/octet-stream", "facescan-multiview.ply")
}

/**
 * Erzeugt die Exportdaten ohne UI und ohne Datei-IO. Null, wenn kein Mesh
 * vorliegt — ein leerer Export ist kein gültiges Ergebnis.
 */
fun MultiViewCapture.Result.encodeExport(format: MeshExportFormat): ByteArray? {
    val mesh = surface.mesh ?: return null
    return when (format) {
        MeshExportFormat.OBJ -> MultiViewCapture.writeObjWithHeader(this)
        MeshExportFormat.GLB -> PartialGlbWriter.write(
            mesh, completeness = completeness, redundancy = redundancy, pointLoss = pointLoss,
            focalConsistency = focalConsistency, viewUse = viewUse)
        MeshExportFormat.PLY -> {
            val rotation = referenceRotation
            val translation = referenceTranslation
            val colors = if (rotation != null && translation != null)
                PartialPlyWriter.uncertaintyColors(mesh, cloud, rotation, translation, intrinsics.fx) else null
            PartialPlyWriter.write(mesh, colors)
        }
    }
}

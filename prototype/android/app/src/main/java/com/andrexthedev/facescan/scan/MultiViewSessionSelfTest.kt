package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.CameraModel
import com.andrexthedev.facescan.geometry.Mat3

/**
 * Synthetischer Geräteselbsttest: echte Klassen, künstliche Kamera und
 * künstliche 468 Punkte. Die 30 Anker liegen auf dem kanonischen
 * Durchschnittsgesicht, alle übrigen Punkte sind frei erfundene, glatte
 * Zusatzpunkte. Das belegt Rechenwege, NICHT die Genauigkeit an einer Person.
 */
object MultiViewSessionSelfTest {
    private const val WIDTH = 640
    private const val HEIGHT = 480
    const val FOCAL_PIXELS = 760.0
    const val VIEW_WIDTH = WIDTH
    const val VIEW_HEIGHT = HEIGHT

    /** Künstliche 3D-Punkte (cm) aller 468 Slots; nur die Anker sind kanonisch. */
    fun syntheticWorldPoints(): Array<DoubleArray> {
        val points = Array(CanonicalAnchors.LANDMARK_COUNT) { i ->
            // Glatte, deterministische Verteilung im Kopfbereich.
            val u = (i % 26) / 25.0
            val v = (i / 26) / 17.0
            doubleArrayOf(-7.0 + 14.0 * u, 8.0 - 17.0 * v, 1.0 + 6.0 * u * v)
        }
        for (a in 0 until CanonicalAnchorData.COUNT) {
            points[CanonicalAnchorData.indices[a]] = doubleArrayOf(
                CanonicalAnchorData.points[3 * a],
                CanonicalAnchorData.points[3 * a + 1],
                CanonicalAnchorData.points[3 * a + 2])
        }
        return points
    }

    /** Normalisierte Landmarks (x/y) aus einer bekannten Kopfhaltung. */
    fun syntheticLandmarks(yawDegrees: Double, translation: DoubleArray = doubleArrayOf(0.0, 0.0, 60.0)): FloatArray {
        val camera = CameraModel(FOCAL_PIXELS, FOCAL_PIXELS, WIDTH / 2.0, HEIGHT / 2.0)
        val rotation = Mat3.fromRodrigues(doubleArrayOf(0.0, Math.toRadians(yawDegrees), 0.0))
        val out = FloatArray(CanonicalAnchors.LANDMARK_COUNT * 3)
        for ((index, p) in syntheticWorldPoints().withIndex()) {
            val q = DoubleArray(2)
            camera.project(rotation, translation, p, q)
            out[3 * index] = (q[0] / WIDTH).toFloat()
            out[3 * index + 1] = (q[1] / HEIGHT).toFloat()
            out[3 * index + 2] = 0f
        }
        return out
    }

    fun run(): Boolean {
        val intrinsics = MultiViewCapture.Intrinsics(FOCAL_PIXELS, FOCAL_PIXELS, WIDTH / 2.0, HEIGHT / 2.0)
        val session = MultiViewSession(intrinsics)
        val frontal = syntheticLandmarks(0.0)
        val left = syntheticLandmarks(-20.0)
        val right = syntheticLandmarks(20.0)
        if (session.add(frontal, WIDTH, HEIGHT) != MultiViewSession.AddResult.ACCEPTED) return false
        if (session.add(frontal, WIDTH, HEIGHT) != MultiViewSession.AddResult.INSUFFICIENT_YAW_DIFFERENCE) return false
        if (session.add(left, WIDTH, HEIGHT) != MultiViewSession.AddResult.ACCEPTED) return false
        if (session.add(right, WIDTH, HEIGHT) != MultiViewSession.AddResult.ACCEPTED) return false
        if (session.size() != 3 || session.yawSpreadDegrees() < 20.0) return false
        // Die Anker werden exakt reprojiziert; ein akzeptierter Fit ist daher
        // nur ein Nachweis des Rechenwegs.
        val evaluated = session.evaluate(frontal, WIDTH, HEIGHT) ?: return false
        if (!evaluated.rmsPixels.isFinite() || evaluated.rmsPixels > 2.0) return false
        val reconstructed = session.reconstruct() as? MultiViewCapture.Outcome.Reconstructed ?: return false
        if (reconstructed.result.acceptedViews.size != 3) return false
        val dense = MultiViewSurface.densePoints(reconstructed.result.cloud)
        if (MultiViewSurface.coverage(dense) < 0.9) return false
        val mesh = reconstructed.result.surface.mesh ?: return false
        if (mesh.triangles.isEmpty() || mesh.vertices.isEmpty()) return false
        // Alle künstlichen Punkte müssen bis auf Rechenrauschen zurückkommen.
        val truth = syntheticWorldPoints()
        for (i in mesh.vertices.indices) {
            val expected = truth[mesh.sourceIndices[i]]
            for (axis in 0..2) {
                if (kotlin.math.abs(mesh.vertices[i][axis] - expected[axis]) > 0.05) return false
            }
        }
        val text = String(MultiViewCapture.writeObjWithHeader(reconstructed.result) ?: return false, Charsets.UTF_8)
        if (!text.contains("f ") || !text.contains("not validated") || !text.contains("views=3")) return false
        // Normalen müssen vorhanden und endlich sein; sie sind kein Messwert.
        if (text.lineSequence().none { it.startsWith("vn ") }) return false
        if (text.lineSequence().filter { it.startsWith("vn ") }.any { line ->
                line.removePrefix("vn ").split(' ').any { it.toFloatOrNull()?.isFinite() != true } }) return false
        // Live-Orientierung: frontal ohne Ansichten ist die Haltung zulässig.
        val guidance = MultiViewSession(intrinsics).guidance(frontal, WIDTH, HEIGHT)
        if (guidance.yawDegrees == null || !guidance.sufficient) return false
        // Falsche Bildgröße darf keine Sitzung mischen.
        session.clear()
        if (session.add(syntheticLandmarks(0.0), WIDTH, HEIGHT) != MultiViewSession.AddResult.ACCEPTED) return false
        if (session.add(syntheticLandmarks(25.0), WIDTH / 2, HEIGHT / 2) !=
            MultiViewSession.AddResult.INCONSISTENT_DIMENSIONS) return false
        if (session.reconstruct() !is MultiViewCapture.Outcome.Rejected) return false
        return true
    }
}

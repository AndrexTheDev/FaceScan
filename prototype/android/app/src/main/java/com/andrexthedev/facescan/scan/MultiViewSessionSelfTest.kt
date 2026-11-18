package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.CameraModel
import com.andrexthedev.facescan.geometry.Mat3

/**
 * Synthetischer Geräteselbsttest: echte Klassen, künstliche Kamera und
 * künstlich erzeugte Landmarks des kanonischen Gesichts. Das belegt Rechenwege,
 * NICHT die Genauigkeit an einer Person.
 */
object MultiViewSessionSelfTest {
    private const val WIDTH = 640
    private const val HEIGHT = 480
    const val FOCAL_PIXELS = 760.0

    /** Normalisierte Landmarks des kanonischen Gesichts aus einer bekannten Pose. */
    fun syntheticLandmarks(yawDegrees: Double, translation: DoubleArray = doubleArrayOf(0.0, 0.0, 60.0)): FloatArray {
        val camera = CameraModel(FOCAL_PIXELS, FOCAL_PIXELS, WIDTH / 2.0, HEIGHT / 2.0)
        val rotation = Mat3.fromRodrigues(doubleArrayOf(0.0, Math.toRadians(yawDegrees), 0.0))
        val out = FloatArray(CanonicalAnchors.LANDMARK_COUNT * 3)
        for (index in 0 until CanonicalAnchors.LANDMARK_COUNT) {
            // Nur die kanonischen Anker sind bekannt; alle anderen Slots bleiben
            // im Test in der Bildmitte (werden nie als Anker verwendet).
            out[3 * index] = 0.5f
            out[3 * index + 1] = 0.5f
            out[3 * index + 2] = 0f
        }
        for (a in 0 until CanonicalAnchorData.COUNT) {
            val p = doubleArrayOf(
                CanonicalAnchorData.points[3 * a],
                CanonicalAnchorData.points[3 * a + 1],
                CanonicalAnchorData.points[3 * a + 2]
            )
            val q = DoubleArray(2)
            camera.project(rotation, translation, p, q)
            val index = CanonicalAnchorData.indices[a]
            out[3 * index] = (q[0] / WIDTH).toFloat()
            out[3 * index + 1] = (q[1] / HEIGHT).toFloat()
        }
        return out
    }

    fun run(): Boolean {
        val intrinsics = MultiViewCapture.Intrinsics(FOCAL_PIXELS, FOCAL_PIXELS, WIDTH / 2.0, HEIGHT / 2.0)
        val session = MultiViewSession(intrinsics)
        // Frontal plus je eine seitliche Ansicht; die Pose stammt aus den Ankern.
        val frontal = syntheticLandmarks(0.0)
        val left = syntheticLandmarks(-20.0)
        val right = syntheticLandmarks(20.0)
        if (session.add(frontal, WIDTH, HEIGHT) != MultiViewSession.AddResult.ACCEPTED) return false
        if (session.add(frontal, WIDTH, HEIGHT) != MultiViewSession.AddResult.INSUFFICIENT_YAW_DIFFERENCE) return false
        if (session.add(left, WIDTH, HEIGHT) != MultiViewSession.AddResult.ACCEPTED) return false
        if (session.add(right, WIDTH, HEIGHT) != MultiViewSession.AddResult.ACCEPTED) return false
        if (session.size() != 3 || session.yawSpreadDegrees() < 20.0) return false
        // Die Anker selbst werden exakt reprojiziert; ein akzeptierter Fit ist
        // daher nur ein Rechenschaftsnachweis.
        val evaluated = session.evaluate(frontal, WIDTH, HEIGHT) ?: return false
        if (!evaluated.rmsPixels.isFinite() || evaluated.rmsPixels > 1.0) return false
        val reconstructed = session.reconstruct() as? MultiViewCapture.Outcome.Reconstructed ?: return false
        if (reconstructed.result.acceptedViews.size != 3) return false
        val dense = MultiViewSurface.densePoints(reconstructed.result.cloud)
        if (MultiViewSurface.coverage(dense) <= 0.0) return false
        val obj = MultiViewCapture.writeObj(reconstructed.result) ?: return false
        val text = String(obj, Charsets.UTF_8)
        if (!text.contains("f ") || !text.contains("not validated")) return false
        // Falsche Bildgröße darf keine neue Sitzung mischen.
        session.clear()
        if (session.add(syntheticLandmarks(0.0), WIDTH, HEIGHT) != MultiViewSession.AddResult.ACCEPTED) return false
        if (session.add(syntheticLandmarks(25.0), WIDTH / 2, HEIGHT / 2) !=
            MultiViewSession.AddResult.INCONSISTENT_DIMENSIONS) return false
        return true
    }
}

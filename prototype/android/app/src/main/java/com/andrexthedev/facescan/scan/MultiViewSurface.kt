package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.MultiViewTriangulation

/**
 * Verbindet die experimentelle Mehransichten-Punktwolke mit der bestehenden
 * Vorschau und dem OBJ-Export. Es entsteht KEINE Animation und keine
 * Fototextur: Weder Ausdrucksformen noch UV-Zuordnung sind für ein
 * trianguliertes Teilnetz verfügbar.
 *
 * Alle 468 Slots müssen belegt sein: fehlende oder abgelehnte Punkte werden
 * mit NaN markiert. Die bestehenden Render-/Exportpfade prüfen auf endliche
 * Werte und lehnen solche Daten ab, statt Ersatzpunkte zu erfinden.
 */
object MultiViewSurface {
    /** NaN-markierte Punkte in MediaPipe-Reihenfolge; Einheit = Zentimeter der Anker. */
    fun densePoints(cloud: com.andrexthedev.facescan.geometry.MultiViewPointCloud.Result): FloatArray {
        require(cloud.points.size == CanonicalAnchors.LANDMARK_COUNT)
        val out = FloatArray(CanonicalAnchors.LANDMARK_COUNT * 3) { Float.NaN }
        for (i in cloud.points.indices) {
            val point = cloud.points[i]
            if (point is MultiViewTriangulation.Result.Point) {
                out[3 * i] = point.xyz[0].toFloat()
                out[3 * i + 1] = point.xyz[1].toFloat()
                out[3 * i + 2] = point.xyz[2].toFloat()
            }
        }
        return out
    }

    /** Diagnose: Anteil belegter Slots (keine Genauigkeitsaussage). */
    fun coverage(points: FloatArray): Double {
        require(points.size == CanonicalAnchors.LANDMARK_COUNT * 3)
        val filled = (0 until CanonicalAnchors.LANDMARK_COUNT).count { i ->
            points[3 * i].isFinite() && points[3 * i + 1].isFinite() && points[3 * i + 2].isFinite()
        }
        return filled.toDouble() / CanonicalAnchors.LANDMARK_COUNT
    }
}

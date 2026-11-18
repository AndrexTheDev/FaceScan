package com.andrexthedev.facescan.geometry

/**
 * Reine Abbildung normalisierter MediaPipe-Landmarks auf Pixel einer
 * aufrechten, ungespiegelten Bitmap. x/y werden mit Breite/Höhe skaliert.
 *
 * z bleibt bewusst ungenutzt: Die MediaPipe-Tiefe ist modellgeschätzt, relativ
 * und ohne metrische Kalibrierung. Aus diesem Modul entsteht KEINE 3D-Aussage.
 */
object LandmarkProjection {
    data class Pixel(val u: Double, val v: Double)

    /** null bei ungültigen Werten oder Landmark außerhalb des Bildes. */
    fun pixel(points: FloatArray, index: Int, width: Int, height: Int, marginPixels: Double = 0.0): Pixel? {
        if (index < 0 || points.size < (index + 1) * 3 || width <= 0 || height <= 0) return null
        if (!marginPixels.isFinite() || marginPixels < 0.0) return null
        val x = points[3 * index]
        val y = points[3 * index + 1]
        if (!x.isFinite() || !y.isFinite()) return null
        // Kontinuierliche Pixelkoordinaten (Pixelzentrum n+0.5): dieselbe
        // Konvention wie das Kameramodell (cx = Breite/2).
        val u = x.toDouble() * width - 0.5
        val v = y.toDouble() * height - 0.5
        if (u !in marginPixels..(width - marginPixels) || v !in marginPixels..(height - marginPixels)) return null
        return Pixel(u, v)
    }

    /** Alle Pixel eines Indexsatzes; null, sobald ein Punkt unbrauchbar ist. */
    fun pixels(points: FloatArray, indices: IntArray, width: Int, height: Int,
               marginPixels: Double = 0.0, scale: Double = 1.0): Pair<DoubleArray, DoubleArray>? {
        if (!scale.isFinite() || scale <= 0.0) return null
        if (indices.isEmpty()) return null
        val u = DoubleArray(indices.size)
        val v = DoubleArray(indices.size)
        for (i in indices.indices) {
            val p = pixel(points, indices[i], width, height, marginPixels) ?: return null
            u[i] = p.u
            v[i] = p.v
        }
        return u to v
    }
}

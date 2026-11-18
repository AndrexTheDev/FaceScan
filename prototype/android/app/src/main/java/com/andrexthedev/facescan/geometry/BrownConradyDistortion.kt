package com.andrexthedev.facescan.geometry

import kotlin.math.abs

/**
 * Explizites Brown-Conrady-Modell für normalisierte Kamerakoordinaten.
 * Koeffizienten müssen zur konkreten Kamera, Brennweite, Korrektur und
 * Bildkoordinate passen. Dies liest oder interpretiert keine Camera2-Metadaten.
 */
data class BrownConradyDistortion(
    val k1: Double, val k2: Double, val k3: Double, val p1: Double, val p2: Double
) {
    data class Point(val x: Double, val y: Double)
    init { require(listOf(k1, k2, k3, p1, p2).all { it.isFinite() }) }

    /** Ungestörter normierter Strahl -> verzerrter normierter Bildpunkt. */
    fun distort(point: Point): Point? {
        if (!point.x.isFinite() || !point.y.isFinite()) return null
        val x = point.x; val y = point.y; val r2 = x*x + y*y
        if (!r2.isFinite() || r2 > 9.0) return null
        val radial = 1.0 + r2 * (k1 + r2 * (k2 + r2*k3))
        val dx = x * radial + 2.0*p1*x*y + p2*(r2 + 2*x*x)
        val dy = y * radial + p1*(r2 + 2*y*y) + 2.0*p2*x*y
        return if (dx.isFinite() && dy.isFinite()) Point(dx, dy) else null
    }

    /** Newton-Inversion mit Konvergenzprüfung; null statt geratener Ersatzwerte. */
    fun undistort(point: Point): Point? {
        if (!point.x.isFinite() || !point.y.isFinite()) return null
        var x = point.x; var y = point.y
        for (iteration in 0 until 30) {
            val r2 = x*x + y*y
            if (!r2.isFinite() || r2 > 9.0) return null
            val predicted = distort(Point(x, y)) ?: return null
            val ex = predicted.x - point.x; val ey = predicted.y - point.y
            val g = k1 + 2*k2*r2 + 3*k3*r2*r2
            val radial = 1 + r2*(k1 + r2*(k2 + r2*k3))
            val a = radial + 2*x*x*g + 2*p1*y + 6*p2*x
            val b = 2*x*y*g + 2*p1*x + 2*p2*y
            val c = b
            val d = radial + 2*y*y*g + 6*p1*y + 2*p2*x
            val det = a*d - b*c
            // Negative/singuläre Jacobi-Matrix: keine stabile lokale Inversion.
            if (!det.isFinite() || det <= 1e-12) return null
            if (maxOf(abs(ex), abs(ey)) <= 1e-10) return Point(x, y)
            val dx = (d*ex - b*ey) / det
            val dy = (-c*ex + a*ey) / det
            if (!dx.isFinite() || !dy.isFinite() || maxOf(abs(dx), abs(dy)) > 1.0) return null
            x -= dx; y -= dy
        }
        return null
    }
}

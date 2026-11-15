package com.andrexthedev.facescan.geometry

/**
 * Kameramodell (Pinhole + Brennweite/Hauptpunkt in Pixel).
 *
 * Verzeichnung wird vor der Auswertung entfernt (Camera2 liefert die
 * Koeffizienten, wir entzerren die Bilder einmalig beim Einlesen) – dadurch
 * bleibt der gesamte Kern frei von Verzeichnungstermen.
 *
 * Einheiten: Pixel. Die metrische Skala kommt aus dem Modell (mm) plus der
 * Brennweite in Pixel – genau das macht ARCore ueberfluessig.
 */
data class CameraModel(
    val fx: Double,
    val fy: Double,
    val cx: Double,
    val cy: Double
) {
    /** Projiziert einen 3D-Punkt (3 Doubles, Weltkoordinaten) in Pixel. */
    fun project(rotation: Mat3, translation: DoubleArray, x: DoubleArray, out: DoubleArray) {
        val xc = rotation.times(x)
        val xc0 = xc[0] + translation[0]
        val xc1 = xc[1] + translation[1]
        val xc2 = xc[2] + translation[2]
        val z = if (kotlin.math.abs(xc2) < 1e-9) 1e-9 else xc2
        out[0] = fx * xc0 / z + cx
        out[1] = fy * xc1 / z + cy
    }

    /** Projiziert N Punkte (3N -> 2N). */
    fun projectAll(
        rotation: Mat3,
        translation: DoubleArray,
        points: DoubleArray,
        out: DoubleArray
    ) {
        val n = points.size / 3
        for (i in 0 until n) {
            val xc = rotation.times(doubleArrayOf(points[3 * i], points[3 * i + 1], points[3 * i + 2]))
            val z = (xc[2] + translation[2]).let { if (kotlin.math.abs(it) < 1e-9) 1e-9 else it }
            out[2 * i] = fx * (xc[0] + translation[0]) / z + cx
            out[2 * i + 1] = fy * (xc[1] + translation[1]) / z + cy
        }
    }

    /** Mittlere Tiefe einer Punktewolke in Kamerakoordinaten (fuer die Orthographie-Naeherung). */
    fun meanDepth(rotation: Mat3, translation: DoubleArray, points: DoubleArray): Double {
        val n = points.size / 3
        var sum = 0.0
        for (i in 0 until n) {
            val xc = rotation.times(doubleArrayOf(points[3 * i], points[3 * i + 1], points[3 * i + 2]))
            sum += xc[2] + translation[2]
        }
        return if (n == 0) 0.0 else sum / n
    }

    companion object {
        /** Intrinsics aus CameraCharacteristics.LENS_INTRINSIC_CALIBRATION. */
        fun fromAndroidIntrinsics(
            focalLength: FloatArray,
            principalPoint: FloatArray,
            imageWidth: Int,
            imageHeight: Int
        ): CameraModel = CameraModel(
            fx = focalLength[0].toDouble(),
            fy = focalLength[1].toDouble(),
            cx = principalPoint.getOrNull(0)?.toDouble() ?: (imageWidth * 0.5),
            cy = principalPoint.getOrNull(1)?.toDouble() ?: (imageHeight * 0.5)
        )
    }
}

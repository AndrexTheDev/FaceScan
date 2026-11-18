package com.andrexthedev.facescan.geometry

/**
 * Explizite Abbildung eines bekannten Sensor-Ausschnitts auf ein skaliertes,
 * ungespiegeltes und in 90-Grad-Schritten gedrehtes Frame. Dies liest oder
 * schätzt keinen CameraX-Crop. Verzerrung muss vorher korrigiert sein oder
 * ausdrücklich mit zum Frame passenden Koeffizienten angegeben werden.
 *
 * Koordinaten sind kontinuierliche Bildkanten-Koordinaten: links/oben = 0,
 * rechts/unten = Breite/Höhe. Pixelzentren liegen bei n+0.5. Intrinsics und
 * Bildpunkte müssen in genau dieser gemeinsamen Konvention übergeben werden.
 */
data class CalibratedPixelMapping(
    val sensorLeft: Double, val sensorTop: Double, val sensorRight: Double, val sensorBottom: Double,
    val bufferWidth: Int, val bufferHeight: Int, val clockwiseRotation: Int,
    val fx: Double, val fy: Double, val cx: Double, val cy: Double, val skew: Double
) {
    data class Pixel(val x: Double, val y: Double)

    init {
        require(listOf(sensorLeft, sensorTop, sensorRight, sensorBottom, fx, fy, cx, cy, skew).all { it.isFinite() })
        require(sensorRight > sensorLeft && sensorBottom > sensorTop && bufferWidth > 0 && bufferHeight > 0)
        require(clockwiseRotation in listOf(0, 90, 180, 270) && fx > 0 && fy > 0)
        require((sensorRight - sensorLeft).isFinite() && (sensorBottom - sensorTop).isFinite())
    }

    val uprightWidth: Int get() = if (clockwiseRotation == 90 || clockwiseRotation == 270) bufferHeight else bufferWidth
    val uprightHeight: Int get() = if (clockwiseRotation == 90 || clockwiseRotation == 270) bufferWidth else bufferHeight

    fun sensorToUpright(p: Pixel): Pixel {
        require(p.x.isFinite() && p.y.isFinite())
        val x = (p.x - sensorLeft) * bufferWidth / (sensorRight - sensorLeft)
        val y = (p.y - sensorTop) * bufferHeight / (sensorBottom - sensorTop)
        val result = when (clockwiseRotation) {
            0 -> Pixel(x, y)
            90 -> Pixel(bufferHeight - y, x)
            180 -> Pixel(bufferWidth - x, bufferHeight - y)
            else -> Pixel(y, bufferWidth - x)
        }
        require(result.x.isFinite() && result.y.isFinite())
        return result
    }

    fun uprightToSensor(p: Pixel): Pixel {
        require(p.x.isFinite() && p.y.isFinite())
        val (x, y) = when (clockwiseRotation) {
            0 -> p
            90 -> Pixel(p.y, bufferHeight - p.x)
            180 -> Pixel(bufferWidth - p.x, bufferHeight - p.y)
            else -> Pixel(bufferWidth - p.y, p.x)
        }
        val result = Pixel(sensorLeft + x * (sensorRight - sensorLeft) / bufferWidth,
            sensorTop + y * (sensorBottom - sensorTop) / bufferHeight)
        require(result.x.isFinite() && result.y.isFinite())
        return result
    }

    /**
     * Ohne [distortion] werden bereits entzerrte Pixel erwartet. Mit explizit
     * übergebenem Modell muss der beobachtete Pixel noch verzerrt sein.
     * Keine automatische Umrechnung aus Camera2-Koeffizienten.
     */
    fun toObservation(pixel: Pixel, worldToCamera: Mat3, translation: DoubleArray,
                      distortion: BrownConradyDistortion? = null): MultiViewTriangulation.Observation {
        val sensor = uprightToSensor(pixel)
        require(sensor.x in sensorLeft..sensorRight && sensor.y in sensorTop..sensorBottom)
        val y = (sensor.y - cy) / fy
        val x = (sensor.x - cx - skew * y) / fx
        require(x.isFinite() && y.isFinite())
        val corrected = if (distortion != null) {
            requireNotNull(distortion.undistort(BrownConradyDistortion.Point(x, y))) { "Verzeichnung nicht invertierbar" }
        } else BrownConradyDistortion.Point(x, y)
        val u = fx * corrected.x + cx; val v = fy * corrected.y + cy
        require(u.isFinite() && v.isFinite())
        return MultiViewTriangulation.Observation(CameraModel(fx, fy, cx, cy), worldToCamera, translation, u, v)
    }
}

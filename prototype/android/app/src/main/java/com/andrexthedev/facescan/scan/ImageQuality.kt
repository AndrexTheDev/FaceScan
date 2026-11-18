package com.andrexthedev.facescan.scan

import kotlin.math.sqrt

/** Heuristische Bildhinweise, ausdrücklich keine Scan- oder Genauigkeitsbewertung. */
object ImageQuality {
    enum class Hint { TOO_DARK, TOO_BRIGHT, POSSIBLY_BLURRY, NO_WARNING }
    data class Result(val meanLuma: Double, val darkFraction: Double, val brightFraction: Double,
                      val laplacianStdDev: Double, val hint: Hint)

    /** Grauwert-Fenster, 0..255; ellipse mindert Hintergrund am Rand. */
    fun analyze(gray: ByteArray, width: Int, height: Int, stride: Int): Result {
        require(width in 8..256 && height in 8..256 && stride >= width)
        require((height - 1).toLong() * stride + width <= gray.size.toLong())
        fun inside(x: Int, y: Int): Boolean {
            val dx = (x + 0.5 - width / 2.0) / (width * 0.42)
            val dy = (y + 0.5 - height / 2.0) / (height * 0.42)
            return dx*dx + dy*dy <= 1.0
        }
        fun pixel(x: Int, y: Int) = gray[y * stride + x].toInt() and 0xff
        var count = 0; var dark = 0; var bright = 0; var sum = 0.0
        var lapCount = 0; var lapSum = 0.0; var lapSq = 0.0
        for (y in 1 until height-1) for (x in 1 until width-1) {
            if (!inside(x, y)) continue
            val p = pixel(x, y)
            count++; sum += p
            if (p <= 10) dark++
            if (p >= 245) bright++
            // Nur innere Nachbarn verwenden, damit der ROI-Rand nicht als Schärfe zählt.
            if (inside(x-1,y) && inside(x+1,y) && inside(x,y-1) && inside(x,y+1)) {
                val lap = 4*p - pixel(x-1,y) - pixel(x+1,y) - pixel(x,y-1) - pixel(x,y+1)
                lapCount++; lapSum += lap; lapSq += lap.toDouble() * lap
            }
        }
        require(count > 0 && lapCount > 0)
        val mean = sum / count
        val darkFraction = dark.toDouble() / count
        val brightFraction = bright.toDouble() / count
        val lapMean = lapSum / lapCount
        val contrast = sqrt((lapSq / lapCount - lapMean * lapMean).coerceAtLeast(0.0))
        // Startwerte nur als Hinweise, nicht als harte Freigabe; nicht kalibriert.
        val hint = when {
            mean < 45.0 || darkFraction > 0.40 -> Hint.TOO_DARK
            mean > 235.0 || brightFraction > 0.35 -> Hint.TOO_BRIGHT
            contrast < 5.0 -> Hint.POSSIBLY_BLURRY
            else -> Hint.NO_WARNING
        }
        return Result(mean, darkFraction, brightFraction, contrast, hint)
    }
}

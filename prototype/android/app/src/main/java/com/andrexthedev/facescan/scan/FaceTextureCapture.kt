package com.andrexthedev.facescan.scan

import android.graphics.Bitmap
import java.io.ByteArrayOutputStream
import kotlin.math.ceil
import kotlin.math.floor

/** Wird nur auf ausdrückliche Anforderung auf dem Analyzer-Thread aufgerufen. */
object FaceTextureCapture {
    const val MAX_EDGE = 768
    const val MAX_JPEG_BYTES = 1024 * 1024

    fun capture(bitmap: Bitmap, points: FloatArray): FaceTexture {
        val w = bitmap.width; val h = bitmap.height
        require(NeutralCaptureQuality.inFrame(points, w, h))
        var minX = 1f; var minY = 1f; var maxX = 0f; var maxY = 0f
        for (i in 0 until FaceTopology.VERTEX_COUNT) {
            minX = minOf(minX, points[3 * i]); maxX = maxOf(maxX, points[3 * i])
            minY = minOf(minY, points[3 * i + 1]); maxY = maxOf(maxY, points[3 * i + 1])
        }
        // Kleiner Rand für Randtexel; der Bildausschnitt kann auch Hintergrund enthalten.
        val marginX = (maxX - minX) * 0.04f; val marginY = (maxY - minY) * 0.04f
        val left = floor((minX - marginX) * w).toInt().coerceIn(0, w - 1)
        val top = floor((minY - marginY) * h).toInt().coerceIn(0, h - 1)
        val right = ceil((maxX + marginX) * w).toInt().coerceIn(left + 1, w)
        val bottom = ceil((maxY + marginY) * h).toInt().coerceIn(top + 1, h)
        val cw = right - left; val ch = bottom - top
        val uv = FloatArray(FaceTopology.VERTEX_COUNT * 2)
        for (i in 0 until FaceTopology.VERTEX_COUNT) {
            uv[2 * i] = (points[3 * i] * w - left) / cw
            uv[2 * i + 1] = (points[3 * i + 1] * h - top) / ch
            require(uv[2 * i] in 0f..1f && uv[2 * i + 1] in 0f..1f)
        }
        val cropped = Bitmap.createBitmap(bitmap, left, top, cw, ch)
        var scaled: Bitmap? = null
        try {
            val factor = minOf(1f, MAX_EDGE.toFloat() / maxOf(cw, ch))
            scaled = if (factor < 1f) Bitmap.createScaledBitmap(cropped,
                maxOf(1, (cw * factor).toInt()), maxOf(1, (ch * factor).toInt()), true) else cropped
            val output = ByteArrayOutputStream()
            check(scaled.compress(Bitmap.CompressFormat.JPEG, 88, output))
            val bytes = output.toByteArray()
            require(bytes.size in 1..MAX_JPEG_BYTES)
            return FaceTexture(bytes, uv)
        } finally {
            // createBitmap kann bei vollständigem Ausschnitt das Original zurückgeben.
            if (scaled != null && scaled !== cropped && scaled !== bitmap) scaled.recycle()
            if (cropped !== bitmap) cropped.recycle()
        }
    }
}

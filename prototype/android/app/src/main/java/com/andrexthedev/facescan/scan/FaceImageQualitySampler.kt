package com.andrexthedev.facescan.scan

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect

/** Wiederverwendetes winziges Analysefenster; keine Speicherung von Kamerabildern. */
class FaceImageQualitySampler : AutoCloseable {
    private val edge = 64
    private var sample: Bitmap? = null
    private val pixels = IntArray(edge * edge)
    private val gray = ByteArray(edge * edge)
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG)

    fun sample(bitmap: Bitmap, landmarks: FloatArray): ImageQuality.Result? {
        if (!NeutralCaptureQuality.inFrame(landmarks, bitmap.width, bitmap.height)) return null
        var minX = 1f; var minY = 1f; var maxX = 0f; var maxY = 0f
        for (i in 0 until FaceTopology.VERTEX_COUNT) {
            minX = minOf(minX, landmarks[3*i]); maxX = maxOf(maxX, landmarks[3*i])
            minY = minOf(minY, landmarks[3*i+1]); maxY = maxOf(maxY, landmarks[3*i+1])
        }
        val w = bitmap.width; val h = bitmap.height
        val left = (minX*w).toInt().coerceIn(0, w-1)
        val top = (minY*h).toInt().coerceIn(0, h-1)
        val right = kotlin.math.ceil(maxX*w).toInt().coerceIn(left+1, w)
        val bottom = kotlin.math.ceil(maxY*h).toInt().coerceIn(top+1, h)
        if (right-left < 8 || bottom-top < 8) return null
        val target = sample ?: Bitmap.createBitmap(edge, edge, Bitmap.Config.ARGB_8888).also { sample = it }
        try {
            Canvas(target).drawBitmap(bitmap, Rect(left, top, right, bottom), Rect(0, 0, edge, edge), paint)
            target.getPixels(pixels, 0, edge, 0, 0, edge, edge)
            for (i in pixels.indices) {
                val c = pixels[i]
                val r = (c shr 16) and 0xff; val g = (c shr 8) and 0xff; val b = c and 0xff
                gray[i] = ((54*r + 183*g + 19*b + 128) shr 8).toByte()
            }
            return ImageQuality.analyze(gray, edge, edge, edge)
        } finally {
            target.eraseColor(Color.TRANSPARENT)
            pixels.fill(0); gray.fill(0)
        }
    }

    override fun close() {
        sample?.recycle(); sample = null
        pixels.fill(0); gray.fill(0)
    }
}

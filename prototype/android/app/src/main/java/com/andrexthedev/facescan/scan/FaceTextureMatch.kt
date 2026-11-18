package com.andrexthedev.facescan.scan

import kotlin.math.sqrt

/** Grobe zeitliche Konsistenz zwischen Neutralaufnahme und Foto, keine Identitätsprüfung. */
object FaceTextureMatch {
    fun isConsistent(neutral: FaceSnapshot, photo: FaceFrame): Boolean {
        if (neutral.width != photo.width || neutral.height != photo.height ||
            !NeutralCaptureQuality.inFrame(neutral.points, neutral.width, neutral.height) ||
            !NeutralCaptureQuality.inFrame(photo.points, photo.width, photo.height)) return false
        val eyeX = (neutral.points[263 * 3] - neutral.points[33 * 3]) * neutral.width
        val eyeY = (neutral.points[263 * 3 + 1] - neutral.points[33 * 3 + 1]) * neutral.height
        val eye = sqrt(eyeX * eyeX + eyeY * eyeY)
        var sum = 0.0
        for (i in 0 until FaceTopology.VERTEX_COUNT) {
            val x = (neutral.points[3 * i] - photo.points[3 * i]) * neutral.width
            val y = (neutral.points[3 * i + 1] - photo.points[3 * i + 1]) * neutral.height
            sum += x * x + y * y
        }
        val rms = sqrt(sum / FaceTopology.VERTEX_COUNT)
        return rms.isFinite() && eye > 0f && rms <= 0.08 * eye
    }
}

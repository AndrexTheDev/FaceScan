package com.andrexthedev.facescan.scan

import kotlin.math.abs

/** Grober Hinweis aus 2D-Landmarks, keine Pose-, Qualitäts- oder Identitätsmessung. */
object FaceFrontalGuidance {
    // Unkalibrierter Startwert, kein Winkel in Grad und kein Capture-Gate.
    const val MAX_NOSE_OFFSET = 0.18
    fun possiblyTurned(points: FloatArray, width: Int, height: Int): Boolean? {
        if (!NeutralCaptureQuality.inFrame(points, width, height)) return null
        val ax = points[33*3].toDouble() * width; val ay = points[33*3+1].toDouble() * height
        val bx = points[263*3].toDouble() * width; val by = points[263*3+1].toDouble() * height
        val nx = points[1*3].toDouble() * width; val ny = points[1*3+1].toDouble() * height
        val dx = bx - ax; val dy = by - ay
        val lengthSq = dx*dx + dy*dy
        if (!lengthSq.isFinite() || lengthSq <= 0.0) return null
        val relative = ((nx - (ax+bx)*0.5)*dx + (ny - (ay+by)*0.5)*dy) / lengthSq
        return if (relative.isFinite()) abs(relative) > MAX_NOSE_OFFSET else null
    }
}

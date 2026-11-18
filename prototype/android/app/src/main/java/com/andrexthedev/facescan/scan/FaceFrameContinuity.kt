package com.andrexthedev.facescan.scan

/** Grobe Sprungerkennung im Bildraum, ausdrücklich keine Personenerkennung. */
object FaceFrameContinuity {
    const val MAX_GAP_MS = 1500L
    const val MAX_CENTER_EYE_DISTANCES = 1.25
    const val MAX_SCALE_RATIO = 1.8

    fun isContinuous(previous: FaceFrame, current: FaceFrame): Boolean {
        if (previous.width != current.width || previous.height != current.height || current.atMs <= previous.atMs ||
            current.atMs - previous.atMs > MAX_GAP_MS ||
            !NeutralCaptureQuality.inFrame(previous.points, previous.width, previous.height) ||
            !NeutralCaptureQuality.inFrame(current.points, current.width, current.height)) return false
        fun eyes(frame: FaceFrame): DoubleArray {
            val ax = frame.points[33*3].toDouble() * frame.width; val ay = frame.points[33*3+1].toDouble() * frame.height
            val bx = frame.points[263*3].toDouble() * frame.width; val by = frame.points[263*3+1].toDouble() * frame.height
            return doubleArrayOf((ax+bx)/2, (ay+by)/2, Math.hypot(ax-bx, ay-by))
        }
        val a = eyes(previous); val b = eyes(current)
        val scale = maxOf(a[2], b[2]) / minOf(a[2], b[2])
        val movement = Math.hypot(a[0]-b[0], a[1]-b[1]) / a[2]
        return scale.isFinite() && movement.isFinite() && scale <= MAX_SCALE_RATIO && movement <= MAX_CENTER_EYE_DISTANCES
    }
}

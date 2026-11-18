package com.andrexthedev.facescan.perception

/** Nur vom Analyzer-Thread aufrufen. MediaPipe benötigt streng steigende Zeitstempel. */
internal class FrameClock(private val minIntervalMs: Long = 250L) {
    private var lastProcessedAtMs: Long? = null
    private var lastTimestampMs = -1L

    fun nextTimestamp(cameraTimestampNs: Long, nowMs: Long): Long? {
        val last = lastProcessedAtMs
        if (last != null && nowMs - last < minIntervalMs) return null
        lastProcessedAtMs = nowMs
        val cameraMs = (cameraTimestampNs / 1_000_000L).coerceAtLeast(0L)
        val next = maxOf(cameraMs, lastTimestampMs + 1)
        lastTimestampMs = next
        return next
    }
}

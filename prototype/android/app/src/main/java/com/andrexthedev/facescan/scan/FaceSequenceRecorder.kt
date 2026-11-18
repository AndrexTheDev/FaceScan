package com.andrexthedev.facescan.scan

import kotlin.math.sqrt

/** Heuristische Hilfen, keine Qualitäts- oder Genauigkeitsgarantie. */
object NeutralCaptureQuality {
    fun isUsable(snapshot: FaceSnapshot): Boolean {
        if (snapshot.points.size < FaceTopology.VERTEX_COUNT * 3 || snapshot.width <= 0 || snapshot.height <= 0 ||
            !snapshot.jitterPx.isFinite() || snapshot.jitterPx < 0 || snapshot.samples < 3 ||
            snapshot.points.take(FaceTopology.VERTEX_COUNT * 3).any { !it.isFinite() }) return false
        val p = snapshot.points
        val eyeX = (p[263 * 3] - p[33 * 3]) * snapshot.width
        val eyeY = (p[263 * 3 + 1] - p[33 * 3 + 1]) * snapshot.height
        val eyeDistance = sqrt(eyeX * eyeX + eyeY * eyeY)
        if (!eyeDistance.isFinite() || eyeDistance < 0.10f * minOf(snapshot.width, snapshot.height)) return false
        if (snapshot.jitterPx > eyeDistance * 0.03) return false
        // Punktabstand zum Bildrand: nur grobe Erkennung von Anschnitt.
        return (0 until FaceTopology.VERTEX_COUNT).all { i ->
            p[3 * i] in 0.015f..0.985f && p[3 * i + 1] in 0.015f..0.985f
        }
    }
}

/** Beschränkte Aufnahme: nur nach Nutzerstart, monotone Echtzeitstempel, keine Bilder. */
class FaceSequenceRecorder {
    companion object {
        const val DURATION_MS = 4000L
        const val SAMPLE_INTERVAL_MS = 250L
        const val MAX_GAP_MS = 1250L
        const val MAX_FRAMES = 16
    }
    private var startMs = 0L
    private var running = false
    private var failed = false
    private var dimensions: Pair<Int, Int>? = null
    private val frames = mutableListOf<FaceFrame>()

    @Synchronized fun start(nowMs: Long) {
        frames.clear(); dimensions = null; failed = false; running = true; startMs = nowMs
    }

    @Synchronized fun add(frame: FaceFrame?) {
        if (!running || failed) return
        if (frame == null) { failed = true; frames.clear(); return }
        if (frame.atMs <= startMs) return // Frame, der vor dem Drücken begonnen hat.
        if (frame.atMs > startMs + DURATION_MS) return
        if (frame.width <= 0 || frame.height <= 0 || frame.points.size < FaceTopology.VERTEX_COUNT * 3 ||
            frame.points.take(FaceTopology.VERTEX_COUNT * 3).any { !it.isFinite() }) {
            failed = true; frames.clear(); return
        }
        val dim = frame.width to frame.height
        if (dimensions != null && dimensions != dim) { failed = true; frames.clear(); return }
        if (frames.isNotEmpty()) {
            val delta = frame.atMs - frames.last().atMs
            if (delta < 0 || delta > MAX_GAP_MS) { failed = true; frames.clear(); return }
            if (delta < SAMPLE_INTERVAL_MS) return
        }
        if (frames.size >= MAX_FRAMES) return
        dimensions = dim
        frames.add(frame.copy(points = frame.points.copyOf(FaceTopology.VERTEX_COUNT * 3)))
    }

    @Synchronized fun cancel() { running = false; failed = false; frames.clear(); dimensions = null }

    /** Nur eine vollständige Folge ausgeben; kein Interpolieren über Gesichtsausfall. */
    @Synchronized fun finish(nowMs: Long, neutral: FaceSnapshot): FaceSurface? {
        if (!running || nowMs < startMs + DURATION_MS) return null
        running = false
        val result = try {
            if (failed || dimensions != (neutral.width to neutral.height) || frames.size < 4 || frames.first().atMs - startMs > MAX_GAP_MS ||
                startMs + DURATION_MS - frames.last().atMs > MAX_GAP_MS) null
            else {
                val neutralPoints = FaceSurfaceBuilder.convert(neutral)
                val keys = mutableListOf(FaceKeyframe(0f, neutralPoints))
                for (frame in frames) {
                    val snap = FaceSnapshot(frame.points, frame.width, frame.height, 0.0, 1)
                    keys.add(FaceKeyframe((frame.atMs - startMs) / 1000f, FaceSurfaceBuilder.convert(snap)))
                }
                FaceSurface(neutralPoints, keys.last().points, neutral.jitterPx, 0.0, keys)
            }
        } catch (_: IllegalArgumentException) { null }
        frames.clear(); dimensions = null
        return result
    }
}

/** Gleiches lineares Keyframe-Mixing wie beim GLB-Export. */
object FaceSequencePlayback {
    fun sample(surface: FaceSurface, seconds: Float): FloatArray {
        val keys = surface.keyframes()
        require(keys.size >= 2 && seconds.isFinite())
        if (seconds <= keys.first().seconds) return keys.first().points.copyOf()
        if (seconds >= keys.last().seconds) return keys.last().points.copyOf()
        val upper = keys.indexOfFirst { it.seconds >= seconds }
        val a = keys[upper - 1]; val b = keys[upper]
        val t = (seconds - a.seconds) / (b.seconds - a.seconds)
        return FloatArray(a.points.size) { a.points[it] + (b.points[it] - a.points[it]) * t }
    }
}

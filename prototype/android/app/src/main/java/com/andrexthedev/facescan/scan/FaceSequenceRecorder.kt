package com.andrexthedev.facescan.scan

import kotlin.math.sqrt

/** Heuristische Hilfen, keine Qualitäts- oder Genauigkeitsgarantie. */
object NeutralCaptureQuality {
    fun inFrame(points: FloatArray, width: Int, height: Int): Boolean {
        if (points.size < FaceTopology.VERTEX_COUNT * 3 || width <= 0 || height <= 0 ||
            points.take(FaceTopology.VERTEX_COUNT * 3).any { !it.isFinite() }) return false
        val eyeX = (points[263 * 3] - points[33 * 3]) * width
        val eyeY = (points[263 * 3 + 1] - points[33 * 3 + 1]) * height
        val eyeDistance = sqrt(eyeX * eyeX + eyeY * eyeY)
        if (!eyeDistance.isFinite() || eyeDistance < 0.10f * minOf(width, height)) return false
        return (0 until FaceTopology.VERTEX_COUNT).all { i ->
            points[3 * i] in 0.015f..0.985f && points[3 * i + 1] in 0.015f..0.985f
        }
    }

    fun isUsable(snapshot: FaceSnapshot): Boolean {
        if (!snapshot.jitterPx.isFinite() || snapshot.jitterPx < 0 || snapshot.samples < 3 ||
            !inFrame(snapshot.points, snapshot.width, snapshot.height)) return false
        val eyeX = (snapshot.points[263 * 3] - snapshot.points[33 * 3]) * snapshot.width
        val eyeY = (snapshot.points[263 * 3 + 1] - snapshot.points[33 * 3 + 1]) * snapshot.height
        val eyeDistance = sqrt(eyeX * eyeX + eyeY * eyeY)
        return snapshot.jitterPx <= eyeDistance * 0.03
    }
}

/** Beschränkte Aufnahme: nur nach Nutzerstart, monotone Echtzeitstempel, keine Bilder. */
class FaceSequenceRecorder {
    companion object {
        const val DURATION_MS = 4000L
        const val SAMPLE_INTERVAL_MS = 250L
        const val MAX_GAP_MS = 1250L
        const val MAX_FRAMES = 16
        // Experimentelle Schwelle in Augenabständen, nicht physisch validiert.
        const val MAX_ANCHOR_RMS = 0.12
    }
    private var startMs = 0L
    private var running = false
    private var failed = false
    private var alignmentFailed = false
    private var dimensions: Pair<Int, Int>? = null
    private val frames = mutableListOf<FaceFrame>()

    @Synchronized fun start(nowMs: Long) {
        frames.clear(); dimensions = null; failed = false; alignmentFailed = false; running = true; startMs = nowMs
    }

    @Synchronized fun add(frame: FaceFrame?) {
        if (!running || failed) return
        if (frame == null) { failed = true; frames.clear(); return }
        if (frame.atMs <= startMs) return // Frame, der vor dem Drücken begonnen hat.
        if (frame.atMs > startMs + DURATION_MS) return
        if (!NeutralCaptureQuality.inFrame(frame.points, frame.width, frame.height)) {
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

    @Synchronized fun cancel() { running = false; failed = false; alignmentFailed = false; frames.clear(); dimensions = null }
    @Synchronized fun wasAlignmentFailure() = alignmentFailed

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
                var maxResidual = 0.0
                for (frame in frames) {
                    val snap = FaceSnapshot(frame.points, frame.width, frame.height, 0.0, 1)
                    val aligned = FaceAlignment.align(neutralPoints, FaceSurfaceBuilder.convert(snap))
                    if (aligned.anchorRms > MAX_ANCHOR_RMS) {
                        alignmentFailed = true
                        break
                    }
                    maxResidual = maxOf(maxResidual, aligned.anchorRms)
                    keys.add(FaceKeyframe((frame.atMs - startMs) / 1000f, aligned.points))
                }
                if (alignmentFailed) null else FaceSurface(neutralPoints, keys.last().points, neutral.jitterPx, 0.0, keys, maxResidual)
            }
        } catch (_: IllegalArgumentException) { alignmentFailed = true; null }
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

package com.andrexthedev.facescan.scan

import kotlin.math.sqrt

/** 468 ungespiegelte Landmarks auf dem aufrecht gedrehten Kamerabild, nur im RAM. */
data class FaceFrame(val points: FloatArray, val width: Int, val height: Int, val atMs: Long)
data class FaceSnapshot(val points: FloatArray, val width: Int, val height: Int, val jitterPx: Double, val samples: Int)
data class FaceKeyframe(val seconds: Float, val points: FloatArray)
data class FaceSurface(
    val neutral: FloatArray,
    val expression: FloatArray,
    val neutralJitterPx: Double,
    val expressionJitterPx: Double,
    val sequence: List<FaceKeyframe> = emptyList(),
    // Interner Fit-Rest im Einheitsaugenabstand; kein 3D-Messfehler.
    val maxAnchorRms: Double? = null
) {
    /** Alte Zwei-Posen-Daten bleiben als explizite Übergangsanimation abspielbar. */
    fun keyframes(): List<FaceKeyframe> = if (sequence.isEmpty()) listOf(
        FaceKeyframe(0f, neutral), FaceKeyframe(1f, expression), FaceKeyframe(2f, neutral)
    ) else sequence
}

/** Kleine Rolling-Window-Mittelung; Ausfall oder veraltete Frames ergeben keinen Scan. */
class FaceFrameBuffer {
    private val frames = ArrayDeque<FaceFrame>()

    @Synchronized fun add(frame: FaceFrame?) {
        if (frame == null) { frames.clear(); return }
        if (frame.points.size < FaceTopology.VERTEX_COUNT * 3 || frame.width <= 0 || frame.height <= 0 ||
            frame.points.take(FaceTopology.VERTEX_COUNT * 3).any { !it.isFinite() }) {
            frames.clear(); return
        }
        if (frames.isNotEmpty() && (frames.last().width != frame.width || frames.last().height != frame.height)) frames.clear()
        frames.addLast(frame.copy(points = frame.points.copyOf(FaceTopology.VERTEX_COUNT * 3)))
        while (frames.size > 5) frames.removeFirst()
    }

    @Synchronized fun snapshot(nowMs: Long): FaceSnapshot? {
        val recent = frames.filter { nowMs >= it.atMs && nowMs - it.atMs <= 5000 }
        if (recent.size < 3 || nowMs - recent.last().atMs > 2500) return null
        val size = FaceTopology.VERTEX_COUNT * 3
        val mean = FloatArray(size)
        for (f in recent) for (i in 0 until size) mean[i] += f.points[i] / recent.size
        val width = recent.last().width
        val height = recent.last().height
        var sq = 0.0
        for (f in recent) for (i in 0 until FaceTopology.VERTEX_COUNT) {
            val dx = (f.points[3 * i] - mean[3 * i]) * width
            val dy = (f.points[3 * i + 1] - mean[3 * i + 1]) * height
            sq += dx * dx + dy * dy
        }
        return FaceSnapshot(mean, width, height, sqrt(sq / (recent.size * FaceTopology.VERTEX_COUNT)), recent.size)
    }
}

/** Normiert auf Augenabstand und korrigiert Bildrotation; nicht metrisch kalibriert. */
object FaceSurfaceBuilder {
    fun build(neutral: FaceSnapshot, expression: FaceSnapshot): FaceSurface {
        require(neutral.jitterPx.isFinite() && expression.jitterPx.isFinite())
        return FaceSurface(convert(neutral), convert(expression), neutral.jitterPx, expression.jitterPx)
    }

    fun convert(frame: FaceSnapshot): FloatArray {
        require(frame.points.size >= FaceTopology.VERTEX_COUNT * 3 && frame.width > 0 && frame.height > 0)
        require(frame.points.take(FaceTopology.VERTEX_COUNT * 3).all { it.isFinite() })
        fun x(i: Int) = frame.points[3 * i] * frame.width
        fun y(i: Int) = frame.points[3 * i + 1] * frame.height
        val dx = (x(263) - x(33)).toDouble()
        val dy = (y(263) - y(33)).toDouble()
        val distance = sqrt(dx * dx + dy * dy)
        require(distance.isFinite() && distance >= 2.0) { "Ungültiger Augenabstand" }
        val ex = dx / distance
        val ey = dy / distance
        val cx = (x(33) + x(263)) / 2.0
        val cy = (y(33) + y(263)) / 2.0
        val centerZ = (frame.points[33 * 3 + 2] + frame.points[263 * 3 + 2]) * frame.width / 2.0
        val out = FloatArray(FaceTopology.VERTEX_COUNT * 3)
        for (i in 0 until FaceTopology.VERTEX_COUNT) {
            val px = x(i) - cx
            val py = y(i) - cy
            out[3 * i] = ((px * ex + py * ey) / distance).toFloat()
            out[3 * i + 1] = ((px * ey - py * ex) / distance).toFloat()
            out[3 * i + 2] = (-(frame.points[3 * i + 2] * frame.width - centerZ) / distance).toFloat()
            require(out[3 * i].isFinite() && out[3 * i + 1].isFinite() && out[3 * i + 2].isFinite())
        }
        return out
    }
}

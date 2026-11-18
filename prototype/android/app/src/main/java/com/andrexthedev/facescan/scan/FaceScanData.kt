package com.andrexthedev.facescan.scan

import kotlin.math.sqrt

/** 468 ungespiegelte Landmarks auf dem aufrecht gedrehten Kamerabild, nur im RAM. */
data class FaceFrame(val points: FloatArray, val width: Int, val height: Int, val atMs: Long)
data class FaceTexture(val jpeg: ByteArray, val uv: FloatArray)
data class FaceSnapshot(
    val points: FloatArray, val width: Int, val height: Int, val jitterPx: Double, val samples: Int,
    val texture: FaceTexture? = null,
    val fusedPoints: FloatArray? = null,
    val fusionAnchorRms: Double? = null,
    // Nur für laufende Kameraaufnahme; nicht als Personenkennung verwenden.
    val sessionEpoch: Long? = null
)
data class FaceKeyframe(val seconds: Float, val points: FloatArray)
data class FaceSurface(
    val neutral: FloatArray,
    val expression: FloatArray,
    val neutralJitterPx: Double,
    val expressionJitterPx: Double,
    val sequence: List<FaceKeyframe> = emptyList(),
    // Interner Fit-Rest im Einheitsaugenabstand; kein 3D-Messfehler.
    val maxAnchorRms: Double? = null,
    val texture: FaceTexture? = null,
    val neutralSamples: Int = 0,
    val neutralFusionAnchorRms: Double? = null
) {
    /** Alte Zwei-Posen-Daten bleiben als explizite Übergangsanimation abspielbar. */
    fun keyframes(): List<FaceKeyframe> = if (sequence.isEmpty()) listOf(
        FaceKeyframe(0f, neutral), FaceKeyframe(1f, expression), FaceKeyframe(2f, neutral)
    ) else sequence
}

/** Kleines Rolling Window; Ausfall oder veraltete Frames ergeben keinen Scan. */
class FaceFrameBuffer {
    private val frames = ArrayDeque<FaceFrame>()
    // Nach Gesichtsverlust oder Dimensionswechsel dürfen laufende Berechnungen
    // kein Ergebnis aus der alten Aufnahmesitzung zurückgeben.
    private var epoch = 0L

    @Synchronized fun add(frame: FaceFrame?) {
        if (frame == null) { frames.clear(); epoch++; return }
        if (frame.points.size < FaceTopology.VERTEX_COUNT * 3 || frame.width <= 0 || frame.height <= 0 ||
            frame.points.take(FaceTopology.VERTEX_COUNT * 3).any { !it.isFinite() }) {
            frames.clear(); epoch++; return
        }
        if (frames.isNotEmpty() && (frames.last().width != frame.width || frames.last().height != frame.height ||
                frame.atMs <= frames.last().atMs)) { frames.clear(); epoch++ }
        frames.addLast(frame.copy(points = frame.points.copyOf(FaceTopology.VERTEX_COUNT * 3)))
        while (frames.size > 5) frames.removeFirst()
    }

    @Synchronized fun hasRecentFace(nowMs: Long): Boolean {
        val recent = frames.filter { nowMs >= it.atMs && nowMs - it.atMs <= 5000 }
        return recent.size >= 3 && nowMs - recent.last().atMs <= 2500 &&
            NeutralCaptureQuality.inFrame(recent.last().points, recent.last().width, recent.last().height)
    }

    /** Prüft auch nach asynchroner Verarbeitung, ob die Aufnahme zur aktuellen Sitzung gehört. */
    @Synchronized fun isCurrent(snapshot: FaceSnapshot, nowMs: Long): Boolean =
        snapshot.sessionEpoch != null && snapshot.sessionEpoch == epoch &&
            frames.lastOrNull()?.let { it.width == snapshot.width && it.height == snapshot.height } == true &&
            hasRecentFace(nowMs)

    fun snapshot(nowMs: Long): FaceSnapshot? {
        val (recent, capturedEpoch) = synchronized(this) {
            frames.filter { nowMs >= it.atMs && nowMs - it.atMs <= 5000 } to epoch
        }
        if (recent.size < 3 || nowMs - recent.last().atMs > 2500) return null
        val size = FaceTopology.VERTEX_COUNT * 3
        val valid = recent.filter { NeutralCaptureQuality.inFrame(it.points, it.width, it.height) }
        if (valid.size < NeutralGeometryFusion.MIN_FRAMES) return null
        val converted = valid.map { frame ->
            try { FaceSurfaceBuilder.convert(FaceSnapshot(frame.points, frame.width, frame.height, 0.0, 1)) }
            catch (_: IllegalArgumentException) { FloatArray(0) }
        }
        val fusion = NeutralGeometryFusion.fuse(converted) ?: return null
        val accepted = fusion.accepted.map { valid[it] }
        // Ein aktueller erkannter Frame muss auch zum Konsens passen.
        if (accepted.last().atMs != recent.last().atMs || nowMs - accepted.last().atMs > 2500) return null
        val mean = FloatArray(size)
        for (f in accepted) for (i in 0 until size) mean[i] += f.points[i] / accepted.size
        val width = accepted.last().width
        val height = accepted.last().height
        var sq = 0.0
        for (f in accepted) for (i in 0 until FaceTopology.VERTEX_COUNT) {
            val dx = (f.points[3 * i] - mean[3 * i]) * width
            val dy = (f.points[3 * i + 1] - mean[3 * i + 1]) * height
            sq += dx * dx + dy * dy
        }
        val snapshot = FaceSnapshot(mean, width, height, sqrt(sq / (accepted.size * FaceTopology.VERTEX_COUNT)),
            accepted.size, fusedPoints = fusion.points, fusionAnchorRms = fusion.maxAnchorRms, sessionEpoch = capturedEpoch)
        return synchronized(this) { if (epoch == capturedEpoch) snapshot else null }
    }
}

/** Normiert auf Augenabstand und korrigiert Bildrotation; nicht metrisch kalibriert. */
object FaceSurfaceBuilder {
    fun build(neutral: FaceSnapshot, expression: FaceSnapshot): FaceSurface {
        require(neutral.jitterPx.isFinite() && expression.jitterPx.isFinite())
        return FaceSurface(neutralPoints(neutral), convert(expression), neutral.jitterPx, expression.jitterPx,
            neutralSamples = neutral.samples, neutralFusionAnchorRms = neutral.fusionAnchorRms)
    }

    fun neutralPoints(frame: FaceSnapshot): FloatArray {
        val fused = frame.fusedPoints ?: return convert(frame)
        require(fused.size == FaceTopology.VERTEX_COUNT * 3 && fused.all { it.isFinite() })
        return fused.copyOf()
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

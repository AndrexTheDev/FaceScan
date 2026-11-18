package com.andrexthedev.facescan.perception

import android.content.Context
import android.os.SystemClock
import android.util.Log
import androidx.camera.core.ImageProxy
import java.io.IOException
import java.util.concurrent.atomic.AtomicBoolean

/** Statusanzeige der experimentellen Erkennung, kein Scan oder Qualitätsurteil. */
enum class FaceStatus { WAITING, NO_FACE, FACE, MISSING_MODEL, ERROR }

/** analyse() und close() werden seriell auf dem CameraX-Analyzer-Thread aufgerufen. */
class FaceFrameAnalyzer(
    private val context: Context,
    private val active: AtomicBoolean,
    private val onStatus: (FaceStatus) -> Unit
) : AutoCloseable {
    private val clock = FrameClock()
    private var runner: FaceLandmarkerRunner? = null
    private var stopped = false

    fun analyse(proxy: ImageProxy) {
        try {
            if (!active.get() || stopped) return
            val timestamp = clock.nextTimestamp(proxy.imageInfo.timestamp, SystemClock.elapsedRealtime()) ?: return
            if (runner == null) {
                try {
                    context.assets.open("face_landmarker.task").use { }
                } catch (e: IOException) {
                    stopped = true
                    onStatus(FaceStatus.MISSING_MODEL)
                    return
                }
                runner = FaceLandmarkerRunner(context)
            }
            // CameraX konvertiert YUV_420_888 inklusive Pixel-/Zeilenstride.
            // Rotation erfolgt in MediaPipe, das Eingabebild bleibt ungespiegelt.
            val found = runner!!.hasFace(proxy.toBitmap(), proxy.imageInfo.rotationDegrees, timestamp)
            if (active.get()) onStatus(if (found) FaceStatus.FACE else FaceStatus.NO_FACE)
        } catch (e: Exception) {
            stopped = true
            Log.e("FaceScan", "Gesichtserkennung konnte nicht ausgeführt werden", e)
            if (active.get()) onStatus(FaceStatus.ERROR)
        } finally {
            proxy.close()
        }
    }

    override fun close() {
        stopped = true
        runner?.close()
        runner = null
    }
}

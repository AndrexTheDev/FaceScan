package com.andrexthedev.facescan.perception

import android.content.Context
import android.os.SystemClock
import android.util.Log
import androidx.camera.core.ImageProxy
import java.io.File
import com.andrexthedev.facescan.diagnostics.TestDiagnostics
import java.util.concurrent.atomic.AtomicBoolean

/** Statusanzeige der experimentellen Erkennung, kein Scan oder Qualitätsurteil. */
enum class FaceStatus { WAITING, NO_FACE, FACE, MISSING_MODEL, ERROR }

/** analyse() und close() werden seriell auf dem CameraX-Analyzer-Thread aufgerufen. */
class FaceFrameAnalyzer(
    private val context: Context,
    private val modelFile: File,
    private val diagnostics: TestDiagnostics,
    private val active: AtomicBoolean,
    private val onStatus: (FaceStatus) -> Unit
) : AutoCloseable {
    private val clock = FrameClock()
    private var runner: FaceLandmarkerRunner? = null
    private var stopped = false

    fun analyse(proxy: ImageProxy) {
        try {
            if (!active.get() || stopped) return
            diagnostics.frame(proxy.width, proxy.height, proxy.imageInfo.rotationDegrees)
            val timestamp = clock.nextTimestamp(proxy.imageInfo.timestamp, SystemClock.elapsedRealtime()) ?: return
            if (runner == null) {
                if (!modelFile.isFile) {
                    stopped = true
                    diagnostics.inferenceError("ModelFileMissing")
                    onStatus(FaceStatus.MISSING_MODEL)
                    return
                }
                runner = FaceLandmarkerRunner(context, modelFile)
            }
            val startedAt = SystemClock.elapsedRealtime()
            // CameraX konvertiert YUV_420_888 inklusive Pixel-/Zeilenstride.
            // Rotation erfolgt in MediaPipe, das Eingabebild bleibt ungespiegelt.
            val found = runner!!.hasFace(proxy.toBitmap(), proxy.imageInfo.rotationDegrees, timestamp)
            diagnostics.result(found, SystemClock.elapsedRealtime() - startedAt)
            if (active.get()) onStatus(if (found) FaceStatus.FACE else FaceStatus.NO_FACE)
        } catch (e: Exception) {
            stopped = true
            diagnostics.inferenceError(e.javaClass.simpleName)
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

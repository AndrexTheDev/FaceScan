package com.andrexthedev.facescan.perception

import android.content.Context
import android.os.SystemClock
import android.util.Log
import androidx.camera.core.ImageProxy
import com.google.mediapipe.framework.MediaPipeException
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
        var phase = "initialization"
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
            phase = "bitmap"
            val bitmap = proxy.toBitmap()
            phase = "inference"
            val found = runner!!.hasFace(bitmap, proxy.imageInfo.rotationDegrees, timestamp)
            diagnostics.result(found, SystemClock.elapsedRealtime() - startedAt)
            if (active.get()) onStatus(if (found) FaceStatus.FACE else FaceStatus.NO_FACE)
        } catch (e: Exception) {
            reportFailure(phase, e)
        } catch (e: LinkageError) {
            // Fehlende oder inkompatible JNI-Bibliotheken sind Errors, keine
            // Exceptions. Der Testbericht muss auch diesen Fall erfassen.
            reportFailure(phase, e)
        } finally {
            proxy.close()
        }
    }

    private fun reportFailure(phase: String, error: Throwable) {
        stopped = true
        val code = if (error is MediaPipeException) ":${error.statusCode.name}" else ""
        diagnostics.inferenceError("$phase:${error.javaClass.simpleName}$code")
        Log.e("FaceScan", "Gesichtserkennung konnte nicht ausgeführt werden", error)
        if (active.get()) onStatus(FaceStatus.ERROR)
    }

    override fun close() {
        stopped = true
        runner?.close()
        runner = null
    }
}

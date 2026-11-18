package com.andrexthedev.facescan.perception

import android.content.Context
import android.os.SystemClock
import android.graphics.Bitmap
import android.graphics.Matrix
import android.util.Log
import androidx.camera.core.ImageProxy
import com.google.mediapipe.framework.MediaPipeException
import java.io.File
import com.andrexthedev.facescan.diagnostics.TestDiagnostics
import com.andrexthedev.facescan.scan.FaceFrame
import com.andrexthedev.facescan.scan.FaceImageQualitySampler
import com.andrexthedev.facescan.scan.ImageQuality
import com.andrexthedev.facescan.scan.FaceTexture
import com.andrexthedev.facescan.scan.FaceTextureCapture
import com.andrexthedev.facescan.scan.FaceTextureRequest
import java.util.concurrent.atomic.AtomicBoolean

/** Statusanzeige der experimentellen Erkennung, kein Scan oder Qualitätsurteil. */
enum class FaceStatus { WAITING, NO_FACE, FACE, MISSING_MODEL, ERROR }

/** analyse() und close() werden seriell auf dem CameraX-Analyzer-Thread aufgerufen. */
class FaceFrameAnalyzer(
    private val context: Context,
    private val modelFile: File,
    private val diagnostics: TestDiagnostics,
    private val active: AtomicBoolean,
    private val onFaceFrame: ((FaceFrame?) -> Unit)? = null,
    private val textureRequest: FaceTextureRequest? = null,
    private val onTexture: ((Long, FaceTexture?, FaceFrame) -> Unit)? = null,
    private val onQualityHint: ((ImageQuality.Hint?) -> Unit)? = null,
    private val onStatus: (FaceStatus) -> Unit
) : AutoCloseable {
    private val clock = FrameClock()
    private var runner: FaceLandmarkerRunner? = null
    private var qualitySampler: FaceImageQualitySampler? = null
    private var lastQualityAt = Long.MIN_VALUE
    private var stopped = false

    fun analyse(proxy: ImageProxy) {
        var phase = "initialization"
        try {
            if (!active.get() || stopped) return
            diagnostics.frame(proxy.width, proxy.height, proxy.imageInfo.rotationDegrees)
            val timestamp = clock.nextTimestamp(proxy.imageInfo.timestamp, SystemClock.elapsedRealtime()) ?: return
            val frameStartedAt = SystemClock.elapsedRealtime()
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
            val raw = proxy.toBitmap()
            val bitmap = if (onFaceFrame == null) raw else upright(raw, proxy.imageInfo.rotationDegrees)
            val width = bitmap.width
            val height = bitmap.height
            phase = "inference"
            val points = runner!!.detect(bitmap, if (onFaceFrame == null) proxy.imageInfo.rotationDegrees else 0, timestamp) { upright, landmarks ->
                if (onQualityHint != null && active.get() &&
                    (lastQualityAt == Long.MIN_VALUE || frameStartedAt - lastQualityAt >= 500L)) {
                    lastQualityAt = frameStartedAt
                    val hint = try {
                        val sampler = qualitySampler ?: FaceImageQualitySampler().also { qualitySampler = it }
                        sampler.sample(upright, landmarks)?.hint
                    } catch (_: Exception) { null }
                    onQualityHint.invoke(hint)
                }
                val id = textureRequest?.take() ?: 0L
                if (id != 0L) {
                    val texture = try { FaceTextureCapture.capture(upright, landmarks) } catch (_: Exception) { null }
                    if (active.get()) onTexture?.invoke(id, texture, FaceFrame(landmarks.copyOf(), width, height, frameStartedAt))
                }
            }
            val found = points != null
            if (!found && active.get()) {
                lastQualityAt = Long.MIN_VALUE
                onQualityHint?.invoke(null)
            }
            diagnostics.result(found, SystemClock.elapsedRealtime() - startedAt, frameStartedAt)
            if (active.get()) {
                onFaceFrame?.invoke(points?.let { FaceFrame(it, width, height, frameStartedAt) })
                onStatus(if (found) FaceStatus.FACE else FaceStatus.NO_FACE)
            }
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

    private fun upright(source: Bitmap, rotation: Int): Bitmap {
        if (rotation == 0) return source
        return try {
            val matrix = Matrix().apply { postRotate(rotation.toFloat()) }
            Bitmap.createBitmap(source, 0, 0, source.width, source.height, matrix, true).also {
                if (it !== source) source.recycle()
            }
        } catch (e: Exception) {
            source.recycle()
            throw e
        }
    }

    private fun reportFailure(phase: String, error: Throwable) {
        stopped = true
        val code = if (error is MediaPipeException) ":${error.statusCode.name}" else ""
        diagnostics.inferenceError("$phase:${error.javaClass.simpleName}$code")
        Log.e("FaceScan", "Gesichtserkennung konnte nicht ausgeführt werden", error)
        if (active.get()) {
            onFaceFrame?.invoke(null)
            onQualityHint?.invoke(null)
            onStatus(FaceStatus.ERROR)
        }
    }

    override fun close() {
        stopped = true
        try { runner?.close() } finally { qualitySampler?.close(); qualitySampler = null; runner = null }
    }
}

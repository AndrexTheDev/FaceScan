package com.andrexthedev.facescan.perception

import android.content.Context
import android.graphics.Bitmap
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.ImageProcessingOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker
import java.io.File
import java.io.FileInputStream
import java.nio.channels.FileChannel

/**
 * Eine Instanz pro Kamera-Sitzung. Alle Methoden laufen auf demselben
 * Analyzer-Thread. VIDEO ist synchron: kein asynchroner Callback hält ein
 * Kamerabild länger fest als der Aufruf. Die Modellgewichte sind separat
 * lizenzpflichtig (docs/09) und nicht im Repository.
 */
class FaceLandmarkerRunner(context: Context, modelFile: File) : AutoCloseable {
    // Die gepinnte, geprüfte Datei bleibt während der Landmarker-Lebensdauer referenziert.
    private val modelBuffer = FileInputStream(modelFile).channel.use {
        it.map(FileChannel.MapMode.READ_ONLY, 0, it.size())
    }
    private val landmarker: FaceLandmarker

    init {
        val options = FaceLandmarker.FaceLandmarkerOptions.builder()
            .setBaseOptions(BaseOptions.builder().setModelAssetBuffer(modelBuffer).build())
            .setRunningMode(RunningMode.VIDEO)
            .setNumFaces(1)
            .setMinFaceDetectionConfidence(0.5f)
            .setMinFacePresenceConfidence(0.5f)
            .setMinTrackingConfidence(0.5f)
            .build()
        landmarker = FaceLandmarker.createFromOptions(context, options)
    }

    /**
     * Liefert die normalisierten Landmarks des ersten Gesichts. Die Daten
     * verlassen das Gerät nur beim ausdrücklich gewählten Export. MPImage.close()
     * gibt auch das Bitmap frei.
     */
    fun detect(bitmap: Bitmap, rotationDegrees: Int, timestampMs: Long): FloatArray? {
        val image = try {
            BitmapImageBuilder(bitmap).build()
        } catch (e: Exception) {
            bitmap.recycle()
            throw e
        }
        return image.use {
            val options = ImageProcessingOptions.builder().setRotationDegrees(rotationDegrees).build()
            val points = landmarker.detectForVideo(it, options, timestampMs).faceLandmarks().firstOrNull()
            points?.let { list ->
                FloatArray(list.size * 3).also { out ->
                    list.forEachIndexed { i, point ->
                        out[3 * i] = point.x()
                        out[3 * i + 1] = point.y()
                        out[3 * i + 2] = point.z()
                    }
                }
            }
        }
    }

    fun hasFace(bitmap: Bitmap, rotationDegrees: Int, timestampMs: Long): Boolean =
        detect(bitmap, rotationDegrees, timestampMs) != null

    override fun close() = landmarker.close()
}

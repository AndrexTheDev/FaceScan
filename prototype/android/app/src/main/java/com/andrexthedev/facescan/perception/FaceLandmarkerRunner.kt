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
     * Nur Anwesenheit, keine Speicherung von Punkten. ImageProcessingOptions
     * dreht das ungespiegelte Kamerabild im Uhrzeigersinn; PreviewView spiegelt
     * die Frontkamera separat. MPImage.close() gibt auch das Bitmap frei.
     */
    fun hasFace(bitmap: Bitmap, rotationDegrees: Int, timestampMs: Long): Boolean {
        val image = try {
            BitmapImageBuilder(bitmap).build()
        } catch (e: Exception) {
            bitmap.recycle()
            throw e
        }
        return image.use {
            val options = ImageProcessingOptions.builder().setRotationDegrees(rotationDegrees).build()
            landmarker.detectForVideo(it, options, timestampMs).faceLandmarks().isNotEmpty()
        }
    }

    override fun close() = landmarker.close()
}

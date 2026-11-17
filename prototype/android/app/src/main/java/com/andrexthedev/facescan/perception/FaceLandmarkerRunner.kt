package com.andrexthedev.facescan.perception

import android.content.Context
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarkerResult

/**
 * Wahrnehmung: Gesichts-Landmarks, 52 Mimik-Werte und die 4x4-Kopfpose.
 *
 * STAND: vom Gradle-Durchlauf in der CI geprueft (MediaPipe Tasks Vision
 * 0.10.14). Dabei hat sich eine Sache anders gezeigt, als man sie nach der
 * Doku erwarten wuerde:
 *
 *   faceBlendshapes()              -> Optional<List<Classifications>>
 *   facialTransformationMatrixes() -> Optional<List<Matrix>>
 *   faceLandmarks()                -> List<List<NormalizedLandmark>>
 *
 * Die Mimik und die Matrix kommen als **Optional**, die Landmarks nicht.
 * Wer alle drei gleich behandelt (etwa mit .firstOrNull()), bekommt den
 * Fehler an der falschen Stelle: Kotlin meldet dann "None of the following
 * candidates is applicable" auf firstOrNull() und danach eine Kaskade von
 * Folgefehlern ("Unresolved reference"), die alle nur davon kommen, dass
 * der Typ nicht aufgeloest werden konnte. Die Landmarks liefen daneben
 * fehlerfrei durch -- das ist der Hinweis, dass nicht die API falsch ist,
 * sondern nur die beiden Optional.
 *
 * Zugriffe tragen kein "get": it.x(), categoryName(), score(), data().
 *
 * Wichtig (haeufigste Fehlerquelle bei Blendshape-Pipelines):
 * Die Modell-Doku weist ausdruecklich darauf hin, dass sich *Left und
 * *Right auf die ABGEBILDETE PERSON beziehen und sich bei horizontal
 * gespiegeltem Eingabebild vertauschen. Wir speisen daher IMMER das
 * ungespiegelte Bild ein und spiegeln nur die Anzeige.
 *
 * Lizenz: MediaPipe Tasks ist Apache-2.0. Die Modellkarten der Gewichte sind
 * vor dem Einbau schriftlich zu pruefen (docs/09).
 */
class FaceLandmarkerRunner(private val context: Context) {

    private var landmarker: FaceLandmarker? = null

    data class Result(
        val landmarks: List<Triple<Float, Float, Float>>,   // 478 Punkte, normalisiert
        val blendshapes: Map<String, Float>,                // 52 ARKit-Namen -> Gewicht
        val headPose: FloatArray                            // 4x4, spaltenweise
    )

    fun init(modelPath: String = "face_landmarker.task") {
        if (landmarker != null) return
        val baseOptions = BaseOptions.builder()
            .setModelAssetPath(modelPath)
            .build()
        val options = FaceLandmarker.FaceLandmarkerOptions.builder()
            .setBaseOptions(baseOptions)
            .setRunningMode(RunningMode.LIVE_STREAM)
            .setNumFaces(1)
            .setMinFaceDetectionConfidence(0.5f)
            .setMinFacePresenceConfidence(0.5f)
            .setMinTrackingConfidence(0.5f)
            .setOutputFaceBlendshapes(true)
            .setOutputFacialTransformationMatrixes(true)
            .setResultListener { result: FaceLandmarkerResult, _ -> lastResult = result.toInternal() }
            .setErrorListener { error ->
                android.util.Log.e("FaceScan", "Landmarker: ${error.message}")
            }
            .build()
        landmarker = FaceLandmarker.createFromOptions(context, options)
    }

    @Volatile
    var lastResult: Result? = null
        private set

    fun detect(bitmap: android.graphics.Bitmap, timestampMs: Long) {
        val mpImage = BitmapImageBuilder(bitmap).build()
        landmarker?.detectAsync(mpImage, timestampMs)
    }

    fun close() {
        landmarker?.close()
        landmarker = null
    }

    private fun FaceLandmarkerResult.toInternal(): Result {
        val points = faceLandmarks().firstOrNull()?.map {
            Triple(it.x(), it.y(), it.z())
        } ?: emptyList()

        val shapes = mutableMapOf<String, Float>()
        // Optional<List<Classifications>> -- erst das Optional auspacken,
        // dann die Liste, dann je Eintrag categories().
        faceBlendshapes().orElse(null)?.firstOrNull()
            ?.categories()
            ?.forEach { shapes[it.categoryName()] = it.score() }

        // Spaltenweise, 16 Zahlen (Doku: "flat column-major float array").
        val matrix = facialTransformationMatrixes().orElse(null)?.firstOrNull()
            ?.data() ?: FloatArray(16)
        return Result(points, shapes, matrix)
    }
}

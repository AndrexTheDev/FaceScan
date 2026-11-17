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
 *   faceLandmarks()                -> List<List<NormalizedLandmark>>
 *   faceBlendshapes()              -> Optional<List<List<Category>>>
 *   facialTransformationMatrixes() -> Optional<List<FloatArray>>
 *
 * Zwei Fallen, beide teuer bezahlt:
 *
 * 1) Mimik und Matrix stecken in einem Optional, die Landmarks nicht. Wer
 *    alle drei gleich behandelt, bekommt den Fehler an der falschen Stelle:
 *    Kotlin meldet "None of the following candidates is applicable" auf
 *    firstOrNull() und danach eine Kaskade von "Unresolved reference", die
 *    nur daraus folgt, dass der Typ nicht aufgeloest werden konnte. Dass
 *    die Landmarks daneben fehlerfrei durchliefen, war der Hinweis -- nicht
 *    die API war falsch, nur die beiden Optional.
 *
 * 2) Die Doku auf developers.google.com/edge beschreibt eine NEUERE Version:
 *    dort heisst es Optional<List<Classifications>> und Optional<List<Matrix>>
 *    mit .categories() und .data(). In 0.10.14 gibt es diese Typen an dieser
 *    Stelle noch nicht. Massgeblich ist der Quelltext des Tags v0.10.14,
 *    nicht die Doku. Bei einem Release-Wechsel ist hier nachzupruefen.
 *
 * Zugriffe tragen kein "get": it.x(), categoryName(), score().
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
        // Optional<List<List<Category>>> -- drei Ebenen, keine davon heisst
        // Classifications (das gilt erst in neueren Releases).
        faceBlendshapes().orElse(null)
            ?.firstOrNull()
            ?.forEach { shapes[it.categoryName()] = it.score() }

        // Spaltenweise, 16 Zahlen (Quelltext: "flat column-major float array").
        val matrix = facialTransformationMatrixes().orElse(null)
            ?.firstOrNull()
            ?: FloatArray(16)
        return Result(points, shapes, matrix)
    }
}

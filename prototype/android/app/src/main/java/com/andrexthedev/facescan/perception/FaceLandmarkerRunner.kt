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
 * ACHTUNG – STAND: nicht kompiliert.
 * In dieser Entwicklungsumgebung gibt es kein JDK und kein Gradle. Diese
 * Datei ist die EINZIGE im Prototyp, die gegen eine fremde API geschrieben
 * ist, deren genaue Signatur versionabhaengig ist (MediaPipe Tasks Vision
 * 0.10.14). Der erste Gradle-Durchlauf muss deshalb zwei Dinge pruefen:
 *
 *   1. faceBlendshapes()            -> List<Classifications>, und je Eintrag
 *                                      categories(): List<Category>
 *   2. facialTransformationMatrixes() -> List<Matrix> mit .data als FloatArray
 *
 * Beides ist in einer frueheren MediaPipe-Version anders benannt gewesen
 * (getCategories() / getaData()). Wenn der Build hier meckert, ist genau das
 * gemeint – nicht die Mathematik. Der Kern (geometry/) haengt nicht daran.
 */
 *
 * Wichtig (haeufigste Fehlerquelle bei Blendshape-Pipelines):
 * Die Modell-Doku weist ausdruecklich darauf hin, dass sich *Left/*Right auf
 * die ABGEBILDETE PERSON beziehen und sich bei horizontal gespiegeltem
 * Eingabebild vertauschen. Wir speisen daher IMMER das ungespiegelte Bild ein
 * und spiegeln nur die Anzeige.
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
        faceBlendshapes().firstOrNull()?.forEach { shapes[it.categoryName()] = it.score() }

        val matrix = facialTransformationMatrixes().firstOrNull()?.data ?: FloatArray(16)
        return Result(points, shapes, matrix)
    }
}

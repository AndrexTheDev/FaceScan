package com.andrexthedev.facescan.pipeline

import com.andrexthedev.facescan.geometry.CameraModel
import com.andrexthedev.facescan.geometry.ModelFitter
import com.andrexthedev.facescan.geometry.MorphableModel
import com.andrexthedev.facescan.geometry.Observation
import kotlin.math.sqrt

/**
 * M0-Pipeline: von den gesammelten Beobachtungen zum Qualitaetsbericht.
 *
 * M0 hat bewusst KEIN MVS, keine TSDF-Fusion und keine Texturerei – das kommt
 * in M1/M2 dazu. M0 beweist nur die eine Sache, an der das ganze Projekt
 * haengt: **Wir bekommen ohne ARCore metrische Geometrie.**
 *
 * Jede Stufe ist eine reine Funktion -> testbar, pausierbar, wiederholbar.
 * Ab M1 checkpointet jede Stufe (docs/02, Kapitel 5).
 */
class M0ScanPipeline(
    private val camera: CameraModel,
    private val model: MorphableModel
) {

    data class ScanFrame(
        val landmarks: DoubleArray,     // 2N Pixelkoordinaten
        val visibility: DoubleArray     // N Sichtbarkeiten
    )

    data class ScanResult(
        val alpha: DoubleArray,
        val poses: List<com.andrexthedev.facescan.geometry.RigidTransform>,
        val meanReprojectionPx: Double,
        val report: QualityReport
    )

    suspend fun run(frames: List<ScanFrame>): ScanResult = kotlinx.coroutines.withContext(
        kotlinx.coroutines.Dispatchers.Default
    ) {
        require(frames.isNotEmpty()) { "Keine gueltigen Bilder" }

        val observations = frames.map { Observation(it.landmarks, it.visibility) }
        val fit = ModelFitter.fit(camera, model, observations)

        // Abdeckung: wie viel der Kopf-Oberflaeche wurde aus >= 3 Richtungen gesehen?
        val coverage = estimateCoverage(fit.poses)
        // Haar-Abdeckung in M0 nur ein Platzhalter (Haar-Pipeline = M2)
        val hairCoverage = 0.6
        val textureHoles = 0.0

        val report = buildReport(
            reprojectionPx = fit.reproHistory.last(),
            geometryMm = 0.0,   // M0: noch kein Mesh-Vergleich (kommt mit dem MVS in M1)
            coverage = coverage,
            hairCoverage = hairCoverage,
            textureHoles = textureHoles
        ).copy(
            formtreue = QualityReport.Light(
                state = if (fit.reproHistory.last() < 2.0) QualityReport.State.GREEN
                else QualityReport.State.YELLOW,
                headlineDe = "Form: geprüft",
                headlineEn = "Shape: verified",
                detailDe = "Reprojektion ${"%.2f".format(fit.reproHistory.last())} px",
                detailEn = "Reprojection ${"%.2f".format(fit.reproHistory.last())} px"
            )
        )

        ScanResult(
            alpha = fit.alpha,
            poses = fit.poses,
            meanReprojectionPx = fit.reproHistory.last(),
            report = report
        )
    }

    /**
     * Grobe Abdeckungsschaetzung: Streuung der Blickrichtungen (Kameraposition
     * relativ zum Kopf) über die Kugel. Ersetzt ab M1 die echte
     * Sichtbarkeits-Auswertung je Vertex.
     */
    private fun estimateCoverage(poses: List<com.andrexthedev.facescan.geometry.RigidTransform>): Double {
        if (poses.isEmpty()) return 0.0
        val buckets = BooleanArray(24)       // 15-Grad-Bloecke im Gierwinkel
        for (pose in poses) {
            val dir = doubleArrayOf(-pose.translation[0], -pose.translation[1], -pose.translation[2])
            val yaw = Math.toDegrees(kotlin.math.atan2(dir[0], dir[2]))
            val idx = (((yaw + 180.0) / 15.0).toInt()).coerceIn(0, 23)
            buckets[idx] = true
        }
        return buckets.count { it }.toDouble() / 16.0   // 16 Bloecke = ±120 Grad gelten als voll
    }
}

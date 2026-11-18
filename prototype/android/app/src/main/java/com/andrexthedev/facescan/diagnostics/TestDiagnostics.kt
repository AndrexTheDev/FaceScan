package com.andrexthedev.facescan.diagnostics

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.andrexthedev.facescan.model.FaceModel
import com.andrexthedev.facescan.capture.CalibrationAvailability

/** Nur aggregierte technische Werte; keine Bilddaten, Landmarks, Namen oder Geräte-IDs. */
class TestDiagnostics {
    private var modelState = "nicht begonnen"
    private var modelError = "-"
    private var cameraError = "-"
    private var inferenceError = "-"
    private var geometryFixture = "nicht ausgeführt"
    private var frames = 0L
    private var processed = 0L
    private var faces = 0L
    private var noFaces = 0L
    private var totalMs = 0L
    private var maxMs = 0L
    private var frameDescription = "-"
    private val challenges = ChallengeTracker()
    private val scanEvents = ScanEventCounters()
    private var selfTests: DeviceSelfTest.Results? = null
    private var calibration = CalibrationAvailability.UNKNOWN

    @Synchronized fun model(state: String, error: String = "-") { modelState = state; modelError = error }
    @Synchronized fun frame(width: Int, height: Int, rotation: Int) {
        frames++
        frameDescription = "${width}x$height, rotation=$rotation"
    }
    @Synchronized internal fun beginChallenge(kind: ChallengeKind, nowMs: Long): Boolean = challenges.begin(kind, nowMs)
    @Synchronized internal fun finishChallenge(offlineStillConfirmed: Boolean = true) = challenges.finish(offlineStillConfirmed)
    @Synchronized internal fun cancelChallenge() = challenges.cancel()
    @Synchronized internal fun challengeResult(kind: ChallengeKind): ChallengeResult = challenges.result(kind)
    @Synchronized fun selfTests(value: DeviceSelfTest.Results) { selfTests = value }
    @Synchronized fun geometryTest(value: String) { geometryFixture = value }
    @Synchronized fun result(found: Boolean, durationMs: Long, frameStartMs: Long) {
        challenges.sample(found, frameStartMs)
        processed++
        if (found) faces++ else noFaces++
        totalMs += durationMs
        maxMs = maxOf(maxMs, durationMs)
    }
    @Synchronized fun calibrationInfo(value: CalibrationAvailability) { calibration = value }
    @Synchronized fun scanEvent(event: ScanEvent) { scanEvents.record(event) }
    @Synchronized fun cameraError(error: String) { cameraError = error }
    @Synchronized fun inferenceError(error: String) { inferenceError = error }

    @Synchronized fun report(context: Context): String {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        val permission = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        val average = if (processed == 0L) "-" else "${totalMs / processed} ms"
        fun challenge(kind: ChallengeKind): String {
            val result = challenges.result(kind)
            val label = when (result.outcome) {
                ChallengeOutcome.NOT_RUN -> "nicht ausgeführt"
                ChallengeOutcome.RUNNING -> "läuft"
                ChallengeOutcome.PASSED -> "bestanden"
                ChallengeOutcome.FAILED -> "fehlgeschlagen"
                ChallengeOutcome.INCONCLUSIVE -> "nicht aussagekräftig"
                ChallengeOutcome.CANCELLED -> "abgebrochen"
            }
            return "$label (${result.matches}/${result.samples} passende Auswertungen)"
        }
        return """
FaceScan Testbericht v2
App: ${info.versionName} (${info.longVersionCode})
Gerät: ${Build.MANUFACTURER} ${Build.MODEL}
Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})
Kamera-Berechtigung: ${if (permission) "erteilt" else "nicht erteilt"}
Modell: $modelState
Modell-SHA256 (Soll): ${FaceModel.SHA256}
Modell-Fehlerklasse: $modelError
Geräte-Selbsttest (Pinhole-Projektion): ${selfTests?.geometry ?: "nicht ausgeführt"}
Geräte-Selbsttest (synthetische Triangulation): ${selfTests?.triangulation ?: "nicht ausgeführt"}
Geräte-Selbsttest (synthetische Berichtszähler): ${selfTests?.reportCounters ?: "nicht ausgeführt"}
Synthetischer M0-Geometrietest: $geometryFixture
Geräte-Selbsttest (synthetisches Scan-Mesh und GLB): ${selfTests?.scanExport ?: "nicht ausgeführt"}
Geräte-Selbsttest (synthetische Bildhinweise): ${selfTests?.imageQuality ?: "nicht ausgeführt"}
Geräte-Selbsttest (synthetisches Foto/UV und OBJ): ${selfTests?.textureExport ?: "nicht ausgeführt"}
Geräte-Selbsttest (synthetische Mehransichten aus kanonischen Ankern): ${selfTests?.multiView ?: "nicht ausgeführt"}
Geräte-Selbsttest (MediaPipe auf Schwarzbild): ${selfTests?.landmarker ?: "nicht ausgeführt"}
Frontkamera laut System: ${selfTests?.frontCamera ?: "nicht geprüft"}
Metadaten der zuletzt gebundenen Kamera: Intrinsics ${calibration.intrinsics.label}; Verzeichnung ${calibration.distortion.label}; Sensorbereich ${calibration.activeArray.label}. Nur statische Angaben, keine validierte Kalibrierung oder Frame-Zuordnung.
Geführter Test: Gesicht im Bild: ${challenge(ChallengeKind.FACE_PRESENT)}
Geführter Test: Gesicht außerhalb: ${challenge(ChallengeKind.FACE_ABSENT)}
Geführter Offline-Test: ${challenge(ChallengeKind.OFFLINE)}
${scanEvents.summary()}
Nicht verfügbar / nicht geprüft: metrisch validierte Genauigkeit, vollständiger Kopf/Haar, Motion-Capture und vollständiger 3D-Flugmodus-Test
Kamera-Fehlerklasse: $cameraError
Erkennungs-Fehler (Phase/Klasse/Code): $inferenceError
Letzter gespeicherter Java-Absturz: ${CrashRecorder.lastCrash(context)}
Kamera-Frames insgesamt: $frames
Letztes Frameformat: $frameDescription
Ausgewertete Frames: $processed
Gesicht erkannt: $faces
Kein Gesicht erkannt: $noFaces
Erkennung inkl. Bildkonvertierung durchschnittlich: $average
Erkennung inkl. Bildkonvertierung maximal: $maxMs ms
Hinweis: Geführte Gesichtstests: mindestens 3 Auswertungen, mindestens 75 % passend. Offline-Test: Flugmodus an und kein internetfähiges Netz laut Android zu Beginn und Ende; keine Netzwerkpaket-Messung. Keine Fotos, Bilddaten oder Gesichtspunkte enthalten. Zähler gelten seit App-Start; der letzte Java-Absturz bleibt lokal gespeichert. Der Bericht enthält keine Gesichtsdaten.
        """.trimIndent()
    }
}

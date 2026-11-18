package com.andrexthedev.facescan.diagnostics

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.andrexthedev.facescan.model.FaceModel

/** Nur aggregierte technische Werte; keine Bilddaten, Landmarks, Namen oder Geräte-IDs. */
class TestDiagnostics {
    private var modelState = "nicht begonnen"
    private var modelError = "-"
    private var cameraError = "-"
    private var inferenceError = "-"
    private var frames = 0L
    private var processed = 0L
    private var faces = 0L
    private var noFaces = 0L
    private var totalMs = 0L
    private var maxMs = 0L
    private var frameDescription = "-"

    @Synchronized fun model(state: String, error: String = "-") { modelState = state; modelError = error }
    @Synchronized fun frame(width: Int, height: Int, rotation: Int) {
        frames++
        frameDescription = "${width}x$height, rotation=$rotation"
    }
    @Synchronized fun result(found: Boolean, durationMs: Long) {
        processed++
        if (found) faces++ else noFaces++
        totalMs += durationMs
        maxMs = maxOf(maxMs, durationMs)
    }
    @Synchronized fun cameraError(error: String) { cameraError = error }
    @Synchronized fun inferenceError(error: String) { inferenceError = error }

    @Synchronized fun report(context: Context): String {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        val permission = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        val average = if (processed == 0L) "-" else "${totalMs / processed} ms"
        return """
FaceScan Testbericht v1
App: ${info.versionName} (${info.longVersionCode})
Gerät: ${Build.MANUFACTURER} ${Build.MODEL}
Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})
Kamera-Berechtigung: ${if (permission) "erteilt" else "nicht erteilt"}
Modell: $modelState
Modell-SHA256 (Soll): ${FaceModel.SHA256}
Modell-Fehlerklasse: $modelError
Kamera-Fehlerklasse: $cameraError
Erkennungs-Fehlerklasse: $inferenceError
Letzter gespeicherter Java-Absturz: ${CrashRecorder.lastCrash(context)}
Kamera-Frames insgesamt: $frames
Letztes Frameformat: $frameDescription
Ausgewertete Frames: $processed
Gesicht erkannt: $faces
Kein Gesicht erkannt: $noFaces
Erkennung inkl. Bildkonvertierung durchschnittlich: $average
Erkennung inkl. Bildkonvertierung maximal: $maxMs ms
Hinweis: Keine Fotos, Bilddaten oder Gesichtspunkte enthalten. Zähler gelten seit App-Start; der letzte Java-Absturz bleibt lokal gespeichert. Kein 3D-Scan.
        """.trimIndent()
    }
}

package com.andrexthedev.facescan.diagnostics

import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import com.andrexthedev.facescan.geometry.CameraModel
import com.andrexthedev.facescan.geometry.Mat3
import com.andrexthedev.facescan.perception.FaceLandmarkerRunner
import com.andrexthedev.facescan.scan.ScanSelfTest
import com.andrexthedev.facescan.scan.TextureSelfTest
import java.io.File
import kotlin.math.abs

/** Kleine Smoke-Tests auf dem Gerät, kein Ersatz für die CI- oder 3D-Ground-Truth-Tests. */
object DeviceSelfTest {
    data class Results(val geometry: String, val landmarker: String, val frontCamera: String, val scanExport: String, val textureExport: String)

    fun run(context: Context, model: File): Results {
        val geometry = try {
            val output = DoubleArray(2)
            CameraModel(1000.0, 1000.0, 320.0, 240.0).project(
                Mat3.identity(), doubleArrayOf(0.0, 0.0, 0.0), doubleArrayOf(10.0, 20.0, 1000.0), output
            )
            if (abs(output[0] - 330.0) < 1e-6 && abs(output[1] - 260.0) < 1e-6) "bestanden" else "fehlgeschlagen"
        } catch (e: Exception) { "fehlgeschlagen:${e.javaClass.simpleName}" }
        val front = try {
            if (context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_FRONT)) "vorhanden" else "nicht gemeldet"
        } catch (e: Exception) { "unbekannt:${e.javaClass.simpleName}" }
        val landmark = try {
            FaceLandmarkerRunner(context, model).use { runner ->
                val bitmap = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888)
                bitmap.eraseColor(Color.BLACK)
                if (runner.hasFace(bitmap, 0, 1)) "fehlgeschlagen:Schwarzbild" else "bestanden"
            }
        } catch (e: Exception) { "fehlgeschlagen:${e.javaClass.simpleName}" }
        catch (e: LinkageError) { "fehlgeschlagen:${e.javaClass.simpleName}" }
        val scan = try { if (ScanSelfTest.run()) "bestanden" else "fehlgeschlagen" }
        catch (e: Exception) { "fehlgeschlagen:${e.javaClass.simpleName}" }
        val texture = try { if (TextureSelfTest.run()) "bestanden" else "fehlgeschlagen" }
        catch (e: Exception) { "fehlgeschlagen:${e.javaClass.simpleName}" }
        return Results(geometry, landmark, front, scan, texture)
    }
}

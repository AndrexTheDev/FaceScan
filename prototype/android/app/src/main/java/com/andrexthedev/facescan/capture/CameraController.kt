package com.andrexthedev.facescan.capture

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Rect
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.util.Range
import android.util.Size
import androidx.camera.camera2.interop.Camera2CameraControl
import androidx.camera.camera2.interop.CaptureRequestOptions
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import java.util.concurrent.Executors

/**
 * Kamera-Steuerung fuer den Scan.
 *
 * Warum CameraX + Camera2-Interop?
 *  - CameraX: Lifecycle, UseCases, Geräte-Kompatibilitaet out of the box
 *  - Camera2-Interop: manuelle Sensorkontrolle (ISO, Verschlusszeit),
 *    LENS_INTRINSIC_CALIBRATION und das Einfrieren von AF/AE/AWB.
 *
 * Ohne manuelle Kontrolle wuerde die Kamera zwischen den Bildern neu fokussieren
 * und die Belichtung aendern -> die Intrinsics/Beleuchtung waeren nicht konstant
 * und die Rekonstruktion wuerde leiden. Das ist einer der haeufigsten Fehler
 * bei Handy-Photogrammetrie.
 */
class CameraController(private val context: Context) {

    private val analyzerExecutor = Executors.newSingleThreadExecutor()
    // bind(), der Provider-Callback und shutdown() laufen auf dem Main-Thread.
    private val session = CameraSessionGuard()
    private var provider: ProcessCameraProvider? = null
    private var preview: Preview? = null
    private var analysis: ImageAnalysis? = null
    private var camera2Control: Camera2CameraControl? = null

    data class Intrinsics(val fx: Double, val fy: Double, val cx: Double, val cy: Double)

    /** Kamera-Parameter einmalig auslesen (vor dem ersten Frame). */
    fun readIntrinsics(lensFacing: Int): Intrinsics {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        for (id in manager.cameraIdList) {
            val chars = manager.getCameraCharacteristics(id)
            if (chars.get(CameraCharacteristics.LENS_FACING) != lensFacing) continue
            val focal = chars.get(CameraCharacteristics.LENS_INTRINSIC_CALIBRATION)
            val principal = chars.get(CameraCharacteristics.LENS_INTRINSIC_CALIBRATION)
            val sensorOrientation = chars.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 0
            // SENSOR_INFO_ACTIVE_ARRAY_SIZE liefert ein Rect, keine Size:
            // den aktiven PixelBEREICH des Sensors, nicht eine Aufloesung.
            // android.util.Size bleibt daneben in Gebrauch (setTargetResolution).
            val activeSize: Rect =
                chars.get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE) ?: Rect()
            if (focal == null || principal == null) continue
            return Intrinsics(
                fx = focal[0].toDouble(),
                fy = focal[1].toDouble(),
                cx = principal[2].toDouble(),
                cy = principal[3].toDouble()
            ).also {
                android.util.Log.d(
                    "FaceScan",
                    "Intrinsics: $it, sensorOrientation=$sensorOrientation, sensor=${activeSize}"
                )
            }
        }
        // Fallback: Schaetzung aus dem Sichtfeld (genuegt fuer M0)
        return Intrinsics(1400.0, 1400.0, 540.0, 960.0)
    }

    /** Friert Fokus, Belichtung und Weissabgleich ein (Pflicht fuer jeden Scan). */
    @SuppressLint("UnsafeOptInUsageError")
    fun lockExposureAndFocus(iso: Int = 200, exposureNs: Long = 8_000_000L) {
        val control = camera2Control ?: return
        val options = CaptureRequestOptions.Builder()
            .setCaptureRequestOption(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_OFF)
            .setCaptureRequestOption(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_OFF)
            .setCaptureRequestOption(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_OFF)
            .setCaptureRequestOption(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_OFF)
            .setCaptureRequestOption(CaptureRequest.SENSOR_SENSITIVITY, iso)
            .setCaptureRequestOption(CaptureRequest.SENSOR_EXPOSURE_TIME, exposureNs)
            .setCaptureRequestOption(
                CaptureRequest.COLOR_CORRECTION_MODE,
                CaptureRequest.COLOR_CORRECTION_MODE_TRANSFORM_MATRIX
            )
            .build()
        val future = control.setCaptureRequestOptions(options)
        future.addListener({
            android.util.Log.d("FaceScan", "Belichtung fixiert: ISO=$iso, ${exposureNs / 1_000_000} ms")
        }, ContextCompat.getMainExecutor(context))
    }

    /** Bindet nur die eigenen Use-Cases und meldet Startfehler an die UI. */
    @SuppressLint("UnsafeOptInUsageError")
    fun bind(
        lifecycleOwner: LifecycleOwner,
        surfaceProvider: Preview.SurfaceProvider,
        onError: () -> Unit,
        onFrame: (androidx.camera.core.ImageProxy) -> Unit
    ) {
        val providerFuture = try {
            ProcessCameraProvider.getInstance(context)
        } catch (e: Exception) {
            android.util.Log.e("FaceScan", "Kamera-Provider konnte nicht erstellt werden", e)
            onError()
            return
        }
        providerFuture.addListener({
            // Der Bildschirm kann verschwinden, bevor der Provider bereit ist.
            session.runIfOpen {
                try {
                    val currentProvider = providerFuture.get()
                    provider = currentProvider
                    val currentPreview = Preview.Builder().build().also {
                        it.setSurfaceProvider(surfaceProvider)
                    }
                    preview = currentPreview
                    val currentAnalysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .setTargetResolution(Size(1080, 1920))
                        .build()
                    analysis = currentAnalysis
                    currentAnalysis.setAnalyzer(analyzerExecutor) { proxy ->
                        try {
                            // Der Empfänger übernimmt die Verantwortung für proxy.close().
                            onFrame(proxy)
                        } catch (e: Exception) {
                            proxy.close()
                            android.util.Log.e("FaceScan", "Frame-Verarbeitung fehlgeschlagen", e)
                        }
                    }
                    val camera = currentProvider.bindToLifecycle(
                        lifecycleOwner, CameraSelector.DEFAULT_FRONT_CAMERA,
                        currentPreview, currentAnalysis
                    )
                    camera2Control = Camera2CameraControl.from(camera.cameraControl)
                    // Die Demo nutzt die automatische Kameraeinstellung. Manuelle
                    // Belichtung benötigt gerätespezifische Prüfung und gehört zu M1.
                } catch (e: Exception) {
                    android.util.Log.e("FaceScan", "Kamera konnte nicht gestartet werden", e)
                    releaseUseCases()
                    onError()
                }
            }
        }, ContextCompat.getMainExecutor(context))
    }

    private fun releaseUseCases() {
        analysis?.clearAnalyzer()
        val useCases = listOfNotNull(preview, analysis)
        try {
            if (useCases.isNotEmpty()) provider?.unbind(*useCases.toTypedArray())
        } catch (e: Exception) {
            android.util.Log.w("FaceScan", "Kamera konnte nicht freigegeben werden", e)
        }
        preview = null
        analysis = null
        provider = null
        camera2Control = null
    }

    /** Verhindert auch ein verspätetes Binden nach Verlassen des Bildschirms. */
    fun shutdown() {
        session.close {
            releaseUseCases()
            analyzerExecutor.shutdown()
        }
    }

    companion object {
        /** Belichtungsreihe fuer die shading-freie Albedo (siehe docs/03). */
        val BRACKET_STOPS = listOf(-1.0, 0.0, 1.0)
        val TARGET_FPS = Range(15, 30)
    }
}

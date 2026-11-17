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
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.Executors
import kotlin.coroutines.resume

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

    @SuppressLint("UnsafeOptInUsageError")
    fun bind(
        lifecycleOwner: LifecycleOwner,
        surfaceProvider: Preview.SurfaceProvider,
        onFrame: (androidx.camera.core.ImageProxy) -> Unit
    ) {
        val providerFuture = ProcessCameraProvider.getInstance(context)
        providerFuture.addListener({
            val provider = providerFuture.get()
            val preview = Preview.Builder().build().also { it.setSurfaceProvider(surfaceProvider) }

            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setTargetResolution(Size(1080, 1920))
                .build()
                .also { it.setAnalyzer(analyzerExecutor) { proxy -> onFrame(proxy) } }

            val camera = provider.bindToLifecycle(
                lifecycleOwner,
                CameraSelector.DEFAULT_FRONT_CAMERA,
                preview,
                analysis
            )
            camera2Control = Camera2CameraControl.from(camera.cameraControl)
            lockExposureAndFocus()
        }, ContextCompat.getMainExecutor(context))
    }

    fun shutdown() {
        analyzerExecutor.shutdown()
    }

    companion object {
        /** Belichtungsreihe fuer die shading-freie Albedo (siehe docs/03). */
        val BRACKET_STOPS = listOf(-1.0, 0.0, 1.0)
        val TARGET_FPS = Range(15, 30)
    }
}

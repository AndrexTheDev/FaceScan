package com.andrexthedev.facescan.capture

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import androidx.camera.camera2.interop.Camera2CameraInfo
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.CameraInfo
import androidx.camera.core.CameraState
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.Observer
import java.util.concurrent.Executors

/** CameraX-Lebenszyklus und Frames. Die App verwendet automatische Kameraeinstellungen. */
class CameraController(private val context: Context) {

    private val analyzerExecutor = Executors.newSingleThreadExecutor()
    // bind(), der Provider-Callback und shutdown() laufen auf dem Main-Thread.
    private val session = CameraSessionGuard()
    private var provider: ProcessCameraProvider? = null
    private var preview: Preview? = null
    private var analysis: ImageAnalysis? = null
    private var cameraInfo: CameraInfo? = null
    private var cameraStateObserver: Observer<CameraState>? = null

    /** Bindet nur die eigenen Use-Cases und meldet Startfehler an die UI. */
    @SuppressLint("UnsafeOptInUsageError")
    fun bind(
        lifecycleOwner: LifecycleOwner,
        surfaceProvider: Preview.SurfaceProvider,
        onError: (String?) -> Unit,
        onCalibrationInfo: (CalibrationAvailability) -> Unit = {},
        onFrame: (androidx.camera.core.ImageProxy) -> Unit
    ) {
        val providerFuture = try {
            ProcessCameraProvider.getInstance(context)
        } catch (e: Exception) {
            android.util.Log.e("FaceScan", "Kamera-Provider konnte nicht erstellt werden", e)
            onError(e.javaClass.simpleName)
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
                    cameraInfo = camera.cameraInfo
                    // Metadaten nur der tatsächlich gebundenen Kamera auswerten;
                    // Fehler dürfen den normalen Scan niemals unterbrechen.
                    val availability = try {
                        val info = Camera2CameraInfo.from(camera.cameraInfo)
                        val active = info.getCameraCharacteristic(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE)
                        CalibrationAvailability.classify(
                            info.getCameraCharacteristic(CameraCharacteristics.LENS_INTRINSIC_CALIBRATION),
                            info.getCameraCharacteristic(CameraCharacteristics.LENS_DISTORTION),
                            active?.width(), active?.height())
                    } catch (_: Exception) { CalibrationAvailability.UNKNOWN }
                    onCalibrationInfo(availability)
                    val observer = Observer<CameraState> { state ->
                        val error = state.error
                        if (error != null) onError("CameraX_${error.code}")
                        else if (state.type == CameraState.Type.OPEN) onError(null)
                    }
                    cameraStateObserver = observer
                    camera.cameraInfo.cameraState.observe(lifecycleOwner, observer)
                    // Die Demo nutzt die automatische Kameraeinstellung. Manuelle
                    // Belichtung benötigt gerätespezifische Prüfung und gehört zu M1.
                } catch (e: Exception) {
                    android.util.Log.e("FaceScan", "Kamera konnte nicht gestartet werden", e)
                    releaseUseCases()
                    onError(e.javaClass.simpleName)
                }
            }
        }, ContextCompat.getMainExecutor(context))
    }

    private fun releaseUseCases() {
        cameraStateObserver?.let { observer -> cameraInfo?.cameraState?.removeObserver(observer) }
        cameraStateObserver = null
        cameraInfo = null
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
    }

    /** Verhindert auch ein verspätetes Binden nach Verlassen des Bildschirms. */
    fun shutdown(onAnalyzerClosed: () -> Unit = {}) {
        session.close {
            releaseUseCases()
            // Nach allen bereits angenommenen Frames auf demselben Thread
            // schließen, auf dem der Landmarker initialisiert wurde.
            analyzerExecutor.execute {
                try {
                    onAnalyzerClosed()
                } catch (e: Exception) {
                    android.util.Log.e("FaceScan", "Analyzer konnte nicht geschlossen werden", e)
                }
            }
            analyzerExecutor.shutdown()
        }
    }

}

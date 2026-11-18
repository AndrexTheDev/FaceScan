package com.andrexthedev.facescan.ui.screen

import android.os.SystemClock
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.capture.CameraController
import com.andrexthedev.facescan.diagnostics.TestDiagnostics
import com.andrexthedev.facescan.perception.FaceFrameAnalyzer
import com.andrexthedev.facescan.perception.FaceStatus
import com.andrexthedev.facescan.scan.FaceFrameBuffer
import com.andrexthedev.facescan.scan.FaceSnapshot
import com.andrexthedev.facescan.scan.FaceSurface
import com.andrexthedev.facescan.scan.FaceSurfaceBuilder
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

/** Zwei ausdrücklich ausgelöste Aufnahmen; Bilddaten werden nicht gespeichert. */
@Composable
fun ScanCaptureScreen(modelFile: File, diagnostics: TestDiagnostics, onCancel: () -> Unit, onComplete: (FaceSurface) -> Unit) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val controller = remember { CameraController(context) }
    val buffer = remember { FaceFrameBuffer() }
    val active = remember { AtomicBoolean(true) }
    val mainExecutor = remember { ContextCompat.getMainExecutor(context) }
    var status by remember { mutableStateOf(FaceStatus.WAITING) }
    var cameraError by remember { mutableStateOf(false) }
    var neutral by remember { mutableStateOf<FaceSnapshot?>(null) }
    var feedback by remember { mutableStateOf("") }
    val analyzer = remember {
        FaceFrameAnalyzer(context.applicationContext, modelFile, diagnostics, active, onFaceFrame = buffer::add) { value ->
            mainExecutor.execute { if (active.get()) status = value }
        }
    }
    DisposableEffect(controller, analyzer) {
        onDispose {
            active.set(false)
            buffer.add(null)
            controller.shutdown { analyzer.close() }
        }
    }
    fun snapshot(): FaceSnapshot? {
        if (cameraError || status != FaceStatus.FACE) return null
        return buffer.snapshot(SystemClock.elapsedRealtime())
    }
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(modifier = Modifier.fillMaxSize(), factory = { ctx ->
            PreviewView(ctx).also { preview ->
                controller.bind(owner, preview.surfaceProvider, onError = { error ->
                    cameraError = error != null
                    if (error != null) diagnostics.cameraError(error)
                }) { analyzer.analyse(it) }
            }
        })
        Surface(Modifier.align(Alignment.BottomCenter).fillMaxWidth(), color = MaterialTheme.colorScheme.surface.copy(alpha = 0.96f)) {
            Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.scan_capture_title), style = MaterialTheme.typography.titleLarge)
                Text(stringResource(R.string.scan_capture_instruction))
                Text(stringResource(when {
                    cameraError -> R.string.camera_error
                    status == FaceStatus.FACE -> R.string.scan_face_ready
                    status == FaceStatus.ERROR || status == FaceStatus.MISSING_MODEL -> R.string.face_error
                    else -> R.string.scan_face_wait
                }))
                if (feedback.isNotEmpty()) Text(feedback, style = MaterialTheme.typography.bodyMedium)
                Button(onClick = {
                    val sample = snapshot()
                    if (sample == null) feedback = context.getString(R.string.scan_wait_samples)
                    else {
                        neutral = sample
                        feedback = context.getString(R.string.scan_neutral_saved, sample.samples, sample.jitterPx)
                    }
                }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_neutral)) }
                Button(onClick = {
                    val base = neutral
                    val expression = snapshot()
                    if (base == null || expression == null) feedback = context.getString(R.string.scan_wait_samples)
                    else {
                        try { onComplete(FaceSurfaceBuilder.build(base, expression)) }
                        catch (_: IllegalArgumentException) { feedback = context.getString(R.string.scan_invalid) }
                    }
                }, enabled = neutral != null, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_expression)) }
                OutlinedButton(onClick = onCancel, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.common_cancel)) }
            }
        }
    }
}

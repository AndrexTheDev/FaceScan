package com.andrexthedev.facescan.ui.screen

import android.os.SystemClock
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
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
import androidx.compose.runtime.LaunchedEffect
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
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.capture.CameraController
import com.andrexthedev.facescan.diagnostics.TestDiagnostics
import com.andrexthedev.facescan.perception.FaceFrameAnalyzer
import com.andrexthedev.facescan.perception.FaceStatus
import com.andrexthedev.facescan.scan.FaceFrameBuffer
import com.andrexthedev.facescan.scan.FaceSnapshot
import com.andrexthedev.facescan.scan.FaceSurface
import com.andrexthedev.facescan.scan.FaceSequenceRecorder
import com.andrexthedev.facescan.scan.NeutralCaptureQuality
import kotlinx.coroutines.delay
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

/** Neutralaufnahme und begrenzte Mimiksequenz; Bilddaten werden nicht gespeichert. */
@Composable
fun ScanCaptureScreen(modelFile: File, diagnostics: TestDiagnostics, onCancel: () -> Unit, onComplete: (FaceSurface) -> Unit) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val controller = remember { CameraController(context) }
    val buffer = remember { FaceFrameBuffer() }
    val recorder = remember { FaceSequenceRecorder() }
    val active = remember { AtomicBoolean(true) }
    val mainExecutor = remember { ContextCompat.getMainExecutor(context) }
    var status by remember { mutableStateOf(FaceStatus.WAITING) }
    var cameraError by remember { mutableStateOf(false) }
    var neutral by remember { mutableStateOf<FaceSnapshot?>(null) }
    var feedback by remember { mutableStateOf("") }
    var recording by remember { mutableStateOf(false) }
    val analyzer = remember {
        FaceFrameAnalyzer(context.applicationContext, modelFile, diagnostics, active, onFaceFrame = { frame -> buffer.add(frame); recorder.add(frame) }) { value ->
            mainExecutor.execute { if (active.get()) status = value }
        }
    }
    DisposableEffect(controller, analyzer) {
        onDispose {
            active.set(false)
            buffer.add(null)
            recorder.cancel()
            controller.shutdown { analyzer.close() }
        }
    }
    DisposableEffect(owner, recorder) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) {
                buffer.add(null)
                neutral = null
                if (recording) {
                    recorder.cancel(); recording = false
                    feedback = context.getString(R.string.scan_record_interrupted)
                }
            }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(recording) {
        if (recording) {
            delay(FaceSequenceRecorder.DURATION_MS + 300)
            val base = neutral
            val result = if (base != null) recorder.finish(SystemClock.elapsedRealtime(), base) else null
            recording = false
            if (result != null) onComplete(result)
            else feedback = context.getString(if (recorder.wasAlignmentFailure()) R.string.scan_alignment_retry else R.string.scan_record_interrupted)
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
                    if (error != null) {
                        diagnostics.cameraError(error)
                        if (recording) { recorder.cancel(); recording = false; feedback = context.getString(R.string.scan_record_interrupted) }
                    }
                }) { analyzer.analyse(it) }
            }
        })
        Surface(Modifier.align(Alignment.BottomCenter).fillMaxWidth().heightIn(max = 360.dp), color = MaterialTheme.colorScheme.surface.copy(alpha = 0.96f)) {
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
                    else if (!NeutralCaptureQuality.isUsable(sample)) {
                        neutral = null
                        feedback = context.getString(R.string.scan_quality_retry)
                    } else {
                        neutral = sample
                        feedback = context.getString(R.string.scan_neutral_saved, sample.samples, sample.jitterPx)
                    }
                }, enabled = !recording, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_neutral)) }
                Button(onClick = {
                    if (snapshot() == null) feedback = context.getString(R.string.scan_wait_samples)
                    else {
                        recorder.start(SystemClock.elapsedRealtime())
                        recording = true
                        feedback = context.getString(R.string.scan_recording)
                    }
                }, enabled = neutral != null && !recording, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_expression)) }
                if (recording) OutlinedButton(onClick = {
                    recorder.cancel(); recording = false; feedback = context.getString(R.string.scan_record_cancelled)
                }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_record_cancel)) }
                OutlinedButton(onClick = onCancel, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.common_cancel)) }
            }
        }
    }
}

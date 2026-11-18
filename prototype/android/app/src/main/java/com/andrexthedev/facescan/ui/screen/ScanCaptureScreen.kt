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
import androidx.compose.runtime.rememberCoroutineScope
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
import com.andrexthedev.facescan.diagnostics.ScanEvent
import com.andrexthedev.facescan.perception.FaceFrameAnalyzer
import com.andrexthedev.facescan.perception.FaceStatus
import com.andrexthedev.facescan.scan.FaceFrameBuffer
import com.andrexthedev.facescan.scan.FaceSnapshot
import com.andrexthedev.facescan.scan.FaceSurface
import com.andrexthedev.facescan.scan.FaceSequenceRecorder
import com.andrexthedev.facescan.scan.FaceTextureRequest
import com.andrexthedev.facescan.scan.FaceTextureMatch
import com.andrexthedev.facescan.scan.NeutralCaptureQuality
import com.andrexthedev.facescan.scan.ImageQuality
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

/** Neutralaufnahme und begrenzte Mimiksequenz; Bilddaten werden nicht gespeichert. */
@Composable
fun ScanCaptureScreen(modelFile: File, diagnostics: TestDiagnostics, onCancel: () -> Unit, onComplete: (FaceSurface) -> Unit) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val controller = remember { CameraController(context) }
    val buffer = remember { FaceFrameBuffer() }
    val recorder = remember { FaceSequenceRecorder() }
    val textureRequest = remember { FaceTextureRequest() }
    val active = remember { AtomicBoolean(true) }
    val hintEpoch = remember { AtomicLong(0) }
    val scope = rememberCoroutineScope()
    val mainExecutor = remember { ContextCompat.getMainExecutor(context) }
    var status by remember { mutableStateOf(FaceStatus.WAITING) }
    var imageHint by remember { mutableStateOf<ImageQuality.Hint?>(null) }
    var frontalHint by remember { mutableStateOf<Boolean?>(null) }
    var cameraError by remember { mutableStateOf(false) }
    var neutral by remember { mutableStateOf<FaceSnapshot?>(null) }
    var feedback by remember { mutableStateOf("") }
    var recording by remember { mutableStateOf(false) }
    var recordingEpoch by remember { mutableStateOf(0L) }
    var processingNeutral by remember { mutableStateOf(false) }
    var pendingTextureId by remember { mutableStateOf(0L) }
    var pendingNeutral by remember { mutableStateOf<FaceSnapshot?>(null) }
    val analyzer = remember {
        FaceFrameAnalyzer(context.applicationContext, modelFile, diagnostics, active,
            onFaceFrame = { frame -> buffer.add(frame); recorder.add(frame) },
            textureRequest = textureRequest,
            onQualityHint = { hint ->
                val epoch = hintEpoch.get()
                mainExecutor.execute {
                    if (active.get() && hintEpoch.get() == epoch && owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) imageHint = hint
                }
            },
            onFrontalHint = { hint ->
                val epoch = hintEpoch.get()
                mainExecutor.execute {
                    if (active.get() && hintEpoch.get() == epoch && owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) frontalHint = hint
                }
            },
            onTexture = { id, texture, photo -> mainExecutor.execute {
                if (active.get() && id == pendingTextureId) {
                    val base = pendingNeutral
                    pendingTextureId = 0L; pendingNeutral = null
                    if (base != null && texture != null && !cameraError && status == FaceStatus.FACE &&
                        owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED) &&
                        buffer.isCurrent(base, SystemClock.elapsedRealtime()) &&
                        SystemClock.elapsedRealtime() - photo.atMs in 0L..2500L && FaceTextureMatch.isConsistent(base, photo)) {
                        neutral = base.copy(texture = texture)
                        diagnostics.scanEvent(ScanEvent.PHOTO_ACCEPTED)
                        feedback = context.getString(R.string.scan_neutral_photo_saved, base.samples, base.jitterPx)
                    } else {
                        diagnostics.scanEvent(ScanEvent.PHOTO_FAILED)
                        feedback = context.getString(R.string.scan_photo_failed)
                    }
                }
            } }) { value ->
            mainExecutor.execute {
                if (active.get()) {
                    status = value
                    if (value == FaceStatus.NO_FACE || value == FaceStatus.ERROR || value == FaceStatus.MISSING_MODEL) {
                        // Nach Verlust niemals ein altes neutrales Gesicht mit einer neuen
                        // Erkennung oder einem anderen Menschen kombinieren.
                        neutral = null
                        if (recording) {
                            recorder.cancel(); recording = false; recordingEpoch++
                            diagnostics.scanEvent(ScanEvent.SEQUENCE_FAILED)
                            feedback = context.getString(R.string.scan_record_interrupted)
                        }
                        if (pendingTextureId != 0L) {
                            textureRequest.cancel(); pendingTextureId = 0L; pendingNeutral = null
                            diagnostics.scanEvent(ScanEvent.PHOTO_FAILED)
                            feedback = context.getString(R.string.scan_photo_failed)
                        }
                    }
                }
            }
        }
    }
    DisposableEffect(controller, analyzer) {
        onDispose {
            active.set(false)
            if (recording) diagnostics.scanEvent(ScanEvent.SEQUENCE_CANCELLED)
            if (pendingTextureId != 0L) diagnostics.scanEvent(ScanEvent.PHOTO_CANCELLED)
            buffer.add(null)
            recorder.cancel()
            textureRequest.cancel()
            controller.shutdown { analyzer.close() }
        }
    }
    DisposableEffect(owner, recorder) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_START || event == Lifecycle.Event.ON_STOP) hintEpoch.incrementAndGet()
            if (event == Lifecycle.Event.ON_STOP) {
                buffer.add(null)
                recordingEpoch++
                imageHint = null; frontalHint = null
                if (pendingTextureId != 0L) diagnostics.scanEvent(ScanEvent.PHOTO_FAILED)
                textureRequest.cancel(); pendingTextureId = 0L; pendingNeutral = null
                neutral = null
                if (recording) {
                    recorder.cancel(); recording = false
                    diagnostics.scanEvent(ScanEvent.SEQUENCE_FAILED)
                    feedback = context.getString(R.string.scan_record_interrupted)
                }
            }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(pendingTextureId) {
        val id = pendingTextureId
        if (id != 0L) {
            delay(5000)
            if (pendingTextureId == id) {
                textureRequest.cancel(); pendingTextureId = 0L; pendingNeutral = null
                diagnostics.scanEvent(ScanEvent.PHOTO_FAILED)
                feedback = context.getString(R.string.scan_photo_failed)
            }
        }
    }
    LaunchedEffect(recording) {
        if (recording) {
            val startedEpoch = recordingEpoch
            delay(FaceSequenceRecorder.DURATION_MS + 300)
            val base = neutral
            val result = if (base != null) withContext(Dispatchers.Default) {
                recorder.finish(SystemClock.elapsedRealtime(), base)
            } else null
            if (!active.get() || startedEpoch != recordingEpoch || !owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) return@LaunchedEffect
            recording = false
            if (result != null && base != null && !cameraError && status == FaceStatus.FACE &&
                buffer.isCurrent(base, SystemClock.elapsedRealtime())) {
                diagnostics.scanEvent(ScanEvent.SEQUENCE_ACCEPTED)
                onComplete(result)
            } else {
                diagnostics.scanEvent(ScanEvent.SEQUENCE_FAILED)
                feedback = context.getString(if (recorder.wasAlignmentFailure()) R.string.scan_alignment_retry else R.string.scan_record_interrupted)
            }
        }
    }
    fun captureNeutral(withPhoto: Boolean) {
        if (processingNeutral) return
        diagnostics.scanEvent(ScanEvent.NEUTRAL_ATTEMPT)
        if (cameraError || status != FaceStatus.FACE) {
            neutral = null
            diagnostics.scanEvent(ScanEvent.NEUTRAL_REJECTED)
            feedback = context.getString(R.string.scan_wait_samples)
            return
        }
        processingNeutral = true
        feedback = context.getString(R.string.scan_processing_neutral)
        scope.launch {
            try {
                val sample = withContext(Dispatchers.Default) { buffer.snapshot(SystemClock.elapsedRealtime()) }
                if (!active.get() || !owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) return@launch
                if (cameraError || status != FaceStatus.FACE || sample == null ||
                    !buffer.isCurrent(sample, SystemClock.elapsedRealtime())) {
                    neutral = null; diagnostics.scanEvent(ScanEvent.NEUTRAL_REJECTED); feedback = context.getString(R.string.scan_wait_samples)
                } else if (!NeutralCaptureQuality.isUsable(sample)) {
                    neutral = null; diagnostics.scanEvent(ScanEvent.NEUTRAL_REJECTED); feedback = context.getString(R.string.scan_quality_retry)
                } else if (withPhoto) {
                    neutral = null; pendingNeutral = sample
                    diagnostics.scanEvent(ScanEvent.NEUTRAL_ACCEPTED)
                    diagnostics.scanEvent(ScanEvent.PHOTO_STARTED)
                    pendingTextureId = textureRequest.request()
                    feedback = context.getString(R.string.scan_photo_wait)
                } else {
                    neutral = sample
                    diagnostics.scanEvent(ScanEvent.NEUTRAL_ACCEPTED)
                    feedback = context.getString(R.string.scan_neutral_saved, sample.samples, sample.jitterPx)
                }
            } finally { processingNeutral = false }
        }
    }
    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(modifier = Modifier.fillMaxSize(), factory = { ctx ->
            PreviewView(ctx).also { preview ->
                controller.bind(owner, preview.surfaceProvider, onError = { error ->
                    cameraError = error != null
                    if (error != null) {
                        diagnostics.cameraError(error)
                        buffer.add(null); neutral = null; imageHint = null; frontalHint = null; recordingEpoch++
                        if (pendingTextureId != 0L) diagnostics.scanEvent(ScanEvent.PHOTO_FAILED)
                        textureRequest.cancel(); pendingTextureId = 0L; pendingNeutral = null
                        if (recording) { recorder.cancel(); recording = false; diagnostics.scanEvent(ScanEvent.SEQUENCE_FAILED); feedback = context.getString(R.string.scan_record_interrupted) }
                    }
                }, onCalibrationInfo = { diagnostics.calibrationInfo(it) }) { analyzer.analyse(it) }
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
                if (!cameraError && status == FaceStatus.FACE) {
                    val hint = imageHint
                    if (hint != null) Text(stringResource(when (hint) {
                        ImageQuality.Hint.TOO_DARK -> R.string.scan_image_dark
                        ImageQuality.Hint.TOO_BRIGHT -> R.string.scan_image_bright
                        ImageQuality.Hint.POSSIBLY_BLURRY -> R.string.scan_image_blur
                        ImageQuality.Hint.NO_WARNING -> R.string.scan_image_no_warning
                    }), style = MaterialTheme.typography.bodyMedium)
                }
                if (!cameraError && status == FaceStatus.FACE && frontalHint == true)
                    Text(stringResource(R.string.scan_frontal_hint), style = MaterialTheme.typography.bodyMedium)
                if (feedback.isNotEmpty()) Text(feedback, style = MaterialTheme.typography.bodyMedium)
                Button(onClick = { captureNeutral(false) },
                    enabled = !recording && !processingNeutral && pendingTextureId == 0L,
                    modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_neutral)) }
                OutlinedButton(onClick = { captureNeutral(true) },
                    enabled = !recording && !processingNeutral && pendingTextureId == 0L,
                    modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_neutral_photo)) }
                if (pendingTextureId != 0L) OutlinedButton(onClick = {
                    textureRequest.cancel(); pendingTextureId = 0L; pendingNeutral = null
                    diagnostics.scanEvent(ScanEvent.PHOTO_CANCELLED)
                    feedback = context.getString(R.string.scan_photo_cancelled)
                }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_photo_cancel)) }
                Button(onClick = {
                    if (cameraError || status != FaceStatus.FACE || neutral?.let { buffer.isCurrent(it, SystemClock.elapsedRealtime()) } != true)
                        feedback = context.getString(R.string.scan_wait_samples)
                    else {
                        recorder.start(SystemClock.elapsedRealtime())
                        diagnostics.scanEvent(ScanEvent.SEQUENCE_STARTED)
                        recordingEpoch++
                        recording = true
                        feedback = context.getString(R.string.scan_recording)
                    }
                }, enabled = neutral != null && !recording && !processingNeutral && pendingTextureId == 0L, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_expression)) }
                if (recording) OutlinedButton(onClick = {
                    recorder.cancel(); recording = false; recordingEpoch++; diagnostics.scanEvent(ScanEvent.SEQUENCE_CANCELLED); feedback = context.getString(R.string.scan_record_cancelled)
                }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_record_cancel)) }
                OutlinedButton(onClick = onCancel, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.common_cancel)) }
            }
        }
    }
}

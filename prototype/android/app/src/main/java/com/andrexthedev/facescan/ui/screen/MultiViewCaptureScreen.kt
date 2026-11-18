package com.andrexthedev.facescan.ui.screen

import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
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
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.capture.CameraController
import com.andrexthedev.facescan.diagnostics.ScanEvent
import com.andrexthedev.facescan.diagnostics.TestDiagnostics
import com.andrexthedev.facescan.perception.FaceFrameAnalyzer
import com.andrexthedev.facescan.perception.FaceStatus
import com.andrexthedev.facescan.scan.FaceMeshRenderer
import com.andrexthedev.facescan.scan.FaceViewRequest
import com.andrexthedev.facescan.scan.ImageQuality
import com.andrexthedev.facescan.scan.MeshExportFormat
import com.andrexthedev.facescan.scan.MultiViewCapture
import com.andrexthedev.facescan.scan.MultiViewQualityGate
import com.andrexthedev.facescan.scan.MultiViewSession
import com.andrexthedev.facescan.scan.encodeExport
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

/**
 * Experimentelle Mehransichten-Aufnahme: Der Nutzer dreht den Kopf leicht nach
 * links und rechts, jede deutlich andere Haltung wird als eigene Ansicht
 * gespeichert. Die Rekonstruktion nutzt kanonische Durchschnittsanker, keine
 * Vermessung der Person; die Skala ist nur so gut wie diese Annahme.
 */
@Composable
fun MultiViewCaptureScreen(
    modelFile: File,
    diagnostics: TestDiagnostics,
    onCancel: () -> Unit,
    onComplete: () -> Unit
) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val controller = remember { CameraController(context) }
    val active = remember { AtomicBoolean(true) }
    val hintEpoch = remember { AtomicLong(0) }
    val viewRequest = remember { FaceViewRequest() }
    // Wird im Analyzer-Thread gelesen; deshalb als atomarer Wert.
    val capturingRef = remember { java.util.concurrent.atomic.AtomicBoolean(false) }
    val lastGuidanceAt = remember { java.util.concurrent.atomic.AtomicLong(0L) }
    val mainExecutor = remember { ContextCompat.getMainExecutor(context) }
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf(FaceStatus.WAITING) }
    var cameraError by remember { mutableStateOf(false) }
    var feedback by remember { mutableStateOf("") }
    var yawSpread by remember { mutableStateOf(0.0) }
    var capturing by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<MultiViewCapture.Result?>(null) }
    // Kein Compose-Status für die Sitzung: Sie wird nur im Analyzer-Thread
    // verändert und über die gespeicherte Anzahl angezeigt.
    var viewCount by remember { mutableIntStateOf(0) }
    // Nur Anzeige der angenommenen Optik; nicht die Kamera-Kalibrierung.
    var pendingIntrinsics by remember { mutableStateOf<MultiViewCapture.Intrinsics?>(null) }
    var sessionReady by remember { mutableStateOf(false) }
    var liveYaw by remember { mutableStateOf<Double?>(null) }
    var nearestDifference by remember { mutableStateOf<Double?>(null) }
    var canCapture by remember { mutableStateOf(false) }

    // Nur eine Sitzung je Bildschirm; Änderungen laufen threadsicher in der Klasse.
    val sessionRef = remember { java.util.concurrent.atomic.AtomicReference<MultiViewSession?>(null) }
    val analyzer = remember {
        FaceFrameAnalyzer(context.applicationContext, modelFile, diagnostics, active,
            viewRequest = viewRequest,
            viewCapture = { frame, hint ->
                FaceViewGeometry.remember(frame.width, frame.height)
                val current = sessionRef.get()
                if (current != null && !capturingRef.get()) {
                    // Grobe Live-Orientierung, gedrosselt; keine Messung.
                    val now = SystemClock.elapsedRealtime()
                    if (now - lastGuidanceAt.get() >= 600L) {
                        lastGuidanceAt.set(now)
                        val guidance = try { current.guidance(frame.points, frame.width, frame.height) }
                            catch (_: Exception) { null }
                        if (guidance != null) mainExecutor.execute {
                            if (active.get()) {
                                liveYaw = guidance.yawDegrees
                                nearestDifference = guidance.nearestDegrees
                                canCapture = guidance.sufficient && viewCount < MultiViewCapture.MAX_VIEWS
                            }
                        }
                    }
                }
                // Zu dunkle oder überstrahlte Aufnahmen werden nicht gespeichert:
                // Sie liefern keine belastbaren Landmarks und würden die
                // Triangulation nur verschlechtern. Unscharfe Aufnahmen werden
                // gespeichert, aber gemeldet.
                val decision = MultiViewQualityGate.decide(hint)
                if (current != null && decision == MultiViewQualityGate.Decision.REJECT) {
                    diagnostics.scanEvent(ScanEvent.MULTIVIEW_VIEW_REJECTED)
                    mainExecutor.execute {
                        if (active.get()) feedback = context.getString(
                            if (hint == ImageQuality.Hint.TOO_BRIGHT) R.string.multiview_reject_bright
                            else R.string.multiview_reject_dark)
                    }
                } else if (current != null) {
                    val outcome = current.add(frame.points, frame.width, frame.height, frame.atMs)
                    val count = current.size()
                    val spread = current.yawSpreadDegrees()
                    mainExecutor.execute {
                        if (active.get()) {
                            viewCount = count
                            yawSpread = spread
                            feedback = when (outcome) {
                                MultiViewSession.AddResult.ACCEPTED ->
                                    if (decision == MultiViewQualityGate.Decision.WARN)
                                        context.getString(R.string.multiview_view_saved_blurry, count)
                                    else context.getString(R.string.multiview_view_saved, count)
                                MultiViewSession.AddResult.INSUFFICIENT_YAW_DIFFERENCE -> context.getString(R.string.multiview_turn_more)
                                MultiViewSession.AddResult.FULL -> context.getString(R.string.multiview_full)
                                MultiViewSession.AddResult.INCONSISTENT_DIMENSIONS -> context.getString(R.string.multiview_failed)
                                MultiViewSession.AddResult.INVALID_VIEW -> context.getString(R.string.multiview_face_missing)
                                MultiViewSession.AddResult.OUT_OF_FRAME_OR_POSE_REJECTED -> context.getString(R.string.multiview_pose_rejected)
                            }
                        }
                    }
                }
                // Sobald ein Frame ausgewertet wurde (angenommen oder
                // verworfen), ist die Aufnahme fertig; der Nutzer muss nicht
                // auf den Timeout warten.
                mainExecutor.execute {
                    if (active.get()) {
                        capturing = false
                        capturingRef.set(false)
                    }
                }
            }
        ) { value ->
            mainExecutor.execute {
                if (active.get()) {
                    status = value
                    if (value == FaceStatus.NO_FACE || value == FaceStatus.ERROR || value == FaceStatus.MISSING_MODEL) {
                        // Ohne Gesicht keine stillen Ansichten aus fremden Frames.
                    }
                }
            }
        }
    }
    DisposableEffect(controller, analyzer) {
        onDispose {
            active.set(false)
            viewRequest.cancel()
            controller.shutdown { analyzer.close() }
        }
    }
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_START || event == Lifecycle.Event.ON_STOP) hintEpoch.incrementAndGet()
            if (event == Lifecycle.Event.ON_STOP) {
                // Ein Hintergrundwechsel beendet die Szene; Ansichten aus zwei
                // Sitzungen dürfen nicht kombiniert werden.
                sessionRef.get()?.clear()
                viewCount = 0
                yawSpread = 0.0
            }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }

    fun captureView() {
        if (capturing) return
        if (cameraError || status != FaceStatus.FACE) {
            feedback = context.getString(R.string.multiview_face_missing)
            return
        }
        capturing = true
        capturingRef.set(true)
        viewRequest.request()
        feedback = context.getString(R.string.multiview_capture_wait)
        scope.launch {
            delay(4200)
            if (viewRequest.isPending()) {
                viewRequest.cancel()
                feedback = context.getString(R.string.multiview_capture_timeout)
            }
            capturing = false
            capturingRef.set(false)
        }
    }

    fun reconstruct() {
        val current = sessionRef.get() ?: return
        if (current.size() < 2) {
            feedback = context.getString(R.string.multiview_need_views)
            return
        }
        feedback = context.getString(R.string.multiview_reconstructing)
        scope.launch {
            val outcome = try {
                withContext(Dispatchers.Default) { current.reconstruct() }
            } catch (e: CancellationException) {
                throw e
            } catch (_: Exception) {
                null
            }
            if (!active.get() || !owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) return@launch
            when (outcome) {
                null -> {
                    diagnostics.scanEvent(ScanEvent.MULTIVIEW_FAILED)
                    feedback = context.getString(R.string.multiview_failed)
                }
                is MultiViewCapture.Outcome.Rejected -> {
                    diagnostics.scanEvent(ScanEvent.MULTIVIEW_FAILED)
                    feedback = context.getString(R.string.multiview_failed)
                }
                is MultiViewCapture.Outcome.Reconstructed -> {
                    diagnostics.scanEvent(ScanEvent.MULTIVIEW_ACCEPTED)
                    result = outcome.result
                }
            }
        }
    }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(modifier = Modifier.fillMaxSize(), factory = { ctx ->
            PreviewView(ctx).also { preview ->
                controller.bind(owner, preview.surfaceProvider, onError = { error ->
                    cameraError = error != null
                    if (error != null) {
                        diagnostics.cameraError(error)
                        sessionRef.get()?.clear()
                        active.set(false)
                    }
                }, onCalibrationInfo = { diagnostics.calibrationInfo(it) }, onFrame = { analyzer.analyse(it) })
            }
        })
        Surface(Modifier.align(Alignment.BottomCenter).fillMaxWidth().heightIn(max = 420.dp),
            color = MaterialTheme.colorScheme.surface.copy(alpha = 0.96f)) {
            Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(R.string.multiview_title), style = MaterialTheme.typography.titleLarge)
                Text(stringResource(R.string.multiview_instruction))
                Text(stringResource(R.string.multiview_limitations), style = MaterialTheme.typography.bodyMedium)
                Text(stringResource(R.string.multiview_status,
                    viewCount, MultiViewCapture.MAX_VIEWS, yawSpread))
                val currentYaw = liveYaw
                if (sessionReady && currentYaw != null) {
                    val difference = nearestDifference
                    // Zwei getrennte Texte statt gemischter Formatargumente:
                    // Zahlen und Handlungsanweisung bleiben so eindeutig.
                    Text(if (canCapture) stringResource(R.string.multiview_live_far, currentYaw)
                        else if (difference == null) stringResource(R.string.multiview_live_first, currentYaw)
                        else stringResource(R.string.multiview_live_near, currentYaw, difference),
                        style = MaterialTheme.typography.bodyMedium)
                }
                pendingIntrinsics?.let {
                    Text(stringResource(R.string.multiview_assumed_intrinsics, it.fx),
                        style = MaterialTheme.typography.bodySmall)
                }
                if (!cameraError && status == FaceStatus.FACE && !sessionReady) {
                    OutlinedButton(enabled = status == FaceStatus.FACE, onClick = {
                        // Bildgröße aus dem letzten Frame des Analyzers übernehmen.
                        val geometry = FaceViewGeometry.remembered()
                        if (geometry == null) feedback = context.getString(R.string.multiview_face_missing)
                        else {
                                val prepared = MultiViewCapture.assumedIntrinsics(geometry.first, geometry.second, 60.0)
                            pendingIntrinsics = prepared
                            sessionRef.set(MultiViewSession(prepared))
                            sessionReady = true
                            feedback = context.getString(R.string.multiview_intrinsics_ready)
                        }
                    }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.multiview_prepare)) }
                }
                Button(onClick = { captureView() },
                    enabled = !cameraError && !capturing && status == FaceStatus.FACE && sessionReady &&
                        viewCount < MultiViewCapture.MAX_VIEWS && canCapture,
                    modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.multiview_capture_view)) }
                if (capturing) OutlinedButton(onClick = {
                    viewRequest.cancel(); capturing = false; capturingRef.set(false)
                    feedback = context.getString(R.string.multiview_cancelled)
                }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.multiview_cancel_view)) }
                if (feedback.isNotEmpty()) Text(feedback, style = MaterialTheme.typography.bodyMedium)
                Button(onClick = { reconstruct() },
                    enabled = !capturing && viewCount >= 2 && status == FaceStatus.FACE,
                    modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.multiview_reconstruct)) }
                OutlinedButton(onClick = onCancel, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.common_cancel))
                }
            }
        }
        val ready = result
        if (ready != null) {
            // Exportierbarkeit einmal je Ergebnis prüfen (reine Bytes, kein IO).
            val stored = remember(ready) { MultiViewCapture.writeObjWithHeader(ready) != null }
            Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.surface) {
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(stringResource(R.string.multiview_result_title), style = MaterialTheme.typography.titleLarge)
                    Text(stringResource(R.string.multiview_result_detail,
                        ready.acceptedViews.size, ready.surface.acceptedPoints, ready.surface.skippedTriangles,
                        ready.maxAnchorRmsPixels, ready.intrinsics.fx))
                    val mesh = ready.surface.mesh
                    if (mesh != null) {
                        var previewYaw by remember(mesh) { mutableFloatStateOf(0f) }
                        Canvas(
                            Modifier
                                .fillMaxWidth()
                                .heightIn(min = 220.dp, max = 320.dp)
                                .pointerInput(mesh) {
                                    detectDragGestures { _, drag ->
                                        previewYaw += drag.x * 0.01f
                                    }
                                }
                        ) {
                            drawIntoCanvas { canvas ->
                                // Die Vorschau zeichnet im Canvas-Koordinatensystem.
                                FaceMeshRenderer.drawPartial(
                                    canvas.nativeCanvas, size.width, size.height, mesh, previewYaw)
                            }
                        }
                        Text(stringResource(R.string.multiview_result_preview),
                            style = MaterialTheme.typography.bodySmall)
                        Text(stringResource(R.string.multiview_topology,
                            ready.topology.triangleCount, ready.topology.boundaryEdges,
                            ready.topology.nonManifoldEdges, ready.topology.components,
                            ready.topology.largestComponentTriangles),
                            style = MaterialTheme.typography.bodySmall)
                        // Viele kleine Fragmente sind ein Warnsignal für Ausreißer,
                        // aber kein Beweis für eine falsche Form.
                        if (ready.topology.components > 3)
                            Text(stringResource(R.string.multiview_topology_fragmented),
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.error)
                    }
                    Text(stringResource(R.string.multiview_result_limits), style = MaterialTheme.typography.bodyMedium)
                    if (ready.acceptedViews.count { it.rmsPixels > 2.0 } > 0)
                        Text(stringResource(R.string.multiview_result_weak_pose), style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.error)
                    if (stored) {
                        MeshExportButton(ready, diagnostics, MeshExportFormat.OBJ)
                        MeshExportButton(ready, diagnostics, MeshExportFormat.GLB)
                        Text(stringResource(R.string.multiview_export_glb_note),
                            style = MaterialTheme.typography.bodySmall)
                    } else Text(stringResource(R.string.multiview_failed))
                    OutlinedButton(onClick = { result = null; onCancel() }, modifier = Modifier.fillMaxWidth()) {
                        Text(stringResource(R.string.multiview_close))
                    }
                }
            }
        }
    }
    BackHandler { onCancel() }
}


/** Merkt sich Bildgröße und Diagnosedaten der zuletzt ausgewerteten Ansicht. */
object FaceViewGeometry {
    private val last = java.util.concurrent.atomic.AtomicReference<Pair<Int, Int>?>(null)
    fun remember(width: Int, height: Int) { if (width > 0 && height > 0) last.set(width to height) }
    fun remembered(): Pair<Int, Int>? = last.get()
    fun clear() { last.set(null) }
}

@Composable
private fun MeshExportButton(result: MultiViewCapture.Result, diagnostics: TestDiagnostics,
                             format: MeshExportFormat) {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument(format.mimeType)) { uri ->
        if (uri != null) {
            val data = result.encodeExport(format)
            if (data == null) diagnostics.scanEvent(ScanEvent.EXPORT_FAILED)
            else {
                val written = runCatching {
                    context.contentResolver.openOutputStream(uri)?.use { it.write(data) }
                }.isSuccess
                diagnostics.scanEvent(if (written) ScanEvent.MESH_SAVED else ScanEvent.EXPORT_FAILED)
            }
        } else diagnostics.scanEvent(ScanEvent.EXPORT_CANCELLED)
    }
    Button(onClick = { launcher.launch(format.fileName) }, modifier = Modifier.fillMaxWidth()) {
        Text(stringResource(if (format == MeshExportFormat.OBJ) R.string.multiview_export_obj
            else R.string.multiview_export_glb))
    }
}

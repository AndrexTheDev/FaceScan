package com.andrexthedev.facescan.ui.screen

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import android.os.SystemClock
import java.util.concurrent.atomic.AtomicBoolean
import java.io.File
import kotlinx.coroutines.delay
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.capture.CameraController
import com.andrexthedev.facescan.diagnostics.TestDiagnostics
import com.andrexthedev.facescan.diagnostics.ChallengeKind
import com.andrexthedev.facescan.diagnostics.ChallengeOutcome
import com.andrexthedev.facescan.diagnostics.NetworkState
import com.andrexthedev.facescan.perception.FaceFrameAnalyzer
import com.andrexthedev.facescan.perception.FaceStatus
import com.andrexthedev.facescan.ui.theme.FaceScanColors

/**
 * Aufnahme-Assistent.
 *
 * Kamera-Vorschau mit experimenteller Gesichtserkennung. Es werden noch
 * keine Daten für die spätere 3D-Rekonstruktion gesammelt.
 */
@Composable
fun CaptureScreen(modelFile: File, diagnostics: TestDiagnostics, onCancel: () -> Unit, onReport: () -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val controller = remember { CameraController(context) }

    var cameraError by remember { mutableStateOf(false) }
    var faceStatus by remember { mutableStateOf(FaceStatus.WAITING) }
    var lastObservation by remember { mutableLongStateOf(0L) }
    var challenge by remember { mutableStateOf<ChallengeKind?>(null) }
    var feedback by remember { mutableStateOf("") }
    val active = remember { AtomicBoolean(true) }
    val mainExecutor = remember { ContextCompat.getMainExecutor(context) }
    val analyzer = remember {
        FaceFrameAnalyzer(context.applicationContext, modelFile, diagnostics, active) { status ->
            mainExecutor.execute {
                if (active.get()) {
                    faceStatus = status
                    if (status == FaceStatus.FACE || status == FaceStatus.NO_FACE) {
                        lastObservation = SystemClock.elapsedRealtime()
                    }
                }
            }
        }
    }
    // Alte Erkennungen nicht dauerhaft als aktuell anzeigen, z. B. wenn
    // die Kamera pausiert oder keine Frames mehr liefert.
    LaunchedEffect(faceStatus, lastObservation) {
        if (faceStatus == FaceStatus.FACE || faceStatus == FaceStatus.NO_FACE) {
            delay(2000)
            faceStatus = FaceStatus.WAITING
        }
    }
    LaunchedEffect(challenge) {
        val current = challenge ?: return@LaunchedEffect
        delay(5000)
        diagnostics.finishChallenge(current != ChallengeKind.OFFLINE || NetworkState.airplaneWithoutInternetNetwork(context))
        val result = diagnostics.challengeResult(current)
        val outcomeId = when (result.outcome) {
            ChallengeOutcome.PASSED -> R.string.challenge_passed
            ChallengeOutcome.FAILED -> R.string.challenge_failed
            else -> R.string.challenge_inconclusive
        }
        feedback = context.getString(R.string.challenge_feedback, context.getString(outcomeId), result.matches, result.samples)
        challenge = null
    }
    fun startChallenge(kind: ChallengeKind) {
        if (kind == ChallengeKind.OFFLINE && !NetworkState.airplaneWithoutInternetNetwork(context)) {
            feedback = context.getString(R.string.challenge_offline_required)
            return
        }
        if (diagnostics.beginChallenge(kind, SystemClock.elapsedRealtime())) {
            feedback = context.getString(R.string.challenge_running)
            challenge = kind
        }
    }
    val ampel = when {
        cameraError || faceStatus == FaceStatus.ERROR -> Ampel.RED
        faceStatus == FaceStatus.FACE -> Ampel.GREEN
        else -> Ampel.YELLOW
    }
    val hint = when {
        cameraError -> R.string.camera_error
        faceStatus == FaceStatus.WAITING -> R.string.face_waiting
        faceStatus == FaceStatus.NO_FACE -> R.string.face_not_found
        faceStatus == FaceStatus.FACE -> R.string.face_found
        faceStatus == FaceStatus.MISSING_MODEL -> R.string.face_model_missing
        else -> R.string.face_error
    }

    DisposableEffect(controller, analyzer) {
        onDispose {
            active.set(false)
            diagnostics.cancelChallenge()
            controller.shutdown { analyzer.close() }
        }
    }

    Box(Modifier.fillMaxSize().background(Color.Black)) {

        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                PreviewView(ctx).also { previewView ->
                    controller.bind(lifecycleOwner, previewView.surfaceProvider, onError = { error -> if (error != null) diagnostics.cameraError(error); cameraError = error != null }, onCalibrationInfo = { diagnostics.calibrationInfo(it) }) { proxy ->
                        analyzer.analyse(proxy)
                    }
                }
            }
        )

        // --- Fuehrungs-Overlay -------------------------------------------
        Canvas(modifier = Modifier.fillMaxSize()) {
            val centerX = size.width / 2f
            val centerY = size.height * 0.42f
            val radius = size.width * 0.34f

            // Ziel-Silhouette (Kopf-Umriss)
            drawOval(
                color = Color.White.copy(alpha = 0.35f),
                topLeft = Offset(centerX - radius * 0.78f, centerY - radius),
                size = Size(radius * 1.56f, radius * 1.9f),
                style = Stroke(width = 3.dp.toPx())
            )
        }

        // --- Ampel --------------------------------------------------------
        Column(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(12.dp)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Surface(
                shape = RoundedCornerShape(16.dp),
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.92f),
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = ampel.symbol,
                        color = ampel.color,
                        fontSize = 26.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.width(12.dp))
                    Text(
                        text = stringResource(hint),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                }
            }

            Spacer(Modifier.height(6.dp))
            Text(stringResource(R.string.challenge_instructions), color = Color.White,
                style = MaterialTheme.typography.bodyMedium)
            if (feedback.isNotEmpty()) {
                Text(feedback, color = Color.White, style = MaterialTheme.typography.bodyMedium)
            }
            val canTest = challenge == null && !cameraError &&
                (faceStatus == FaceStatus.FACE || faceStatus == FaceStatus.NO_FACE)
            Button(onClick = { startChallenge(ChallengeKind.FACE_PRESENT) }, enabled = canTest,
                modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.challenge_face)) }
            Button(onClick = { startChallenge(ChallengeKind.FACE_ABSENT) }, enabled = canTest,
                modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.challenge_empty)) }
            Button(onClick = { startChallenge(ChallengeKind.OFFLINE) }, enabled = canTest,
                modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.challenge_offline)) }

            Spacer(Modifier.height(6.dp))

            Row(Modifier.fillMaxWidth()) {
                Button(
                    onClick = onCancel,
                    modifier = Modifier.weight(1f).height(56.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Color.Transparent,
                        contentColor = FaceScanColors.NightError
                    )
                ) { Text(stringResource(R.string.common_cancel)) }

                Spacer(Modifier.width(12.dp))

                Button(
                    onClick = onReport,
                    modifier = Modifier.weight(1f).height(56.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = FaceScanColors.NightGreen,
                        contentColor = Color.Black
                    )
                ) { Text(stringResource(R.string.report_open)) }
            }
        }
    }
}

enum class Ampel(val symbol: String, val color: Color) {
    GREEN("✔", FaceScanColors.NightGreen),
    YELLOW("!", FaceScanColors.Warn),
    RED("✕", FaceScanColors.NightError)
}

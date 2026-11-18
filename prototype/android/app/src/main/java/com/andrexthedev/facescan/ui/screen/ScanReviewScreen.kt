package com.andrexthedev.facescan.ui.screen

import android.net.Uri
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.scan.FaceSurface
import com.andrexthedev.facescan.scan.FaceTopology
import com.andrexthedev.facescan.scan.GlbWriter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.cos
import kotlin.math.sin

@Composable
fun ScanReviewScreen(surface: FaceSurface, onClose: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var yaw by remember { mutableFloatStateOf(0f) }
    var weight by remember { mutableFloatStateOf(0f) }
    var playing by remember { mutableStateOf(false) }
    var writing by remember { mutableStateOf(false) }
    var feedback by remember { mutableStateOf("") }

    LaunchedEffect(playing) {
        if (playing) {
            val start = SystemClock.elapsedRealtime()
            while (true) {
                val phase = (SystemClock.elapsedRealtime() - start) / 1000.0
                weight = ((1.0 - cos(phase * Math.PI)) / 2.0).toFloat()
                delay(33)
            }
        }
    }
    val save = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("model/gltf-binary")) { uri: Uri? ->
        if (uri != null && !writing) {
            writing = true
            scope.launch {
                try {
                    withContext(Dispatchers.IO) {
                        var complete = false
                        try {
                            val data = GlbWriter.write(surface)
                            val stream = context.contentResolver.openOutputStream(uri, "w") ?: error("No output stream")
                            stream.use { it.write(data) }
                            complete = true
                        } finally {
                            if (!complete) try { context.contentResolver.delete(uri, null, null) } catch (_: Exception) { }
                        }
                    }
                    feedback = context.getString(R.string.scan_export_ok)
                } catch (e: kotlinx.coroutines.CancellationException) {
                    throw e
                } catch (_: Exception) {
                    feedback = context.getString(R.string.scan_export_error)
                } finally {
                    writing = false
                }
            }
        }
    }
    BackHandler { if (!writing) onClose() }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.scan_review_title), style = MaterialTheme.typography.headlineSmall)
        Text(stringResource(R.string.scan_limitations), style = MaterialTheme.typography.bodyMedium)
        Text(stringResource(R.string.scan_jitter, surface.neutralJitterPx, surface.expressionJitterPx))
        Canvas(
            Modifier.fillMaxWidth().height(280.dp).background(Color(0xff10141b))
                .pointerInput(Unit) { detectDragGestures { change, drag -> change.consume(); yaw += drag.x * 0.01f } }
        ) {
            val n = surface.neutral.size / 3
            val xy = Array(n) { Offset.Zero }
            val angleCos = cos(yaw)
            val angleSin = sin(yaw)
            val scale = minOf(size.width, size.height) * 0.27f
            for (i in 0 until n) {
                val x = surface.neutral[3 * i] + (surface.expression[3 * i] - surface.neutral[3 * i]) * weight
                val y = surface.neutral[3 * i + 1] + (surface.expression[3 * i + 1] - surface.neutral[3 * i + 1]) * weight
                val z = surface.neutral[3 * i + 2] + (surface.expression[3 * i + 2] - surface.neutral[3 * i + 2]) * weight
                xy[i] = Offset(size.width * 0.5f + (x * angleCos + z * angleSin) * scale, size.height * 0.36f - y * scale)
            }
            val triangles = FaceTopology.triangles
            for (i in triangles.indices step 3) {
                val a = xy[triangles[i]]; val b = xy[triangles[i + 1]]; val c = xy[triangles[i + 2]]
                drawLine(Color(0xff89d0c1), a, b, 1.dp.toPx())
                drawLine(Color(0xff89d0c1), b, c, 1.dp.toPx())
                drawLine(Color(0xff89d0c1), c, a, 1.dp.toPx())
            }
        }
        Text(stringResource(R.string.scan_preview_hint))
        Slider(value = weight, onValueChange = { playing = false; weight = it })
        Button(onClick = { playing = !playing }, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(if (playing) R.string.scan_pause else R.string.scan_play))
        }
        Button(onClick = {
            try { save.launch("facescan.glb") } catch (_: Exception) { feedback = context.getString(R.string.scan_export_error) }
        }, enabled = !writing, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_export)) }
        if (feedback.isNotEmpty()) Text(feedback)
        OutlinedButton(onClick = onClose, enabled = !writing, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.scan_discard))
        }
    }
}
EOF
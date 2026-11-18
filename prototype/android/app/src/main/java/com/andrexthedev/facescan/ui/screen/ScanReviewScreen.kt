package com.andrexthedev.facescan.ui.screen

import android.net.Uri
import android.graphics.BitmapFactory
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.scan.FaceSurface
import com.andrexthedev.facescan.scan.FaceMeshRenderer
import com.andrexthedev.facescan.scan.FaceSequencePlayback
import com.andrexthedev.facescan.scan.FaceSequenceSmoothing
import com.andrexthedev.facescan.scan.GlbWriter
import com.andrexthedev.facescan.scan.ObjWriter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun ScanReviewScreen(surface: FaceSurface, onClose: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var yaw by remember { mutableFloatStateOf(0f) }
    var weight by remember { mutableFloatStateOf(0f) }
    var playing by remember { mutableStateOf(false) }
    var smoothing by remember { mutableStateOf(false) }
    val selectedSurface = remember(surface, smoothing) {
        if (smoothing) FaceSequenceSmoothing.smooth(surface) else surface
    }
    var writing by remember { mutableStateOf(false) }
    var feedback by remember { mutableStateOf("") }

    LaunchedEffect(playing) {
        if (playing) {
            val duration = surface.keyframes().last().seconds
            val start = SystemClock.elapsedRealtime() - (weight * duration * 1000).toLong()
            while (true) {
                weight = (((SystemClock.elapsedRealtime() - start) / 1000f) % duration) / duration
                delay(33)
            }
        }
    }
    fun export(uri: Uri?, obj: Boolean) {
        if (uri == null || writing) return
        writing = true
        // Vorschau und Export verwenden denselben Stand, auch bei späterer UI-Änderung.
        val exportSurface = selectedSurface
        scope.launch {
            try {
                withContext(Dispatchers.IO) {
                    val data = if (obj) ObjWriter.write(exportSurface) else GlbWriter.write(exportSurface)
                    val stream = context.contentResolver.openOutputStream(uri, "w") ?: error("No output stream")
                    stream.use { it.write(data) }
                }
                feedback = context.getString(if (obj) R.string.scan_obj_ok else R.string.scan_export_ok)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (_: Exception) {
                feedback = context.getString(R.string.scan_export_error)
            } finally { writing = false }
        }
    }
    val save = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("model/gltf-binary")) { uri: Uri? -> export(uri, false) }
    val saveObj = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("model/obj")) { uri: Uri? -> export(uri, true) }
    val textureBitmap = remember(surface.texture) {
        surface.texture?.jpeg?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
    }
    BackHandler { if (!writing) onClose() }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.scan_review_title), style = MaterialTheme.typography.headlineSmall)
        Text(stringResource(R.string.scan_limitations), style = MaterialTheme.typography.bodyMedium)
        Text(stringResource(R.string.scan_jitter_neutral, surface.neutralJitterPx))
        surface.neutralFusionAnchorRms?.let { Text(stringResource(R.string.scan_neutral_fusion, surface.neutralSamples, it)) }
        surface.maxAnchorRms?.let { Text(stringResource(R.string.scan_alignment_residual, it)) }
        Text(stringResource(R.string.scan_sequence_info, surface.keyframes().size - 1, surface.keyframes().last().seconds))
        Canvas(
            Modifier.fillMaxWidth().height(280.dp).background(Color(0xff10141b))
                .pointerInput(Unit) { detectDragGestures { change, drag -> change.consume(); yaw += drag.x * 0.01f } }
        ) {
            val points = FaceSequencePlayback.sample(selectedSurface, weight * selectedSurface.keyframes().last().seconds)
            drawIntoCanvas { canvas ->
                FaceMeshRenderer.draw(canvas.nativeCanvas, size.width, size.height, points, yaw, surface.texture, textureBitmap)
            }
        }
        Text(stringResource(R.string.scan_preview_hint))
        if (textureBitmap != null) {
            Text(stringResource(R.string.scan_texture_preview))
            Image(bitmap = textureBitmap.asImageBitmap(), contentDescription = stringResource(R.string.scan_texture_description),
                modifier = Modifier.fillMaxWidth().height(180.dp))
        }
        Row {
            Checkbox(checked = smoothing, onCheckedChange = { smoothing = it }, enabled = !writing)
            Text(stringResource(R.string.scan_smoothing))
        }
        if (smoothing) Text(stringResource(R.string.scan_smoothing_warning), style = MaterialTheme.typography.bodySmall)
        Slider(value = weight, onValueChange = { playing = false; weight = it })
        Button(onClick = { playing = !playing }, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(if (playing) R.string.scan_pause else R.string.scan_play))
        }
        Button(onClick = {
            try { save.launch("facescan.glb") } catch (_: Exception) { feedback = context.getString(R.string.scan_export_error) }
        }, enabled = !writing, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_export)) }
        OutlinedButton(onClick = {
            try { saveObj.launch("facescan-neutral.obj") } catch (_: Exception) { feedback = context.getString(R.string.scan_export_error) }
        }, enabled = !writing, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.scan_export_obj)) }
        if (feedback.isNotEmpty()) Text(feedback)
        OutlinedButton(onClick = onClose, enabled = !writing, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.scan_discard))
        }
    }
}

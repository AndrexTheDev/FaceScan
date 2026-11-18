package com.andrexthedev.facescan.ui.screen

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.andrexthedev.facescan.R

/** Nur die Kamera-Vorschau ist geschützt; der Rest der App bleibt zugänglich. */
@Composable
fun CameraPermissionGate(onCancel: () -> Unit, content: @Composable () -> Unit) {
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    fun hasPermission() = ContextCompat.checkSelfPermission(
        context, Manifest.permission.CAMERA
    ) == PackageManager.PERMISSION_GRANTED

    var granted by remember { mutableStateOf(hasPermission()) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        // Android ist die Quelle der Wahrheit, auch nach einer Rückkehr aus den Einstellungen.
        granted = hasPermission()
    }
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) granted = hasPermission()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }

    if (granted) {
        content()
    } else {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text(stringResource(R.string.camera_permission_title), style = MaterialTheme.typography.headlineSmall)
            Text(stringResource(R.string.camera_permission_explanation), style = MaterialTheme.typography.bodyLarge)
            Button(onClick = { launcher.launch(Manifest.permission.CAMERA) }, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.camera_permission_request))
            }
            Text(stringResource(R.string.camera_permission_settings_hint), style = MaterialTheme.typography.bodyMedium)
            OutlinedButton(
                onClick = {
                    context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                        data = Uri.fromParts("package", context.packageName, null)
                    })
                },
                modifier = Modifier.fillMaxWidth()
            ) { Text(stringResource(R.string.camera_permission_settings)) }
            OutlinedButton(onClick = onCancel, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.common_cancel))
            }
        }
    }
}

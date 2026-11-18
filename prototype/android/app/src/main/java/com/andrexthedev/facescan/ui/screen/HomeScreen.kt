package com.andrexthedev.facescan.ui.screen

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.model.ModelState
import com.andrexthedev.facescan.geometry.GeometryRunState
import com.andrexthedev.facescan.diagnostics.DeviceSelfTest

@Composable
fun HomeScreen(state: ModelState, selfTests: DeviceSelfTest.Results?, geometryState: GeometryRunState, onGeometryTest: () -> Unit, onRetry: () -> Unit, onStart: () -> Unit, onReport: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(stringResource(R.string.app_name), style = MaterialTheme.typography.headlineMedium)
        Text(stringResource(R.string.testapp_description), style = MaterialTheme.typography.bodyLarge)
        Text(stringResource(R.string.model_network_notice), style = MaterialTheme.typography.bodyMedium)
        when (state) {
            ModelState.Loading -> {
                CircularProgressIndicator()
                Text(stringResource(R.string.model_downloading))
            }
            is ModelState.Ready -> {
                Text(stringResource(R.string.model_ready))
                selfTests?.let {
                    Text(stringResource(R.string.selftest_summary, it.geometry, it.landmarker, it.frontCamera))
                }
                Text(stringResource(R.string.test_instructions))
            }
            ModelState.Failed -> {
                Text(stringResource(R.string.model_failed), color = MaterialTheme.colorScheme.error)
                OutlinedButton(onClick = onRetry, modifier = Modifier.fillMaxWidth()) {
                    Text(stringResource(R.string.model_retry))
                }
            }
        }
        val geometryLabel = when (geometryState) {
            GeometryRunState.NOT_RUN -> R.string.geometry_not_run
            GeometryRunState.RUNNING -> R.string.geometry_running
            GeometryRunState.PASSED -> R.string.geometry_passed
            GeometryRunState.FAILED -> R.string.geometry_failed
        }
        Text(stringResource(geometryLabel))
        OutlinedButton(onClick = onGeometryTest, enabled = geometryState != GeometryRunState.RUNNING && state !is ModelState.Loading,
            modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.geometry_start)) }
        Button(onClick = onStart, enabled = state is ModelState.Ready && geometryState != GeometryRunState.RUNNING, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.test_start))
        }
        OutlinedButton(onClick = onReport, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.report_open))
        }
        Text(stringResource(R.string.report_privacy), style = MaterialTheme.typography.bodyMedium)
    }
}

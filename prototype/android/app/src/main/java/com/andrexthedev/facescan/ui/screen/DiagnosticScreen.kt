package com.andrexthedev.facescan.ui.screen

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.unit.dp
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.diagnostics.TestDiagnostics

@Composable
fun DiagnosticScreen(diagnostics: TestDiagnostics, onBack: () -> Unit) {
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    var copied by remember { mutableStateOf(false) }
    // Vorschau und geteilter Inhalt sind identisch; beim erneuten Öffnen aktualisiert.
    val report = remember { diagnostics.report(context) }
    val chooserTitle = stringResource(R.string.report_share)
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(stringResource(R.string.report_title), style = MaterialTheme.typography.headlineSmall)
        Text(stringResource(R.string.report_privacy))
        SelectionContainer { Text(report, style = MaterialTheme.typography.bodyMedium) }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { clipboard.setText(AnnotatedString(report)); copied = true }, modifier = Modifier.weight(1f)) {
                Text(stringResource(R.string.report_copy))
            }
            Button(onClick = {
                val intent = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, report)
                context.startActivity(Intent.createChooser(intent, chooserTitle))
            }, modifier = Modifier.weight(1f)) { Text(chooserTitle) }
        }
        if (copied) Text(stringResource(R.string.report_copied))
        OutlinedButton(onClick = onBack, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.report_back)) }
    }
}

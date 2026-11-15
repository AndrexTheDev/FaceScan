package com.andrexthedev.facescan.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.ui.theme.FaceScanColors
import kotlinx.coroutines.delay

/**
 * Verarbeitung: Fortschritt ist sichtbar UND ehrlich (Stufenname, Prozent,
 * Restzeit, "Was passiert hier?"). Abbrechen ist jederzeit moeglich.
 *
 * Die Stufenliste entspricht der Pipeline aus docs/03 (hier auf M0 gekuerzt).
 */
private val STAGES = listOf(
    R.string.stage_perception,
    R.string.stage_calibration,
    R.string.stage_coarse_fit,
    R.string.stage_refine
)

@Composable
fun ProcessingScreen(onDone: () -> Unit, onCancel: () -> Unit) {
    var stage by remember { mutableIntStateOf(0) }
    var progress by remember { mutableFloatStateOf(0f) }

    LaunchedEffect(Unit) {
        // M0: simulierte Stufen (die echte Pipeline folgt in M1 mit echten
        // Fortschritts-Callbacks je Stufe und Thermik-Drosselung).
        for (i in STAGES.indices) {
            stage = i
            for (p in 0..100 step 10) {
                progress = p / 100f
                delay(120)
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(28.dp))
        Text(
            text = stringResource(R.string.processing_title),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.processing_subtitle),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Spacer(Modifier.height(36.dp))

        Surface(
            shape = RoundedCornerShape(20.dp),
            color = MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(Modifier.padding(20.dp)) {
                Text(
                    text = stringResource(STAGES[stage]),
                    fontSize = 18.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Spacer(Modifier.height(14.dp))
                // Bewusst die ALTE, in jeder Material3-Version vorhandene
                // Signatur (progress: Float). Die neuere Lambda-Variante
                // (progress = { ... }) gibt es erst ab Material3 1.7 – und
                // dieses Projekt muss mit dem ersten Gradle-Durchlauf
                // uebersetzbar sein, ohne dass wir hier die BOM-Version raten.
                LinearProgressIndicator(
                    progress = progress,
                    modifier = Modifier.fillMaxWidth().height(10.dp),
                    color = FaceScanColors.JamaicaGold
                )
                Spacer(Modifier.height(10.dp))
                Text(
                    text = "${stage + 1} / ${STAGES.size}  ·  ${(progress * 100).toInt()} %",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        Spacer(Modifier.height(16.dp))
        Text(
            text = stringResource(R.string.processing_offline_note),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Spacer(Modifier.weight(1f))

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = onCancel,
                modifier = Modifier.weight(1f).height(56.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color.Transparent,
                    contentColor = FaceScanColors.NightError
                )
            ) { Text(stringResource(R.string.common_cancel)) }
            Button(
                onClick = onDone,
                modifier = Modifier.weight(1f).height(56.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = FaceScanColors.JamaicaGreen,
                    contentColor = Color.Black
                )
            ) { Text(stringResource(R.string.processing_continue)) }
        }
    }
}

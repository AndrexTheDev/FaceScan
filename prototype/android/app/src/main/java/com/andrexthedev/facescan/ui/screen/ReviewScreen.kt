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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.pipeline.QualityReport
import com.andrexthedev.facescan.ui.theme.FaceScanColors

/**
 * Ergebnis-Ansicht: Qualitaetsbericht als Ampeln mit Laien-Text.
 * Jede Ampel hat ein Symbol UND einen Satz – nie nur Farbe (docs/07).
 */
@Composable
fun ReviewScreen(onBackHome: () -> Unit) {
    val report = demoReport()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(20.dp)
    ) {
        Text(
            text = stringResource(R.string.review_title),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.onBackground
        )
        Spacer(Modifier.height(14.dp))

        LightRow(report.formtreue)
        LightRow(report.detail)
        LightRow(report.haar)
        LightRow(report.abdeckung)
        LightRow(report.textur)

        if (report.tips.isNotEmpty()) {
            Spacer(Modifier.height(14.dp))
            Surface(
                shape = RoundedCornerShape(16.dp),
                color = MaterialTheme.colorScheme.surfaceVariant,
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.review_tips_title),
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Spacer(Modifier.height(8.dp))
                    report.tips.forEach { tip ->
                        Text("• $tip", style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }

        Spacer(Modifier.weight(1f))

        Button(
            onClick = { /* TODO M3: Animieren */ },
            modifier = Modifier.fillMaxWidth().height(58.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = FaceScanColors.JamaicaGold,
                contentColor = Color.Black
            )
        ) { Text(stringResource(R.string.review_animate), fontSize = 17.sp, fontWeight = FontWeight.Bold) }

        Spacer(Modifier.height(10.dp))

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(
                onClick = { /* TODO M4: Export */ },
                modifier = Modifier.weight(1f).height(54.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = FaceScanColors.JamaicaGreen,
                    contentColor = Color.Black
                )
            ) { Text(stringResource(R.string.review_export)) }
            Button(
                onClick = onBackHome,
                modifier = Modifier.weight(1f).height(54.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Color.Transparent,
                    contentColor = MaterialTheme.colorScheme.onSurface
                )
            ) { Text(stringResource(R.string.review_done)) }
        }
    }
}

@Composable
private fun LightRow(light: QualityReport.Light) {
    val color = when (light.state) {
        QualityReport.State.GREEN -> FaceScanColors.NightGreen
        QualityReport.State.YELLOW -> FaceScanColors.Warn
        QualityReport.State.RED -> FaceScanColors.NightError
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(light.symbol, color = color, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(light.headlineDe, style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onBackground)
            Text(light.detailDe, style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private val QualityReport.Light.symbol: String
    get() = when (state) {
        QualityReport.State.GREEN -> "✔"
        QualityReport.State.YELLOW -> "!"
        QualityReport.State.RED -> "✕"
    }

/** Platzhalter bis der echte Bericht aus der Pipeline kommt (M1). */
private fun demoReport(): QualityReport = com.andrexthedev.facescan.pipeline.buildReport(
    reprojectionPx = 1.4,
    geometryMm = 0.8,
    coverage = 0.95,
    hairCoverage = 0.72,
    textureHoles = 0.005
)

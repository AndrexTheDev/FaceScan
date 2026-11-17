package com.andrexthedev.facescan.ui.screen

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.andrexthedev.facescan.R
import com.andrexthedev.facescan.ui.theme.AppThemeMode
import com.andrexthedev.facescan.ui.theme.FaceScanColors

/**
 * Startbildschirm. Ein Ziel, ein Knopf.
 * Der goldene Button ist die groesste und einzige "Hauptaktion" – Regel 2.
 */
@Composable
fun HomeScreen(
    onStartScan: () -> Unit,
    onToggleTheme: () -> Unit,
    themeMode: AppThemeMode
) {
    val isDay = themeMode == AppThemeMode.DAY
    val gold = if (isDay) FaceScanColors.DayGoldFill else FaceScanColors.NightGold
    val green = if (isDay) FaceScanColors.DayGreen else FaceScanColors.NightGreen
    val onGold = Color.Black

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Image(
                painter = painterResource(R.drawable.ic_facescan_logo),
                contentDescription = null,
                modifier = Modifier.size(34.dp)
            )
            Spacer(Modifier.width(10.dp))
            Text(
                text = stringResource(R.string.app_name),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.weight(1f)
            )
            OutlinedButton(onClick = onToggleTheme, modifier = Modifier.height(44.dp)) {
                Text(if (isDay) "☾" else "☀", fontSize = 18.sp)
            }
        }

        Spacer(Modifier.height(18.dp))

        // Platzhalter fuer die 3D-Vorschau (ab M1 das echte Modell)
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(260.dp)
                .clip(RoundedCornerShape(24.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant),
            contentAlignment = Alignment.Center
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Image(
                    painter = painterResource(R.drawable.ic_facescan_logo),
                    contentDescription = null,
                    modifier = Modifier.size(96.dp)
                )
                Spacer(Modifier.height(12.dp))
                Text(
                    text = stringResource(R.string.home_empty),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.padding(horizontal = 24.dp)
                )
            }
        }

        Spacer(Modifier.height(16.dp))

        Surface(
            shape = RoundedCornerShape(14.dp),
            color = MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.padding(14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("●", color = green, fontSize = 20.sp)
                Spacer(Modifier.width(10.dp))
                Text(
                    text = stringResource(R.string.home_offline_badge),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        Spacer(Modifier.weight(1f))

        // stringResource() ist selbst @Composable. Innerhalb von
        // .semantics { } gilt das NICHT -- dieser Lambda-Rumpf ist kein
        // Kompositions-Kontext, sondern ein SemanticsPropertyReceiver.
        // Der Text muss deshalb VORHER geholt werden.
        val startScanBeschreibung = stringResource(R.string.cd_start_scan)
        Button(
            onClick = onStartScan,
            modifier = Modifier
                .fillMaxWidth()
                .height(64.dp)
                .semantics { contentDescription = startScanBeschreibung },
            colors = ButtonDefaults.buttonColors(containerColor = gold, contentColor = onGold),
            shape = RoundedCornerShape(18.dp)
        ) {
            Text(
                text = stringResource(R.string.home_start_scan),
                fontSize = 19.sp,
                fontWeight = FontWeight.Bold
            )
        }

        Spacer(Modifier.height(10.dp))

        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            OutlinedButton(
                onClick = { /* TODO M1: Projekt oeffnen */ },
                modifier = Modifier.weight(1f).height(52.dp)
            ) { Text(stringResource(R.string.home_open_project)) }
            OutlinedButton(
                onClick = { /* TODO M6: Einstellungen */ },
                modifier = Modifier.weight(1f).height(52.dp)
            ) { Text(stringResource(R.string.home_settings)) }
        }
    }
}

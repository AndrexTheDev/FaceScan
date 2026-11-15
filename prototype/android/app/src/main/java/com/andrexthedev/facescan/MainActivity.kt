package com.andrexthedev.facescan

import android.Manifest
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.andrexthedev.facescan.ui.FaceScanApp

/**
 * Einstiegspunkt.
 *
 * Wichtig fuer den Play Store: die Kamera-Erklaerung muss IN der App, VOR der
 * Berechtigung und ALLEINSTEHEND erscheinen (Prominent Disclosure, docs/09).
 * Bis der Onboarding-Flow (M1) steht, passiert das hier ueber einen
 * einfachen Zustand, der den weiteren Aufbau blockiert.
 */
class MainActivity : ComponentActivity() {

    private var cameraGranted by mutableStateOf(false)

    private val requestCamera = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> cameraGranted = granted }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            LaunchedEffect(Unit) {
                if (!cameraGranted) requestCamera.launch(Manifest.permission.CAMERA)
            }
            FaceScanApp()
        }
    }
}

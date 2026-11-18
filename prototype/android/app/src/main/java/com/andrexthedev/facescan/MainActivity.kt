package com.andrexthedev.facescan

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.andrexthedev.facescan.ui.FaceScanApp

/** Die Kameraerlaubnis wird erst beim Öffnen der Aufnahme erfragt. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { FaceScanApp() }
    }
}

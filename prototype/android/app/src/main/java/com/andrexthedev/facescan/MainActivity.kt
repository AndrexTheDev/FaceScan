package com.andrexthedev.facescan

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.andrexthedev.facescan.ui.FaceScanApp
import com.andrexthedev.facescan.diagnostics.CrashRecorder

/** Die Kameraerlaubnis wird erst beim Öffnen der Aufnahme erfragt. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        CrashRecorder.install(applicationContext)
        enableEdgeToEdge()
        setContent { FaceScanApp() }
    }
}

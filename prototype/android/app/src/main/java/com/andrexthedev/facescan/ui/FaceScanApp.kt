package com.andrexthedev.facescan.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.andrexthedev.facescan.diagnostics.TestDiagnostics
import com.andrexthedev.facescan.diagnostics.DeviceSelfTest
import com.andrexthedev.facescan.model.ModelInstaller
import com.andrexthedev.facescan.model.ModelHttpException
import com.andrexthedev.facescan.model.ModelState
import com.andrexthedev.facescan.ui.screen.CameraPermissionGate
import com.andrexthedev.facescan.ui.screen.CaptureScreen
import com.andrexthedev.facescan.ui.screen.DiagnosticScreen
import com.andrexthedev.facescan.ui.screen.HomeScreen
import com.andrexthedev.facescan.ui.theme.FaceScanTheme
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

@Composable
fun FaceScanApp() {
    val context = LocalContext.current.applicationContext
    val diagnostics = remember { TestDiagnostics() }
    var state by remember { mutableStateOf<ModelState>(ModelState.Loading) }
    var selfTests by remember { mutableStateOf<DeviceSelfTest.Results?>(null) }
    var attempt by remember { mutableIntStateOf(0) }
    val navController = rememberNavController()

    // Nur das Modell wird geladen; sämtliche Code-Abhängigkeiten sind in der APK.
    LaunchedEffect(attempt) {
        state = ModelState.Loading
        diagnostics.model("wird vorbereitet")
        try {
            val file = withContext(Dispatchers.IO) {
                ModelInstaller(File(context.filesDir, "models")).ensureInstalled()
            }
            diagnostics.model("bereit (SHA-256 geprüft)")
            val results = withContext(Dispatchers.Default) { DeviceSelfTest.run(context, file) }
            diagnostics.selfTests(results)
            selfTests = results
            state = ModelState.Ready(file)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            diagnostics.model("fehlgeschlagen", if (e is ModelHttpException) "HTTP_${e.status}" else e.javaClass.simpleName)
            state = ModelState.Failed
        }
    }

    FaceScanTheme {
        NavHost(navController = navController, startDestination = "home") {
            composable("home") {
                HomeScreen(
                    state = state,
                    selfTests = selfTests,
                    onRetry = { attempt++ },
                    onStart = { navController.navigate("capture") },
                    onReport = { navController.navigate("report") }
                )
            }
            composable("capture") {
                val ready = state as? ModelState.Ready
                if (ready != null) {
                    CameraPermissionGate(onCancel = { navController.popBackStack() }) {
                        CaptureScreen(
                            modelFile = ready.file,
                            diagnostics = diagnostics,
                            onCancel = { navController.popBackStack() },
                            onReport = { navController.navigate("report") }
                        )
                    }
                }
            }
            composable("report") {
                DiagnosticScreen(diagnostics) { navController.popBackStack() }
            }
        }
    }
}

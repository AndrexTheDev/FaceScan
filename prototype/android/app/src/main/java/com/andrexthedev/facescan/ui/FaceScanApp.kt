package com.andrexthedev.facescan.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.andrexthedev.facescan.diagnostics.TestDiagnostics
import com.andrexthedev.facescan.diagnostics.DeviceSelfTest
import com.andrexthedev.facescan.geometry.GeometryRunState
import com.andrexthedev.facescan.geometry.GeometrySelfTest
import com.andrexthedev.facescan.model.ModelInstaller
import com.andrexthedev.facescan.model.ModelHttpException
import com.andrexthedev.facescan.model.ModelState
import com.andrexthedev.facescan.ui.screen.CameraPermissionGate
import com.andrexthedev.facescan.ui.screen.CaptureScreen
import com.andrexthedev.facescan.ui.screen.DiagnosticScreen
import com.andrexthedev.facescan.ui.screen.HomeScreen
import com.andrexthedev.facescan.ui.screen.ScanCaptureScreen
import com.andrexthedev.facescan.ui.screen.ScanReviewScreen
import com.andrexthedev.facescan.scan.FaceSurface
import com.andrexthedev.facescan.ui.theme.FaceScanTheme
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.launch
import java.io.File

@Composable
fun FaceScanApp() {
    val context = LocalContext.current.applicationContext
    val diagnostics = remember { TestDiagnostics() }
    var state by remember { mutableStateOf<ModelState>(ModelState.Loading) }
    var selfTests by remember { mutableStateOf<DeviceSelfTest.Results?>(null) }
    var attempt by remember { mutableIntStateOf(0) }
    var geometryState by remember { mutableStateOf(GeometryRunState.NOT_RUN) }
    var faceSurface by remember { mutableStateOf<FaceSurface?>(null) }
    val scope = rememberCoroutineScope()
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
                    geometryState = geometryState,
                    onGeometryTest = {
                        if (geometryState != GeometryRunState.RUNNING) {
                            geometryState = GeometryRunState.RUNNING
                            diagnostics.geometryTest("läuft")
                            scope.launch {
                                try {
                                    val result = withContext(Dispatchers.Default) { GeometrySelfTest.run() }
                                    diagnostics.geometryTest(result.details)
                                    geometryState = if (result.passed) GeometryRunState.PASSED else GeometryRunState.FAILED
                                } catch (e: CancellationException) {
                                    throw e
                                } catch (e: Exception) {
                                    diagnostics.geometryTest("fehlgeschlagen:${e.javaClass.simpleName}")
                                    geometryState = GeometryRunState.FAILED
                                }
                            }
                        }
                    },
                    onRetry = { attempt++ },
                    onStart = { navController.navigate("capture") },
                    onScan = { faceSurface = null; navController.navigate("scan") },
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
            composable("scan") {
                val ready = state as? ModelState.Ready
                if (ready != null) {
                    CameraPermissionGate(onCancel = { navController.popBackStack() }) {
                        ScanCaptureScreen(ready.file, diagnostics,
                            onCancel = { navController.popBackStack() },
                            onComplete = { faceSurface = it; navController.navigate("scan-review") })
                    }
                }
            }
            composable("scan-review") {
                val surface = faceSurface
                if (surface != null) {
                    DisposableEffect(surface) { onDispose { faceSurface = null } }
                    ScanReviewScreen(surface, diagnostics) { navController.popBackStack("home", false) }
                }
            }
            composable("report") {
                DiagnosticScreen(diagnostics) { navController.popBackStack() }
            }
        }
    }
}

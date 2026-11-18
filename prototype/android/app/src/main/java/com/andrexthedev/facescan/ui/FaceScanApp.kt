package com.andrexthedev.facescan.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.andrexthedev.facescan.ui.screen.CameraPermissionGate
import com.andrexthedev.facescan.ui.screen.CaptureScreen
import com.andrexthedev.facescan.ui.screen.HomeScreen
import com.andrexthedev.facescan.ui.screen.ProcessingScreen
import com.andrexthedev.facescan.ui.screen.ReviewScreen
import com.andrexthedev.facescan.ui.theme.AppThemeMode
import com.andrexthedev.facescan.ui.theme.FaceScanTheme

object Route {
    const val HOME = "home"
    const val CAPTURE = "capture"
    const val PROCESSING = "processing"
    const val REVIEW = "review"
}

/**
 * Navigation: bewusst flach und linear. Ein Ziel pro Bildschirm, kein
 * verschachteltes Menue – das ist Regel 1 des UX-Leitfadens (docs/07).
 */
@Composable
fun FaceScanApp() {
    var themeMode by remember { mutableStateOf(AppThemeMode.SYSTEM) }
    val navController = rememberNavController()

    FaceScanTheme(mode = themeMode) {
        NavHost(navController = navController, startDestination = Route.HOME) {
            composable(Route.HOME) {
                HomeScreen(
                    onStartScan = { navController.navigate(Route.CAPTURE) },
                    onToggleTheme = {
                        themeMode = when (themeMode) {
                            AppThemeMode.SYSTEM -> AppThemeMode.NIGHT
                            AppThemeMode.NIGHT -> AppThemeMode.DAY
                            AppThemeMode.DAY -> AppThemeMode.SYSTEM
                        }
                    },
                    themeMode = themeMode
                )
            }
            composable(Route.CAPTURE) {
                CameraPermissionGate(onCancel = { navController.popBackStack() }) {
                    CaptureScreen(
                        onCancel = { navController.popBackStack() },
                        onFinished = { navController.navigate(Route.PROCESSING) }
                    )
                }
            }
            composable(Route.PROCESSING) {
                ProcessingScreen(
                    onDone = { navController.navigate(Route.REVIEW) { popUpTo(Route.HOME) } },
                    onCancel = { navController.popBackStack() }
                )
            }
            composable(Route.REVIEW) {
                ReviewScreen(onBackHome = { navController.popBackStack(Route.HOME, false) })
            }
        }
    }
}

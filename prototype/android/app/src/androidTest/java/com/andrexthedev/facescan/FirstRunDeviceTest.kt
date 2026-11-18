package com.andrexthedev.facescan

import android.content.ClipboardManager
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.andrexthedev.facescan.perception.FaceLandmarkerRunner
import com.andrexthedev.facescan.diagnostics.NetworkState
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Die CI steuert Netzwerk und App-Daten zwischen den einzelnen Tests. */
@RunWith(AndroidJUnit4::class)
class FirstRunDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun text(id: Int) = context.getString(id)

    private fun awaitText(id: Int) {
        val value = text(id)
        compose.waitUntil(timeoutMillis = 120_000) {
            compose.onAllNodesWithText(value).fetchSemanticsNodes().isNotEmpty()
        }
    }

    @Test fun offlineFirstLaunchShowsRetryAndDiagnostic() {
        awaitText(R.string.model_failed)
        compose.onNodeWithText(text(R.string.test_start)).assertIsNotEnabled()
        compose.onNodeWithText(text(R.string.report_open)).performScrollTo().performClick()
        compose.onNodeWithText("Modell: fehlgeschlagen", substring = true).assertExists()
    }

    @Test fun onlineFirstLaunchDownloadsModelAndAllowsReportAndInference() {
        awaitText(R.string.model_ready)
        compose.onNodeWithText(text(R.string.test_start)).assertIsEnabled()
        val model = File(context.filesDir, "models/face_landmarker.task")
        assertTrue("Model must be downloaded to private app storage", model.isFile && model.length() > 0)
        // Unverfängliches schwarzes Testbild: testet das native Modell und die
        // Bitmap-/Rotations-API, nicht die Erkennung eines realen Gesichts.
        FaceLandmarkerRunner(context, model).use { runner ->
            val bitmap = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888)
            bitmap.eraseColor(Color.BLACK)
            assertFalse("A black image must not contain a face", runner.hasFace(bitmap, 90, 1))
        }
        compose.onNodeWithText(text(R.string.report_open)).performScrollTo().performClick()
        compose.onNodeWithText("Modell: bereit", substring = true).assertExists()
        compose.onNodeWithText("Geräte-Selbsttest (Pinhole-Projektion): bestanden", substring = true).assertExists()
        compose.onNodeWithText("Geräte-Selbsttest (synthetische Triangulation): bestanden", substring = true).assertExists()
        compose.onNodeWithText("Geräte-Selbsttest (MediaPipe auf Schwarzbild): bestanden", substring = true).assertExists()
        compose.onNodeWithText("Geräte-Selbsttest (synthetisches Scan-Mesh und GLB): bestanden", substring = true).assertExists()
        compose.onNodeWithText("Geräte-Selbsttest (synthetisches Foto/UV und OBJ): bestanden", substring = true).assertExists()
        compose.onNodeWithText("Geräte-Selbsttest (synthetische Bildhinweise): bestanden", substring = true).assertExists()
        compose.onNodeWithText(text(R.string.report_copy)).performScrollTo().performClick()
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val report = clipboard.primaryClip?.getItemAt(0)?.coerceToText(context)?.toString() ?: ""
        assertTrue(report.contains("FaceScan Testbericht"))
        assertTrue(report.contains("Keine Fotos, Bilddaten oder Gesichtspunkte"))
    }

    @Test fun cameraFramesReachTheLandmarkerAndReport() {
        awaitText(R.string.model_ready)
        compose.onNodeWithText(text(R.string.test_start)).performScrollTo().performClick()
        // Die Emulator-Kamera liefert künstliche Bilder; wir prüfen den
        // Framepfad, nicht die Erkennungsqualität an einem echten Gesicht.
        compose.waitUntil(timeoutMillis = 120_000) {
            listOf(R.string.face_found, R.string.face_not_found, R.string.face_error, R.string.camera_error)
                .any { compose.onAllNodesWithText(text(it)).fetchSemanticsNodes().isNotEmpty() }
        }
        assertTrue("Camera/landmarker reported an error", listOf(R.string.face_found, R.string.face_not_found)
            .any { compose.onAllNodesWithText(text(it)).fetchSemanticsNodes().isNotEmpty() })
        compose.onNodeWithText(text(R.string.challenge_empty)).performScrollTo().performClick()
        awaitChallengeFeedback()
        compose.onNodeWithText(text(R.string.report_open)).performScrollTo().performClick()
        compose.onNodeWithText("Geführter Test: Gesicht außerhalb:", substring = true).assertExists()
        assertTrue("Guided test should be recorded",
            compose.onAllNodesWithText("Geführter Test: Gesicht außerhalb: nicht ausgeführt", substring = true).fetchSemanticsNodes().isEmpty())
        compose.onNodeWithText("Ausgewertete Frames:", substring = true).assertExists()
        assertTrue("Expected at least one analyzed frame",
            compose.onAllNodesWithText("Ausgewertete Frames: 0", substring = true).fetchSemanticsNodes().isEmpty())
    }

    @Test fun scanScreenProcessesEmulatedCameraAndReturns() {
        awaitText(R.string.model_ready)
        compose.onNodeWithText(text(R.string.scan_start)).performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 120_000) {
            listOf(R.string.scan_face_ready, R.string.scan_face_wait, R.string.face_error, R.string.camera_error)
                .any { compose.onAllNodesWithText(text(it)).fetchSemanticsNodes().isNotEmpty() }
        }
        compose.onNodeWithText(text(R.string.scan_expression)).assertIsNotEnabled()
        compose.onNodeWithText(text(R.string.scan_neutral)).performScrollTo().performClick()
        // Der Emulator zeigt kein echtes Gesicht, deshalb darf kein Scan entstehen.
        compose.onNodeWithText(text(R.string.scan_wait_samples)).assertExists()
        compose.onNodeWithText(text(R.string.common_cancel)).performScrollTo().performClick()
        awaitText(R.string.model_ready)
    }

    @Test fun syntheticGeometryTestRunsAndAppearsInReport() {
        awaitText(R.string.model_ready)
        compose.onNodeWithText(text(R.string.geometry_start)).performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 120_000) {
            listOf(R.string.geometry_passed, R.string.geometry_failed)
                .any { compose.onAllNodesWithText(text(it)).fetchSemanticsNodes().isNotEmpty() }
        }
        compose.onNodeWithText(text(R.string.geometry_passed)).assertExists()
        compose.onNodeWithText(text(R.string.report_open)).performScrollTo().performClick()
        compose.onNodeWithText("Synthetischer M0-Geometrietest: F1 bestanden", substring = true).assertExists()
        compose.onNodeWithText("F2 bestanden", substring = true).assertExists()
    }

    @Test fun deniedPermissionShowsDisclosureAndReturn() {
        awaitText(R.string.model_ready)
        compose.onNodeWithText(text(R.string.test_start)).performScrollTo().performClick()
        compose.onNodeWithText(text(R.string.camera_permission_title)).assertExists()
        compose.onNodeWithText(text(R.string.common_cancel)).performClick()
        awaitText(R.string.model_ready)
    }

    @Test fun guidedOfflineTestRecordsResult() {
        assertTrue("Emulator must be in simulated airplane mode without internet", NetworkState.airplaneWithoutInternetNetwork(context))
        awaitText(R.string.model_ready)
        compose.onNodeWithText(text(R.string.test_start)).performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 120_000) {
            listOf(R.string.face_found, R.string.face_not_found)
                .any { compose.onAllNodesWithText(text(it)).fetchSemanticsNodes().isNotEmpty() }
        }
        compose.onNodeWithText(text(R.string.challenge_offline)).performScrollTo().performClick()
        awaitChallengeFeedback()
        compose.onNodeWithText(text(R.string.report_open)).performScrollTo().performClick()
        compose.onNodeWithText("Geführter Offline-Test:", substring = true).assertExists()
        assertTrue("Offline test should be recorded", compose.onAllNodesWithText(
            "Geführter Offline-Test: nicht ausgeführt", substring = true).fetchSemanticsNodes().isEmpty())
    }

    private fun awaitChallengeFeedback() {
        compose.waitUntil(timeoutMillis = 30_000) {
            listOf(R.string.challenge_passed, R.string.challenge_failed, R.string.challenge_inconclusive)
                .any { compose.onAllNodesWithText(text(it) + ":", substring = true).fetchSemanticsNodes().isNotEmpty() }
        }
    }

    @Test fun cachedModelStartsOffline() {
        awaitText(R.string.model_ready)
        compose.onNodeWithText(text(R.string.test_start)).assertIsEnabled()
        compose.onNodeWithText(text(R.string.report_open)).performScrollTo().performClick()
        compose.onNodeWithText("Modell: bereit", substring = true).assertExists()
    }
}

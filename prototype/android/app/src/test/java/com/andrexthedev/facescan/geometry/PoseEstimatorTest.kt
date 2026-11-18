package com.andrexthedev.facescan.geometry

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.sqrt

/**
 * Posenschaetzung gegen synthetische Ground Truth.
 *
 * Diese Tests prüfen nur künstliche metrische Anker und bekannte Kameras.
 * Sie belegen keine reale Kalibrierung oder metrische Gerätegenauigkeit.
 */
class PoseEstimatorTest {

    private val camera = TestData.camera()

    @Test
    fun poseWirdOhneARCoreMetrischRekonstruiert() {
        var worstRotation = 0.0
        var worstTranslation = 0.0
        var sumRotation = 0.0
        var sumTranslation = 0.0

        for (f in 0 until M0Fixtures.N_FRAMES) {
            val (p3, p2) = TestData.visibleCorrespondences(f, M0Fixtures.baseVertices)
            val estimate = PoseEstimator.estimate(camera, p3, p2)
            val truth = TestData.groundTruth(f)
            val rot = estimate.transform.rotationErrorDeg(truth)
            val tra = estimate.transform.translationErrorMm(truth)
            sumRotation += rot
            sumTranslation += tra
            worstRotation = maxOf(worstRotation, rot)
            worstTranslation = maxOf(worstTranslation, tra)
            assertTrue("Frame $f: Rotation $rot deg sollte < 1.0 deg sein", rot < 1.0)
            assertTrue("Frame $f: Translation $tra mm sollte < 5.0 mm sein", tra < 5.0)
            assertTrue("Frame $f: Inlier-Anteil ${estimate.inlierRatio} sollte > 0.9 sein",
                estimate.inlierRatio > 0.9)
        }

        val meanRotation = sumRotation / M0Fixtures.N_FRAMES
        val meanTranslation = sumTranslation / M0Fixtures.N_FRAMES
        // ACHTUNG: expectedRotDegMean / expectedTransMmMean gehoeren zum
        // Multi-Frame-Fit (F2, ModelFitterTest) und sind hier FALSCH. F1 ohne
        // bekannte Identitaet ist groesser -- wer die F2-Zahlen einsetzt,
        // prueft gegen eine Genauigkeit, die dieser Schritt gar nicht liefert.
        assertTrue(
            "Rotationsfehler $meanRotation weicht von ${M0Fixtures.expectedPoseOnlyRotDegMean} ab",
            kotlin.math.abs(meanRotation - M0Fixtures.expectedPoseOnlyRotDegMean) < 0.05)
        assertTrue(
            "Translationsfehler $meanTranslation weicht von ${M0Fixtures.expectedPoseOnlyTransMmMean} ab",
            kotlin.math.abs(meanTranslation - M0Fixtures.expectedPoseOnlyTransMmMean) < 0.05)

        // Schlechtester Einzelfall gegen die Referenz. 10 % Luft, weil der
        // Kotlin-Kern nicht bitgleich mit numpy rechnet; eine echte
        // Verschlechterung faellt trotzdem auf (die alte Schranke lag bei
        // 1.0 deg bzw. 5.0 mm, also beim 2,5-fachen des Referenzwertes).
        assertTrue(
            "Schlechtester Frame: $worstRotation deg, Referenz ${M0Fixtures.expectedPoseOnlyRotDegMax}",
            worstRotation < M0Fixtures.expectedPoseOnlyRotDegMax * 1.1)
        assertTrue(
            "Schlechtester Frame: $worstTranslation mm, Referenz ${M0Fixtures.expectedPoseOnlyTransMmMax}",
            worstTranslation < M0Fixtures.expectedPoseOnlyTransMmMax * 1.1)

        println("[M0] Pose ohne ARCore: rot ${"%.4f".format(meanRotation)} deg " +
            "(max ${"%.4f".format(worstRotation)}), trans ${"%.4f".format(meanTranslation)} mm " +
            "(max ${"%.4f".format(worstTranslation)})")
    }

    @Test
    fun grundwahrheitProjiziertSauberePunkteKorrekt() {
        // Ohne die kuenstlich verrauschten Ausreisser muss die wahre Pose die
        // Landmarks bis auf das eingestreute Rauschen (1 px) reproduzieren.
        val truth = TestData.groundTruth(0)
        val lm = TestData.landmarks(0)
        val vis = TestData.visibility(0)
        val out = TestData.outliers(0)
        val n = M0Fixtures.N_POINTS
        val proj = DoubleArray(2 * n)
        camera.projectAll(truth.rotation, truth.translation, M0Fixtures.baseVertices, proj)

        var sumSq = 0.0
        var count = 0
        for (i in 0 until n) {
            if (vis[i] < 0.5 || out[i] > 0.5) continue
            val du = proj[2 * i] - lm[2 * i]
            val dv = proj[2 * i + 1] - lm[2 * i + 1]
            sumSq += du * du + dv * dv
            count++
        }
        val rms = sqrt(sumSq / count)
        assertTrue("Inlier-RMS der Grundwahrheit ($rms px) sollte < 2.5 px sein", rms < 2.5)
        println("[M0] Grundwahrheit: Inlier-RMS = ${"%.4f".format(rms)} px ($count Punkte)")
    }

    /**
     * WICHTIGSTER EINZELTEST: die Jacobi-Matrix gegen finite Differenzen.
     *
     * Hintergrund: Eine falsche Jacobi-Matrix (falscher Hebelarm der Rotation)
     * laesst das Verfahren trotzdem konvergieren – nur eben systematisch
     * schief. Genau dieser Fehler ist hier einmal passiert und wurde nur durch
     * diesen Vergleich gefunden. Gauss-Newton "funktioniert" auch mit einer
     * falschen Ableitung, deshalb MUSS sie getestet werden.
     */
    @Test
    fun poseJacobianStimmtMitFiniterDifferenzUeberein() {
        val truth = TestData.groundTruth(2)
        val jRow = DoubleArray(12)
        val h = 1e-6
        var worst = 0.0

        for (i in 0 until M0Fixtures.N_POINTS step 7) {
            val x = doubleArrayOf(
                M0Fixtures.baseVertices[3 * i],
                M0Fixtures.baseVertices[3 * i + 1],
                M0Fixtures.baseVertices[3 * i + 2]
            )
            PoseEstimator.poseJacobianRow(camera, x, truth.rotation, truth.translation, jRow)

            for (k in 0 until 6) {
                val omega = DoubleArray(3)
                val dt = DoubleArray(3)
                if (k < 3) omega[k] = h else dt[k - 3] = h

                val rPlus = Mat3.fromRodrigues(omega) * truth.rotation
                val tPlus = doubleArrayOf(
                    truth.translation[0] + dt[0],
                    truth.translation[1] + dt[1],
                    truth.translation[2] + dt[2]
                )
                val rMinus = Mat3.fromRodrigues(doubleArrayOf(-omega[0], -omega[1], -omega[2])) *
                    truth.rotation
                val tMinus = doubleArrayOf(
                    truth.translation[0] - dt[0],
                    truth.translation[1] - dt[1],
                    truth.translation[2] - dt[2]
                )

                val pPlus = DoubleArray(2)
                val pMinus = DoubleArray(2)
                camera.project(rPlus, tPlus, x, pPlus)
                camera.project(rMinus, tMinus, x, pMinus)

                val numericU = (pPlus[0] - pMinus[0]) / (2 * h)
                val numericV = (pPlus[1] - pMinus[1]) / (2 * h)
                val tol = 1e-4 + 1e-6 * kotlin.math.abs(jRow[k])
                worst = maxOf(worst, kotlin.math.abs(numericU - jRow[k]))
                worst = maxOf(worst, kotlin.math.abs(numericV - jRow[6 + k]))
                assertEquals("d u / d pose[$k] an Punkt $i", numericU, jRow[k], tol)
                assertEquals("d v / d pose[$k] an Punkt $i", numericV, jRow[6 + k], tol)
            }
        }
        println("[M0] Jacobi-Check: groesste Abweichung = ${"%.2e".format(worst)}")
    }

    @Test
    fun rodriguesIstUmkehrbar() {
        val omega = doubleArrayOf(0.21, -0.45, 0.13)
        val back = Mat3.toRodrigues(Mat3.fromRodrigues(omega))
        for (i in 0..2) assertEquals(omega[i], back[i], 1e-9)
        val identity = Mat3.toRodrigues(Mat3.identity())
        for (i in 0..2) assertEquals(0.0, identity[i], 1e-9)
    }

    @Test
    fun orthonormalizeErzeugtGueltigeRotation() {
        val noisy = Mat3(doubleArrayOf(1.1, 0.05, -0.02, -0.03, 0.9, 0.07, 0.01, -0.06, 1.05))
        val r = noisy.orthonormalize()
        assertEquals(1.0, r.determinant(), 1e-6)
        val should = r * r.transpose()
        for (i in 0..2) {
            for (j in 0..2) {
                val expected = if (i == j) 1.0 else 0.0
                assertEquals(expected, should[i, j], 1e-6)
            }
        }
    }

    @Test
    fun choleskyLoestKleinesSystem() {
        // (A^T A + I) x = b mit bekannter Loesung
        val a = doubleArrayOf(4.0, 1.0, 1.0, 3.0)
        val b = doubleArrayOf(1.0, 2.0)
        val x = Linalg.solveSpd(a, b, 2)
        requireNotNull(x) { "Cholesky darf hier nicht scheitern" }
        assertEquals(4.0 * x[0] + 1.0 * x[1], 1.0, 1e-10)
        assertEquals(1.0 * x[0] + 3.0 * x[1], 2.0, 1e-10)
    }
}

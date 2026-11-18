package com.andrexthedev.facescan.geometry

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.sqrt

/**
 * Multi-Frame-Fit gegen die Ground Truth.
 *
 * Erwartungswerte stammen aus dem Python-Referenzlauf
 * (prototype/reference/python/run_m0.py) und sind in M0Fixtures.kt
 * festgeschrieben. Zusaetzlich gibt es kotlin_mirror.py: ein reiner
 * Python-Nachbau des Kotlin-Kerns, der dieselben Zahlen reproduziert und damit
 * die Index-Arithmetik unabhaengig bestaetigt.
 */
class ModelFitterTest {

    private val camera = TestData.camera()
    private val model = TestData.model()

    /** Kennzahlen des Fits, berechnet wie in run_m0.py / evaluate(). */
    private data class Metrics(
        val rotDegMean: Double,
        val transMmMean: Double,
        val geometryFrame0Mm: Double,
        val geometryNeutralMm: Double,
        val reproFinalPx: Double,
        val reproFirstPx: Double,
        val inlierRmsPx: Double,
        val alphaCorr: Double
    )

    private fun runFit(): Pair<FitResult, Metrics> {
        val result = ModelFitter.fit(camera, model, TestData.observations())

        val n = model.nVertices
        var sumRot = 0.0
        var sumTra = 0.0
        for (f in 0 until M0Fixtures.N_FRAMES) {
            val truth = TestData.groundTruth(f)
            sumRot += result.poses[f].rotationErrorDeg(truth)
            sumTra += result.poses[f].translationErrorMm(truth)
        }

        // Geometrie wie die Referenz: wahre Form von Frame 0 gegen geschaetzte
        val shapeTrueF0 = model.shape(M0Fixtures.alphaTrue, M0Fixtures.betaTrueFrame0)
        val shapeEstF0 = model.shape(result.alpha, result.betas[0])
        val geomF0 = model.meanVertexDistance(shapeTrueF0, shapeEstF0)

        // ... und zusaetzlich die NEUTRALE Kopfform (die spaeter exportiert wird)
        val shapeTrueNeutral = model.shape(M0Fixtures.alphaTrue, DoubleArray(M0Fixtures.K_EXPRESSION))
        val geomNeutral = model.meanVertexDistance(shapeTrueNeutral, result.finalShape)

        // Inlier-RMS: nur sichtbare UND nicht kuenstlich verrauschte Punkte.
        // Der RMS ueber ALLE Punkte wird von den Ausreissern dominiert und
        // sagt ueber das Verfahren nichts aus.
        val pred = DoubleArray(2 * n)
        var sumSq = 0.0
        var count = 0
        for (f in 0 until M0Fixtures.N_FRAMES) {
            val shape = model.shape(result.alpha, result.betas[f])
            camera.projectAll(result.poses[f].rotation, result.poses[f].translation, shape, pred)
            val lm = TestData.landmarks(f)
            val vis = TestData.visibility(f)
            val out = TestData.outliers(f)
            for (i in 0 until n) {
                if (vis[i] < 0.5 || out[i] > 0.5) continue
                val du = pred[2 * i] - lm[2 * i]
                val dv = pred[2 * i + 1] - lm[2 * i + 1]
                sumSq += du * du + dv * dv
                count++
            }
        }
        val inlierRms = sqrt(sumSq / count)

        val metrics = Metrics(
            rotDegMean = sumRot / M0Fixtures.N_FRAMES,
            transMmMean = sumTra / M0Fixtures.N_FRAMES,
            geometryFrame0Mm = geomF0,
            geometryNeutralMm = geomNeutral,
            reproFinalPx = result.reproHistory.last(),
            reproFirstPx = result.reproHistory.first(),
            inlierRmsPx = inlierRms,
            alphaCorr = pearson(M0Fixtures.alphaTrue, result.alpha)
        )
        return result to metrics
    }

    @Test
    fun gemeinsameIdentitaetWirdStabilGeschaetzt() {
        val (result, m) = runFit()

        assertTrue("Rotation ${m.rotDegMean} vs. erwartet ${M0Fixtures.expectedRotDegMean}",
            kotlin.math.abs(m.rotDegMean - M0Fixtures.expectedRotDegMean) < 0.05)
        assertTrue("Translation ${m.transMmMean} vs. erwartet ${M0Fixtures.expectedTransMmMean}",
            kotlin.math.abs(m.transMmMean - M0Fixtures.expectedTransMmMean) < 0.05)
        assertTrue("Geometrie ${m.geometryFrame0Mm} vs. erwartet ${M0Fixtures.expectedGeometryMm}",
            kotlin.math.abs(m.geometryFrame0Mm - M0Fixtures.expectedGeometryMm) < 0.05)
        assertTrue("Inlier-RMS ${m.inlierRmsPx} vs. erwartet ${M0Fixtures.expectedInlierRmsPx}",
            kotlin.math.abs(m.inlierRmsPx - M0Fixtures.expectedInlierRmsPx) < 0.05)
        assertTrue("Reprojektion ${m.reproFinalPx} vs. erwartet ${M0Fixtures.expectedReproFinalPx}",
            kotlin.math.abs(m.reproFinalPx - M0Fixtures.expectedReproFinalPx) < 0.05)

        // Der Fit muss konvergieren, nicht divergieren
        assertTrue("Reprojektion darf nicht schlechter werden", m.reproFinalPx <= m.reproFirstPx + 1e-9)
        assertTrue("Reprojektion muss < 10 px bleiben", m.reproFinalPx < 10.0)
        assertTrue("Geometrie muss < 1 mm bleiben", m.geometryNeutralMm < 1.0)

        // Es muss ueberhaupt eine Identitaet herauskommen (nicht der Nullvektor)
        var norm = 0.0
        for (v in result.alpha) norm += v * v
        assertTrue("Identitaet darf nicht null sein", sqrt(norm) > 0.05)

        // Posen muessen metrisch plausibel sein (~50 cm Abstand zum Kopf)
        for (pose in result.poses) {
            assertTrue(
                "Kameraabstand ${pose.translation[2]} mm sollte zwischen 300 und 900 mm liegen",
                pose.translation[2] in 300.0..900.0
            )
        }

        println("[M0] Fit: Reprojektion ${"%.4f".format(m.reproFirstPx)} -> " +
            "${"%.4f".format(m.reproFinalPx)} px | Inlier ${"%.4f".format(m.inlierRmsPx)} px | " +
            "rot ${"%.4f".format(m.rotDegMean)} deg | trans ${"%.4f".format(m.transMmMean)} mm | " +
            "Geometrie ${"%.4f".format(m.geometryFrame0Mm)} mm " +
            "(neutral ${"%.4f".format(m.geometryNeutralMm)} mm) | " +
            "Ident.-Korr. ${"%.3f".format(m.alphaCorr)}")
    }

    @Test
    fun basisLayoutIstKomponentenweise() {
        // Vertrag: basis[komponente * kAnzahl + k]. Wird dieser Test rot, ist
        // das LAYOUT der Fixtures und des Modells nicht mehr dasselbe -- der
        // haeufigste und am schwersten zu findende Fehler in so einem Kern.
        val alpha = DoubleArray(M0Fixtures.K_IDENTITY) { 0.5 }
        val beta = DoubleArray(M0Fixtures.K_EXPRESSION)
        val shape = model.shape(alpha, beta)
        val n3 = M0Fixtures.baseVertices.size
        for (i in 0 until n3) {
            var expected = M0Fixtures.baseVertices[i]
            for (k in 0 until M0Fixtures.K_IDENTITY) {
                expected += 0.5 * M0Fixtures.identityBasis[i * M0Fixtures.K_IDENTITY + k]
            }
            assertEquals("Komponente $i", expected, shape[i], 1e-9)
        }
    }

    @Test
    fun formelStimmtMitDemModellUeberein() {
        val alpha = doubleArrayOf(0.4, -0.2, 0.15, 0.0, 0.9, -0.5, 0.3, 0.05)
        val beta = doubleArrayOf(0.2, 0.0, -0.4, 0.1, 0.0, 0.35)
        val shape = model.shape(alpha, beta)
        val n3 = M0Fixtures.baseVertices.size
        var maxDiff = 0.0
        for (i in 0 until n3) {
            var expected = M0Fixtures.baseVertices[i]
            for (k in 0 until M0Fixtures.K_IDENTITY) {
                expected += alpha[k] * M0Fixtures.identityBasis[i * M0Fixtures.K_IDENTITY + k]
            }
            for (k in 0 until M0Fixtures.K_EXPRESSION) {
                expected += beta[k] * M0Fixtures.expressionBasis[i * M0Fixtures.K_EXPRESSION + k]
            }
            maxDiff = maxOf(maxDiff, kotlin.math.abs(expected - shape[i]))
        }
        assertEquals(0.0, maxDiff, 1e-9)
    }

    @Test
    fun mehrFramesVerbessernDieIdentitaetNichtDiePose() {
        // Erkenntnis aus dem Referenzlauf: mit der Zahl der Bilder steigt
        // vor allem die Formtreue, die Pose bleibt auf demselben Niveau.
        // Das ist die Begruendung fuer 16 / 48 / 120 Frames (Quick/Standard/Pro).
        val full = runFit().second
        val half = ModelFitter.fit(
            camera, model,
            TestData.observations().take(M0Fixtures.N_FRAMES / 2)
        )
        assertTrue("Weniger Frames duerfen die Pose nicht katastrophal verschlechtern",
            half.reproHistory.last() < full.reproFinalPx + 2.0)
        println("[M0] Frames: ${M0Fixtures.N_FRAMES / 2} -> ${"%.4f".format(half.reproHistory.last())} px, " +
            "${M0Fixtures.N_FRAMES} -> ${"%.4f".format(full.reproFinalPx)} px")
    }

    private fun pearson(a: DoubleArray, b: DoubleArray): Double {
        val n = minOf(a.size, b.size)
        val ma = a.take(n).average()
        val mb = b.take(n).average()
        var num = 0.0
        var da = 0.0
        var db = 0.0
        for (i in 0 until n) {
            val x = a[i] - ma
            val y = b[i] - mb
            num += x * y
            da += x * x
            db += y * y
        }
        val den = sqrt(da * db)
        return if (den > 0) num / den else Double.NaN
    }
}

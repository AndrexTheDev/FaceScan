package com.andrexthedev.facescan.geometry

import kotlin.math.sqrt

/**
 * Kleine lineare Algebra fuer den M0-Kern.
 *
 * Es gibt bewusst KEINE Abhaengigkeit zu einer externen Matrix-Bibliothek:
 *  - weniger APK-Groesse,
 *  - keine Lizenzpruefung noetig,
 *  - die Systeme sind klein (4x4, 6x6, ~60x60), Cholesky reicht dafuer.
 */
object Linalg {

    /**
     * Loest A x = b fuer symmetrisch positiv definite A (Cholesky).
     * A ist zeilenweise (n*n), b der Laenge n.
     * Liefert null, wenn A nicht positiv definit ist.
     */
    fun solveSpd(a: DoubleArray, b: DoubleArray, n: Int): DoubleArray? {
        val l = DoubleArray(n * n)
        for (i in 0 until n) {
            for (j in 0..i) {
                var sum = a[i * n + j]
                for (k in 0 until j) sum -= l[i * n + k] * l[j * n + k]
                when {
                    i == j -> {
                        if (sum <= 1e-18) return null
                        l[i * n + j] = sqrt(sum)
                    }
                    else -> l[i * n + j] = sum / (l[j * n + j].let { if (it == 0.0) 1e-18 else it })
                }
            }
        }
        // Vorwaerts substitution: L y = b
        val y = DoubleArray(n)
        for (i in 0 until n) {
            var sum = b[i]
            for (k in 0 until i) sum -= l[i * n + k] * y[k]
            val d = l[i * n + i]
            if (d == 0.0) return null
            y[i] = sum / d
        }
        // Rueckwaerts substitution: L^T x = y
        val x = DoubleArray(n)
        for (i in n - 1 downTo 0) {
            var sum = y[i]
            for (k in i + 1 until n) sum -= l[k * n + i] * x[k]
            val d = l[i * n + i]
            if (d == 0.0) return null
            x[i] = sum / d
        }
        return x
    }

    /**
     * Kleinste-Quadrate-Loesung von A x ~= b ueber die Normalgleichungen
     * (A^T A + lambda*I) x = A^T b.
     *
     * A ist zeilenweise (rows*cols). Fuer unsere Systeme numerisch unkritisch.
     */
    fun leastSquares(
        a: DoubleArray,
        b: DoubleArray,
        rows: Int,
        cols: Int,
        damping: Double = 1e-9
    ): DoubleArray? {
        val ata = DoubleArray(cols * cols)
        val atb = DoubleArray(cols)
        for (r in 0 until rows) {
            val rowOffset = r * cols
            for (i in 0 until cols) {
                val avi = a[rowOffset + i]
                if (avi == 0.0) continue
                atb[i] += avi * b[r]
                var j = i
                while (j < cols) {
                    ata[i * cols + j] += avi * a[rowOffset + j]
                    j++
                }
            }
        }
        // Symmetrie ergaenzen + Daempfung
        for (i in 0 until cols) {
            for (j in i + 1 until cols) ata[j * cols + i] = ata[i * cols + j]
            ata[i * cols + i] += damping
        }
        return solveSpd(ata, atb, cols)
    }

    /** Median eines DoubleArray (kopiert, Eingabe bleibt unveraendert). */
    fun median(values: DoubleArray): Double {
        if (values.isEmpty()) return 0.0
        val sorted = values.copyOf()
        sorted.sort()
        val mid = sorted.size / 2
        return if (sorted.size % 2 == 0) (sorted[mid - 1] + sorted[mid]) * 0.5 else sorted[mid]
    }

    /**
     * Robuster Sigma-Schaetzer: 1.4826 * MAD.
     * (Bei normalverteilten Residuen erwartungstreu fuer sigma.)
     */
    fun madSigma(values: DoubleArray): Double {
        val med = median(values)
        val dev = DoubleArray(values.size) { kotlin.math.abs(values[it] - med) }
        return 1.4826 * median(dev) + 1e-6
    }
}

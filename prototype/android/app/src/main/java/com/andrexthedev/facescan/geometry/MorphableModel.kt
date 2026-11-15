package com.andrexthedev.facescan.geometry

/**
 * Lineares 3D-Morphable Model (Geometrie), wie es FaceScan verwendet:
 *
 *   S(alpha, beta) = S_mean + A_id * alpha + A_exp * beta
 *
 * LAYOUT DER BASEN (verbindlich, wird von den Tests geprueft):
 *   komponentenweise, genau so wie numpy `.tolist()` es schreibt –
 *   eine Zeile je Vertex-Komponente, eine Spalte je Basisvektor:
 *
 *       basis[komponente * kAnzahl + k]
 *       komponente = 3 * vertexIndex + (0 = x, 1 = y, 2 = z)
 *
 * Warum komponentenweise und nicht "ein Vektor nach dem anderen"?
 * Der Fit liest pro Punkt drei aufeinanderfolgende Komponenten aller Moden
 * (siehe ModelFitter) – dabei ist dieses Layout der cache-freundliche Fall.
 *
 * Einheiten: Millimeter. S_mean ist bereits zentriert.
 *
 * Rechtlicher Hinweis: fuer das Produkt wird eine EIGENE Basis aus eigenen,
 * schriftlich lizenzierten Aufnahmen gebaut (FLAME/Basel/ICT-FaceKit sind
 * forschungs- oder einzelfalllizenziert und damit tabu – siehe docs/09).
 */
class MorphableModel(
    val meanVertices: DoubleArray,          // 3N
    val identityBasis: DoubleArray,         // 3N * K_IDENTITY, komponentenweise
    val expressionBasis: DoubleArray,       // 3N * K_EXPRESSION, komponentenweise
    val kIdentity: Int,
    val kExpression: Int
) {
    val nVertices: Int get() = meanVertices.size / 3

    init {
        require(meanVertices.size % 3 == 0) { "meanVertices muss durch 3 teilbar sein" }
        require(identityBasis.size == meanVertices.size * kIdentity) {
            "identityBasis: ${identityBasis.size} != ${meanVertices.size} * $kIdentity"
        }
        require(expressionBasis.size == meanVertices.size * kExpression) {
            "expressionBasis: ${expressionBasis.size} != ${meanVertices.size} * $kExpression"
        }
    }

    /** Form des Kopfes (3N) zu gegebenen Parametern. */
    fun shape(
        alpha: DoubleArray,
        beta: DoubleArray,
        out: DoubleArray = DoubleArray(meanVertices.size)
    ): DoubleArray {
        val kId = kIdentity
        val kExp = kExpression
        for (i in meanVertices.indices) {
            var acc = meanVertices[i]
            val idOff = i * kId
            for (k in 0 until kId) {
                val a = alpha[k]
                if (a != 0.0) acc += a * identityBasis[idOff + k]
            }
            val expOff = i * kExp
            for (k in 0 until kExp) {
                val b = beta[k]
                if (b != 0.0) acc += b * expressionBasis[expOff + k]
            }
            out[i] = acc
        }
        return out
    }

    /** Mittlerer euklidischer Vertex-Abstand zweier Formen (mm). */
    fun meanVertexDistance(a: DoubleArray, b: DoubleArray): Double {
        val n = a.size / 3
        var sum = 0.0
        for (i in 0 until n) {
            val dx = a[3 * i] - b[3 * i]
            val dy = a[3 * i + 1] - b[3 * i + 1]
            val dz = a[3 * i + 2] - b[3 * i + 2]
            sum += kotlin.math.sqrt(dx * dx + dy * dy + dz * dz)
        }
        return sum / n
    }
}

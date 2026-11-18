package com.andrexthedev.facescan.geometry

import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * 3x3-Matrix, zeilenweise in einem [DoubleArray] der Laenge 9 gespeichert.
 *
 * Bewusst als primitives Array (kein Objekt pro Element): der Kern laeuft
 * spaeter zehntausendfach pro Scan durch, die Allokationsrate zaehlt.
 */
class Mat3(val m: DoubleArray) {

    init { require(m.size == 9) }

    operator fun get(row: Int, col: Int): Double = m[row * 3 + col]

    operator fun times(other: Mat3): Mat3 {
        val out = DoubleArray(9)
        for (r in 0..2) {
            for (c in 0..2) {
                out[r * 3 + c] = this[r, 0] * other[0, c] +
                    this[r, 1] * other[1, c] +
                    this[r, 2] * other[2, c]
            }
        }
        return Mat3(out)
    }

    /** Matrix mal 3-Vektor. */
    fun times(v: DoubleArray): DoubleArray = doubleArrayOf(
        m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
        m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
        m[6] * v[0] + m[7] * v[1] + m[8] * v[2]
    )

    fun transpose(): Mat3 = Mat3(
        doubleArrayOf(m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8])
    )

    fun determinant(): Double =
        m[0] * (m[4] * m[8] - m[5] * m[7]) -
            m[1] * (m[3] * m[8] - m[5] * m[6]) +
            m[2] * (m[3] * m[7] - m[4] * m[6])

    fun inverse(): Mat3 {
        val d = determinant()
        require(abs(d) > 1e-18) { "Matrix ist singulaer" }
        val inv = DoubleArray(9)
        inv[0] = (m[4] * m[8] - m[5] * m[7]) / d
        inv[1] = (m[2] * m[7] - m[1] * m[8]) / d
        inv[2] = (m[1] * m[5] - m[2] * m[4]) / d
        inv[3] = (m[5] * m[6] - m[3] * m[8]) / d
        inv[4] = (m[0] * m[8] - m[2] * m[6]) / d
        inv[5] = (m[2] * m[3] - m[0] * m[5]) / d
        inv[6] = (m[3] * m[7] - m[4] * m[6]) / d
        inv[7] = (m[1] * m[6] - m[0] * m[7]) / d
        inv[8] = (m[0] * m[4] - m[1] * m[3]) / d
        return Mat3(inv)
    }

    /** Naechste orthonormale Matrix (polarer Faktor), Newton-Iteration. */
    fun orthonormalize(): Mat3 {
        var x = this
        repeat(12) {
            val y = x.inverse().transpose()
            val next = DoubleArray(9)
            for (i in 0..8) next[i] = 0.5 * (x.m[i] + y.m[i])
            val cand = Mat3(next)
            var delta = 0.0
            for (i in 0..8) delta += abs(cand.m[i] - x.m[i])
            x = cand
            if (delta < 1e-14) return x
        }
        return x
    }

    companion object {
        fun identity(): Mat3 = Mat3(doubleArrayOf(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))

        /** Kreuzprodukt-Matrix eines 3-Vektors. */
        fun skew(v: DoubleArray): Mat3 = Mat3(
            doubleArrayOf(
                0.0, -v[2], v[1],
                v[2], 0.0, -v[0],
                -v[1], v[0], 0.0
            )
        )

        /** Rodrigues: Rotationsvektor (so(3)) -> Rotationsmatrix. */
        fun fromRodrigues(omega: DoubleArray): Mat3 {
            val theta = sqrt(omega[0] * omega[0] + omega[1] * omega[1] + omega[2] * omega[2])
            if (theta < 1e-12) return identity().let { id ->
                val s = skew(omega)
                Mat3(DoubleArray(9) { id.m[it] + s.m[it] })
            }
            val k = doubleArrayOf(omega[0] / theta, omega[1] / theta, omega[2] / theta)
            val kk = skew(k)
            val kk2 = kk * kk
            val out = DoubleArray(9)
            for (i in 0..8) {
                out[i] = identity().m[i] + sin(theta) * kk.m[i] + (1.0 - cos(theta)) * kk2.m[i]
            }
            return Mat3(out)
        }

        /** Rotationsmatrix -> Rotationsvektor. */
        fun toRodrigues(r: Mat3): DoubleArray {
            val cosTheta = ((r[0, 0] + r[1, 1] + r[2, 2]) - 1.0) * 0.5
            val clamped = cosTheta.coerceIn(-1.0, 1.0)
            val theta = kotlin.math.acos(clamped)
            val raw = doubleArrayOf(
                r[2, 1] - r[1, 2],
                r[0, 2] - r[2, 0],
                r[1, 0] - r[0, 1]
            )
            return if (theta < 1e-8) {
                doubleArrayOf(raw[0] * 0.5, raw[1] * 0.5, raw[2] * 0.5)
            } else {
                val f = theta / (2.0 * sin(theta))
                doubleArrayOf(raw[0] * f, raw[1] * f, raw[2] * f)
            }
        }

        /** Winkel zwischen zwei Rotationen in Grad. */
        fun rotationErrorDeg(a: Mat3, b: Mat3): Double {
            val rel = a * b.transpose()
            val cosTheta = ((rel[0, 0] + rel[1, 1] + rel[2, 2]) - 1.0) * 0.5
            return Math.toDegrees(kotlin.math.acos(cosTheta.coerceIn(-1.0, 1.0)))
        }
    }
}

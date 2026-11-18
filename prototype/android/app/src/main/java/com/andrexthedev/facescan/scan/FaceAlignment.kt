package com.andrexthedev.facescan.scan

import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Starrkörper-Ausrichtung an Augenwinkeln, Stirn und Nasenrücken. Kein PnP,
 * keine Kamerakalibrierung und keine Garantie bei perspektivischer Verzerrung.
 * Quaternionenlösung nach Horn: maximale Eigenlösung der 4x4-Matrix.
 */
object FaceAlignment {
    private val anchors = intArrayOf(10, 151, 9, 168, 6, 197, 195, 5, 4, 33, 133, 263, 362)
    data class Result(val points: FloatArray, val anchorRms: Double)

    fun align(reference: FloatArray, moving: FloatArray): Result {
        val n = FaceTopology.VERTEX_COUNT * 3
        require(reference.size == n && moving.size == n)
        require(reference.all { it.isFinite() } && moving.all { it.isFinite() })
        fun centroid(points: FloatArray): DoubleArray = DoubleArray(3) { axis ->
            anchors.sumOf { points[3 * it + axis].toDouble() } / anchors.size
        }
        val sourceCenter = centroid(moving)
        val targetCenter = centroid(reference)
        fun centered(points: FloatArray, index: Int, center: DoubleArray) =
            DoubleArray(3) { points[3 * index + it] - center[it] }
        // Mindestens zwei unabhängige Richtungen sind für die Lage nötig.
        fun hasArea(points: FloatArray, center: DoubleArray): Boolean {
            val v = anchors.map { centered(points, it, center) }
            var maxCrossSquared = 0.0
            for (a in v) for (b in v) {
                val x = a[1] * b[2] - a[2] * b[1]
                val y = a[2] * b[0] - a[0] * b[2]
                val z = a[0] * b[1] - a[1] * b[0]
                maxCrossSquared = maxOf(maxCrossSquared, x*x + y*y + z*z)
            }
            return maxCrossSquared > 1e-10
        }
        require(hasArea(reference, targetCenter) && hasArea(moving, sourceCenter)) { "Degenerierte Anker" }
        val s = Array(3) { DoubleArray(3) }
        for (i in anchors) {
            val a = centered(moving, i, sourceCenter); val b = centered(reference, i, targetCenter)
            for (r in 0..2) for (c in 0..2) s[r][c] += a[r] * b[c]
        }
        val xx = s[0][0]; val xy = s[0][1]; val xz = s[0][2]
        val yx = s[1][0]; val yy = s[1][1]; val yz = s[1][2]
        val zx = s[2][0]; val zy = s[2][1]; val zz = s[2][2]
        val matrix = arrayOf(
            doubleArrayOf(xx+yy+zz, yz-zy, zx-xz, xy-yx),
            doubleArrayOf(yz-zy, xx-yy-zz, xy+yx, zx+xz),
            doubleArrayOf(zx-xz, xy+yx, -xx+yy-zz, yz+zy),
            doubleArrayOf(xy-yx, zx+xz, yz+zy, -xx-yy+zz)
        )
        val vectors = Array(4) { r -> DoubleArray(4) { c -> if (r == c) 1.0 else 0.0 } }
        // Symmetrisches Jacobi-Eigenwertverfahren; wählt größten algebraischen
        // Eigenwert (nicht den mit dem größten absoluten Betrag).
        for (iteration in 0 until 80) {
            var p = 0; var q = 1
            for (r in 0..3) for (c in r+1..3) if (abs(matrix[r][c]) > abs(matrix[p][q])) { p = r; q = c }
            val apq = matrix[p][q]
            if (abs(apq) < 1e-14) break
            val angle = 0.5 * atan2(2 * apq, matrix[q][q] - matrix[p][p])
            val cs = cos(angle); val sn = sin(angle)
            val app = matrix[p][p]; val aqq = matrix[q][q]
            for (i in 0..3) if (i != p && i != q) {
                val ip = matrix[i][p]; val iq = matrix[i][q]
                matrix[i][p] = cs * ip - sn * iq; matrix[p][i] = matrix[i][p]
                matrix[i][q] = sn * ip + cs * iq; matrix[q][i] = matrix[i][q]
            }
            matrix[p][p] = cs*cs*app - 2*cs*sn*apq + sn*sn*aqq
            matrix[q][q] = sn*sn*app + 2*cs*sn*apq + cs*cs*aqq
            matrix[p][q] = 0.0; matrix[q][p] = 0.0
            for (i in 0..3) {
                val vp = vectors[i][p]; val vq = vectors[i][q]
                vectors[i][p] = cs * vp - sn * vq; vectors[i][q] = sn * vp + cs * vq
            }
        }
        val largest = (0..3).maxByOrNull { matrix[it][it] }!!
        val w = vectors[0][largest]; val x = vectors[1][largest]; val y = vectors[2][largest]; val z = vectors[3][largest]
        val rotation = arrayOf(
            doubleArrayOf(1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)),
            doubleArrayOf(2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)),
            doubleArrayOf(2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y))
        )
        val output = FloatArray(n)
        for (i in 0 until FaceTopology.VERTEX_COUNT) for (r in 0..2) {
            var value = targetCenter[r]
            for (c in 0..2) value += rotation[r][c] * (moving[3 * i + c] - sourceCenter[c])
            output[3 * i + r] = value.toFloat()
            require(output[3 * i + r].isFinite())
        }
        var sum = 0.0
        for (i in anchors) for (axis in 0..2) {
            val d = output[3*i+axis].toDouble() - reference[3*i+axis]
            sum += d*d
        }
        return Result(output, sqrt(sum / anchors.size))
    }
}

package com.andrexthedev.facescan.geometry

import kotlin.math.acos
import kotlin.math.sqrt

/**
 * Geometrischer Kern für einen Punkt mit korrespondierenden, entzerrten Pixeln.
 * R,t transformieren Welt- in Kamerakoordinaten: Xc = R Xw + t, Blickrichtung +Z.
 * Kameraposen müssen in einem gemeinsamen, starren Koordinatensystem vorliegen.
 * Dieses Modul kalibriert keine Kamera und schätzt keine Posen oder Korrespondenzen.
 */
object MultiViewTriangulation {
    data class Observation(
        val camera: CameraModel,
        val worldToCamera: Mat3,
        val translation: DoubleArray,
        val u: Double,
        val v: Double
    )

    enum class Failure { INVALID_INPUT, INSUFFICIENT_VIEWS, INSUFFICIENT_PARALLAX, DEGENERATE_GEOMETRY, BEHIND_CAMERA, REPROJECTION_ERROR }
    sealed class Result {
        data class Point(val xyz: DoubleArray, val maxParallaxDegrees: Double, val rmsPixels: Double, val maxPixels: Double) : Result()
        data class Rejected(val reason: Failure) : Result()
    }

    /**
     * Kleinste quadratische Abstände zu den Kamerastrahlen, danach strenge
     * Prüfung positiver Tiefe und aller Reprojektionsreste. Keine Ausreißerentfernung.
     * Skala/Einheit stammen ausschließlich aus den eingegebenen Posen.
     * Schwellen sind Startwerte, keine Kalibrierungs- oder Genauigkeitsgarantie.
     */
    fun triangulate(
        observations: List<Observation>,
        minParallaxDegrees: Double = 1.0,
        maxReprojectionPixels: Double = 2.0
    ): Result {
        fun reject(reason: Failure): Result = Result.Rejected(reason)
        if (observations.size !in 2..32 || !minParallaxDegrees.isFinite() ||
            minParallaxDegrees <= 0.0 || minParallaxDegrees >= 90.0 ||
            !maxReprojectionPixels.isFinite() || maxReprojectionPixels < 0.0) return reject(Failure.INVALID_INPUT)
        val origins = ArrayList<DoubleArray>(observations.size)
        val directions = ArrayList<DoubleArray>(observations.size)
        for (obs in observations) {
            val c = obs.camera
            val r = obs.worldToCamera
            if (!c.fx.isFinite() || !c.fy.isFinite() || c.fx <= 0 || c.fy <= 0 ||
                !c.cx.isFinite() || !c.cy.isFinite() || !obs.u.isFinite() || !obs.v.isFinite() ||
                obs.translation.size != 3 || obs.translation.any { !it.isFinite() } || r.m.any { !it.isFinite() })
                return reject(Failure.INVALID_INPUT)
            // Nur echte Rotation akzeptieren, keine Spiegelung, Skalierung oder Scherung.
            val gram = r * r.transpose()
            if (kotlin.math.abs(r.determinant() - 1.0) > 1e-5 || (0..8).any { i ->
                    kotlin.math.abs(gram.m[i] - if (i % 4 == 0) 1.0 else 0.0) > 1e-5
                }) return reject(Failure.INVALID_INPUT)
            val rt = r.transpose()
            val origin = rt.times(obs.translation).map { -it }.toDoubleArray()
            val ray = rt.times(doubleArrayOf((obs.u - c.cx) / c.fx, (obs.v - c.cy) / c.fy, 1.0))
            val length = Math.hypot(Math.hypot(ray[0], ray[1]), ray[2])
            if (!length.isFinite() || length <= 0.0 || origin.any { !it.isFinite() }) return reject(Failure.INVALID_INPUT)
            origins.add(origin)
            directions.add(DoubleArray(3) { ray[it] / length })
        }
        var maxAngle = 0.0
        for (i in directions.indices) for (j in 0 until i) {
            val d = directions[i]; val e = directions[j]
            val dot = (0..2).sumOf { d[it] * e[it] }.coerceIn(-1.0, 1.0)
            maxAngle = maxOf(maxAngle, Math.toDegrees(acos(dot)))
        }
        if (maxAngle < minParallaxDegrees) return reject(Failure.INSUFFICIENT_PARALLAX)
        val a = DoubleArray(9)
        val b = DoubleArray(3)
        for (i in directions.indices) for (row in 0..2) for (col in 0..2) {
            val value = (if (row == col) 1.0 else 0.0) - directions[i][row] * directions[i][col]
            a[3 * row + col] += value
            b[row] += value * origins[i][col]
        }
        val matrix = Mat3(a)
        val n = observations.size.toDouble()
        if (a.any { !it.isFinite() } || b.any { !it.isFinite() } ||
            !matrix.determinant().isFinite() || matrix.determinant() / (n * n * n) < 1e-12)
            return reject(Failure.DEGENERATE_GEOMETRY)
        val point = try { matrix.inverse().times(b) } catch (_: IllegalArgumentException) { return reject(Failure.DEGENERATE_GEOMETRY) }
        if (point.any { !it.isFinite() }) return reject(Failure.DEGENERATE_GEOMETRY)
        var sumSq = 0.0
        var worst = 0.0
        for (obs in observations) {
            val cameraPoint = obs.worldToCamera.times(point)
            for (i in 0..2) cameraPoint[i] += obs.translation[i]
            if (cameraPoint.any { !it.isFinite() } || cameraPoint[2] <= 1e-9) return reject(Failure.BEHIND_CAMERA)
            val du = obs.camera.fx * cameraPoint[0] / cameraPoint[2] + obs.camera.cx - obs.u
            val dv = obs.camera.fy * cameraPoint[1] / cameraPoint[2] + obs.camera.cy - obs.v
            val error = Math.hypot(du, dv)
            if (!error.isFinite()) return reject(Failure.DEGENERATE_GEOMETRY)
            worst = maxOf(worst, error)
            sumSq += error * error
        }
        if (worst > maxReprojectionPixels) return reject(Failure.REPROJECTION_ERROR)
        return Result.Point(point, maxAngle, sqrt(sumSq / observations.size), worst)
    }
}

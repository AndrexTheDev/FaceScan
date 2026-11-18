package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.CameraModel
import com.andrexthedev.facescan.geometry.ValidatedAnchorPose

/**
 * Sucht zu einer angenommenen Pinhole-Kamera (fy = fx) die Brennweite, die den
 * Ankerfit am besten erklärt. Gedacht ist das für unbekannte Sichtfelder, etwa
 * wenn eine Kamera keine Intrinsics meldet.
 *
 * Das ist ausdrücklich KEINE Kalibrierung: Ein kleiner Reprojektionsrest kann
 * auch durch falsche Personengeometrie, falsche Anker oder eine verzerrte
 * Optik entstehen. Skala und Kopfabstand sind mit der Kamera gekoppelt und
 * nicht eindeutig; das Ergebnis ist keine metrische Messung. Ohne
 * Perspektivwechsel bleibt die Brennweite kaum bestimmbar, deshalb ist die
 * Suche auf einen plausiblen Bereich begrenzt und liefert dann oft einen
 * Randwert.
 */
object FocalSearch {
    /** Suchbereich relativ zur längeren Bildkante; bewusst konservativ. */
    const val MIN_FOCAL_FACTOR = 0.6
    const val MAX_FOCAL_FACTOR = 2.5

    data class Result(
        val pose: ValidatedAnchorPose.Result.Pose,
        val intrinsics: MultiViewCapture.Intrinsics,
        val relativeStep: Double
    )

    /**
     * Deterministische grobe Raster- und Feinsuche. Null, wenn keine
     * Brennweite im Bereich einen akzeptablen Fit liefert.
     */
    fun estimate(
        anchors: List<ValidatedAnchorPose.Anchor>,
        base: CameraModel,
        maxRmsPixels: Double = MultiViewSession.MAX_VIEW_RMS_PIXELS,
        minInlierRatio: Double = 0.5
    ): Result? {
        if (anchors.size < 6 || maxRmsPixels <= 0.0 || !maxRmsPixels.isFinite()) return null
        val width = 2.0 * base.cx
        val height = 2.0 * base.cy
        // Annahme des Aufrufers: cx/cy liegen in der Bildmitte; sonst wäre die
        // Suche nicht auf die Bildgröße beziehbar.
        if (!width.isFinite() || !height.isFinite() || width <= 0.0 || height <= 0.0) return null
        val reference = maxOf(width, height)
        fun evaluate(factor: Double): Pair<ValidatedAnchorPose.Result.Pose, Double>? {
            val f = factor * reference
            if (!f.isFinite() || f <= 0.0) return null
            val camera = CameraModel(f, f, base.cx, base.cy)
            val result = ValidatedAnchorPose.estimate(camera, anchors, maxRmsPixels, minInlierRatio)
            return when (result) {
                is ValidatedAnchorPose.Result.Pose -> result to (f / base.fx)
                is ValidatedAnchorPose.Result.Rejected -> null
            }
        }
        var best: Result? = null
        var bestRms = Double.POSITIVE_INFINITY
        fun consider(factor: Double) {
            val (pose, relative) = evaluate(factor) ?: return
            if (pose.rmsPixels < bestRms || (pose.rmsPixels == bestRms && best != null &&
                    kotlin.math.abs(relative - 1.0) < kotlin.math.abs(best!!.relativeStep - 1.0))) {
                bestRms = pose.rmsPixels
                val f = factor * reference
                val roundtrip = base.fx.takeIf { it.isFinite() && it > 0.0 }
                best = Result(pose, MultiViewCapture.Intrinsics(f, f, base.cx, base.cy),
                    if (roundtrip != null) f / roundtrip else relative)
            }
        }
        val coarse = 16
        for (step in 0..coarse) {
            consider(MIN_FOCAL_FACTOR + (MAX_FOCAL_FACTOR - MIN_FOCAL_FACTOR) * step / coarse)
        }
        val coarseBest = best ?: return null
        // Feinsuche um den besten Rasterpunkt (± ein Rasterschritt).
        val center = coarseBest.intrinsics.fx / reference
        val spacing = (MAX_FOCAL_FACTOR - MIN_FOCAL_FACTOR) / coarse
        for (step in -10..10) {
            val factor = (center + spacing * step / 10.0).coerceIn(MIN_FOCAL_FACTOR, MAX_FOCAL_FACTOR)
            consider(factor)
        }
        return best
    }
}

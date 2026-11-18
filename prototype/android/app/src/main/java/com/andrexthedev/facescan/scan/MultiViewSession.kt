package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.LandmarkProjection

/**
 * Sammelt bewusst unterschiedliche Kopfhaltungen für die experimentelle
 * Mehransichten-Rekonstruktion. Eine Ansicht wird nur übernommen, wenn die
 * Ankerpose plausibel ist und sich die geschätzte Gierwinkel-Lage deutlich von
 * allen bereits übernommenen Ansichten unterscheidet.
 *
 * Grenzen: Der Gierwinkel stammt aus einem Populationsmittel-Ankerfit, ist
 * also selbst unsicher. Die Prüfung verhindert keine Personwechsel; der
 * Aufrufer muss dieselbe Person und dieselbe Kamera-Sitzung sicherstellen.
 * Schwellen sind nicht an realen Geräten validiert.
 */
class MultiViewSession(
    val intrinsics: MultiViewCapture.Intrinsics,
    private val minYawDifferenceDegrees: Double = MIN_YAW_DIFFERENCE_DEGREES,
    private val maxViews: Int = MultiViewCapture.MAX_VIEWS
) {
    companion object {
        /** Experimenteller Mindestunterschied der Gierwinkel-Schätzung. */
        const val MIN_YAW_DIFFERENCE_DEGREES = 12.0
        /** Experimentelle Obergrenze je Ansicht; nicht validiert. */
        const val MAX_VIEW_RMS_PIXELS = 6.0
    }

    init {
        require(minYawDifferenceDegrees.isFinite() && minYawDifferenceDegrees > 0.0)
        require(maxViews in 2..MultiViewCapture.MAX_VIEWS)
    }

    enum class AddResult {
        ACCEPTED, FULL, INVALID_VIEW, OUT_OF_FRAME_OR_POSE_REJECTED,
        INSUFFICIENT_YAW_DIFFERENCE, INCONSISTENT_DIMENSIONS
    }

    data class Stored(val view: MultiViewCapture.View, val yawDegrees: Double, val rmsPixels: Double,
                      val estimatedIntrinsics: MultiViewCapture.Intrinsics)

    private val views = mutableListOf<Stored>()
    private var dimensions: Pair<Int, Int>? = null

    @Synchronized fun size(): Int = views.size
    @Synchronized fun isEmpty(): Boolean = views.isEmpty()
    @Synchronized fun stored(): List<Stored> = views.toList()
    @Synchronized fun clear() { views.clear(); dimensions = null }

    /**
     * Vorprüfung einer Ansicht ohne sie zu übernehmen. Null, wenn Anker fehlen
     * oder keine plausible Pose gefunden wird.
     */
    fun evaluate(points: FloatArray, width: Int, height: Int): Stored? =
        if (width <= 0 || height <= 0 || points.size < CanonicalAnchors.LANDMARK_COUNT * 3 ||
            points.any { !it.isFinite() }) null else inspect(points, width, height)

    /** Gierwinkel der geschätzten Pose in Grad; null bei unbrauchbarer Ansicht. */
    fun yawDegrees(points: FloatArray, width: Int, height: Int): Double? {
        if (width <= 0 || height <= 0 || points.size < CanonicalAnchors.LANDMARK_COUNT * 3 ||
            points.any { !it.isFinite() }) return null
        // Beide Kameras sind wegen fy = fx nur skaliert; die Suche verhindert,
        // dass eine grob falsche Annahme alle Ansichten verwirft.
        val (u, v) = LandmarkProjection.pixels(points, CanonicalAnchorData.indices, width, height, 1.0) ?: return null
        val search = FocalSearch.estimate(CanonicalAnchorData.anchors(u, v), intrinsics.camera(),
            maxRmsPixels = MAX_VIEW_RMS_PIXELS, minInlierRatio = 0.5) ?: return null
        val pose = search.pose
        // Kanonische +Z-Achse zeigt aus dem Gesicht; ihre Kamera-X-Komponente
        // beschreibt die seitliche Drehung.
        val axis = pose.transform.rotation.times(doubleArrayOf(0.0, 0.0, 1.0))
        val yaw = Math.toDegrees(kotlin.math.atan2(axis[0], axis[2]))
        return if (yaw.isFinite()) yaw else null
    }

    @Synchronized fun add(points: FloatArray, width: Int, height: Int, atMs: Long = 0L): AddResult {
        if (views.size >= maxViews) return AddResult.FULL
        if (points.size < CanonicalAnchors.LANDMARK_COUNT * 3 || points.any { !it.isFinite() }) return AddResult.INVALID_VIEW
        if (width <= 0 || height <= 0) return AddResult.INVALID_VIEW
        val dim = width to height
        if (dimensions != null && dimensions != dim) return AddResult.INCONSISTENT_DIMENSIONS
        val stored = inspect(points, width, height) ?: return AddResult.OUT_OF_FRAME_OR_POSE_REJECTED
        if (views.any { angularDistance(it.yawDegrees, stored.yawDegrees) < minYawDifferenceDegrees })
            return AddResult.INSUFFICIENT_YAW_DIFFERENCE
        dimensions = dim
        views.add(stored)
        return AddResult.ACCEPTED
    }

    private fun inspect(points: FloatArray, width: Int, height: Int): Stored? {
        // Beide Kameras sind wegen fy = fx nur skaliert; die Suche verhindert,
        // dass eine grob falsche Annahme alle Ansichten verwirft.
        val (u, v) = LandmarkProjection.pixels(points, CanonicalAnchorData.indices, width, height, 1.0) ?: return null
        val search = FocalSearch.estimate(CanonicalAnchorData.anchors(u, v), intrinsics.camera(),
            maxRmsPixels = MAX_VIEW_RMS_PIXELS, minInlierRatio = 0.5) ?: return null
        val pose = search.pose
        val axis = pose.transform.rotation.times(doubleArrayOf(0.0, 0.0, 1.0))
        val yaw = Math.toDegrees(kotlin.math.atan2(axis[0], axis[2]))
        if (!yaw.isFinite() || !pose.rmsPixels.isFinite()) return null
        return Stored(MultiViewCapture.View(points.copyOf(), width, height), yaw, pose.rmsPixels, search.intrinsics)
    }

    /**
     * Rekonstruiert ausschließlich aus den bereits übernommenen Ansichten.
     * Die Brennweite wird als Median der Einzelansichten verwendet, weil eine
     * feste Sichtfeld-Annahme alle Ansichten sonst systematisch verschiebt. Das
     * ist keine Kalibrierung: Alle Ansichten teilen dieselbe Kamera, und bei
     * geringer Perspektivänderung ist die Brennweite kaum bestimmt.
     */
    @Synchronized fun reconstruct(maxEdgeCm: Double? = null): MultiViewCapture.Outcome {
        if (views.size < 2) return MultiViewCapture.Outcome.Rejected(MultiViewCapture.Failure.INSUFFICIENT_ACCEPTED_VIEWS)
        val focals = views.map { it.estimatedIntrinsics.fx }.sorted()
        val median = focals[focals.size / 2]
        val camera = if (median.isFinite() && median > 0.0)
            MultiViewCapture.Intrinsics(median, median, intrinsics.cx, intrinsics.cy) else intrinsics
        return MultiViewCapture.reconstruct(views.map { it.view }, camera, maxEdgeCm)
    }

    private fun angularDistance(a: Double, b: Double): Double {
        val diff = Math.abs(a - b) % 360.0
        return if (diff > 180.0) 360.0 - diff else diff
    }

    /** Diagnose: Spanne der übernommenen Gierwinkel in Grad. */
    @Synchronized fun yawSpreadDegrees(): Double =
        if (views.isEmpty()) 0.0 else views.maxOf { it.yawDegrees } - views.minOf { it.yawDegrees }
}

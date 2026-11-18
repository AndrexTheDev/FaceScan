package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.Mat3
import com.andrexthedev.facescan.geometry.MultiViewPointCloud
import com.andrexthedev.facescan.geometry.MultiViewTriangulation

/**
 * Grober Vollständigkeits- und Unsicherheitsbericht für das triangulierte
 * Teilnetz.
 *
 * Zonen: Das Gesicht wird allein über die Höhe (kanonische Y-Achse in cm, +Y
 * oben) in fünf Streifen geteilt. Die Grenzen sind feste Werte aus den
 * Ankerhöhen; sie sind KEINE Anatomie und keine Segmentierung. Ein Punkt
 * gehört in die Zone seiner eigenen Y-Koordinate, ein Anker in die Zone seiner
 * kanonischen Y-Koordinate. Damit ist der Nenner je Zone exakt die Anzahl der
 * Anker in dieser Zone – nicht die unbekannte Anzahl fehlender Landmarks.
 *
 * Unsicherheit: Die Tiefe eines triangulierten Punktes reagiert auf einen
 * Pixelrest umso stärker, je kleiner die Parallaxe ist. Als Schätzung erster
 * Ordnung gilt
 *
 *     relative Tiefenunsicherheit ≈ rmsPixel / (fx · sin(Parallaxe))
 *     absolute Tiefenunsicherheit ≈ relative · Tiefe in der Referenzansicht
 *
 * Das ist eine Fehlerfortpflanzung aus dem gemessenen Reprojektionsrest und der
 * gemessenen Parallaxe – KEINE validierte Genauigkeit. Sie ignoriert
 * Kalibrierfehler, falsche Korrespondenzen, Verdeckung, Mimik und die
 * Unsicherheit der Ankerskala. Punkte ohne positive Parallaxe oder ohne
 * gültige Tiefe fließen nicht in die Statistik ein; es werden keine Werte
 * erfunden.
 */
object MultiViewCompleteness {
    /** Obergrenze der Zonen, nur zur Plausibilitätsprüfung der Tabelle. */
    const val ZONE_COUNT = 5

    data class Zone(val name: String, val minY: Double, val aboveIsInside: Boolean) {
        val isUpperMost: Boolean get() = aboveIsInside
    }

    /**
     * Zonen von oben nach unten. `minY` ist die untere Grenze; die oberste Zone
     * hat keine obere Grenze, die unterste keine untere.
     */
    val zones: List<Zone> = listOf(
        Zone("forehead", 5.5, true),
        Zone("eyes", 2.5, false),
        Zone("nose", -2.5, false),
        Zone("mouth", -6.5, false),
        Zone("chin", Double.NEGATIVE_INFINITY, false)
    )

    init {
        require(zones.size == ZONE_COUNT)
        require(zones.zipWithNext().all { (upper, lower) -> upper.minY > lower.minY })
    }

    /** Zone einer kanonischen Y-Koordinate; `null` nur bei nicht-endlichen Werten. */
    fun zoneIndex(y: Double): Int? {
        if (!y.isFinite()) return null
        for (i in 0 until zones.size - 1) if (y >= zones[i].minY) return i
        return zones.size - 1
    }

    data class ZoneCoverage(
        val name: String,
        val anchorsInZone: Int,
        val anchorsTriangulated: Int,
        val pointsInZone: Int
    ) {
        val complete: Boolean get() = anchorsInZone > 0 && anchorsTriangulated == anchorsInZone
    }

    data class Report(
        val zoneCoverages: List<ZoneCoverage>,
        val totalPoints: Int,
        val anchorsInZoneTotal: Int,
        val anchorsTriangulatedTotal: Int,
        /** Median der geschätzten absoluten Tiefenunsicherheit in cm; null ohne Messwerte. */
        val medianDepthUncertaintyCm: Double?,
        /** 90-%-Perzentil derselben Schätzung; null ohne Messwerte. */
        val highDepthUncertaintyCm: Double?,
        val uncertaintySamples: Int
    ) {
        /** Zonen ohne einen einzigen triangulierten Anker; leer heißt vollständig. */
        val emptyZoneNames: List<String>
            get() = zoneCoverages.filter { it.anchorsTriangulated == 0 }.map { it.name }

        val anchorCoverageFraction: Double
            get() = if (anchorsInZoneTotal == 0) 0.0 else anchorsTriangulatedTotal.toDouble() / anchorsInZoneTotal
    }

    /**
     * @param cloud triangulierte Punkte in der Ankerskala (cm).
     * @param referenceRotation Rotation der Referenzansicht (Welt → Kamera).
     * @param referenceTranslation Translation derselben Ansicht.
     * @param focalPixels fx der Triangulation; muss positiv und endlich sein.
     */
    fun analyze(
        cloud: MultiViewPointCloud.Result,
        referenceRotation: Mat3,
        referenceTranslation: DoubleArray,
        focalPixels: Double
    ): Report {
        require(cloud.points.size == CanonicalAnchors.LANDMARK_COUNT)
        require(referenceTranslation.size == 3 && referenceTranslation.all { it.isFinite() })
        require(focalPixels.isFinite() && focalPixels > 0.0)

        val pointsByZone = IntArray(zones.size)
        val anchorTriangulated = IntArray(zones.size)
        val uncertainties = ArrayList<Double>()

        for (index in cloud.points.indices) {
            val point = cloud.points[index]
            if (point !is MultiViewTriangulation.Result.Point) continue
            val y = point.xyz[1]
            zoneIndex(y)?.let { pointsByZone[it]++ }
            val depth = depthInReference(point.xyz, referenceRotation, referenceTranslation)
            val uncertainty = depthUncertaintyCm(depth, point.rmsPixels, point.maxParallaxDegrees, focalPixels)
            if (uncertainty != null) uncertainties.add(uncertainty)
        }
        // Anker sind feste Landmark-Indizes mit kanonischer Y-Koordinate.
        for (a in 0 until CanonicalAnchorData.COUNT) {
            val index = CanonicalAnchorData.indices[a]
            val zone = zoneIndex(CanonicalAnchorData.points[3 * a + 1]) ?: continue
            if (cloud.points[index] is MultiViewTriangulation.Result.Point) anchorTriangulated[zone]++
        }
        val coverage = zones.indices.map { i ->
            ZoneCoverage(zones[i].name, anchorsInZone(i), anchorTriangulated[i], pointsByZone[i])
        }
        val sorted = uncertainties.sorted()
        return Report(
            zoneCoverages = coverage,
            totalPoints = cloud.acceptedCount,
            anchorsInZoneTotal = CanonicalAnchorData.COUNT,
            anchorsTriangulatedTotal = anchorTriangulated.sum(),
            medianDepthUncertaintyCm = percentile(sorted, 0.5),
            highDepthUncertaintyCm = percentile(sorted, 0.9),
            uncertaintySamples = sorted.size
        )
    }

    /** Anzahl der Anker in einer Zone; aus den kanonischen Y-Koordinaten, nicht geraten. */
    fun anchorsInZone(zone: Int): Int {
        require(zone in zones.indices)
        return (0 until CanonicalAnchorData.COUNT).count { a ->
            zoneIndex(CanonicalAnchorData.points[3 * a + 1]) == zone
        }
    }

    /** Tiefe eines Weltpunktes in der Referenzansicht; null bei Punkt hinter der Kamera. */
    fun depthInReference(point: DoubleArray, rotation: Mat3, translation: DoubleArray): Double? {
        require(point.size == 3 && point.all { it.isFinite() })
        val camera = rotation.times(point)
        val depth = camera[2] + translation[2]
        return if (depth.isFinite() && depth > 1e-6) depth else null
    }

    /**
     * Schätzung erster Ordnung in cm; null, wenn Parallaxe, Tiefe oder Rest
     * keine belastbare Rechnung erlauben. Kein Ersatzwert.
     */
    fun depthUncertaintyCm(
        depthCm: Double?,
        rmsPixels: Double,
        maxParallaxDegrees: Double,
        focalPixels: Double
    ): Double? {
        if (depthCm == null || !depthCm.isFinite() || depthCm <= 0.0) return null
        if (!rmsPixels.isFinite() || rmsPixels < 0.0) return null
        if (!maxParallaxDegrees.isFinite() || maxParallaxDegrees <= 0.0 || maxParallaxDegrees >= 90.0) return null
        if (!focalPixels.isFinite() || focalPixels <= 0.0) return null
        val sine = Math.sin(Math.toRadians(maxParallaxDegrees))
        if (!sine.isFinite() || sine <= 1e-6) return null
        val relative = rmsPixels / (focalPixels * sine)
        val absolute = relative * depthCm
        return if (absolute.isFinite() && absolute >= 0.0) absolute else null
    }

    private fun percentile(sorted: List<Double>, fraction: Double): Double? {
        if (sorted.isEmpty()) return null
        if (sorted.size == 1) return sorted[0]
        val position = fraction * (sorted.size - 1)
        val lower = Math.floor(position).toInt()
        val upper = Math.ceil(position).toInt()
        return if (lower == upper) sorted[lower]
        else sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower)
    }

    /** Kurzfassung für Dateiköpfe; feste Reihenfolge, damit sie prüfbar bleibt. */
    fun describe(report: Report): String {
        val zoneText = report.zoneCoverages.joinToString(",") { z ->
            "${z.name}=${z.anchorsTriangulated}/${z.anchorsInZone}"
        }
        fun format(value: Double?) =
            if (value == null) "n/a" else "%.2f".format(java.util.Locale.ROOT, value)
        return "anchors=${report.anchorsTriangulatedTotal}/${report.anchorsInZoneTotal} " +
            "zones=$zoneText medianDepthUncertaintyCm=${format(report.medianDepthUncertaintyCm)} " +
            "highDepthUncertaintyCm=${format(report.highDepthUncertaintyCm)} " +
            "samples=${report.uncertaintySamples} (first-order estimate, not validated)"
    }
}

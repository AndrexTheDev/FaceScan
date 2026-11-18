package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.MultiViewPointCloud
import com.andrexthedev.facescan.geometry.MultiViewTriangulation

/**
 * Wie viele Ansichten einen triangulierten Punkt stützen.
 *
 * Zwei Zahlen je Punkt, die auseinandergehalten werden müssen:
 *  - `seen`   : Ansichten, in denen der Punkt überhaupt beobachtet wurde,
 *  - `used`   : Ansichten, die nach dem Mehrheitskonsens tatsächlich zum
 *               Ergebnis beigetragen haben.
 *
 * Nur `used` sagt etwas über die Belastbarkeit des Punktes aus. Ein Punkt mit
 * zwei Stützen ist deutlich schwieriger gegen eine falsche Zuordnung zu
 * schützen als einer mit vier. Das ist eine Aussage über die Rechnung, NICHT
 * über die Genauigkeit: vier übereinstimmende falsch zugeordnete Punkte bleiben
 * falsch.
 *
 * Es werden keine Zahlen geschätzt: Punkte ohne Konsens zählen nicht mit, und
 * wenn keine Inlier-Listen vorliegen (Zwei-Ansichten-Fall), bleibt `used` leer.
 */
object MultiViewRedundancy {
    data class Report(
        /** Anzahl der Punkte je Zahl beitragender Ansichten; Index 0 bleibt 0. */
        val usedHistogram: IntArray,
        /** Anzahl der Punkte je Zahl beobachtender Ansichten; Index 0 bleibt 0. */
        val seenHistogram: IntArray,
        val triangulatedPoints: Int,
        /** Median der beitragenden Ansichten; null, wenn keine Inlier-Listen vorliegen. */
        val medianUsedViews: Double?,
        /** Punkte, die von nur zwei Ansichten gestützt werden. */
        val supportedByTwoViews: Int
    ) {
        init {
            require(usedHistogram.size >= 1 && seenHistogram.size >= 1)
        }

        /** Anteil der triangulierten Punkte mit mindestens drei Stützen; null ohne Inlier-Daten. */
        val fractionWithThreeOrMore: Double?
            get() {
                if (medianUsedViews == null || triangulatedPoints == 0) return null
                val strong = (3 until usedHistogram.size).sumOf { usedHistogram[it] }
                return strong.toDouble() / triangulatedPoints
            }

        val hasInlierData: Boolean get() = medianUsedViews != null
    }

    /**
     * Variante ohne Inlier-Daten (Zwei-Ansichten-Fall). `used` bleibt dann
     * unbekannt und wird als `null` gemeldet, nicht als 0.
     */
    fun analyze(points: List<MultiViewTriangulation.Result>, seenBy: IntArray): Report {
        require(seenBy.isEmpty() || seenBy.size == points.size)
        return build(seenHistogram(seenBy), emptyMap(), points, seenBy)
    }

    /**
     * Bevorzugte Variante: nutzt die echten Inlier-Zahlen aus
     * [MultiViewPointCloud.RobustResult]. `usedByPoint` enthält je Punkt die
     * Zahl der beitragenden Ansichten; 0 bedeutet "nicht trianguliert".
     */
    fun analyzeRobust(robust: MultiViewPointCloud.RobustResult, usedByPoint: IntArray): Report {
        require(usedByPoint.size == robust.points.size)
        require(usedByPoint.all { it >= 0 })
        val points = robust.points.map { value ->
            when (value) {
                is com.andrexthedev.facescan.geometry.RobustMultiViewTriangulation.Result.Point -> value.fit
                is com.andrexthedev.facescan.geometry.RobustMultiViewTriangulation.Result.Rejected ->
                    MultiViewTriangulation.Result.Rejected(value.reason)
            }
        }
        val used = HashMap<Int, Int>()
        for (i in robust.points.indices) {
            if (robust.points[i] is com.andrexthedev.facescan.geometry.RobustMultiViewTriangulation.Result.Point)
                used[i] = usedByPoint[i]
        }
        return build(seenHistogram(robust.seenByViewCount), used, points, robust.seenByViewCount)
    }

    private fun seenHistogram(seenBy: IntArray): IntArray {
        val histogram = IntArray((seenBy.maxOrNull() ?: 0) + 1)
        for (count in seenBy) {
            require(count >= 0)
            if (count > 0) histogram[count]++
        }
        return histogram
    }

    private fun build(
        seenHistogram: IntArray,
        usedByPoint: Map<Int, Int>,
        points: List<MultiViewTriangulation.Result>,
        seenBy: IntArray
    ): Report {
        val triangulated = points.count { it is MultiViewTriangulation.Result.Point }
        val maxUsed = usedByPoint.values.maxOrNull() ?: 0
        val used = IntArray(maxUsed + 1)
        for (value in usedByPoint.values) if (value > 0) used[value]++
        val sorted = usedByPoint.values.filter { it > 0 }.sorted()
        val median = if (sorted.isEmpty()) null else {
            if (sorted.size % 2 == 1) sorted[sorted.size / 2].toDouble()
            else (sorted[sorted.size / 2 - 1] + sorted[sorted.size / 2]) / 2.0
        }
        // Punkte mit genau zwei Stützen; ohne Inlier-Daten gibt es dazu keine Aussage.
        val two = if (usedByPoint.isEmpty()) 0 else used.getOrElse(2) { 0 }
        // seenBy wird hier nur zur Vollständigkeitsprüfung genutzt.
        require(seenBy.isEmpty() || seenBy.size == points.size)
        return Report(used, seenHistogram, triangulated, median, two)
    }

    /** Kurzfassung für Dateiköpfe; feste Reihenfolge, damit sie prüfbar bleibt. */
    fun describe(report: Report): String {
        val median = report.medianUsedViews?.let { "%.1f".format(java.util.Locale.ROOT, it) } ?: "n/a"
        val fraction = report.fractionWithThreeOrMore?.let { "%.3f".format(java.util.Locale.ROOT, it) } ?: "n/a"
        return "triangulated=${report.triangulatedPoints} usedViewsMedian=$median " +
            "fractionThreePlus=$fraction twoViewOnly=${report.supportedByTwoViews} " +
            "(view support, not accuracy)"
    }
}

package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.MultiViewTriangulation

/**
 * Warum Landmarks im Teilnetz fehlen, nach Ursache getrennt.
 *
 * Bisher nannte das Ergebnis nur "wie viele Punkte fehlen". Diese Zahl allein
 * ist nicht handlungsfähig: ein Punkt, der in nur einer Ansicht beobachtet
 * wurde, ist etwas anderes als einer, dessen Strahlen zu flach aufeinander
 * stehen, und beides ist etwas anderes als ein Punkt hinter der Kamera.
 *
 * Die Kategorien folgen exakt den Ablehnungsgründen der Triangulation. Sie
 * werden NICHT geschätzt oder aufgeteilt: jeder nicht triangulierte Punkt
 * zählt in genau eine Kategorie. Ist der Grund unbekannt, bleibt er in
 * [UNKNOWN] statt in eine plausible Kategorie zu rutschen.
 */
object MultiViewPointLoss {
    /** Weniger als zwei Beobachtungen: der Punkt ist nicht triangulierbar. */
    const val TOO_FEW_VIEWS = "tooFewViews"
    /** Strahlen stehen zu flach aufeinander; die Tiefe wäre praktisch unbestimmt. */
    const val INSUFFICIENT_PARALLAX = "insufficientParallax"
    /** Punkt liegt hinter mindestens einer Kamera. */
    const val BEHIND_CAMERA = "behindCamera"
    /** Keine stabile Lösung (entartete Geometrie oder zu großer Reprojektionsrest). */
    const val UNSTABLE = "unstableGeometry"
    /** Kein Mehrheitskonsens (nur im robusten Pfad möglich). */
    const val NO_CONSENSUS = "noConsensus"
    /** Ursache nicht bekannt; es wird nichts hineininterpretiert. */
    const val UNKNOWN = "unknown"

    /** Feste Reihenfolge für Anzeige und Dateikopf. */
    val order = listOf(TOO_FEW_VIEWS, INSUFFICIENT_PARALLAX, BEHIND_CAMERA, UNSTABLE, NO_CONSENSUS, UNKNOWN)

    data class Report(
        val counts: Map<String, Int>,
        val triangulated: Int,
        val totalSlots: Int
    ) {
        init {
            require(totalSlots >= triangulated && triangulated >= 0)
            require(counts.keys.all { it in order })
            require(counts.values.all { it >= 0 })
        }

        val missing: Int get() = totalSlots - triangulated
        /** Summe der Kategorien; muss [missing] entsprechen. */
        val categorized: Int get() = counts.values.sum()
        /** true, wenn jede fehlende Stelle genau eine Ursache hat. */
        val complete: Boolean get() = categorized == missing

        fun count(reason: String): Int = counts[reason] ?: 0

        /** Nur die Kategorien mit mindestens einem Punkt, in fester Reihenfolge. */
        fun nonEmpty(): List<Pair<String, Int>> = order.mapNotNull { key ->
            val value = count(key)
            if (value > 0) key to value else null
        }
    }

    /**
     * Ordnet jedem abgelehnten Punkt genau einen Grund zu.
     *
     * @param points Ergebnisse in Landmark-Reihenfolge (Punkt oder Ablehnung).
     * @param seenBy Zahl der beobachtenden Ansichten je Punkt; leer erlaubt.
     */
    fun analyze(points: List<MultiViewTriangulation.Result>, seenBy: IntArray): Report {
        require(seenBy.isEmpty() || seenBy.size == points.size)
        val counts = HashMap<String, Int>()
        var triangulated = 0
        for (i in points.indices) {
            when (val value = points[i]) {
                is MultiViewTriangulation.Result.Point -> triangulated++
                is MultiViewTriangulation.Result.Rejected ->
                    counts.merge(reasonOf(value.reason, seenBy.getOrElse(i) { 0 }), 1, Int::plus)
            }
        }
        return Report(counts, triangulated, points.size)
    }

    /**
     * Übersetzt den Ablehnungsgrund der Triangulation in eine Kategorie.
     * `seen` trennt "gar nicht beobachtet" von echten Geometrieproblemen.
     */
    fun reasonOf(reason: MultiViewTriangulation.Failure, seen: Int): String = when {
        seen < 2 -> TOO_FEW_VIEWS
        reason == MultiViewTriangulation.Failure.INSUFFICIENT_VIEWS -> TOO_FEW_VIEWS
        reason == MultiViewTriangulation.Failure.INSUFFICIENT_PARALLAX -> INSUFFICIENT_PARALLAX
        reason == MultiViewTriangulation.Failure.BEHIND_CAMERA -> BEHIND_CAMERA
        reason == MultiViewTriangulation.Failure.DEGENERATE_GEOMETRY -> UNSTABLE
        reason == MultiViewTriangulation.Failure.REPROJECTION_ERROR -> UNSTABLE
        reason == MultiViewTriangulation.Failure.NO_CONSENSUS -> NO_CONSENSUS
        else -> UNKNOWN
    }

    /** Kurzfassung für Dateiköpfe; feste Reihenfolge, damit sie prüfbar bleibt. */
    fun describe(report: Report): String {
        val parts = order.joinToString(",") { "$it=${report.count(it)}" }
        return "triangulated=${report.triangulated}/${report.totalSlots} missing=${report.missing} $parts " +
            "complete=${report.complete} (rejection reasons, no accuracy statement)"
    }
}

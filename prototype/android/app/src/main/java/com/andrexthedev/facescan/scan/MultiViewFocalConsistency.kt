package com.andrexthedev.facescan.scan

/**
 * Streuung der je Ansicht geschätzten Brennweite.
 *
 * Warum das hier steht: Die Brennweite ist die größte offene Annahme des
 * Mehransichten-Pfads. Sie wird aus einem angenommenen Sichtfeld abgeleitet,
 * und jede Ansicht schätzt sie beim Ankerfit erneut. Weichen diese Schätzungen
 * weit auseinander, ist die gemeinsame Kamera für diese Sitzung schlecht
 * bestimmt – dann sind Tiefenwerte und Triangulation entsprechend unsicher.
 *
 * Was der Bericht LEISTET: eine Aussage über die Selbstkonsistenz der
 * Schätzungen innerhalb einer Sitzung. Er sagt, ob mehrere Ansichten dieselbe
 * Brennweite plausibel finden.
 *
 * Was er NICHT leistet: keine Kalibrierung. Eine systematisch falsche
 * Sichtfeld-Annahme kann von allen Ansichten gleich falsch geschätzt werden und
 * bleibt dann scheinbar konsistent. Es wird nichts korrigiert, nichts
 * nachjustiert und nichts als Genauigkeit ausgegeben.
 */
object MultiViewFocalConsistency {
    /**
     * Relative Spanne, bis zu der die Schätzungen als miteinander verträglich
     * gelten. Startwert, NICHT an realen Kameras oder Gesichtern validiert.
     */
    const val TOLERANCE = 0.15

    /** Kleinste sinnvolle Brennweite in Pixeln; kleinere Werte sind Rechenmüll. */
    private const val MIN_FOCAL_PX = 1.0

    data class Report(
        /** Je Ansicht geschätzte Brennweite in Pixeln, in Aufnahmereihenfolge. */
        val perViewFocalPx: List<Double>,
        val medianFocalPx: Double,
        /** Brennweite aus der Sichtfeld-Annahme; null, wenn nicht übergeben. */
        val assumedFocalPx: Double?,
        /** (größte - kleinste) / Median; null, wenn das nicht rechenbar ist. */
        val relativeSpread: Double?,
        /** true, wenn die relative Spanne die Toleranz nicht überschreitet. */
        val consistent: Boolean
    ) {
        /** Anzahl der Schätzungen; 0 ist kein gültiger Bericht. */
        val viewCount: Int get() = perViewFocalPx.size

        /** Abweichung des Medians von der Annahme, relativ; null ohne Annahme. */
        val deviationFromAssumed: Double?
            get() {
                val assumed = assumedFocalPx ?: return null
                if (!assumed.isFinite() || assumed <= 0.0) return null
                return (medianFocalPx - assumed) / assumed
            }
    }

    /**
     * @param perViewFocalPx Schätzungen je Ansicht; nicht-endliche und
     *   nicht-positive Werte werden verworfen und NICHT ersetzt.
     * @param assumedFocalPx Brennweite der Annahme, nur zum Vergleich.
     * @param tolerance relative Spanne, ab der die Schätzungen auseinanderlaufen.
     * @return null, wenn weniger als zwei brauchbare Schätzungen vorliegen –
     *   eine einzelne Zahl sagt nichts über Streuung aus.
     */
    fun analyze(
        perViewFocalPx: List<Double>,
        assumedFocalPx: Double? = null,
        tolerance: Double = TOLERANCE
    ): Report? {
        require(tolerance.isFinite() && tolerance > 0.0)
        val valid = perViewFocalPx.filter { it.isFinite() && it > MIN_FOCAL_PX }
        if (valid.size < 2) return null
        val sorted = valid.sorted()
        val median = if (sorted.size % 2 == 1) sorted[sorted.size / 2]
        else (sorted[sorted.size / 2 - 1] + sorted[sorted.size / 2]) / 2.0
        if (!median.isFinite() || median <= MIN_FOCAL_PX) return null
        val spread = (sorted.last() - sorted.first()) / median
        val relative = if (spread.isFinite() && spread >= 0.0) spread else null
        val assumed = assumedFocalPx?.takeIf { it.isFinite() && it > MIN_FOCAL_PX }
        return Report(valid, median, assumed, relative, relative != null && relative <= tolerance)
    }

    /**
     * Anteil der Ansichten, deren Schätzung vom Median um höchstens die halbe
     * Toleranz abweicht. Das ist eine Mehrheitsaussage über die Schätzungen,
     * keine Aussage über die Richtigkeit des Medians.
     */
    fun agreeingViews(report: Report, tolerance: Double = TOLERANCE): Int {
        require(tolerance.isFinite() && tolerance > 0.0)
        if (!report.medianFocalPx.isFinite() || report.medianFocalPx <= MIN_FOCAL_PX) return 0
        return report.perViewFocalPx.count { focal ->
            focal.isFinite() && kotlin.math.abs(focal - report.medianFocalPx) / report.medianFocalPx <= tolerance / 2.0
        }
    }

    /** Kurzfassung für Dateiköpfe; feste Reihenfolge, damit sie prüfbar bleibt. */
    fun describe(report: Report): String {
        fun value(input: Double?) =
            if (input == null || !input.isFinite()) "n/a" else "%.4f".format(java.util.Locale.ROOT, input)
        fun focal(input: Double?) =
            if (input == null || !input.isFinite()) "n/a" else "%.1f".format(java.util.Locale.ROOT, input)
        return "views=${report.viewCount} medianFocalPx=${focal(report.medianFocalPx)} " +
            "assumedFocalPx=${focal(report.assumedFocalPx)} relativeSpread=${value(report.relativeSpread)} " +
            "deviationFromAssumed=${value(report.deviationFromAssumed)} consistent=${report.consistent} " +
            "(self-consistency, not calibration)"
    }
}

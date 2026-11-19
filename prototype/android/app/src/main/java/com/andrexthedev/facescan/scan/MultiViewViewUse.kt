package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.ValidatedAnchorPose

/**
 * Was mit den aufgenommenen Ansichten bei der Rekonstruktion passiert ist.
 *
 * Bisher nannte das Ergebnis nur die Zahl der übernommenen Ansichten. Der
 * Nutzer konnte damit nicht erkennen, ob eine Aufnahme schlicht nie
 * gespeichert wurde, ob sie gespeichert wurde und erst in der Rekonstruktion
 * herausfiel, oder wie viele Versuche zu keiner Ansicht gefuehrt haben.
 * Genau diese drei Faelle sind jetzt getrennt.
 *
 * Was der Bericht NICHT ist: keine Aussage ueber die Qualitaet einer Ansicht und
 * keine Aussage ueber die Genauigkeit des Ergebnisses. Eine uebernommene Ansicht
 * kann trotzdem falsch zugeordnet sein; eine verworfene kann am Rand des
 * Bildfelds gelegen haben. Der Bericht zaehlt, was passiert ist, und begruendet
 * es nur so weit, wie der Code den Grund wirklich kennt.
 */
object MultiViewViewUse {
    /** Ansicht wurde gespeichert und hat eine Pose beigetragen. */
    const val USED = "used"

    /**
     * @param storedViews Anzahl der tatsaechlich gespeicherten Ansichten.
     * @param attemptedViews Anzahl der versuchten Aufnahmen; nie kleiner als
     *   [storedViews].
     * @param poses Ergebnisse des Ankerfits je gespeicherter Ansicht in
     *   Aufnahmereihenfolge; null, wenn keine Posen vorliegen.
     */
    data class Report(
        val storedViews: Int,
        val attemptedViews: Int,
        val poses: List<ValidatedAnchorPose.Result>?
    ) {
        init {
            require(storedViews >= 0 && attemptedViews >= storedViews)
            require(poses == null || poses.size == storedViews)
        }

        /** Ansichten mit beitragender Pose. */
        val usedViews: Int get() = poses?.count { it is ValidatedAnchorPose.Result.Pose } ?: 0
        /** Gespeicherte Ansichten ohne beitragende Pose. */
        val storedNotUsed: Int get() = storedViews - usedViews
        /** Versuche, die zu keiner gespeicherten Ansicht gefuehrt haben. */
        val attemptsNotStored: Int get() = attemptedViews - storedViews
        /** Liegen ueberhaupt Posen vor? Ohne sie gibt es keine Ursachen. */
        val hasPoseData: Boolean get() = poses != null
        /** Reicht das Ergebnis fuer eine Rekonstruktion? */
        val sufficient: Boolean get() = usedViews >= 2
        /** Jede nicht beitragende Ansicht hat genau einen bekannten Grund. */
        val complete: Boolean get() = hasPoseData && dropReasons().sumOf { it.second } == storedNotUsed

        /** Gruende der verworfenen Posen, in fester Reihenfolge; nur echte Faelle. */
        fun dropReasons(): List<Pair<AnchorPoseDropReason, Int>> {
            val list = poses ?: return emptyList()
            val counts = HashMap<AnchorPoseDropReason, Int>()
            for (pose in list) if (pose is ValidatedAnchorPose.Result.Rejected)
                counts.merge(AnchorPoseDropReason.of(pose.reason), 1, Int::plus)
            return AnchorPoseDropReason.entries.mapNotNull { key ->
                val value = counts[key] ?: 0
                if (value > 0) key to value else null
            }
        }

        fun reason(reason: AnchorPoseDropReason): Int =
            dropReasons().firstOrNull { it.first == reason }?.second ?: 0
    }

    /** Erzeugt den Bericht; bei fehlenden Posen bleibt der Grund unbekannt. */
    fun analyze(storedViews: Int, attemptedViews: Int, poses: List<ValidatedAnchorPose.Result>?): Report =
        Report(storedViews, attemptedViews, poses)

    /** Kurzfassung fuer Dateikoepfe; feste Reihenfolge, damit sie pruefbar bleibt. */
    fun describe(report: Report): String {
        val reasons = AnchorPoseDropReason.entries.joinToString(",") { "${it.key}=${report.reason(it)}" }
        return "stored=${report.storedViews} used=${report.usedViews} " +
            "notStored=${report.attemptsNotStored} dropped=${report.storedNotUsed} " +
            "reasons=$reasons complete=${report.complete} " +
            "(which views contributed, not accuracy)"
    }
}

/**
 * Warum eine gespeicherte Ansicht keine Pose beigetragen hat. Die Werte sind die
 * Ablehnungsgruende des Ankerfits, nicht neu geschaetzt.
 */
enum class AnchorPoseDropReason(val key: String) {
    INVALID_INPUT("invalidInput"),
    DEGENERATE_ANCHORS("degenerateAnchors"),
    ESTIMATION_FAILED("estimationFailed"),
    BEHIND_CAMERA("behindCamera"),
    HIGH_RESIDUAL("highResidual");

    companion object {
        fun of(reason: ValidatedAnchorPose.Failure): AnchorPoseDropReason = when (reason) {
            ValidatedAnchorPose.Failure.INVALID_INPUT -> INVALID_INPUT
            ValidatedAnchorPose.Failure.DEGENERATE_ANCHORS -> DEGENERATE_ANCHORS
            ValidatedAnchorPose.Failure.ESTIMATION_FAILED -> ESTIMATION_FAILED
            ValidatedAnchorPose.Failure.BEHIND_CAMERA -> BEHIND_CAMERA
            ValidatedAnchorPose.Failure.HIGH_RESIDUAL -> HIGH_RESIDUAL
        }
    }
}

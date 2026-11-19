package com.andrexthedev.facescan.scan

/**
 * Warum eine Mehransichten-Rekonstruktion gescheitert ist, in einer Form, die
 * die Oberflaeche uebersetzen kann.
 *
 * Bisher meldete die App bei jedem Fehlschlag denselben Satz. Das ist nicht
 * handlungsfaehig: "zu wenige brauchbare Posen" verlangt etwas anderes vom
 * Nutzer als "Bildgroesse uneinheitlich" oder "zu viele Ansichten". Die Werte
 * hier sind woertlich die Ablehnungsgruende aus [MultiViewCapture.Failure] und
 * werden NICHT neu interpretiert oder gewichtet.
 *
 * Was das nicht ist: keine Diagnose der Ursache hinter dem Grund. "Zu wenige
 * brauchbare Posen" kann an Licht, an einer falschen Personenzuordnung oder an
 * einem zu kleinen Gesicht liegen; der Code kennt nur den Zaehler, nicht den
 * Grund dahinter.
 */
object MultiViewOutcomeText {
    /** Reihenfolge der Anzeige; nur die Faelle, die der Code wirklich kennt. */
    val order = listOf(
        MultiViewCapture.Failure.INVALID_VIEW,
        MultiViewCapture.Failure.INCONSISTENT_DIMENSIONS,
        MultiViewCapture.Failure.ANCHORS_OUT_OF_FRAME,
        MultiViewCapture.Failure.POSE_REJECTED,
        MultiViewCapture.Failure.INSUFFICIENT_ACCEPTED_VIEWS,
        MultiViewCapture.Failure.EMPTY_CLOUD,
        MultiViewCapture.Failure.TOO_MANY_VIEWS
    )

    init {
        require(order.size == MultiViewCapture.Failure.entries.size)
        require(order.toSet() == MultiViewCapture.Failure.entries.toSet())
    }

    /**
     * Stabiler Schluessel fuer Anzeige und Bericht. Bewusst dieselbe
     * Schreibweise wie die anderen Metadaten (kleiner Anfangsbuchstabe).
     */
    fun key(failure: MultiViewCapture.Failure): String = when (failure) {
        MultiViewCapture.Failure.INVALID_VIEW -> "invalidView"
        MultiViewCapture.Failure.INCONSISTENT_DIMENSIONS -> "inconsistentDimensions"
        MultiViewCapture.Failure.ANCHORS_OUT_OF_FRAME -> "anchorsOutOfFrame"
        MultiViewCapture.Failure.POSE_REJECTED -> "poseRejected"
        MultiViewCapture.Failure.INSUFFICIENT_ACCEPTED_VIEWS -> "insufficientAcceptedViews"
        MultiViewCapture.Failure.EMPTY_CLOUD -> "emptyCloud"
        MultiViewCapture.Failure.TOO_MANY_VIEWS -> "tooManyViews"
    }

    /**
     * Was der Nutzer als Naechstes tun kann. Kurz, ohne Ursachenbehauptung.
     * Jeder Grund hat genau einen Vorschlag; er ist eine Handlungsempfehlung,
     * kein Nachweis der Ursache.
     */
    fun actionKey(failure: MultiViewCapture.Failure): String = when (failure) {
        MultiViewCapture.Failure.INVALID_VIEW -> "retrySmooth"
        MultiViewCapture.Failure.INCONSISTENT_DIMENSIONS -> "restartSession"
        MultiViewCapture.Failure.ANCHORS_OUT_OF_FRAME -> "centerFace"
        MultiViewCapture.Failure.POSE_REJECTED -> "turnFurther"
        MultiViewCapture.Failure.INSUFFICIENT_ACCEPTED_VIEWS -> "turnFurther"
        MultiViewCapture.Failure.EMPTY_CLOUD -> "addView"
        MultiViewCapture.Failure.TOO_MANY_VIEWS -> "restartSession"
    }

    /** Kurzfassung fuer den Geraetebericht; feste Reihenfolge. */
    fun describe(failure: MultiViewCapture.Failure): String =
        "${key(failure)} action=${actionKey(failure)} (reason as reported by the reconstruction)"
}

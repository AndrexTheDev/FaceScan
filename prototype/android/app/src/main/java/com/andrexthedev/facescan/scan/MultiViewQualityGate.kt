package com.andrexthedev.facescan.scan

/**
 * Entscheidet anhand des Bildhinweises, ob eine angeforderte Ansicht
 * übernommen werden darf.
 *
 * Wichtig: Das ist KEINE Qualitäts- oder Genauigkeitsbewertung des Scans und
 * keine Freigabe. Es verhindert nur, dass eine Ansicht ohne auswertbare Pixel
 * (praktisch schwarz oder überstrahlt) als Messung gespeichert wird. Ein
 * verwackeltes Bild wird lediglich gemeldet, nicht verworfen, weil die
 * Schwellen unkalibriert sind und ein verwackeltes Bild noch brauchbare
 * Landmarks liefern kann.
 *
 * [ImageQuality.Hint] ist null, wenn gar kein Bildausschnitt ausgewertet werden
 * konnte (Gesicht zu klein oder außerhalb des Bildes). Dann entscheidet allein
 * die Ankerpose, ob die Ansicht übernommen wird.
 */
object MultiViewQualityGate {
    enum class Decision {
        /** Ansicht darf gespeichert werden. */
        ACCEPT,
        /** Ansicht darf gespeichert werden, wird aber als unsicher gemeldet. */
        WARN,
        /** Ansicht wird nicht gespeichert; es lohnt eine neue Aufnahme. */
        REJECT
    }

    fun decide(hint: ImageQuality.Hint?): Decision = when (hint) {
        ImageQuality.Hint.TOO_DARK, ImageQuality.Hint.TOO_BRIGHT -> Decision.REJECT
        ImageQuality.Hint.POSSIBLY_BLURRY -> Decision.WARN
        ImageQuality.Hint.NO_WARNING, null -> Decision.ACCEPT
    }
}

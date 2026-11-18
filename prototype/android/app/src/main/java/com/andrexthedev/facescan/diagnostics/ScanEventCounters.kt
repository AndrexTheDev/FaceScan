package com.andrexthedev.facescan.diagnostics

/** Nur lokale Zähler ohne Fotos, Punkte, Dateinamen oder einzelne Ereigniszeiten. */
enum class ScanEvent {
    NEUTRAL_ATTEMPT, NEUTRAL_ACCEPTED, NEUTRAL_REJECTED,
    PHOTO_STARTED, PHOTO_ACCEPTED, PHOTO_FAILED, PHOTO_CANCELLED,
    SEQUENCE_STARTED, SEQUENCE_ACCEPTED, SEQUENCE_FAILED, SEQUENCE_CANCELLED,
    GLB_SAVED, OBJ_SAVED, MESH_SAVED, EXPORT_FAILED, EXPORT_CANCELLED,
    MULTIVIEW_ACCEPTED, MULTIVIEW_FAILED
}

class ScanEventCounters {
    private val counts = LongArray(ScanEvent.entries.size)
    @Synchronized fun record(event: ScanEvent) {
        if (counts[event.ordinal] < Long.MAX_VALUE) counts[event.ordinal]++
    }
    @Synchronized fun snapshot(): Map<ScanEvent, Long> = ScanEvent.entries.associateWith { counts[it.ordinal] }
    @Synchronized fun summary(): String {
        fun n(event: ScanEvent) = counts[event.ordinal]
        return """Neutral-Versuche/übernommen/abgelehnt: ${n(ScanEvent.NEUTRAL_ATTEMPT)}/${n(ScanEvent.NEUTRAL_ACCEPTED)}/${n(ScanEvent.NEUTRAL_REJECTED)}
Fotoanforderungen/übernommen/fehlgeschlagen/abgebrochen: ${n(ScanEvent.PHOTO_STARTED)}/${n(ScanEvent.PHOTO_ACCEPTED)}/${n(ScanEvent.PHOTO_FAILED)}/${n(ScanEvent.PHOTO_CANCELLED)}
Mimikaufnahmen gestartet/übernommen/fehlgeschlagen/abgebrochen: ${n(ScanEvent.SEQUENCE_STARTED)}/${n(ScanEvent.SEQUENCE_ACCEPTED)}/${n(ScanEvent.SEQUENCE_FAILED)}/${n(ScanEvent.SEQUENCE_CANCELLED)}
Export gespeichert GLB/OBJ/Teilnetz, fehlgeschlagen/abgebrochen: ${n(ScanEvent.GLB_SAVED)}/${n(ScanEvent.OBJ_SAVED)}/${n(ScanEvent.MESH_SAVED)}, ${n(ScanEvent.EXPORT_FAILED)}/${n(ScanEvent.EXPORT_CANCELLED)}
Mehransichten-Rekonstruktionen rekonstruiert/fehlgeschlagen: ${n(ScanEvent.MULTIVIEW_ACCEPTED)}/${n(ScanEvent.MULTIVIEW_FAILED)}
Zähler seit App-Start; laufende oder durch App-Ende unterbrochene Aktionen müssen nicht in den Ergebnissummen erscheinen. Speichern bestätigt keine Lesbarkeit in Fremdprogrammen."""
    }
}

/** Ausschließlich künstliche Ereignisse, getrennt von den echten Berichts-Zählern. */
object ScanEventCountersSelfTest {
    fun run(): Boolean {
        val counts = ScanEventCounters()
        counts.record(ScanEvent.NEUTRAL_ATTEMPT)
        counts.record(ScanEvent.NEUTRAL_REJECTED)
        counts.record(ScanEvent.EXPORT_CANCELLED)
        val values = counts.snapshot()
        return values[ScanEvent.NEUTRAL_ATTEMPT] == 1L && values[ScanEvent.NEUTRAL_REJECTED] == 1L &&
            values[ScanEvent.EXPORT_CANCELLED] == 1L && values[ScanEvent.GLB_SAVED] == 0L &&
            counts.summary().contains("Neutral-Versuche/übernommen/abgelehnt: 1/0/1")
    }
}

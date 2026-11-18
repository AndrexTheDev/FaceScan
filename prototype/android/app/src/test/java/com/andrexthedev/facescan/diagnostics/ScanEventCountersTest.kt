package com.andrexthedev.facescan.diagnostics

import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class ScanEventCountersTest {
    @Test fun syntheticDeviceTestPasses() { assertTrue(ScanEventCountersSelfTest.run()) }
    @Test fun countsAreIndependentAndContainNoPayload() {
        val counters = ScanEventCounters()
        counters.record(ScanEvent.NEUTRAL_ATTEMPT)
        counters.record(ScanEvent.NEUTRAL_ACCEPTED)
        counters.record(ScanEvent.PHOTO_STARTED)
        counters.record(ScanEvent.PHOTO_CANCELLED)
        counters.record(ScanEvent.GLB_SAVED)
        assertEquals(1L, counters.snapshot()[ScanEvent.NEUTRAL_ATTEMPT])
        assertEquals(0L, counters.snapshot()[ScanEvent.PHOTO_ACCEPTED])
        assertTrue(counters.summary().contains("Neutral-Versuche/übernommen/abgelehnt: 1/1/0"))
        assertTrue(counters.summary().contains("Fotoanforderungen/übernommen/fehlgeschlagen/abgebrochen: 1/0/0/1"))
        assertTrue(counters.summary().contains("Export gespeichert GLB/OBJ/Teilnetz, fehlgeschlagen/abgebrochen: 1/0/0, 0/0"))
        counters.record(ScanEvent.MESH_SAVED)
        assertTrue(counters.summary().contains("Export gespeichert GLB/OBJ/Teilnetz, fehlgeschlagen/abgebrochen: 1/0/1, 0/0"))
        assertTrue(counters.summary().contains("Mehransichten-Rekonstruktionen rekonstruiert/fehlgeschlagen: 0/0"))
        counters.record(ScanEvent.MULTIVIEW_ACCEPTED)
        counters.record(ScanEvent.MULTIVIEW_FAILED)
        counters.record(ScanEvent.MULTIVIEW_FAILED)
        assertTrue(counters.summary().contains("Mehransichten-Rekonstruktionen rekonstruiert/fehlgeschlagen: 1/2"))
        assertTrue(counters.summary().contains("Mehransichten-Ansichten wegen Licht/Helligkeit verworfen: 0"))
        counters.record(ScanEvent.MULTIVIEW_VIEW_REJECTED)
        assertTrue(counters.summary().contains("Mehransichten-Ansichten wegen Licht/Helligkeit verworfen: 1"))
    }
    @Test fun countingIsThreadSafe() {
        val counters = ScanEventCounters()
        val executor = Executors.newFixedThreadPool(4)
        try {
            val tasks = List(4) { executor.submit { repeat(1000) { counters.record(ScanEvent.SEQUENCE_STARTED) } } }
            tasks.forEach { it.get(5, TimeUnit.SECONDS) }
            assertEquals(4000L, counters.snapshot()[ScanEvent.SEQUENCE_STARTED])
        } finally { executor.shutdownNow() }
    }
}

package com.andrexthedev.facescan.scan

import java.util.concurrent.atomic.AtomicLong

/**
 * Einmalige Anforderung einer zusätzlichen Mehransichten-Aufnahme aus dem
 * Analyzer-Thread. Ein Timeout darf nicht in einer späteren Sitzung greifen:
 * deshalb zählt jede Anforderung eine eigene ID, und [take] konsumiert sie nur
 * einmal.
 */
class FaceViewRequest {
    private val pending = AtomicLong(0L)
    private val next = AtomicLong(1L)

    /** Fordert genau eine weitere Ansicht an und liefert deren ID. */
    fun request(): Long {
        var id: Long
        do {
            id = next.incrementAndGet()
            val current = pending.get()
            if (current != 0L) return current
        } while (!pending.compareAndSet(0L, id))
        return id
    }

    /** true, wenn ein angeforderter Frame noch nicht geliefert wurde. */
    fun take(): Boolean {
        while (true) {
            val current = pending.get()
            if (current == 0L) return false
            if (pending.compareAndSet(current, 0L)) return true
        }
    }

    fun cancel() { pending.set(0L) }

    fun isPending(): Boolean = pending.get() != 0L
}

package com.andrexthedev.facescan.scan

import java.util.concurrent.atomic.AtomicLong

/** Einmal-Anforderung: vor Opt-in wird kein Fotoausschnitt erzeugt. */
class FaceTextureRequest {
    private val sequence = AtomicLong(0)
    private val pending = AtomicLong(0)
    fun request(): Long = sequence.incrementAndGet().also { pending.set(it) }
    fun cancel() { pending.set(0) }
    fun take(): Long = pending.getAndSet(0)
}

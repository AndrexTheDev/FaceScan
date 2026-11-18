package com.andrexthedev.facescan.capture

/** Main-Thread-only: ein später Provider-Callback darf nach dem Schließen nichts binden. */
internal class CameraSessionGuard {
    private var closed = false

    fun runIfOpen(block: () -> Unit) {
        if (!closed) block()
    }

    fun close(release: () -> Unit) {
        if (closed) return
        closed = true
        release()
    }
}

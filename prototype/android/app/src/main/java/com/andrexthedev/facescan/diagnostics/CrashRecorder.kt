package com.andrexthedev.facescan.diagnostics

import android.content.Context

/** Letzten Java-Absturz ohne Nachricht, Bilder oder persönliche Eingaben festhalten. */
object CrashRecorder {
    private const val PREFS = "test_diagnostics"
    private const val CRASH = "last_crash"
    private var installed = false

    @Synchronized fun install(context: Context) {
        if (installed) return
        installed = true
        val app = context.applicationContext
        val original = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            try {
                val frames = error.stackTrace.filter { it.className.startsWith("com.andrexthedev.facescan") }
                    .take(8).joinToString("; ") { "${it.className}.${it.methodName}:${it.lineNumber}" }
                val summary = "${error.javaClass.name} | $frames"
                app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(CRASH, summary).commit()
            } catch (_: Throwable) {
                // Die Android-Standardbehandlung darf nie verdeckt werden.
            }
            if (original != null) original.uncaughtException(thread, error)
            else android.os.Process.killProcess(android.os.Process.myPid())
        }
    }

    fun lastCrash(context: Context): String =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(CRASH, null) ?: "-"
}

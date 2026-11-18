package com.andrexthedev.facescan.diagnostics

/** Kein Testfall wird aus unbeschrifteten Kameraframes automatisch als bestanden gezählt. */
internal enum class ChallengeKind { FACE_PRESENT, FACE_ABSENT, OFFLINE }
internal enum class ChallengeOutcome { NOT_RUN, RUNNING, PASSED, FAILED, INCONCLUSIVE, CANCELLED }
internal data class ChallengeResult(
    val outcome: ChallengeOutcome = ChallengeOutcome.NOT_RUN,
    val samples: Int = 0,
    val matches: Int = 0
)

/** Nur unter der Sperre von TestDiagnostics verwenden. */
internal class ChallengeTracker {
    private val results = ChallengeKind.entries.associateWith { ChallengeResult() }.toMutableMap()
    private var running: ChallengeKind? = null
    private var startedAt = 0L

    fun begin(kind: ChallengeKind, nowMs: Long): Boolean {
        if (running != null) return false
        running = kind
        startedAt = nowMs
        results[kind] = ChallengeResult(ChallengeOutcome.RUNNING)
        return true
    }

    fun sample(found: Boolean, frameStartMs: Long) {
        val kind = running ?: return
        if (frameStartMs < startedAt) return // ein vor dem Knopfdruck begonnenes Frame
        val current = results.getValue(kind)
        val match = when (kind) {
            ChallengeKind.FACE_PRESENT -> found
            ChallengeKind.FACE_ABSENT -> !found
            ChallengeKind.OFFLINE -> true // nur erfolgreich ausgewertete Frames
        }
        results[kind] = current.copy(samples = current.samples + 1,
            matches = current.matches + if (match) 1 else 0)
    }

    fun finish(offlineStillConfirmed: Boolean = true) {
        val kind = running ?: return
        val current = results.getValue(kind)
        val outcome = when {
            kind == ChallengeKind.OFFLINE && !offlineStillConfirmed -> ChallengeOutcome.INCONCLUSIVE
            current.samples < 3 -> ChallengeOutcome.INCONCLUSIVE
            current.matches * 4 >= current.samples * 3 -> ChallengeOutcome.PASSED
            else -> ChallengeOutcome.FAILED
        }
        results[kind] = current.copy(outcome = outcome)
        running = null
    }

    fun cancel() {
        val kind = running ?: return
        results[kind] = results.getValue(kind).copy(outcome = ChallengeOutcome.CANCELLED)
        running = null
    }

    fun result(kind: ChallengeKind): ChallengeResult = results.getValue(kind)
}

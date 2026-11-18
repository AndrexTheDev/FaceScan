package com.andrexthedev.facescan.diagnostics

import org.junit.Assert.*
import org.junit.Test

class ChallengeTrackerTest {
    @Test fun faceTestRequiresThreeSamplesAndAtLeastSeventyFivePercent() {
        val tracker = ChallengeTracker()
        assertTrue(tracker.begin(ChallengeKind.FACE_PRESENT, 100))
        tracker.sample(true, 99) // begonnen bevor der Nutzer den Test gestartet hat
        tracker.sample(true, 101)
        tracker.sample(true, 102)
        tracker.finish()
        assertEquals(ChallengeOutcome.INCONCLUSIVE, tracker.result(ChallengeKind.FACE_PRESENT).outcome)
        assertTrue(tracker.begin(ChallengeKind.FACE_PRESENT, 200))
        repeat(3) { tracker.sample(true, 201) }
        tracker.sample(false, 201)
        tracker.finish()
        assertEquals(ChallengeOutcome.PASSED, tracker.result(ChallengeKind.FACE_PRESENT).outcome)
        assertEquals(4, tracker.result(ChallengeKind.FACE_PRESENT).samples)
    }

    @Test fun noFaceTestFailsIfMostFramesContainAFace() {
        val tracker = ChallengeTracker()
        tracker.begin(ChallengeKind.FACE_ABSENT, 0)
        tracker.sample(false, 1)
        repeat(3) { tracker.sample(true, 1) }
        tracker.finish()
        assertEquals(ChallengeOutcome.FAILED, tracker.result(ChallengeKind.FACE_ABSENT).outcome)
        assertEquals(1, tracker.result(ChallengeKind.FACE_ABSENT).matches)
    }

    @Test fun offlineTestIsInconclusiveIfOfflineStateWasLost() {
        val tracker = ChallengeTracker()
        tracker.begin(ChallengeKind.OFFLINE, 0)
        repeat(5) { tracker.sample(true, 1) }
        tracker.finish(offlineStillConfirmed = false)
        assertEquals(ChallengeOutcome.INCONCLUSIVE, tracker.result(ChallengeKind.OFFLINE).outcome)
    }

    @Test fun interruptedTestIsCancelledAndCannotOverlapAnother() {
        val tracker = ChallengeTracker()
        assertTrue(tracker.begin(ChallengeKind.FACE_PRESENT, 0))
        assertFalse(tracker.begin(ChallengeKind.FACE_ABSENT, 0))
        tracker.sample(true, 1)
        tracker.cancel()
        assertEquals(ChallengeOutcome.CANCELLED, tracker.result(ChallengeKind.FACE_PRESENT).outcome)
        assertTrue(tracker.begin(ChallengeKind.FACE_ABSENT, 2))
        repeat(3) { tracker.sample(false, 3) }
        tracker.finish()
        assertEquals(ChallengeOutcome.PASSED, tracker.result(ChallengeKind.FACE_ABSENT).outcome)
    }

    @Test fun offlineTestAcceptsEitherDetectionResult() {
        val tracker = ChallengeTracker()
        tracker.begin(ChallengeKind.OFFLINE, 0)
        tracker.sample(true, 1)
        tracker.sample(false, 1)
        tracker.sample(false, 1)
        tracker.finish(offlineStillConfirmed = true)
        assertEquals(ChallengeOutcome.PASSED, tracker.result(ChallengeKind.OFFLINE).outcome)
    }
}

package com.andrexthedev.facescan.capture

import org.junit.Assert.assertEquals
import org.junit.Test

class CameraSessionGuardTest {
    @Test
    fun callbackWhileOpenRuns() {
        val guard = CameraSessionGuard()
        var calls = 0
        guard.runIfOpen { calls++ }
        assertEquals(1, calls)
    }

    @Test
    fun lateProviderCallbackIsIgnoredAfterClose() {
        val guard = CameraSessionGuard()
        var binds = 0
        var releases = 0
        guard.close { releases++ }
        guard.runIfOpen { binds++ }
        assertEquals(0, binds)
        assertEquals(1, releases)
    }

    @Test
    fun closingTwiceReleasesOnlyOnceAndStaysClosed() {
        val guard = CameraSessionGuard()
        val events = mutableListOf<String>()
        guard.runIfOpen { events.add("bind") }
        guard.close { events.add("release") }
        guard.close { events.add("release") }
        guard.runIfOpen { events.add("late bind") }
        assertEquals(listOf("bind", "release"), events)
    }
}

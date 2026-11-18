package com.andrexthedev.facescan.perception

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class FrameClockTest {
    @Test
    fun firstFrameIsProcessedAndExcessFramesAreDropped() {
        val clock = FrameClock(minIntervalMs = 250)
        assertEquals(100L, clock.nextTimestamp(100_000_000L, 10_000L))
        assertNull(clock.nextTimestamp(150_000_000L, 10_249L))
        assertEquals(350L, clock.nextTimestamp(350_000_000L, 10_250L))
    }

    @Test
    fun timestampsRemainStrictlyIncreasingEvenIfCameraRepeatsOrMovesBack() {
        val clock = FrameClock(minIntervalMs = 250)
        assertEquals(100L, clock.nextTimestamp(100_100_000L, 0L))
        assertEquals(101L, clock.nextTimestamp(100_900_000L, 250L))
        assertEquals(102L, clock.nextTimestamp(90_000_000L, 500L))
        assertEquals(200L, clock.nextTimestamp(200_000_000L, 750L))
    }

    @Test
    fun aNewSessionStartsWithFreshTimingState() {
        val first = FrameClock()
        assertEquals(900L, first.nextTimestamp(900_000_000L, 0L))
        val second = FrameClock()
        assertEquals(1L, second.nextTimestamp(1_000_000L, 0L))
    }
}

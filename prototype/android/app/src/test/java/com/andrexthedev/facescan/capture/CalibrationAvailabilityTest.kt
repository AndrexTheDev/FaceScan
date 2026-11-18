package com.andrexthedev.facescan.capture

import org.junit.Assert.*
import org.junit.Test

class CalibrationAvailabilityTest {
    @Test fun metadataIsOnlyClassifiedNotUsedAsCalibration() {
        val all = CalibrationAvailability.classify(floatArrayOf(1000f, 1001f, 500f, 400f, 0f), FloatArray(5), 4000, 3000)
        assertEquals(CalibrationAvailability.State.PRESENT, all.intrinsics)
        assertEquals(CalibrationAvailability.State.PRESENT, all.distortion)
        assertEquals(CalibrationAvailability.State.PRESENT, all.activeArray)
        val absent = CalibrationAvailability.classify(null, null, null, null)
        assertEquals(CalibrationAvailability.State.MISSING, absent.intrinsics)
        assertEquals(CalibrationAvailability.State.MISSING, absent.distortion)
        assertEquals(CalibrationAvailability.State.MISSING, absent.activeArray)
        val invalid = CalibrationAvailability.classify(floatArrayOf(0f, 1f, 0f, 0f, 0f), floatArrayOf(Float.NaN), 0, 100)
        assertEquals(CalibrationAvailability.State.INVALID, invalid.intrinsics)
        assertEquals(CalibrationAvailability.State.INVALID, invalid.distortion)
        assertEquals(CalibrationAvailability.State.INVALID, invalid.activeArray)
        assertEquals(CalibrationAvailability.State.INVALID, CalibrationAvailability.classify(floatArrayOf(1f), null, 1, 1).intrinsics)
        assertEquals(CalibrationAvailability.State.UNKNOWN, CalibrationAvailability.UNKNOWN.intrinsics)
    }
}

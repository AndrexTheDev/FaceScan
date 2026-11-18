package com.andrexthedev.facescan.geometry

import org.junit.Assert.assertTrue
import org.junit.Test

class GeometrySelfTestTest {
    @Test fun bundledSyntheticFixtureMatchesF1AndF2Reference() {
        val result = GeometrySelfTest.run()
        assertTrue(result.details, result.passed)
        assertTrue(result.details.contains("F1 bestanden"))
        assertTrue(result.details.contains("F2 bestanden"))
    }
}

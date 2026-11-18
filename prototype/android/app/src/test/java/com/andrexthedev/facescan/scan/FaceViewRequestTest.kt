package com.andrexthedev.facescan.scan

import org.junit.Assert.*
import org.junit.Test

class FaceViewRequestTest {
    @Test fun requestIsConsumedExactlyOnce() {
        val request = FaceViewRequest()
        assertFalse(request.take())
        val id = request.request()
        assertTrue(id > 0)
        assertTrue(request.isPending())
        assertTrue(request.take())
        assertFalse(request.isPending())
        assertFalse(request.take())
        // Eine zweite Anforderung liefert eine neue ID, keinen Altwert.
        val second = request.request()
        assertTrue(second > id)
        request.cancel()
        assertFalse(request.take())
    }

    @Test fun repeatedRequestsWhilePendingKeepTheSameId() {
        val request = FaceViewRequest()
        val first = request.request()
        assertEquals(first, request.request())
        assertTrue(request.take())
        assertTrue(request.request() > first)
    }
}

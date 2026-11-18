package com.andrexthedev.facescan.model

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest

class ModelInstallerTest {
    @get:Rule val folder = TemporaryFolder()
    private val data = "known model bytes".toByteArray()
    private val hash = MessageDigest.getInstance("SHA-256").digest(data)
        .joinToString("") { "%02x".format(it.toInt() and 0xff) }

    @Test fun downloadsOnceAndReusesVerifiedFileOffline() {
        var calls = 0
        val installer = ModelInstaller(folder.root, hash, 100) {
            calls++
            if (calls > 1) throw IOException("offline")
            ByteArrayInputStream(data)
        }
        assertArrayEquals(data, installer.ensureInstalled().readBytes())
        assertArrayEquals(data, installer.ensureInstalled().readBytes())
        assertEquals(1, calls)
    }

    @Test fun corruptCachedFileIsReplaced() {
        folder.root.resolve("face_landmarker.task").writeText("bad")
        val installer = ModelInstaller(folder.root, hash, 100) { ByteArrayInputStream(data) }
        assertArrayEquals(data, installer.ensureInstalled().readBytes())
    }

    @Test fun wrongHashLeavesNoUsableFileOrPartialFile() {
        val installer = ModelInstaller(folder.root, hash, 100) { ByteArrayInputStream("tampered".toByteArray()) }
        try { installer.ensureInstalled(); fail("Expected integrity failure") } catch (_: IOException) { }
        assertFalse(folder.root.resolve("face_landmarker.task").exists())
        assertFalse(folder.root.resolve("face_landmarker.task.part").exists())
    }

    @Test fun oversizedDownloadIsDiscarded() {
        val installer = ModelInstaller(folder.root, hash, 4) { ByteArrayInputStream(data) }
        try { installer.ensureInstalled(); fail("Expected size failure") } catch (_: IOException) { }
        assertFalse(folder.root.resolve("face_landmarker.task").exists())
        assertFalse(folder.root.resolve("face_landmarker.task.part").exists())
    }

    @Test fun interruptedDownloadCanBeRetried() {
        var offline = true
        val installer = ModelInstaller(folder.root, hash, 100) {
            if (offline) throw IOException("offline")
            ByteArrayInputStream(data)
        }
        try { installer.ensureInstalled(); fail("Expected network failure") } catch (_: IOException) { }
        offline = false
        assertArrayEquals(data, installer.ensureInstalled().readBytes())
    }
    @Test fun partialReadFailureIsRemovedAndCanBeRetried() {
        var broken = true
        val installer = ModelInstaller(folder.root, hash, 100) {
            if (!broken) ByteArrayInputStream(data) else object : InputStream() {
                var emitted = false
                override fun read(): Int {
                    if (emitted) throw IOException("interrupted")
                    emitted = true
                    return data[0].toInt() and 0xff
                }
            }
        }
        try { installer.ensureInstalled(); fail("Expected interrupted download") } catch (_: IOException) { }
        assertFalse(folder.root.resolve("face_landmarker.task.part").exists())
        assertFalse(folder.root.resolve("face_landmarker.task").exists())
        broken = false
        assertArrayEquals(data, installer.ensureInstalled().readBytes())
    }

}

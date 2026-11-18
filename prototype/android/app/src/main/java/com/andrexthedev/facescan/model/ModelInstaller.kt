package com.andrexthedev.facescan.model

import java.io.File
import java.io.FilterInputStream
import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest
import javax.net.ssl.HttpsURLConnection

class ModelHttpException(val status: Int) : IOException("HTTP $status")
class ModelTooLargeException : IOException("Model too large")
class ModelIntegrityException : IOException("Model integrity check failed")

/** Fester, versionierter Hersteller-Download; Hash und Größe werden vor Nutzung geprüft. */
object FaceModel {
    const val URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    const val SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
    const val MAX_BYTES = 10L * 1024 * 1024

    fun download(): InputStream {
        val connection = java.net.URL(URL).openConnection() as HttpsURLConnection
        connection.connectTimeout = 15_000
        connection.readTimeout = 30_000
        connection.instanceFollowRedirects = false
        connection.useCaches = false
        try {
            if (connection.responseCode != 200) throw ModelHttpException(connection.responseCode)
            if (connection.contentLengthLong > MAX_BYTES) throw ModelTooLargeException()
            return object : FilterInputStream(connection.inputStream) {
                override fun close() { try { super.close() } finally { connection.disconnect() } }
            }
        } catch (e: Exception) {
            connection.disconnect()
            throw e
        }
    }
}

/** Kein Android-Code, damit Cache, Hashprüfung und Fehlerpfade unit-testbar sind. */
class ModelInstaller(
    private val directory: File,
    private val expectedSha256: String = FaceModel.SHA256,
    private val maxBytes: Long = FaceModel.MAX_BYTES,
    private val download: () -> InputStream = FaceModel::download
) {
    companion object { private val installationLock = Any() }

    fun ensureInstalled(): File = synchronized(installationLock) { install() }

    private fun install(): File {
        if (!directory.exists() && !directory.mkdirs()) throw IOException("Cannot create model directory")
        val model = File(directory, "face_landmarker.task")
        val temporary = File(directory, "face_landmarker.task.part")
        // Abgebrochene Downloads werden nie als Modell akzeptiert.
        temporary.delete()
        if (model.isFile && validHash(model)) return model
        if (model.exists() && !model.delete()) throw IOException("Cannot remove invalid model")
        try {
            download().use { source ->
                temporary.outputStream().buffered().use { output ->
                    val buffer = ByteArray(16 * 1024)
                    var size = 0L
                    while (true) {
                        val count = source.read(buffer)
                        if (count < 0) break
                        if (count == 0) continue
                        size += count
                        if (size > maxBytes) throw ModelTooLargeException()
                        output.write(buffer, 0, count)
                    }
                }
            }
            if (!validHash(temporary)) throw ModelIntegrityException()
            if (!temporary.renameTo(model)) throw IOException("Cannot save model")
            return model
        } finally {
            temporary.delete()
        }
    }

    private fun validHash(file: File): Boolean {
        if (!file.isFile || file.length() <= 0 || file.length() > maxBytes) return false
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { stream ->
            val buffer = ByteArray(16 * 1024)
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) break
                if (count > 0) digest.update(buffer, 0, count)
            }
        }
        val actual = digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
        return actual == expectedSha256
    }
}

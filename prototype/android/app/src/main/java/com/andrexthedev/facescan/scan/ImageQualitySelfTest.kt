package com.andrexthedev.facescan.scan

/** Tests ausschließlich mit künstlichen Grauwerten, kein Rückschluss auf reale Scanqualität. */
object ImageQualitySelfTest {
    fun run(): Boolean {
        val dark = ByteArray(64*64)
        val bright = ByteArray(64*64) { 255.toByte() }
        val flat = ByteArray(64*64) { 128.toByte() }
        val pattern = ByteArray(64*64) { i -> if ((i / 64 + i % 64) % 2 == 0) 90.toByte() else 180.toByte() }
        return ImageQuality.analyze(dark, 64, 64, 64).hint == ImageQuality.Hint.TOO_DARK &&
            ImageQuality.analyze(bright, 64, 64, 64).hint == ImageQuality.Hint.TOO_BRIGHT &&
            ImageQuality.analyze(flat, 64, 64, 64).hint == ImageQuality.Hint.POSSIBLY_BLURRY &&
            ImageQuality.analyze(pattern, 64, 64, 64).hint == ImageQuality.Hint.NO_WARNING
    }
}

package com.andrexthedev.facescan.scan

import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Schnelltest mit künstlichen Punkten; sagt nichts über echte Scan-Genauigkeit aus. */
object ScanSelfTest {
    fun run(): Boolean {
        val points = FloatArray(FaceTopology.VERTEX_COUNT * 3) { i ->
            when (i % 3) {
                0 -> 0.2f + (i / 3 % 20) * 0.02f
                1 -> 0.2f + (i / 3 / 20) * 0.02f
                else -> -0.01f
            }
        }
        points[33 * 3] = 0.3f; points[33 * 3 + 1] = 0.4f
        points[263 * 3] = 0.7f; points[263 * 3 + 1] = 0.4f
        val buffer = FaceFrameBuffer()
        for (t in 1L..3L) buffer.add(FaceFrame(points, 640, 480, t * 100))
        val neutral = buffer.snapshot(300) ?: return false
        val changed = points.copyOf().apply { this[13 * 3 + 1] += 0.04f }
        val expression = FaceSnapshot(changed, 640, 480, 0.0, 1)
        val surface = FaceSurfaceBuilder.build(neutral, expression)
        if (surface.neutral.contentEquals(surface.expression)) return false
        val bytes = GlbWriter.write(surface)
        val glb = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        if (glb.int != 0x46546c67 || glb.int != 2 || glb.int != bytes.size) return false
        val jsonLength = glb.int
        if (jsonLength <= 0 || jsonLength % 4 != 0 || jsonLength > glb.remaining() - 12 || glb.int != 0x4e4f534a) return false
        val jsonBytes = ByteArray(jsonLength); glb.get(jsonBytes)
        val json = String(jsonBytes, Charsets.UTF_8)
        if (!json.contains("\"animations\"") || !json.contains("\"targets\"")) return false
        val binaryLength = glb.int
        return glb.int == 0x004e4942 && binaryLength == glb.remaining()
    }
}

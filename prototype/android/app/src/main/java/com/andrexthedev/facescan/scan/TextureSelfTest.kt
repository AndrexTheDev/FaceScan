package com.andrexthedev.facescan.scan

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Canvas
import kotlin.math.abs

/** Testbild mit künstlichem Farbverlauf – keine Kamera oder Gesichter beteiligt. */
object TextureSelfTest {
    fun run(): Boolean {
        val bitmap = Bitmap.createBitmap(80, 80, Bitmap.Config.ARGB_8888)
        try {
            for (y in 0 until 80) for (x in 0 until 80) bitmap.setPixel(x, y, Color.rgb(x * 3, y * 3, 80))
            val points = FloatArray(468 * 3) { i ->
                when (i % 3) {
                    0 -> 0.2f + (i / 3 % 20) * 0.03f
                    1 -> 0.2f + (i / 3 / 20) * 0.025f
                    else -> 0f
                }
            }
            points[33 * 3] = 0.3f; points[33 * 3 + 1] = 0.4f
            points[263 * 3] = 0.7f; points[263 * 3 + 1] = 0.4f
            val texture = FaceTextureCapture.capture(bitmap, points)
            if (texture.uv.size != 936 || texture.uv.any { it !in 0f..1f }) return false
            val decoded = BitmapFactory.decodeByteArray(texture.jpeg, 0, texture.jpeg.size) ?: return false
            try {
                val i = 13
                val x = (texture.uv[2*i] * decoded.width).toInt().coerceIn(0, decoded.width - 1)
                val y = (texture.uv[2*i+1] * decoded.height).toInt().coerceIn(0, decoded.height - 1)
                val color = decoded.getPixel(x, y)
                if (abs(Color.red(color) - (points[3*i] * 80).toInt() * 3) > 15 ||
                    abs(Color.green(color) - (points[3*i+1] * 80).toInt() * 3) > 15) return false
                val snapshot = FaceSnapshot(points, 80, 80, 0.0, 3, texture)
                val surface = FaceSurfaceBuilder.build(snapshot, snapshot).copy(texture = texture)
                // Beiden Vorschaupfaden nur synthetische Daten übergeben.
                val target = Bitmap.createBitmap(160, 160, Bitmap.Config.ARGB_8888)
                try {
                    for (withTexture in listOf(false, true)) {
                        target.eraseColor(Color.BLACK)
                        FaceMeshRenderer.draw(Canvas(target), 160f, 160f, surface.neutral, 0f,
                            if (withTexture) texture else null, if (withTexture) decoded else null)
                        var colored = 0
                        for (py in 0 until 160) for (px in 0 until 160) {
                            if (target.getPixel(px, py) != Color.BLACK) colored++
                        }
                        if (colored < 50) return false
                    }
                } finally { target.recycle() }
                val glb = GlbWriter.write(surface)
                if (!String(glb, Charsets.ISO_8859_1).contains("image/jpeg")) return false
                val obj = String(ObjWriter.write(surface), Charsets.UTF_8)
                return obj.lineSequence().count { it.startsWith("v ") } == 468 &&
                    obj.lineSequence().count { it.startsWith("f ") } == 898
            } finally { decoded.recycle() }
        } finally { bitmap.recycle() }
    }
}

package com.andrexthedev.facescan.scan

import android.graphics.Bitmap
import android.graphics.BitmapShader
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Shader
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/** Einfache orthografische Software-/Canvas-Vorschau, keine photometrische Rekonstruktion. */
object FaceMeshRenderer {
    fun draw(canvas: Canvas, width: Float, height: Float, points: FloatArray, yaw: Float, texture: FaceTexture?, bitmap: Bitmap?) {
        require(points.size == FaceTopology.VERTEX_COUNT * 3 && points.all { it.isFinite() })
        if (width <= 0 || height <= 0 || !yaw.isFinite()) return
        val n = FaceTopology.VERTEX_COUNT
        val c = cos(yaw); val s = sin(yaw)
        val size = minOf(width, height) * 0.27f
        val xy = FloatArray(n * 2)
        val rotated = FloatArray(n * 3)
        for (i in 0 until n) {
            val x = points[3*i]; val y = points[3*i+1]; val z = points[3*i+2]
            val rx = x*c + z*s; val rz = -x*s + z*c
            rotated[3*i] = rx; rotated[3*i+1] = y; rotated[3*i+2] = rz
            xy[2*i] = width*0.5f + rx*size; xy[2*i+1] = height*0.36f - y*size
        }
        val triangles = FaceTopology.triangles
        // Painter-Sortierung ist nur eine Näherung, kein Z-Buffer.
        val order = (0 until triangles.size / 3).sortedBy { t ->
            (rotated[3*triangles[3*t]+2] + rotated[3*triangles[3*t+1]+2] + rotated[3*triangles[3*t+2]+2]) / 3f
        }
        val indices = ShortArray(triangles.size)
        for (i in order.indices) for (j in 0..2) indices[3*i+j] = triangles[3*order[i]+j].toShort()
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE }
        val validTexture = texture != null && bitmap != null && !bitmap.isRecycled &&
            texture.uv.size == n*2 && texture.uv.all { it.isFinite() && it in 0f..1f }
        val uv = if (validTexture) FloatArray(n * 2) { i ->
            texture!!.uv[i] * if (i % 2 == 0) bitmap!!.width else bitmap!!.height
        } else null
        val colors = if (!validTexture) {
            val normals = FloatArray(n*3)
            for (t in triangles.indices step 3) {
                val a = triangles[t]; val b = triangles[t+1]; val d = triangles[t+2]
                val abx=rotated[3*b]-rotated[3*a]; val aby=rotated[3*b+1]-rotated[3*a+1]; val abz=rotated[3*b+2]-rotated[3*a+2]
                val acx=rotated[3*d]-rotated[3*a]; val acy=rotated[3*d+1]-rotated[3*a+1]; val acz=rotated[3*d+2]-rotated[3*a+2]
                val nx=aby*acz-abz*acy; val ny=abz*acx-abx*acz; val nz=abx*acy-aby*acx
                for (v in intArrayOf(a,b,d)) { normals[3*v]+=nx; normals[3*v+1]+=ny; normals[3*v+2]+=nz }
            }
            IntArray(n) { i ->
                val x=normals[3*i]; val y=normals[3*i+1]; val z=normals[3*i+2]
                val len=sqrt(x*x+y*y+z*z)
                val light = if (len > 1e-8f) 0.35f + 0.65f * kotlin.math.abs(z / len) else 0.5f
                Color.rgb((191*light).toInt().coerceIn(0,255), (158*light).toInt().coerceIn(0,255), (140*light).toInt().coerceIn(0,255))
            }
        } else null
        if (validTexture) paint.shader = BitmapShader(bitmap!!, Shader.TileMode.CLAMP, Shader.TileMode.CLAMP)
        canvas.drawVertices(Canvas.VertexMode.TRIANGLES, xy.size, xy, 0, uv, 0, colors, 0, indices, 0, indices.size, paint)
    }
}

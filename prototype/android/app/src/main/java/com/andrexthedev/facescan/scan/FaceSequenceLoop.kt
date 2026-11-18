package com.andrexthedev.facescan.scan

/** Erzeugt optional einen künstlichen Übergang zurück zur Neutralform. */
object FaceSequenceLoop {
    const val RETURN_SECONDS = 0.5f
    fun close(surface: FaceSurface): FaceSurface {
        val keys = surface.keyframes()
        val size = FaceTopology.VERTEX_COUNT * 3
        require(keys.size in 2..FaceSequenceRecorder.MAX_FRAMES + 1)
        require(surface.neutral.size == size && surface.neutral.all { it.isFinite() })
        require(keys.first().seconds == 0f && keys.first().points.contentEquals(surface.neutral))
        keys.forEachIndexed { i, frame ->
            require(frame.seconds.isFinite() && frame.points.size == size && frame.points.all { it.isFinite() })
            if (i > 0) require(frame.seconds > keys[i - 1].seconds)
        }
        val end = keys.last().seconds + RETURN_SECONDS
        require(end.isFinite() && end > keys.last().seconds)
        val neutral = surface.neutral.copyOf()
        return surface.copy(expression = neutral, sequence = keys + FaceKeyframe(end, neutral))
    }
}

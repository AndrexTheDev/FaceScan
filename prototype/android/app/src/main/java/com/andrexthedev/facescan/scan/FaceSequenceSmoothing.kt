package com.andrexthedev.facescan.scan

/** Optionaler zeitlicher Tiefpass für vorhandene Formen, keine neue Geometrie. */
object FaceSequenceSmoothing {
    // Heuristischer Startwert, nicht anhand echter Aufnahmen optimiert.
    const val TIME_CONSTANT_SECONDS = 0.12

    /**
     * Ein kausaler, zeitabhängiger Tiefpass pro Koordinate. Der erste (neutrale)
     * Keyframe bleibt unverändert; Eingaben und Zeitstempel werden nicht verändert.
     * Bewegungen werden verzögert und abgeschwächt, kurze Ausdrücke können verloren gehen.
     */
    fun smooth(surface: FaceSurface): FaceSurface {
        val keys = surface.keyframes()
        val size = FaceTopology.VERTEX_COUNT * 3
        require(keys.size in 2..FaceSequenceRecorder.MAX_FRAMES + 1)
        require(surface.neutral.size == size && surface.neutral.all { it.isFinite() })
        require(keys.first().seconds == 0f && keys.first().points.contentEquals(surface.neutral))
        keys.forEachIndexed { index, key ->
            require(key.seconds.isFinite() && key.points.size == size && key.points.all { it.isFinite() })
            if (index > 0) require(key.seconds > keys[index - 1].seconds)
        }
        val filtered = ArrayList<FaceKeyframe>(keys.size)
        var previous = keys.first().points.copyOf()
        filtered.add(FaceKeyframe(keys.first().seconds, previous))
        for (i in 1 until keys.size) {
            val dt = keys[i].seconds.toDouble() - keys[i - 1].seconds.toDouble()
            val alpha = dt / (TIME_CONSTANT_SECONDS + dt)
            val current = FloatArray(size) { j ->
                // Double vermeidet Überlauf bei großen, aber endlichen Float-Eingaben.
                (previous[j].toDouble() * (1.0 - alpha) + keys[i].points[j].toDouble() * alpha).toFloat()
            }
            require(current.all { it.isFinite() })
            filtered.add(FaceKeyframe(keys[i].seconds, current))
            previous = current
        }
        return surface.copy(expression = filtered.last().points, sequence = filtered)
    }
}

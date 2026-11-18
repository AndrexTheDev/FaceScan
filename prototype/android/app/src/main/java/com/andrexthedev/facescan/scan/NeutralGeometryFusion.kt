package com.andrexthedev.facescan.scan

/**
 * Kombiniert mehrfach erkannte neutrale Oberflächen aus derselben Ansicht.
 * Starre Ausrichtung + koordinatenweiser Median mindern einzelne Ausreißer;
 * die Eingaben bleiben monokular und nicht metrisch kalibriert.
 */
object NeutralGeometryFusion {
    const val MIN_FRAMES = 3
    const val MAX_FRAMES = 5
    // Experimenteller Wert in normierten Augenabständen, keine Genauigkeitsgrenze.
    const val MAX_ANCHOR_RMS = 0.06

    data class Result(val points: FloatArray, val accepted: IntArray, val maxAnchorRms: Double)

    fun fuse(frames: List<FloatArray>): Result? {
        if (frames.size !in MIN_FRAMES..MAX_FRAMES) return null
        val candidates = frames.indices.filter { i ->
            val points = frames[i]
            points.size == FaceTopology.VERTEX_COUNT * 3 && points.all { it.isFinite() } && try {
                FaceAlignment.align(points, points)
                true
            } catch (_: IllegalArgumentException) { false }
        }
        if (candidates.size < MIN_FRAMES) return null
        // Medoid statt erster/letzter Frame: ein einzelner Anker-Ausreißer soll
        // nicht alle anderen Frames aus dem Konsens drängen.
        var bestIndex = -1
        var bestCount = 0
        var bestSum = Double.POSITIVE_INFINITY
        for (ref in candidates) {
            var count = 0
            var sum = 0.0
            for (candidate in candidates) {
                val rms = try { FaceAlignment.align(frames[ref], frames[candidate]).anchorRms }
                    catch (_: IllegalArgumentException) { Double.POSITIVE_INFINITY }
                if (rms <= MAX_ANCHOR_RMS) { count++; sum += rms }
            }
            if (count > bestCount || (count == bestCount && sum <= bestSum)) {
                bestIndex = ref; bestCount = count; bestSum = sum
            }
        }
        if (bestIndex < 0 || bestCount < MIN_FRAMES) return null
        val aligned = mutableListOf<FloatArray>()
        val accepted = mutableListOf<Int>()
        var worst = 0.0
        for (index in candidates) {
            val fit = try { FaceAlignment.align(frames[bestIndex], frames[index]) }
                catch (_: IllegalArgumentException) { continue }
            if (fit.anchorRms <= MAX_ANCHOR_RMS) {
                aligned.add(fit.points); accepted.add(index); worst = maxOf(worst, fit.anchorRms)
            }
        }
        if (aligned.size < MIN_FRAMES) return null
        val size = FaceTopology.VERTEX_COUNT * 3
        val result = FloatArray(size)
        val values = FloatArray(aligned.size)
        for (i in 0 until size) {
            for (j in aligned.indices) values[j] = aligned[j][i]
            values.sort()
            val mid = values.size / 2
            result[i] = if (values.size % 2 == 1) values[mid] else (values[mid-1] + values[mid]) * 0.5f
            if (!result[i].isFinite()) return null
        }
        return Result(result, accepted.toIntArray(), worst)
    }
}

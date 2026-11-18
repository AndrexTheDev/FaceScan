package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.AnchoredMultiView

/** Experimentelle Pipeline für explizit kalibrierte Daten; kein aktiver Kameraablauf. */
object AnchoredFaceReconstruction {
    data class Result(val reconstruction: AnchoredMultiView.Result, val surface: PartialFaceMesh.Result?)

    fun reconstruct(views: List<AnchoredMultiView.View>, maxEdgeLength: Double? = null): Result {
        require(views.all { it.points.size == FaceTopology.VERTEX_COUNT })
        val result = AnchoredMultiView.reconstruct(views)
        return Result(result, result.cloud?.let { PartialFaceMesh.build(it, maxEdgeLength) })
    }
}

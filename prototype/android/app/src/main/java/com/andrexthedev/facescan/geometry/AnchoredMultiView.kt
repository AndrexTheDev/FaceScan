package com.andrexthedev.facescan.geometry

/** End-to-end-Baustein für vorgegebene 3D-Anker und kalibrierte Pixel; kein Kamera-Capture. */
object AnchoredMultiView {
    data class View(val camera: CameraModel, val anchors: List<ValidatedAnchorPose.Anchor>, val points: List<MultiViewPointCloud.Pixel?>)
    data class Result(val poses: List<ValidatedAnchorPose.Result>, val acceptedViewIndices: List<Int>,
                      val cloud: MultiViewPointCloud.Result?)

    /**
     * Fehlerhafte Posen werden ausgeschlossen; fehlende Punkte bleiben unbekannt.
     * Anker und Punktindizes müssen vom Aufrufer richtig zugeordnet sein. Der
     * Aufrufer sollte Anker und ausgewertete Punkte getrennt halten; die Methode
     * kann das ohne echte Referenzdaten nicht garantieren.
     */
    fun reconstruct(views: List<View>): Result {
        require(views.size in 2..32)
        val count = views.first().points.size
        require(count in 1..2048 && views.all { it.points.size == count })
        val poses = views.map { ValidatedAnchorPose.estimate(it.camera, it.anchors) }
        val accepted = poses.indices.filter { poses[it] is ValidatedAnchorPose.Result.Pose }
        if (accepted.size < 2) return Result(poses, accepted, null)
        val calibrated = accepted.map { i ->
            val pose = poses[i] as ValidatedAnchorPose.Result.Pose
            val view = views[i]
            MultiViewPointCloud.View(view.camera, pose.transform.rotation, pose.transform.translation, view.points)
        }
        return Result(poses, accepted, MultiViewPointCloud.reconstruct(calibrated))
    }
}

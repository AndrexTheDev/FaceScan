package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.AnchoredMultiView
import com.andrexthedev.facescan.geometry.CameraModel
import com.andrexthedev.facescan.geometry.ValidatedAnchorPose

/**
 * Experimentelle Mehransichten-Aufnahme aus echten Kamera-Landmarks.
 *
 * Was hier WIRKLICH gemessen wird: Die 30 kanonischen Anker werden je Ansicht
 * über die gelieferten Pixel einer Pinhole-Kamera zugeordnet; daraus entsteht
 * eine Kamerapose relativ zum kanonischen Durchschnittsgesicht. Andere
 * Landmarks werden aus mehreren Ansichten trianguliert.
 *
 * Was das NICHT ist:
 *  - keine Vermessung der Person (die Anker sind ein Populationsmittel),
 *  - keine validierte Kalibrierung (Intrinsics/FOV müssen vom Aufrufer stimmen),
 *  - keine Fusion zu einer Oberfläche (das Teilnetz bleibt offen und kann Löcher
 *    und Ausreißer enthalten),
 *  - keine Personenerkennung.
 *
 * Der Aufrufer muss dieselbe, ungespiegelte und aufrechte Pixelgeometrie für
 * Anker und Punkte liefern und die Ansichten demselben Menschen in derselben
 * Sitzung zuordnen.
 */
object MultiViewCapture {
    const val MAX_VIEWS = 8

    /** Eine Ansicht: Landmarks (normiert) plus Bildgröße der aufrechten Bitmap. */
    data class View(val points: FloatArray, val width: Int, val height: Int)

    data class Intrinsics(val fx: Double, val fy: Double, val cx: Double, val cy: Double) {
        init {
            require(fx.isFinite() && fy.isFinite() && cx.isFinite() && cy.isFinite())
            require(fx > 0.0 && fy > 0.0)
        }
        fun camera(): CameraModel = CameraModel(fx, fy, cx, cy)
    }

    /**
     * Schätzt Intrinsics aus vertikalem Sichtfeld und Bildgröße. Die FOV ist
     * eine Annahme des Aufrufers (typische Frontkamera), keine Kalibrierung.
     */
    fun assumedIntrinsics(width: Int, height: Int, verticalFovDegrees: Double): Intrinsics {
        require(width > 0 && height > 0)
        require(verticalFovDegrees.isFinite() && verticalFovDegrees > 10.0 && verticalFovDegrees < 150.0)
        val fy = (height / 2.0) / Math.tan(Math.toRadians(verticalFovDegrees) / 2.0)
        require(fy.isFinite() && fy > 0.0)
        return Intrinsics(fy, fy, width / 2.0, height / 2.0)
    }

    enum class Failure {
        INVALID_VIEW, INCONSISTENT_DIMENSIONS, ANCHORS_OUT_OF_FRAME, POSE_REJECTED,
        INSUFFICIENT_ACCEPTED_VIEWS, EMPTY_CLOUD, TOO_MANY_VIEWS
    }

    data class AcceptedView(val viewIndex: Int, val rmsPixels: Double)
    data class Result(
        val surface: PartialFaceMesh.Result,
        val acceptedViews: List<AcceptedView>,
        val cloud: com.andrexthedev.facescan.geometry.MultiViewPointCloud.Result,
        val intrinsics: Intrinsics,
        val maxAnchorRmsPixels: Double
    )
    sealed class Outcome {
        data class Reconstructed(val result: Result) : Outcome()
        data class Rejected(val reason: Failure) : Outcome()
    }

    /**
     * Alle Ansichten müssen dieselbe Bildgröße haben. Fehlende Beobachtungen
     * bleiben unbekannt; es werden keine Punkte erfunden. Zu lange Dreiecks-
     * kanten können optional verworfen werden (Einheit: Zentimeter der Anker).
     */
    fun reconstruct(views: List<View>, intrinsics: Intrinsics, maxEdgeCm: Double? = null,
                    robust: Boolean = true): Outcome {
        fun reject(reason: Failure): Outcome = Outcome.Rejected(reason)
        if (views.size !in 2..MAX_VIEWS) return reject(if (views.size > MAX_VIEWS) Failure.TOO_MANY_VIEWS else Failure.INVALID_VIEW)
        val width = views.first().width
        val height = views.first().height
        if (views.any { it.width != width || it.height != height || it.width <= 0 || it.height <= 0 }) return reject(Failure.INCONSISTENT_DIMENSIONS)
        // Physikalisch unsinnige Kantenlängen dürfen keine leere Wolke erzwingen.
        if (maxEdgeCm != null && (!maxEdgeCm.isFinite() || maxEdgeCm <= 0.0 || maxEdgeCm > MAX_EDGE_CM))
            return reject(Failure.INVALID_VIEW)
        val anchorPixels = ArrayList<Pair<DoubleArray, DoubleArray>>(views.size)
        if (views.any { it.points.size < CanonicalAnchors.LANDMARK_COUNT * 3 || it.points.any { v -> !v.isFinite() } })
            return reject(Failure.INVALID_VIEW)
        for (view in views) {
            anchorPixels.add(com.andrexthedev.facescan.geometry.LandmarkProjection.pixels(
                view.points, CanonicalAnchorData.indices, width, height, marginPixels = 1.0)
                ?: return reject(Failure.ANCHORS_OUT_OF_FRAME))
        }
        // Vollständige Korrespondenz je Landmark; fehlt ein Punkt in einer
        // Ansicht, bleibt er dort unbekannt (null).
        val calibrated = views.indices.map { i ->
            val view = views[i]
            val (u, v) = anchorPixels[i]
            val pixels = (0 until CanonicalAnchors.LANDMARK_COUNT).map { index ->
                com.andrexthedev.facescan.geometry.LandmarkProjection.pixel(view.points, index, width, height, marginPixels = 1.0)
                    ?.let { com.andrexthedev.facescan.geometry.MultiViewPointCloud.Pixel(it.u, it.v) }
            }
            AnchoredMultiView.View(intrinsics.camera(), CanonicalAnchorData.anchors(u, v), pixels)
        }
        val anchored = try { AnchoredMultiView.reconstruct(calibrated) }
            catch (_: IllegalArgumentException) { return reject(Failure.INVALID_VIEW) }
        if (anchored.acceptedViewIndices.size < 2) return reject(Failure.POSE_REJECTED)
        // Ab drei Ansichten kann ein einzelner falsch zugeordneter Punkt durch
        // Mehrheitskonsens verworfen werden; bei zwei Ansichten bleibt nur die
        // strenge Reprojektionsprüfung. Kein Konsens erfindet Punkte: nicht
        // bestätigte Landmarks fehlen im Ergebnis.
        val cloud = if (robust && anchored.acceptedViewIndices.size >= 3) {
            // Nur die akzeptierten Posen dürfen in die robuste Triangulation.
            val calibratedViews = anchored.acceptedViewIndices.map { index ->
                val view = calibrated[index]
                val pose = anchored.poses[index] as ValidatedAnchorPose.Result.Pose
                com.andrexthedev.facescan.geometry.MultiViewPointCloud.View(
                    view.camera, pose.transform.rotation, pose.transform.translation, view.points)
            }
            val robustCloud = com.andrexthedev.facescan.geometry.MultiViewPointCloud.reconstructRobust(calibratedViews)
            val converted = robustCloud.points.map { value ->
                when (value) {
                    is com.andrexthedev.facescan.geometry.RobustMultiViewTriangulation.Result.Point -> value.fit
                    is com.andrexthedev.facescan.geometry.RobustMultiViewTriangulation.Result.Rejected ->
                        com.andrexthedev.facescan.geometry.MultiViewTriangulation.Result.Rejected(value.reason)
                }
            }
            com.andrexthedev.facescan.geometry.MultiViewPointCloud.Result(converted,
                converted.count { it is com.andrexthedev.facescan.geometry.MultiViewTriangulation.Result.Point })
        } else anchored.cloud
        if (cloud == null) return reject(Failure.POSE_REJECTED)
        val surface = PartialFaceMesh.build(cloud, maxEdgeCm)
        if (surface.mesh == null) return reject(Failure.EMPTY_CLOUD)
        val accepted = anchored.acceptedViewIndices.map { i ->
            AcceptedView(i, (anchored.poses[i] as com.andrexthedev.facescan.geometry.ValidatedAnchorPose.Result.Pose).rmsPixels)
        }
        val worst = accepted.maxOf { it.rmsPixels }
        if (!worst.isFinite() || worst > MAX_ANCHOR_RMS_PIXELS) return reject(Failure.POSE_REJECTED)
        // Alle Ansichten stammen von derselben Kamera; die übergebenen
        // Intrinsics gelten daher für die Triangulation. Die Brennweitensuche
        // dient nur der Plausibilitätsprüfung je Ansicht.
        return Outcome.Reconstructed(Result(surface, accepted, cloud, intrinsics, worst))
    }

    /**
     * Experimentelle Obergrenze für den Anker-Fit in Pixeln. Sie hängt an der
     * Bildgröße und ist NICHT an realen Kameras oder Personen validiert; ein
     * kleiner Rest beweist keine korrekte Pose.
     */
    const val MAX_ANCHOR_RMS_PIXELS = 6.0

    /** Obergrenze der optionalen Kantenlänge in Zentimetern (grober Kopfbereich). */
    const val MAX_EDGE_CM = 60.0

    /** OBJ-Ausgabe mit expliziter Einheit und ohne Verschönerung. */
    fun writeObj(result: Result): ByteArray? = result.surface.mesh?.let { PartialFaceMesh.writeObj(it) }

    /**
     * Variante mit zusätzlicher Kopfzeile zur Datenlage. Der Aufrufer muss die
     * Gegebenheiten selbst dokumentieren; die Zahlen stammen aus dem Fit.
     */
    fun writeObjWithHeader(result: Result): ByteArray? {
        val base = writeObj(result) ?: return null
        val header = "# views=${result.acceptedViews.size} points=${result.surface.acceptedPoints} " +
            "maxAnchorRmsPx=${"%.3f".format(java.util.Locale.ROOT, result.maxAnchorRmsPixels)} " +
            "assumedFocalPx=${"%.1f".format(java.util.Locale.ROOT, result.intrinsics.fx)}\n" +
            "# Canonical average anchors in centimetres, not a measurement of the subject.\n"
        return header.toByteArray(Charsets.UTF_8) + base
    }
}

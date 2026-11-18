package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.CameraModel
import com.andrexthedev.facescan.geometry.LandmarkProjection
import com.andrexthedev.facescan.geometry.Mat3
import com.andrexthedev.facescan.geometry.MultiViewTriangulation
import com.andrexthedev.facescan.geometry.ValidatedAnchorPose
import org.junit.Assert.*
import org.junit.Test
import kotlin.math.abs

class MultiViewCaptureTest {
    private val w = 640
    private val h = 480
    private val f = 760.0
    private val intrinsics = MultiViewCapture.Intrinsics(f, f, w / 2.0, h / 2.0)

    /**
     * Künstliche Aufnahme des synthetischen Punktesatzes. `hole` liegt
     * absichtlich außerhalb des Bildes, `shiftIndex` wird um Pixel verschoben.
     */
    private fun view(
        yawDegrees: Double,
        translation: DoubleArray = doubleArrayOf(0.0, 0.0, 60.0),
        hole: Int? = null,
        shiftIndex: Int? = null,
        shiftPixels: Double = 0.0
    ): MultiViewCapture.View {
        val camera = CameraModel(f, f, w / 2.0, h / 2.0)
        val rotation = Mat3.fromRodrigues(doubleArrayOf(0.0, Math.toRadians(yawDegrees), 0.0))
        val points = FloatArray(CanonicalAnchors.LANDMARK_COUNT * 3)
        for ((index, p) in MultiViewSessionSelfTest.syntheticWorldPoints().withIndex()) {
            if (index == hole) {
                // -1 liegt außerhalb des zulässigen Bildbereichs.
                points[3 * index] = -1f
                points[3 * index + 1] = -1f
                continue
            }
            val q = DoubleArray(2)
            camera.project(rotation, translation, p, q)
            val offset = if (index == shiftIndex) shiftPixels else 0.0
            points[3 * index] = ((q[0] + offset) / w).toFloat()
            points[3 * index + 1] = (q[1] / h).toFloat()
        }
        return MultiViewCapture.View(points, w, h)
    }

    @Test fun syntheticDeviceSelfTestPasses() { assertTrue(MultiViewSessionSelfTest.run()) }

    @Test fun anchorsMatchIndependentlyExtractedCanonicalModel() {
        // Referenzwerte aus canonical_face_model.obj v0.10.14, unabhängig per
        // Python extrahiert: Nasenspitze (4), Kinn (152), rechtes Augeninnen (33),
        // linke Augeninnen (263), rechte Wange (234).
        val expected = mapOf(
            4 to doubleArrayOf(0.0, -0.463170, 7.586580),
            152 to doubleArrayOf(0.0, -9.403378, 4.264492),
            33 to doubleArrayOf(-4.445859, 2.663991, 3.173422),
            234 to doubleArrayOf(-7.664182, 0.673132, -2.435867),
            263 to doubleArrayOf(4.445859, 2.663991, 3.173422)
        )
        for ((landmark, point) in expected) {
            val slot = CanonicalAnchorData.indices.indexOf(landmark)
            assertTrue("Anker $landmark fehlt; gefunden: ${CanonicalAnchorData.indices.joinToString()}",
                slot >= 0)
            for (axis in 0..2) assertEquals(point[axis], CanonicalAnchorData.points[3 * slot + axis], 1e-6)
        }
        assertEquals(30, CanonicalAnchorData.COUNT)
        assertEquals(30, CanonicalAnchorData.indices.distinct().size)
        val zs = (0 until CanonicalAnchorData.COUNT).map { CanonicalAnchorData.points[3 * it + 2] }
        assertTrue(zs.max() - zs.min() > 5.0)
    }

    @Test fun assumesSymmetricIntrinsicsFromVerticalFieldOfView() {
        // Hochformat: die Brennweite folgt der Höhe, nicht der Breite.
        val assumed = MultiViewCapture.assumedIntrinsics(1080, 1920, 60.0)
        assertEquals(1920 / 2.0 / Math.tan(Math.toRadians(30.0)), assumed.fy, 1e-9)
        assertEquals(assumed.fy, assumed.fx, 0.0)
        assertEquals(540.0, assumed.cx, 0.0)
        try { MultiViewCapture.assumedIntrinsics(0, 10, 60.0); fail() } catch (_: IllegalArgumentException) { }
        try { MultiViewCapture.assumedIntrinsics(100, 10, 200.0); fail() } catch (_: IllegalArgumentException) { }
    }

    @Test fun reconstructsLiveStyleViewsFromDifferentHeadTurns() {
        val views = listOf(view(0.0), view(-22.0), view(24.0))
        when (val outcome = MultiViewCapture.reconstruct(views, intrinsics)) {
            is MultiViewCapture.Outcome.Rejected -> fail("Abgelehnt: ${outcome.reason}")
            is MultiViewCapture.Outcome.Reconstructed -> {
                val result = outcome.result
                assertEquals(3, result.acceptedViews.size)
                // Die frei erfundenen Zusatzpunkte müssen zurückkommen.
                val truth = MultiViewSessionSelfTest.syntheticWorldPoints()
                for (index in listOf(0, 100, 233)) {
                    val point = result.cloud.points[index] as MultiViewTriangulation.Result.Point
                    assertArrayEquals(truth[index], point.xyz, 0.1)
                }
                assertTrue(result.maxAnchorRmsPixels < 1.0)
                assertEquals(468, result.surface.acceptedPoints)
                val mesh = result.surface.mesh!!
                assertTrue(mesh.triangles.isNotEmpty())
                val text = String(MultiViewCapture.writeObjWithHeader(result)!!, Charsets.UTF_8)
                assertTrue(text.contains("not validated"))
                assertTrue(text.contains("views=3"))
            }
        }
    }

    @Test fun rejectsCorruptedInconsistentAndOutOfFrameInputs() {
        // Ein einzelner um 200 px verschobener Anker erzeugt einen großen Rest.
        val shifted = view(0.0, shiftIndex = CanonicalAnchorData.indices[3], shiftPixels = 200.0)
        val corrupted = MultiViewCapture.reconstruct(listOf(view(0.0), shifted), intrinsics)
        assertTrue(corrupted is MultiViewCapture.Outcome.Rejected)

        assertEquals(MultiViewCapture.Failure.TOO_MANY_VIEWS,
            (MultiViewCapture.reconstruct(List(9) { view(it * 15.0) }, intrinsics) as MultiViewCapture.Outcome.Rejected).reason)
        assertEquals(MultiViewCapture.Failure.INCONSISTENT_DIMENSIONS,
            (MultiViewCapture.reconstruct(listOf(view(0.0), view(20.0).copy(width = 320)), intrinsics)
                as MultiViewCapture.Outcome.Rejected).reason)
        assertEquals(MultiViewCapture.Failure.ANCHORS_OUT_OF_FRAME,
            (MultiViewCapture.reconstruct(listOf(view(0.0, hole = CanonicalAnchorData.indices[0]), view(20.0)), intrinsics)
                as MultiViewCapture.Outcome.Rejected).reason)
        val wide = view(-70.0)
        val invalid = wide.copy(points = wide.points.copyOf().also { it[0] = Float.NaN })
        assertEquals(MultiViewCapture.Failure.INVALID_VIEW,
            (MultiViewCapture.reconstruct(listOf(view(0.0), invalid), intrinsics) as MultiViewCapture.Outcome.Rejected).reason)
        assertEquals(MultiViewCapture.Failure.INVALID_VIEW,
            (MultiViewCapture.reconstruct(listOf(view(0.0), view(20.0)), intrinsics, -1.0)
                as MultiViewCapture.Outcome.Rejected).reason)
        assertEquals(MultiViewCapture.Failure.INVALID_VIEW,
            (MultiViewCapture.reconstruct(listOf(view(0.0), view(20.0)), intrinsics, 61.0)
                as MultiViewCapture.Outcome.Rejected).reason)
    }

    @Test fun robustConsensusDropsAWrongCorrespondenceWithoutGuessing() {
        // In einer der drei Ansichten ist ein einzelner Nicht-Ankerpunkt um
        // 120 px verschoben. Mit drei Ansichten ist der Ausreißer nicht sicher
        // erkennbar; der Punkt darf deshalb fehlen, aber nie falsch sein.
        val corrupted = view(24.0, shiftIndex = 0, shiftPixels = 120.0)
        val views = listOf(view(0.0), view(-22.0), corrupted)
        val robust = MultiViewCapture.reconstruct(views, intrinsics) as MultiViewCapture.Outcome.Reconstructed
        val point = robust.result.cloud.points[0]
        val truth = MultiViewSessionSelfTest.syntheticWorldPoints()[0]
        assertTrue("Ausreißer darf nicht als Punkt erscheinen", point is MultiViewTriangulation.Result.Rejected)
        // Nur dieser eine Punkt fehlt; alle anderen bleiben rekonstruiert.
        assertEquals(467, robust.result.cloud.acceptedCount)
        // Ohne Konsens (zwei Ansichten) bleibt nur die strenge Prüfung.
        val strict = MultiViewCapture.reconstruct(listOf(view(0.0), view(-22.0)), intrinsics,
            robust = false) as MultiViewCapture.Outcome.Reconstructed
        val strictPoint = strict.result.cloud.points[0] as MultiViewTriangulation.Result.Point
        for (axis in 0..2) assertEquals(truth[axis], strictPoint.xyz[axis], 0.1)
    }

    @Test fun robustConsensusWithFourViewsRejectsOutlierAndKeepsOthers() {
        val corrupted = view(-40.0, shiftIndex = 0, shiftPixels = 120.0)
        val views = listOf(view(0.0), view(-22.0), view(24.0), corrupted)
        val robust = MultiViewCapture.reconstruct(views, intrinsics) as MultiViewCapture.Outcome.Reconstructed
        val truth = MultiViewSessionSelfTest.syntheticWorldPoints()
        // Der verschobene Punkt darf nicht mit dem falschen Wert erscheinen:
        // entweder fehlt er oder er liegt (nach Mehrheit) nahe der Wahrheit.
        val outlier = robust.result.cloud.points[0]
        if (outlier is MultiViewTriangulation.Result.Point) {
            for (axis in 0..2) assertEquals(truth[0][axis], outlier.xyz[axis], 0.3)
        }
        // Unbeteiligte Punkte bleiben in allen vier Ansichten bestätigt.
        val survivor = robust.result.cloud.points[100] as MultiViewTriangulation.Result.Point
        for (axis in 0..2) assertEquals(truth[100][axis], survivor.xyz[axis], 0.1)
        assertEquals(4, robust.result.acceptedViews.size)
        assertTrue(robust.result.surface.acceptedPoints >= 460)
    }

    @Test fun rejectedAnchorsNeverProduceInventedPixels() {
        val projection = LandmarkProjection.pixel(floatArrayOf(0.5f, 0.5f, 0f), 0, w, h)
        assertNotNull(projection)
        assertNull(LandmarkProjection.pixel(floatArrayOf(1.2f, 0.5f, 0f), 0, w, h))
        assertNull(LandmarkProjection.pixel(floatArrayOf(0.5f, 0.5f, 0f), 0, 0, h))
        assertNull(LandmarkProjection.pixel(floatArrayOf(Float.NaN, 0.5f, 0f), 0, w, h))
        assertNull(LandmarkProjection.pixels(floatArrayOf(0.5f, 0.5f, 0f), intArrayOf(0, 5), w, h))
        assertEquals((0.5 * w) - 0.5, projection!!.u, 1e-9)
        assertEquals((0.5 * h) - 0.5, projection.v, 1e-9)
    }

    @Test fun sessionRequiresDistinctHeadTurnsAndKeepsSessionState() {
        val session = MultiViewSession(intrinsics)
        assertEquals(MultiViewSession.AddResult.ACCEPTED, session.add(view(0.0).points, w, h))
        assertEquals(MultiViewSession.AddResult.INSUFFICIENT_YAW_DIFFERENCE, session.add(view(4.0).points, w, h))
        assertEquals(MultiViewSession.AddResult.ACCEPTED, session.add(view(-25.0).points, w, h))
        assertEquals(MultiViewSession.AddResult.INCONSISTENT_DIMENSIONS, session.add(view(25.0).points, w / 2, h / 2))
        assertEquals(2, session.size())
        assertTrue(session.yawSpreadDegrees() > 20.0)
        assertTrue(session.reconstruct() is MultiViewCapture.Outcome.Reconstructed)
        session.clear()
        assertEquals(0, session.size())
        assertTrue(session.reconstruct() is MultiViewCapture.Outcome.Rejected)
    }

    @Test fun guidanceTracksDistanceToNearestStoredView() {
        val session = MultiViewSession(intrinsics)
        val frontal = MultiViewSessionSelfTest.syntheticLandmarks(0.0)
        val near = MultiViewSessionSelfTest.syntheticLandmarks(5.0)
        val far = MultiViewSessionSelfTest.syntheticLandmarks(20.0)
        // Ohne gespeicherte Ansicht ist jede erkannte Haltung zulässig.
        assertTrue(session.guidance(frontal, w, h).sufficient)
        assertEquals(MultiViewSession.AddResult.ACCEPTED, session.add(frontal, w, h))
        val nearGuidance = session.guidance(near, w, h)
        assertNotNull(nearGuidance.yawDegrees)
        assertTrue("5 Grad reichen nicht", !nearGuidance.sufficient)
        assertTrue(nearGuidance.nearestDegrees!! < MultiViewSession.MIN_YAW_DIFFERENCE_DEGREES)
        val farGuidance = session.guidance(far, w, h)
        assertTrue(farGuidance.sufficient)
        assertTrue(farGuidance.nearestDegrees!! >= MultiViewSession.MIN_YAW_DIFFERENCE_DEGREES)
        // Ungültige Eingaben liefern keine erfundene Orientierung.
        val invalid = frontal.copyOf().also { it[0] = Float.NaN }
        assertNull(session.guidance(invalid, w, h).yawDegrees)
        assertNull(session.guidance(frontal, 0, h).yawDegrees)
        assertEquals(MultiViewSession.MIN_YAW_DIFFERENCE_DEGREES, session.minimumViewDifference(), 0.0)
    }

    @Test fun partialObjWithNormalsIsFiniteAndCommentOnlyWhereAllowed() {
        val outcome = MultiViewCapture.reconstruct(listOf(view(0.0), view(-22.0)), intrinsics)
            as MultiViewCapture.Outcome.Reconstructed
        val mesh = outcome.result.surface.mesh!!
        val bytes = PartialFaceMesh.writeObjWithNormals(mesh)
        val lines = String(bytes, Charsets.UTF_8).lines()
        assertEquals(mesh.vertices.size, lines.count { it.startsWith("v ") })
        assertEquals(mesh.vertices.size, lines.count { it.startsWith("vn ") })
        assertEquals(mesh.triangles.size / 3, lines.count { it.startsWith("f ") })
        assertTrue(lines.filter { it.startsWith("f ") }.all { it.split(" ").drop(1).all { f -> f.matches(Regex("\\d+//\\d+")) } })
        // Degenerierte Normalen sind im Export nicht erlaubt (Einheitsvektoren).
        lines.filter { it.startsWith("vn ") }.forEach { line ->
            val v = line.removePrefix("vn ").split(" ").map(String::toDouble)
            assertEquals(1.0, kotlin.math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]), 1e-5)
        }
    }

    @Test fun localFocalSearchRecoversApproximateFocalLengthFromAnchors() {
        // Ansicht mit einer anderen als der angenommenen Brennweite.
        val trueFocal = 1050.0
        val camera = CameraModel(trueFocal, trueFocal, w / 2.0, h / 2.0)
        val rotation = Mat3.fromRodrigues(doubleArrayOf(0.05, 0.35, -0.02))
        val anchors = (0 until CanonicalAnchorData.COUNT).map { a ->
            val p = doubleArrayOf(
                CanonicalAnchorData.points[3 * a] + 2.0,
                CanonicalAnchorData.points[3 * a + 1],
                CanonicalAnchorData.points[3 * a + 2])
            val q = DoubleArray(2)
            camera.project(rotation, doubleArrayOf(-5.0, 2.0, 55.0), p, q)
            ValidatedAnchorPose.Anchor(p, q[0], q[1])
        }
        val search = FocalSearch.estimate(anchors, CameraModel(760.0, 760.0, w / 2.0, h / 2.0))
        assertNotNull("Keine Brennweite gefunden", search)
        // Die Suche ist grob und nicht eindeutig; sie muss aber deutlich besser
        // passen als die falsche Ausgangsannahme und im zulässigen Bereich liegen.
        assertTrue(search!!.pose.rmsPixels < 1.0)
        assertTrue(search.intrinsics.fx.isFinite() && search.intrinsics.fx > 0.0)
        assertTrue(abs(search.intrinsics.fx - trueFocal) / trueFocal < 0.5)
        assertTrue(search.intrinsics.fx >= FocalSearch.MIN_FOCAL_FACTOR * w)
        assertTrue(search.intrinsics.fx <= FocalSearch.MAX_FOCAL_FACTOR * w)
    }
}

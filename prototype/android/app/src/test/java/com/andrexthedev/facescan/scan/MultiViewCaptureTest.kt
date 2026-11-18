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

    @Test fun reconstructedResultExportsObjAndGlbWithTheSameTriangles() {
        val views = listOf(view(0.0), view(-22.0), view(24.0))
        val ready = MultiViewCapture.reconstruct(views, intrinsics) as MultiViewCapture.Outcome.Reconstructed
        val obj = ready.result.encodeExport(MeshExportFormat.OBJ)
        val glb = ready.result.encodeExport(MeshExportFormat.GLB)
        assertNotNull(obj)
        assertNotNull(glb)
        val mesh = ready.result.surface.mesh!!
        val objText = String(obj!!, Charsets.UTF_8)
        // OBJ beginnt mit den Fit-Zahlen des Exports; GLB trägt dieselbe Geometrie ohne Kommentare.
        assertTrue(objText.lines().first().startsWith("# views=3 points="))
        assertTrue(objText.contains("not a measurement of the subject"))
        assertEquals(mesh.triangles.size / 3, objText.lines().count { it.startsWith("f ") })
        // OBJ-Indizes sind 1-basiert und müssen zum Mesh passen.
        val firstFace = objText.lines().first { it.startsWith("f ") }.trim().split(" ")
        assertEquals(4, firstFace.size)
        for ((position, token) in firstFace.drop(1).withIndex()) {
            assertEquals((mesh.triangles[position] + 1).toString(), token.substringBefore("//"))
        }
        val input = java.nio.ByteBuffer.wrap(glb!!).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        assertEquals(0x46546c67, input.int)
        assertEquals(2, input.int)
        assertEquals(glb.size, input.int)
        val jsonLength = input.int
        // Chunk-Kopf (Typ) gehört nicht zum JSON; ohne dieses Lesen verschiebt
        // sich der Text um vier Bytes und jede Inhaltsprüfung scheitert.
        assertEquals(0x4e4f534a, input.int)
        // ByteArray(jsonLength) allein liest nichts aus dem Puffer.
        val jsonBytes = ByteArray(jsonLength)
        input.get(jsonBytes)
        val json = String(jsonBytes, Charsets.UTF_8)
        assertTrue("JSON beginnt nicht wie erwartet: ${json.take(40)}", json.startsWith("{\n\"asset\":"))
        val positions = FloatArray(mesh.vertices.size * 3) { i -> mesh.vertices[i / 3][i % 3].toFloat() }
        val written = PartialGlbWriter.floatSafeTriangles(positions, mesh.triangles)
        assertTrue(json.take(200), json.contains("\"count\":${written.size}"))
        // Ohne Mesh darf kein Export entstehen, statt einer leeren Datei.
        val empty = ready.result.copy(surface = ready.result.surface.copy(mesh = null))
        assertNull(empty.encodeExport(MeshExportFormat.OBJ))
        assertNull(empty.encodeExport(MeshExportFormat.GLB))
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



    @Test fun qualityGateRejectsUnusableLightButOnlyWarnsOnBlur() {
        assertEquals(MultiViewQualityGate.Decision.REJECT, MultiViewQualityGate.decide(ImageQuality.Hint.TOO_DARK))
        assertEquals(MultiViewQualityGate.Decision.REJECT, MultiViewQualityGate.decide(ImageQuality.Hint.TOO_BRIGHT))
        assertEquals(MultiViewQualityGate.Decision.WARN, MultiViewQualityGate.decide(ImageQuality.Hint.POSSIBLY_BLURRY))
        assertEquals(MultiViewQualityGate.Decision.ACCEPT, MultiViewQualityGate.decide(ImageQuality.Hint.NO_WARNING))
        // Ohne auswertbaren Bildausschnitt entscheidet nur die Ankerpose.
        assertEquals(MultiViewQualityGate.Decision.ACCEPT, MultiViewQualityGate.decide(null))
    }

    @Test fun completenessZonesUseCanonicalHeightsAndAreNotGuessed() {
        // Die Zonengrenzen stammen aus den Ankerhöhen; die Summe muss 30 sein.
        val total = (0 until MultiViewCompleteness.ZONE_COUNT).sumOf { MultiViewCompleteness.anchorsInZone(it) }
        assertEquals(CanonicalAnchorData.COUNT, total)
        assertEquals(2, MultiViewCompleteness.anchorsInZone(0))   // Stirn
        assertEquals(7, MultiViewCompleteness.anchorsInZone(1))   // Augen
        assertEquals(14, MultiViewCompleteness.anchorsInZone(2))  // Nase
        assertEquals(4, MultiViewCompleteness.anchorsInZone(3))   // Mund
        assertEquals(3, MultiViewCompleteness.anchorsInZone(4))   // Kinn
        // Grenzen gehören zur oberen Zone, nicht zu beiden.
        assertEquals(0, MultiViewCompleteness.zoneIndex(5.5))
        assertEquals(1, MultiViewCompleteness.zoneIndex(5.499))
        // Die Mundzone beginnt bei -6,5 cm (einschließlich); erst darunter Kinn.
        assertEquals(3, MultiViewCompleteness.zoneIndex(-6.5))
        assertEquals(4, MultiViewCompleteness.zoneIndex(-6.51))
        assertNull(MultiViewCompleteness.zoneIndex(Double.NaN))
        assertNull(MultiViewCompleteness.zoneIndex(Double.POSITIVE_INFINITY))
    }

    @Test fun depthUncertaintyFollowsResidualAndParallaxWithoutInventingValues() {
        // 1 px Rest, fx = 760, 10 Grad Parallaxe, 60 cm Tiefe.
        val expected = 1.0 / (760.0 * kotlin.math.sin(Math.toRadians(10.0))) * 60.0
        assertEquals(expected, MultiViewCompleteness.depthUncertaintyCm(60.0, 1.0, 10.0, 760.0)!!, 1e-12)
        // Kleinerer Rest und größere Parallaxe müssen die Schätzung senken.
        val better = MultiViewCompleteness.depthUncertaintyCm(60.0, 0.5, 20.0, 760.0)!!
        assertTrue(better < expected)
        // Ohne belastbare Eingaben wird kein Wert erfunden.
        assertNull(MultiViewCompleteness.depthUncertaintyCm(null, 1.0, 10.0, 760.0))
        assertNull(MultiViewCompleteness.depthUncertaintyCm(60.0, Double.NaN, 10.0, 760.0))
        assertNull(MultiViewCompleteness.depthUncertaintyCm(60.0, 1.0, 0.0, 760.0))
        assertNull(MultiViewCompleteness.depthUncertaintyCm(60.0, 1.0, 10.0, 0.0))
        assertNull(MultiViewCompleteness.depthUncertaintyCm(-5.0, 1.0, 10.0, 760.0))
    }

    @Test fun completenessReportOfRealReconstructionIsConsistent() {
        val outcome = MultiViewCapture.reconstruct(listOf(view(0.0), view(-22.0), view(24.0)), intrinsics)
            as MultiViewCapture.Outcome.Reconstructed
        val report = outcome.result.completeness
        assertNotNull(report)
        report!!
        assertEquals(CanonicalAnchorData.COUNT, report.anchorsInZoneTotal)
        // Die Anker der aufgenommenen Ansichten liegen dicht beieinander, also
        // müssen alle 30 vorhanden sein – sonst wäre die Pose falsch akzeptiert.
        assertEquals(CanonicalAnchorData.COUNT, report.anchorsTriangulatedTotal)
        assertEquals(1.0, report.anchorCoverageFraction, 0.0)
        assertTrue(report.zoneCoverages.all { it.complete })
        assertTrue(report.emptyZoneNames.isEmpty())
        assertTrue(report.uncertaintySamples > 0)
        // Exakt synthetische Punkte haben praktisch keinen Rest; die Schätzung
        // darf dann nahe null liegen, aber nie negativ oder unendlich sein.
        assertTrue(report.medianDepthUncertaintyCm!! >= 0.0 && report.medianDepthUncertaintyCm!!.isFinite())
        assertTrue(report.medianDepthUncertaintyCm!! < 0.01)
        assertTrue(report.highDepthUncertaintyCm!! >= report.medianDepthUncertaintyCm!!)
        val obj = String(MultiViewCapture.writeObjWithHeader(outcome.result)!!, Charsets.UTF_8)
        assertTrue(obj.contains("# completeness anchors=30/30 zones=forehead=2/2,eyes=7/7,nose=14/14,mouth=4/4,chin=3/3"))
        assertTrue(obj.contains("first-order estimate, not validated"))
        val glb = String(PartialGlbWriter.write(outcome.result.surface.mesh!!, report), Charsets.ISO_8859_1)
        assertTrue(glb.contains("\"zoneCoverage\":\"forehead=2/2,eyes=7/7,nose=14/14,mouth=4/4,chin=3/3\""))
        assertTrue(glb.contains("\"samples\":${report.uncertaintySamples}"))
    }

    @Test fun noisyViewsRaiseTheDepthUncertaintyEstimate() {
        // Künstliches, gemischtes Rauschen von 0,5 px: die Ankerpose bleibt
        // akzeptabel, die Punkte haben aber einen echten Rest. Die Schätzung
        // muss dann über dem rauschfreien Fall liegen.
        // Verschiebung abwechselnd je Punkt und Ansicht: eine reine
        // Translation würde die Ankerpose teilweise auffangen und den Rest
        // verschwinden lassen. Das ist Absicht, kein Messfehler.
        fun shifted(yaw: Double, viewIndex: Int): MultiViewCapture.View {
            val base = view(yaw)
            val points = base.points.copyOf()
            for (i in 0 until CanonicalAnchors.LANDMARK_COUNT) {
                if (!points[3 * i].isFinite()) continue
                val sign = (if (i % 2 == 0) 1.0 else -1.0) * (if (viewIndex % 2 == 0) 1.0 else -1.0)
                points[3 * i] += (sign * 0.5 / w).toFloat()
            }
            return MultiViewCapture.View(points, w, h)
        }
        val exact = MultiViewCapture.reconstruct(listOf(view(0.0), view(-22.0), view(24.0)), intrinsics)
            as MultiViewCapture.Outcome.Reconstructed
        val noisy = MultiViewCapture.reconstruct(
            listOf(shifted(0.0, 0), shifted(-22.0, 1), shifted(24.0, 0)), intrinsics)
        if (noisy is MultiViewCapture.Outcome.Rejected) return  // Pose zu schlecht: kein stiller Wert.
        val report = (noisy as MultiViewCapture.Outcome.Reconstructed).result.completeness!!
        assertTrue(report.uncertaintySamples > 0)
        val median = report.medianDepthUncertaintyCm!!
        val baseline = exact.result.completeness!!.medianDepthUncertaintyCm ?: 0.0
        // Eine gleichmäßige Verschiebung wird von der Pose teilweise
        // aufgefangen; gemischtes Rauschen nicht. Entscheidend ist, dass die
        // Schätzung den Rest sieht und über dem rauschfreien Fall liegt.
        assertTrue("Median $median liegt nicht über dem rauschfreien Fall $baseline", median > baseline)
        assertTrue("Kein Rest erkannt: median=$median", median > 0.0)
        assertTrue(report.highDepthUncertaintyCm!! >= median)
    }

    @Test fun glbWithoutCompletenessDoesNotClaimNumbers() {
        val outcome = MultiViewCapture.reconstruct(listOf(view(0.0), view(-22.0)), intrinsics)
            as MultiViewCapture.Outcome.Reconstructed
        val glb = String(PartialGlbWriter.write(outcome.result.surface.mesh!!), Charsets.ISO_8859_1)
        // Ohne Bericht: leere Zonenzeichenfolge, keine erfundene Unsicherheit.
        assertTrue(glb.contains("\"zoneCoverage\":\"\""))
        assertTrue(glb.contains("\"median\":null"))
        assertTrue(glb.contains("\"samples\":0"))
    }

    @Test fun plyWriterEmitsBinaryTrianglesWithUncertaintyColours() {
        val outcome = MultiViewCapture.reconstruct(listOf(view(0.0), view(-22.0), view(24.0)), intrinsics)
            as MultiViewCapture.Outcome.Reconstructed
        val result = outcome.result
        val mesh = result.surface.mesh!!
        val colors = PartialPlyWriter.uncertaintyColors(mesh, result.cloud,
            result.referenceRotation!!, result.referenceTranslation!!, intrinsics.fx)
        assertEquals(mesh.vertices.size, colors.vertexCount)
        assertEquals(mesh.vertices.size, colors.known + colors.unknown)
        // Graustufen im erlaubten Bereich; 0 ist für "keine Schätzung" reserviert.
        for (i in 0 until colors.vertexCount) {
            val r = colors.colors[3 * i].toInt() and 0xff
            assertEquals(r, colors.colors[3 * i + 1].toInt() and 0xff)
            assertEquals(r, colors.colors[3 * i + 2].toInt() and 0xff)
            assertTrue(r == PartialPlyWriter.UNKNOWN_SHADE || r in 25..255)
        }
        val bytes = PartialPlyWriter.write(mesh, colors)
        val text = String(bytes, Charsets.ISO_8859_1)
        assertTrue(text.startsWith("ply\nformat binary_little_endian 1.0\n"))
        assertTrue(text.contains("element vertex ${mesh.vertices.size}"))
        assertTrue(text.contains("property uchar red"))
        assertTrue(text.contains("uncertaintyKnown ${colors.known} uncertaintyUnknown ${colors.unknown}"))
        val headerLength = text.indexOf("end_header\n") + "end_header\n".length
        // 3 Float32 + 3 Byte je Vertex, 1 Byte Anzahl + 3 Int32 je Dreieck.
        assertEquals(mesh.vertices.size * 15 + mesh.triangles.size / 3 * 13, bytes.size - headerLength)
        // Layout prüfen: x,y,z,r,g,b liegen bei JEDEM Vertex hintereinander,
        // nicht als getrennte Blöcke. Sonst ist die Datei formal gültig, aber falsch.
        // Absolute Indizes zählen ab Dateianfang; deshalb den Offset addieren.
        val body = java.nio.ByteBuffer.wrap(bytes).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        for (v in 0 until 3) {
            val at = headerLength + v * 15
            assertEquals(mesh.vertices[v][0].toFloat(), body.getFloat(at), 0f)
            assertEquals(mesh.vertices[v][1].toFloat(), body.getFloat(at + 4), 0f)
            assertEquals(mesh.vertices[v][2].toFloat(), body.getFloat(at + 8), 0f)
            assertEquals(colors.colors[3 * v], body.get(at + 12))
            assertEquals(colors.colors[3 * v + 1], body.get(at + 13))
            assertEquals(colors.colors[3 * v + 2], body.get(at + 14))
        }
        assertEquals("application/octet-stream", MeshExportFormat.PLY.mimeType)
        assertNotNull(result.encodeExport(MeshExportFormat.PLY))
    }

    @Test fun plyWithoutReferencePoseOmitsColoursInsteadOfInventingThem() {
        val outcome = MultiViewCapture.reconstruct(listOf(view(0.0), view(-22.0)), intrinsics)
            as MultiViewCapture.Outcome.Reconstructed
        val mesh = outcome.result.surface.mesh!!
        val bytes = PartialPlyWriter.write(mesh)
        val text = String(bytes, Charsets.ISO_8859_1)
        // Ohne Schätzung gibt es keine Farbkanäle und keinen erfundenen Wert.
        assertTrue(text.contains("comment no colour channel: no uncertainty estimate available"))
        assertTrue(!text.contains("property uchar red"))
        val headerLength = text.indexOf("end_header\n") + "end_header\n".length
        assertEquals(mesh.vertices.size * 12 + mesh.triangles.size / 3 * 13, bytes.size - headerLength)
    }

    @Test fun plyUncertaintyColoursScaleWithTheWorstPoint() {
        val outcome = MultiViewCapture.reconstruct(listOf(view(0.0), view(-22.0), view(24.0)), intrinsics)
            as MultiViewCapture.Outcome.Reconstructed
        val result = outcome.result
        val mesh = result.surface.mesh!!
        val colors = PartialPlyWriter.uncertaintyColors(mesh, result.cloud,
            result.referenceRotation!!, result.referenceTranslation!!, intrinsics.fx)
        val shades = (0 until colors.vertexCount).map { colors.colors[3 * it].toInt() and 0xff }
        if (colors.known > 1) {
            // Relative Skala: der unsicherste Punkt ist weiß, keiner ist schwarz.
            assertEquals(255, shades.max())
            assertEquals(0, colors.unknown)
            assertTrue("Sicherster Punkt muss mindestens 25 sein", shades.min()!! >= 25)
        }
        // Ohne gültige Brennweite gibt es keine Schätzung und damit keine Farbe.
        val invalid = PartialPlyWriter.uncertaintyColors(mesh, result.cloud,
            result.referenceRotation!!, result.referenceTranslation!!, Double.NaN)
        assertEquals(0, invalid.known)
        assertEquals(mesh.vertices.size, invalid.unknown)
        assertTrue(invalid.colors.all { it == 0.toByte() })
    }

    @Test fun topologyReportsBoundaryNonManifoldAndComponents() {
        // Ein einzelnes Dreieck hat drei Randkanten und eine Komponente.
        val single = PartialMeshTopology.inspect(3, intArrayOf(0, 1, 2))
        assertEquals(1, single.triangleCount)
        assertEquals(3, single.boundaryEdges)
        assertEquals(0, single.nonManifoldEdges)
        assertEquals(1, single.components)
        assertEquals(1, single.largestComponentTriangles)
        // Geschlossener Tetraeder: keine Randkante, eine Komponente.
        val tetra = PartialMeshTopology.inspect(4, intArrayOf(0, 1, 2, 0, 2, 3, 0, 3, 1, 1, 3, 2))
        assertEquals(0, tetra.boundaryEdges)
        assertEquals(0, tetra.nonManifoldEdges)
        assertEquals(1, tetra.components)
        assertEquals(4, tetra.largestComponentTriangles)
        // Zwei getrennte Dreiecke: zwei Komponenten, sechs Randkanten.
        val split = PartialMeshTopology.inspect(6, intArrayOf(0, 1, 2, 3, 4, 5))
        assertEquals(2, split.components)
        assertEquals(6, split.boundaryEdges)
        assertEquals(1, split.largestComponentTriangles)
        // Drei Dreiecke an einer gemeinsamen Kante sind keine Mannigfaltigkeit.
        val fan = PartialMeshTopology.inspect(5, intArrayOf(0, 1, 2, 0, 1, 3, 0, 1, 4))
        assertEquals(1, fan.nonManifoldEdges)
        assertEquals(1, fan.components)
        // Leeres Netz: keine erfundenen Zahlen.
        val empty = PartialMeshTopology.inspect(7, intArrayOf())
        assertEquals(0, empty.components)
        assertEquals(0, empty.triangleCount)
        assertEquals(7, empty.vertexCount)
    }

    @Test fun partialExportDeclaresTopologyConsistently() {
        val outcome = MultiViewCapture.reconstruct(listOf(view(0.0), view(-22.0)), intrinsics)
            as MultiViewCapture.Outcome.Reconstructed
        val result = outcome.result
        val mesh = result.surface.mesh!!
        val expected = PartialMeshTopology.inspect(mesh)
        assertEquals(expected.triangleCount, result.topology.triangleCount)
        assertEquals(expected.boundaryEdges, result.topology.boundaryEdges)
        assertEquals(expected.components, result.topology.components)
        // Ein offenes Teilnetz muss Randkanten haben, sonst wäre es geschlossen.
        assertTrue(result.topology.boundaryEdges > 0)
        assertEquals(0, result.topology.nonManifoldEdges)
        val obj = String(MultiViewCapture.writeObjWithHeader(result)!!, Charsets.UTF_8)
        assertTrue(obj.contains("# topology ${PartialMeshTopology.describe(expected)}"))
        // Das GLB deklariert die Struktur der tatsächlich geschriebenen Flächen;
        // in Float32 können zusätzliche Dreiecke flächenlos werden.
        val flat = FloatArray(mesh.vertices.size * 3) { i -> mesh.vertices[i / 3][i % 3].toFloat() }
        val written = PartialGlbWriter.floatSafeTriangles(flat, mesh.triangles)
        val writtenTopology = PartialMeshTopology.inspect(mesh.vertices.size, written)
        assertTrue(writtenTopology.triangleCount <= expected.triangleCount)
        val glb = String(PartialGlbWriter.write(mesh), Charsets.ISO_8859_1)
        assertTrue(glb.contains("\"triangles\":${writtenTopology.triangleCount}"))
        assertTrue(glb.contains("\"boundaryEdges\":${writtenTopology.boundaryEdges}"))
        assertTrue(glb.contains("\"components\":${writtenTopology.components}"))
        assertTrue(glb.contains("structure only, not a quality or accuracy measure"))
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

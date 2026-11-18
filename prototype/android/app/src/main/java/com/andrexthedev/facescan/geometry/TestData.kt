package com.andrexthedev.facescan.geometry

/**
 * Kleiner Helfer fuer die Unit-Tests: liefert die Ground-Truth-Daten je Frame.
 *
 * Die Fixtures sind von run_m0.py erzeugte Konstanten (M0Fixtures.kt), damit
 * die Tests ohne Robolectric und ohne JSON-Parser laufen.
 */
internal object TestData {

    fun camera(): CameraModel = CameraModel(
        fx = M0Fixtures.intrinsics[0],
        fy = M0Fixtures.intrinsics[1],
        cx = M0Fixtures.intrinsics[2],
        cy = M0Fixtures.intrinsics[3]
    )

    fun model(): MorphableModel = MorphableModel(
        meanVertices = M0Fixtures.baseVertices,
        identityBasis = M0Fixtures.identityBasis,
        expressionBasis = M0Fixtures.expressionBasis,
        kIdentity = M0Fixtures.K_IDENTITY,
        kExpression = M0Fixtures.K_EXPRESSION
    )

    fun landmarks(index: Int): DoubleArray = when (index) {
        0 -> M0Fixtures.landmarks0
        1 -> M0Fixtures.landmarks1
        2 -> M0Fixtures.landmarks2
        3 -> M0Fixtures.landmarks3
        4 -> M0Fixtures.landmarks4
        5 -> M0Fixtures.landmarks5
        6 -> M0Fixtures.landmarks6
        7 -> M0Fixtures.landmarks7
        else -> error("Fixture hat nur ${M0Fixtures.N_FRAMES} Frames")
    }

    fun visibility(index: Int): DoubleArray = when (index) {
        0 -> M0Fixtures.visibility0
        1 -> M0Fixtures.visibility1
        2 -> M0Fixtures.visibility2
        3 -> M0Fixtures.visibility3
        4 -> M0Fixtures.visibility4
        5 -> M0Fixtures.visibility5
        6 -> M0Fixtures.visibility6
        7 -> M0Fixtures.visibility7
        else -> error("Fixture hat nur ${M0Fixtures.N_FRAMES} Frames")
    }

    /** 1.0 = kuenstlich verrauschter Ausreisser. Nur fuer die Auswertung. */
    fun outliers(index: Int): DoubleArray = when (index) {
        0 -> M0Fixtures.outlierMask0
        1 -> M0Fixtures.outlierMask1
        2 -> M0Fixtures.outlierMask2
        3 -> M0Fixtures.outlierMask3
        4 -> M0Fixtures.outlierMask4
        5 -> M0Fixtures.outlierMask5
        6 -> M0Fixtures.outlierMask6
        7 -> M0Fixtures.outlierMask7
        else -> error("Fixture hat nur ${M0Fixtures.N_FRAMES} Frames")
    }

    fun groundTruth(index: Int): RigidTransform = RigidTransform(
        Mat3(
            when (index) {
                0 -> M0Fixtures.rotationTrue0
                1 -> M0Fixtures.rotationTrue1
                2 -> M0Fixtures.rotationTrue2
                3 -> M0Fixtures.rotationTrue3
                4 -> M0Fixtures.rotationTrue4
                5 -> M0Fixtures.rotationTrue5
                6 -> M0Fixtures.rotationTrue6
                7 -> M0Fixtures.rotationTrue7
                else -> error("Fixture hat nur ${M0Fixtures.N_FRAMES} Frames")
            }
        ),
        when (index) {
            0 -> M0Fixtures.translationTrue0
            1 -> M0Fixtures.translationTrue1
            2 -> M0Fixtures.translationTrue2
            3 -> M0Fixtures.translationTrue3
            4 -> M0Fixtures.translationTrue4
            5 -> M0Fixtures.translationTrue5
            6 -> M0Fixtures.translationTrue6
            7 -> M0Fixtures.translationTrue7
            else -> error("Fixture hat nur ${M0Fixtures.N_FRAMES} Frames")
        }
    )

    /** Sichtbare Korrespondenzen eines Frames (wie sie der Fit bekommt). */
    fun visibleCorrespondences(index: Int, points3d: DoubleArray): Pair<DoubleArray, DoubleArray> {
        val lm = landmarks(index)
        val vis = visibility(index)
        val n = points3d.size / 3
        var count = 0
        for (i in 0 until n) if (vis[i] >= 0.5) count++
        val p3 = DoubleArray(count * 3)
        val p2 = DoubleArray(count * 2)
        var w = 0
        for (i in 0 until n) {
            if (vis[i] < 0.5) continue
            p3[3 * w] = points3d[3 * i]
            p3[3 * w + 1] = points3d[3 * i + 1]
            p3[3 * w + 2] = points3d[3 * i + 2]
            p2[2 * w] = lm[2 * i]
            p2[2 * w + 1] = lm[2 * i + 1]
            w++
        }
        return p3 to p2
    }

    fun observations(): List<Observation> =
        (0 until M0Fixtures.N_FRAMES).map { Observation(landmarks(it), visibility(it)) }
}

package com.andrexthedev.facescan.scan

import com.andrexthedev.facescan.geometry.ValidatedAnchorPose

/**
 * Nur die Landmarkenanzahl des MediaPipe-Netzes; keine Geometrie.
 */
internal object CanonicalAnchors {
    const val LANDMARK_COUNT = 468
}

/**
 * 30 ausgewählte 3D-Anker einer kanonischen Durchschnittsgeometrie in
 * Zentimetern, exakt aus MediaPipe canonical_face_model.obj v0.10.14
 * (Apache-2.0, siehe assets/licenses/mediapipe.txt) extrahiert. Keine
 * Modellgewichte, keine personenbezogenen Daten.
 *
 * Achtung: Das ist ein Populationsmittel, keine Vermessung der aufgenommenen
 * Person. Die Anker weichen bei jeder realen Person ab; der daraus folgende
 * absolute Fehler ist NICHT validiert. Indizes und [points] müssen exakt
 * zueinander passen.
 */
internal object CanonicalAnchorData {
    val indices = intArrayOf(
        1, 4, 5, 6, 9, 10, 33, 45, 61, 105, 122, 133, 151, 152, 168,
        175, 195, 197, 199, 234, 263, 266, 275, 291, 308, 351, 362, 405, 425, 447
    )

    val points: DoubleArray = doubleArrayOf(
        0.000000, -1.126865, 7.475604,   // 1
        0.000000, -0.463170, 7.586580,   // 4 Nasenspitze
        0.000000, 0.365669, 7.242870,    // 5
        0.000000, 2.473255, 5.788627,    // 6
        0.000000, 4.885979, 5.385258,    // 9 Stirn
        0.000000, 8.261778, 4.481535,    // 10
        -4.445859, 2.663991, 3.173422,   // 33 rechtes Auge innen
        -0.496396, -0.475659, 7.440358,  // 45
        -2.456206, -4.342621, 4.283884,  // 61
        -3.986562, 5.109487, 4.466315,   // 105
        -0.563221, 2.307693, 5.566789,   // 122
        -1.856432, 2.585245, 3.757904,   // 133 rechtes Auge außen
        0.000000, 6.545390, 5.027311,    // 151
        0.000000, -9.403378, 4.264492,   // 152 Kinn
        0.000000, 3.271027, 5.236015,    // 168
        0.000000, -8.765243, 4.891441,   // 175
        0.000000, 1.059413, 6.774605,    // 195
        0.000000, 1.728369, 6.316750,    // 197
        0.000000, -7.942194, 5.181173,   // 199
        -7.664182, 0.673132, -2.435867,  // 234 rechte Wange
        4.445859, 2.663991, 3.173422,    // 263 linkes Auge innen
        2.844939, -0.720868, 4.433130,   // 266
        0.496396, -0.475659, 7.440358,   // 275
        2.456206, -4.342621, 4.283884,   // 291
        2.153084, -4.276322, 4.038093,   // 308
        0.563221, 2.307693, 5.566789,    // 351
        1.856432, 2.585245, 3.757904,    // 362 linkes Auge außen
        1.325085, -5.106507, 5.205010,   // 405
        3.832928, -1.537326, 4.137731,   // 425
        7.297331, 0.763172, -0.048769    // 447
    )

    const val COUNT = 30

    init {
        require(indices.size == COUNT && points.size == COUNT * 3)
        require(indices.distinct().size == COUNT && indices.all { it in 0 until CanonicalAnchors.LANDMARK_COUNT })
        require(points.all { it.isFinite() })
    }

    /** Weltanker mit den zugehörigen, vom Aufrufer gelieferten Bildpixeln. */
    fun anchors(pixelU: DoubleArray, pixelV: DoubleArray): List<ValidatedAnchorPose.Anchor> {
        require(pixelU.size == COUNT && pixelV.size == COUNT)
        require(pixelU.all { it.isFinite() } && pixelV.all { it.isFinite() })
        return List(COUNT) { i ->
            ValidatedAnchorPose.Anchor(
                doubleArrayOf(points[3 * i], points[3 * i + 1], points[3 * i + 2]),
                pixelU[i], pixelV[i]
            )
        }
    }

    /** Abstand zweier Anker in Zentimetern (Diagnose). */
    fun distance(a: Int, b: Int): Double {
        require(a in 0 until COUNT && b in 0 until COUNT)
        val dx = points[3 * a] - points[3 * b]
        val dy = points[3 * a + 1] - points[3 * b + 1]
        val dz = points[3 * a + 2] - points[3 * b + 2]
        return Math.sqrt(dx * dx + dy * dy + dz * dz)
    }
}

package com.andrexthedev.facescan.pipeline

/**
 * Qualitaetsbericht in LAIENSPRACHE (direkt so in der UI dargestellt).
 *
 * Regel: Jede Ampel hat ein Symbol und einen Satz – Farbe allein traegt nie
 * die Information (Barrierefreiheit, docs/07).
 */
data class QualityReport(
    val formtreue: Light,
    val detail: Light,
    val haar: Light,
    val abdeckung: Light,
    val textur: Light,
    val reprojectionPx: Double,
    val geometryMm: Double,
    val tips: List<String>
) {
    enum class State { GREEN, YELLOW, RED }

    data class Light(
        val state: State,
        val headlineDe: String,
        val headlineEn: String,
        val detailDe: String,
        val detailEn: String
    )

    val overall: State
        get() {
            val states = listOf(formtreue, detail, haar, abdeckung, textur).map { it.state }
            return when {
                states.any { it == State.RED } -> State.RED
                states.any { it == State.YELLOW } -> State.YELLOW
                else -> State.GREEN
            }
        }
}

object QualityThresholds {
    // Startwerte; muessen in M1 gegen die synthetische Ground Truth und die
    // 20 echten Testpersonen kalibriert werden (docs/10).
    const val REPRO_GREEN_PX = 1.5
    const val REPRO_YELLOW_PX = 3.0
    const val GEOMETRY_GREEN_MM = 0.8
    const val GEOMETRY_YELLOW_MM = 2.0
    const val COVERAGE_GREEN = 0.95
    const val COVERAGE_YELLOW = 0.80
}

fun buildReport(
    reprojectionPx: Double,
    geometryMm: Double,
    coverage: Double,
    hairCoverage: Double,
    textureHoles: Double
): QualityReport {
    fun light(state: QualityReport.State, de: String, en: String, detailDe: String, detailEn: String) =
        QualityReport.Light(state, de, en, detailDe, detailEn)

    val formtreue = when {
        geometryMm < QualityThresholds.GEOMETRY_GREEN_MM ->
            light(QualityReport.State.GREEN, "Form: sehr gut", "Shape: very good",
                "Abweichung ${"%.2f".format(geometryMm)} mm", "Deviation ${"%.2f".format(geometryMm)} mm")
        geometryMm < QualityThresholds.GEOMETRY_YELLOW_MM ->
            light(QualityReport.State.YELLOW, "Form: okay", "Shape: okay",
                "Abweichung ${"%.2f".format(geometryMm)} mm – für Details erneut scannen",
                "Deviation ${"%.2f".format(geometryMm)} mm – rescan for more detail")
        else ->
            light(QualityReport.State.RED, "Form: ungenau", "Shape: imprecise",
                "Abweichung ${"%.2f".format(geometryMm)} mm", "Deviation ${"%.2f".format(geometryMm)} mm")
    }

    val detail = when {
        reprojectionPx < QualityThresholds.REPRO_GREEN_PX ->
            light(QualityReport.State.GREEN, "Passung: sehr gut", "Alignment: very good",
                "${"%.2f".format(reprojectionPx)} px Abweichung", "${"%.2f".format(reprojectionPx)} px deviation")
        reprojectionPx < QualityThresholds.REPRO_YELLOW_PX ->
            light(QualityReport.State.YELLOW, "Passung: okay", "Alignment: okay",
                "${"%.2f".format(reprojectionPx)} px Abweichung", "${"%.2f".format(reprojectionPx)} px deviation")
        else ->
            light(QualityReport.State.RED, "Passung: schwach", "Alignment: weak",
                "${"%.2f".format(reprojectionPx)} px Abweichung", "${"%.2f".format(reprojectionPx)} px deviation")
    }

    val haar = when {
        hairCoverage > 0.85 -> light(QualityReport.State.GREEN, "Haare: gut erfasst", "Hair: captured well",
            "${(hairCoverage * 100).toInt()} % der Haarfläche", "${(hairCoverage * 100).toInt()} % of the hair area")
        hairCoverage > 0.70 -> light(QualityReport.State.YELLOW, "Haare: teilweise", "Hair: partial",
            "Hinterkopf ist geschätzt", "Back of the head is estimated")
        else -> light(QualityReport.State.RED, "Haare: lückenhaft", "Hair: incomplete",
            "Mit Spiegel oder Helfer erneut scannen", "Rescan with a mirror or a helper")
    }

    val abdeckung = when {
        coverage > QualityThresholds.COVERAGE_GREEN ->
            light(QualityReport.State.GREEN, "Rundum: vollständig", "Coverage: complete",
                "${(coverage * 100).toInt()} % der Oberfläche", "${(coverage * 100).toInt()} % of the surface")
        coverage > QualityThresholds.COVERAGE_YELLOW ->
            light(QualityReport.State.YELLOW, "Rundum: fast", "Coverage: almost",
                "Einige Stellen nur von einer Seite", "Some spots seen from one side only")
        else -> light(QualityReport.State.RED, "Rundum: lückenhaft", "Coverage: incomplete",
            "Bitte vollständig um den Kopf drehen", "Please turn all the way around")
    }

    val textur = when {
        textureHoles < 0.01 -> light(QualityReport.State.GREEN, "Oberfläche: vollständig", "Texture: complete",
            "Keine Lücken", "No gaps")
        textureHoles < 0.03 -> light(QualityReport.State.YELLOW, "Oberfläche: paar Lücken", "Texture: few gaps",
            "Automatisch aufgefüllt", "Filled automatically")
        else -> light(QualityReport.State.RED, "Oberfläche: viele Lücken", "Texture: many gaps",
            "Für saubere Textur erneut scannen", "Rescan for a clean texture")
    }

    val tips = ArrayList<String>()
    if (haar.state != QualityReport.State.GREEN) tips += "Hinterkopf: Spiegel oder zweite Person nutzen"
    if (abdeckung.state != QualityReport.State.GREEN) tips += "Langsamer und vollständig von -75° bis +75° drehen"
    if (detail.state == QualityReport.State.RED) tips += "Mehr Licht und ruhigere Hand – das bringt am meisten"
    if (textur.state == QualityReport.State.RED) tips += "Nicht direkt vor dem Fenster stehen (Gegenlicht)"

    return QualityReport(formtreue, detail, haar, abdeckung, textur, reprojectionPx, geometryMm, tips)
}

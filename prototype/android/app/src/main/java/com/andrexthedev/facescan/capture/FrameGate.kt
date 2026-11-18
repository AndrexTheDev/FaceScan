package com.andrexthedev.facescan.capture

import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Akzeptanzpruefung je Kamerabild.
 *
 * Prinzip: Es werden NUR Bilder gespeichert, die wirklich gut sind. Das spart
 * 60–80 % Speicher und Rechenzeit und ist der Unterschied zwischen "geht so"
 * und "sieht aus wie ich".
 *
 * Die Schwellwerte sind Startwerte und muessen in M1 empirisch kalibriert
 * werden (docs/03, Kapitel 11).
 */
class FrameGate {

    enum class Verdict { ACCEPT, RETRY, REJECT }

    data class Hint(val verdict: Verdict, val messageDe: String, val messageEn: String)

    data class Input(
        val sharpness: Float,          // Varianz des Laplacians im Gesichtsfenster
        val motionPx: Float,           // Landmark-Verschiebung zum Vorframe
        val meanLuma: Float,           // 0..255
        val clippedRatio: Float,       // Anteil ueberbelichteter Hautpixel
        val yawDeg: Float,
        val pitchDeg: Float,
        val coveredYaw: Set<Int>,      // bereits abgedeckte 5-Grad-Bloecke
        val hairPixelRatio: Float
    )

    fun evaluate(input: Input): Hint {
        if (input.clippedRatio > 0.02f) {
            return Hint(Verdict.RETRY,
                "Zu hell – geh etwas aus dem Licht.",
                "Too bright – step out of the light a little.")
        }
        if (input.meanLuma < 70f) {
            return Hint(Verdict.RETRY,
                "Zu dunkel – stell dich ans Fenster.",
                "Too dark – move towards a window.")
        }
        if (input.sharpness < 90f) {
            return Hint(Verdict.RETRY,
                "Bild ist unscharf – Handy ruhiger halten.",
                "Blurry – hold the phone steadier.")
        }
        if (input.motionPx > 2.5f) {
            return Hint(Verdict.RETRY,
                "Zu schnelle Bewegung – langsamer drehen.",
                "Too fast – turn more slowly.")
        }
        if (abs(input.pitchDeg) > 32f) {
            return Hint(Verdict.RETRY,
                "Kopf etwas mehr in die Waagerechte.",
                "Keep your head more level.")
        }
        if (input.hairPixelRatio < 0.03f) {
            return Hint(Verdict.RETRY,
                "Die Haare sind nicht im Bild – etwas weiter weg.",
                "Hair is out of frame – move a bit further away.")
        }
        val block = (input.yawDeg / 5f).toInt()
        if (block in input.coveredYaw) {
            return Hint(Verdict.REJECT,
                "Diesen Winkel haben wir schon – weiterdrehen.",
                "We already have this angle – keep turning.")
        }
        return Hint(Verdict.ACCEPT, "Perfekt – bleib so.", "Perfect – hold that.")
    }

    /** Schaerfe (Varianz des Laplacians) auf einem Grauwert-Streifen. */
    fun sharpness(gray: ByteArray, width: Int, height: Int, stride: Int): Float {
        if (width < 3 || height < 3) return 0f
        var sum = 0.0
        var sumSq = 0.0
        var count = 0
        for (y in 1 until height - 1) {
            for (x in 1 until width - 1) {
                val i = y * stride + x
                val lap = (4 * (gray[i].toInt() and 0xFF)
                    - ((gray[i - 1].toInt() and 0xFF) + (gray[i + 1].toInt() and 0xFF)
                    + (gray[i - stride].toInt() and 0xFF) + (gray[i + stride].toInt() and 0xFF)))
                sum += lap
                sumSq += lap * lap
                count++
            }
        }
        if (count == 0) return 0f
        val mean = sum / count
        return sqrt((sumSq / count - mean * mean).coerceAtLeast(0.0)).toFloat()
    }
}

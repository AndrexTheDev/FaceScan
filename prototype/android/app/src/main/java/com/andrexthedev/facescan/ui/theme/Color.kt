package com.andrexthedev.facescan.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Design-Tokens – Farben der jamaikanischen Flagge.
 *
 * WICHTIGE KONTRASTREGEL (gemessen, WCAG 2.2):
 *   Schwarz auf Flaggen-Gruen #009B3A  = 5,75:1  -> AA bestanden
 *   Schwarz auf Flaggen-Gold  #FFD100  = 14,37:1 -> AAA bestanden
 *   WEISS auf Flaggen-Gruen            = 3,65:1  -> faellt durch!
 *   Gold auf Weiss                     = 1,46:1  -> unbrauchbar!
 *
 * Daraus folgt die zentrale Designentscheidung:
 *   **Text auf Gruen und Gold ist immer SCHWARZ.**
 * Im Day-Mode wird Gruen abgedunkelt (#007A2E, 5,49:1 auf Weiss) und Gold nur
 * als Flaeche oder in der dunklen Textvariante #8A6A00 (5,07:1) verwendet.
 */
object FaceScanColors {

    // --- Markenfarben (Flagge) ------------------------------------------
    val JamaicaBlack = Color(0xFF000000)
    val JamaicaGreen = Color(0xFF009B3A)
    val JamaicaGold = Color(0xFFFFD100)

    // --- Night-Mode "Rasta Night" (Standard) ----------------------------
    val NightBackground = Color(0xFF000000)
    val NightSurface1 = Color(0xFF0E0E0E)
    val NightSurface2 = Color(0xFF1A1A1A)
    val NightSurface3 = Color(0xFF2A2A2A)
    val NightText = Color(0xFFF5F5F5)
    val NightTextSecondary = Color(0xFFA8A8A8)
    val NightGreen = Color(0xFF00B34A)       // 6,94:1 auf #0E0E0E
    val NightGold = Color(0xFFFFD100)
    val NightError = Color(0xFFFF6B6B)
    val OnBrandNight = Color(0xFF000000)     // Text auf Gruen/Gold

    // --- Day-Mode "Sunrise" ---------------------------------------------
    val DayBackground = Color(0xFFFFFFFF)
    val DaySurface1 = Color(0xFFF5F5F2)
    val DaySurface2 = Color(0xFFE9E9E4)
    val DaySurface3 = Color(0xFFD9D9D3)
    val DayText = Color(0xFF101010)
    val DayTextSecondary = Color(0xFF5A5A55)
    val DayGreen = Color(0xFF007A2E)         // 5,49:1 auf Weiss
    val DayGoldFill = Color(0xFFFFD100)      // nur als Flaeche mit schwarzer Schrift
    val DayGoldText = Color(0xFF8A6A00)      // Gold als Text/Link
    val DayError = Color(0xFFB3261E)         // 6,54:1
    val OnBrandDay = Color(0xFFFFFFFF)       // Text auf DayGreen

    // --- Semantik --------------------------------------------------------
    val Ok = NightGreen
    val Warn = Color(0xFFFFC400)
    val Error = NightError
}

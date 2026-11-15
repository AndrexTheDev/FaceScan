package com.andrexthedev.facescan.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * Designsystem: Night (Standard) + Day.
 *
 * Schatten werden im Night-Mode weggelassen (auf Schwarz unsichtbar) und durch
 * 1-dp-Raender ersetzt. "Dynamic Color" (Android 12+) wird bewusst NICHT
 * verwendet: die Markenfarben sind Teil des Produkts und duerfen sich nicht
 * nach dem Hintergrundbild des Nutzers verfaerben.
 */
private val NightScheme = darkColorScheme(
    primary = FaceScanColors.NightGreen,
    onPrimary = FaceScanColors.OnBrandNight,
    secondary = FaceScanColors.NightGold,
    onSecondary = FaceScanColors.OnBrandNight,
    background = FaceScanColors.NightBackground,
    onBackground = FaceScanColors.NightText,
    surface = FaceScanColors.NightSurface1,
    onSurface = FaceScanColors.NightText,
    surfaceVariant = FaceScanColors.NightSurface2,
    onSurfaceVariant = FaceScanColors.NightTextSecondary,
    error = FaceScanColors.NightError,
    onError = Color.Black,
    outline = FaceScanColors.NightSurface3
)

private val DayScheme = lightColorScheme(
    primary = FaceScanColors.DayGreen,
    onPrimary = FaceScanColors.OnBrandDay,
    secondary = FaceScanColors.DayGoldFill,
    onSecondary = Color.Black,
    background = FaceScanColors.DayBackground,
    onBackground = FaceScanColors.DayText,
    surface = FaceScanColors.DaySurface1,
    onSurface = FaceScanColors.DayText,
    surfaceVariant = FaceScanColors.DaySurface2,
    onSurfaceVariant = FaceScanColors.DayTextSecondary,
    error = FaceScanColors.DayError,
    onError = Color.White,
    outline = FaceScanColors.DaySurface3
)

private val AppTypography = Typography(
    displayLarge = TextStyle(fontSize = 34.sp, fontWeight = FontWeight.Bold, lineHeight = 40.sp),
    headlineMedium = TextStyle(fontSize = 24.sp, fontWeight = FontWeight.SemiBold, lineHeight = 30.sp),
    titleMedium = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 23.sp),
    bodyMedium = TextStyle(fontSize = 15.sp, lineHeight = 22.sp),
    labelLarge = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Bold)
)

enum class AppThemeMode { SYSTEM, NIGHT, DAY }

@Composable
fun FaceScanTheme(
    mode: AppThemeMode = AppThemeMode.SYSTEM,
    useDynamicColor: Boolean = false,
    content: @Composable () -> Unit
) {
    val darkTheme = when (mode) {
        AppThemeMode.SYSTEM -> isSystemInDarkTheme()
        AppThemeMode.NIGHT -> true
        AppThemeMode.DAY -> false
    }
    val context = LocalContext.current
    val colorScheme = when {
        useDynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
            if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        }
        darkTheme -> NightScheme
        else -> DayScheme
    }
    MaterialTheme(
        colorScheme = colorScheme,
        typography = AppTypography,
        content = content
    )
}

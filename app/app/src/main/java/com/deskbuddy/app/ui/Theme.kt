package com.deskbuddy.app.ui

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import com.deskbuddy.app.R

/**
 * The kawaii pastel colour tokens, in light and dark. Same names and values as the Figma
 * variables "Kawaii / Light" and "Kawaii / Dark" (file qS3xjTV6SfNbELhLHzSix4).
 */
data class Pal(
    val bg: Color,        // screen background
    val surface: Color,   // cards, tab bar, outlined tiles
    val surface2: Color,  // segmented tracks, fields, soft buttons, chips
    val line: Color,      // 1.5 dp outlines, switch track when off
    val ink: Color,       // text and icons
    val sub: Color,       // secondary text
    val accent: Color,    // selected / primary
    val accentInk: Color, // text and icons on accent
    val lavender: Color,  // pastel tiles and avatars
    val mint: Color,
    val butter: Color,
    val sky: Color,
    val oled: Color,      // Mochi's screen
    val pixel: Color,     // Mochi's face
    val blush: Color,     // Mochi's cheeks
    val glow: Color,      // soft shadows: pink in light, black in dark
)

val LightPal = Pal(
    bg = Color(0xFFFFF5F8), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFFFE9F1), line = Color(0xFFF4D7E3),
    ink = Color(0xFF3A2840), sub = Color(0xFF8A7590), accent = Color(0xFFFF8FB3), accentInk = Color(0xFF3A2840),
    lavender = Color(0xFFE3D9FF), mint = Color(0xFFCDF2E2), butter = Color(0xFFFFEDB8), sky = Color(0xFFD3EAFF),
    oled = Color(0xFF241C2C), pixel = Color(0xFFFFFFFF), blush = Color(0xFFFF9EBB), glow = Color(0xFFFF8FB2),
)

val DarkPal = Pal(
    bg = Color(0xFF1B1520), surface = Color(0xFF282030), surface2 = Color(0xFF35293D), line = Color(0xFF45374E),
    ink = Color(0xFFFBEFF5), sub = Color(0xFFBFAAC6), accent = Color(0xFFFF9EBF), accentInk = Color(0xFF2A1A26),
    lavender = Color(0xFF43395F), mint = Color(0xFF2C5144), butter = Color(0xFF56482A), sky = Color(0xFF2B455C),
    oled = Color(0xFF0E0A12), pixel = Color(0xFFFFFFFF), blush = Color(0xFFFF9EBB), glow = Color(0xFF000000),
)

val LocalPal = staticCompositionLocalOf { LightPal }

/** Fredoka SemiBold for titles and big numbers, Nunito for everything else (both SIL OFL, see FONTS-OFL.txt). */
val HeadFont = FontFamily(Font(R.font.fredoka_semibold, FontWeight.SemiBold))
val BodyFont = FontFamily(
    Font(R.font.nunito_regular, FontWeight.Normal),
    Font(R.font.nunito_bold, FontWeight.Bold),
)

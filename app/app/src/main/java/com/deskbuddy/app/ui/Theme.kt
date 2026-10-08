package com.deskbuddy.app.ui

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import com.deskbuddy.app.R

/** The app's whole colour system: one neutral set + one accent, in light and dark. */
data class Pal(
    val bg: Color,      // screen background
    val panel: Color,   // cards, buttons
    val line: Color,    // hard offset shadows
    val sub: Color,     // secondary text
    val ink: Color,     // text + borders
    val scr: Color,     // Mochi's OLED screen
    val px: Color,      // Mochi's pixels
    val acc: Color,     // active / selected
    val onAcc: Color,   // text on accent
    val soft: Color,    // inputs, toggle tracks, empty segments
)

val LightPal = Pal(
    bg = Color(0xFFF7F5F0), panel = Color(0xFFFFFFFF), line = Color(0xFF1A1A1A), sub = Color(0xFF5C5A55),
    ink = Color(0xFF1A1A1A), scr = Color(0xFF0D0D0D), px = Color(0xFFFFFFFF),
    acc = Color(0xFFC2410C), onAcc = Color(0xFFFFFFFF), soft = Color(0xFFECE9E1),
)

val DarkPal = Pal(
    bg = Color(0xFF121212), panel = Color(0xFF1D1D1D), line = Color(0xFF000000), sub = Color(0xFFA9A9A9),
    ink = Color(0xFFF2F2F2), scr = Color(0xFF050505), px = Color(0xFFFFFFFF),
    acc = Color(0xFFFB923C), onAcc = Color(0xFF121212), soft = Color(0xFF2A2A2A),
)

val LocalPal = staticCompositionLocalOf { LightPal }

/** Pixel font for headings/labels, terminal font for body text (both SIL OFL). */
val PixelFont = FontFamily(Font(R.font.press_start_2p))
val TermFont = FontFamily(Font(R.font.vt323))

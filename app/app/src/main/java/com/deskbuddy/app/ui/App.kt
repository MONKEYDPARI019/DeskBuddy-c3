package com.deskbuddy.app.ui

import android.app.Activity
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import com.deskbuddy.app.AppState

@Composable
fun DeskBuddyApp(actions: Actions) {
    val dark = when (AppState.theme) {
        "dark" -> true
        "light" -> false
        else -> isSystemInDarkTheme()
    }
    val pal = if (dark) DarkPal else LightPal

    // status + navigation bar follow the theme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            @Suppress("DEPRECATION")
            window.statusBarColor = pal.bg.toArgb()
            @Suppress("DEPRECATION")
            window.navigationBarColor = pal.bg.toArgb()
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = !dark
                isAppearanceLightNavigationBars = !dark
            }
        }
    }

    var tab by rememberSaveable { mutableStateOf("home") }
    CompositionLocalProvider(LocalPal provides pal) {
        Column(Modifier.fillMaxSize().background(pal.bg)) {
            Header(AppState.connected, dark) { actions.setTheme(if (dark) "light" else "dark") }
            Box(Modifier.weight(1f).fillMaxWidth()) {
                when (tab) {
                    "moods" -> MoodsScreen()
                    "inbox" -> InboxScreen(actions)
                    "voice" -> VoiceScreen(actions)
                    "setup" -> SetupScreen(actions)
                    else -> HomeScreen(actions) { tab = "setup" }
                }
            }
            TabBar(tab) { tab = it }
        }
    }
}

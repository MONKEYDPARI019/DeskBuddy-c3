package com.deskbuddy.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deskbuddy.app.AppState
import com.deskbuddy.app.DeskBuddyClient
import kotlin.math.roundToInt

/** Things the screens need from the Activity (phone features). */
interface Actions {
    val host: String
    val port: Int
    var forward: Boolean
    var echo: Boolean
    fun link(host: String, port: Int)
    fun stop()
    fun find(onFound: (String, Int) -> Unit)
    fun openNotificationAccess()
    fun speak(text: String)
    fun setTheme(theme: String)
    fun setBlocked(app: String, blocked: Boolean)
    fun setModel(model: String)          // "v2" (ESP32 desk) | "c3" (ESP32-C3 pocket)
    fun setLinkMode(mode: String)        // C3 only: "ble" | "wifi"
}

@Composable
private fun ScreenColumn(content: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(start = 20.dp, top = 20.dp, end = 22.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) { content() }
}

private fun faceLabel(): String = when (AppState.face) {
    "listen" -> "LISTENING"
    "think" -> "THINKING"
    "speak" -> "SPEAKING"
    "notify" -> "NEW MSG!"
    "sleep" -> "ASLEEP"
    else -> AppState.shown.uppercase()
}

@Composable
private fun OfflineBanner(onGoSetup: () -> Unit) {
    if (AppState.connected) return
    val c = LocalPal.current
    Column(
        Modifier.fillMaxWidth().border(3.dp, c.ink).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        PxText("NOT LINKED", 9.sp)
        TermText(AppState.statusText, 20.sp, c.sub)
        PixelButton("GO TO SETUP", Modifier.fillMaxWidth(), fontSize = 8.sp) { onGoSetup() }
    }
}

// ================================================================ HOME

@Composable
fun HomeScreen(actions: Actions, goSetup: () -> Unit) {
    val c = LocalPal.current
    ScreenColumn {
        OfflineBanner(goSetup)
        PixelCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                PxText("MOCHI.LIVE", 9.sp, modifier = Modifier.weight(1f))
                TermText(faceLabel(), 22.sp, c.sub)
            }
            Box(Modifier.fillMaxWidth().border(3.dp, c.ink).padding(3.dp)) {
                MochiFace(AppState.shown, AppState.face, Modifier.fillMaxWidth().aspectRatio2to1())
            }
            OptionRow(
                if (AppState.isC3) listOf("clock" to "CLOCK", "mochi" to "MOCHI", "notify" to "INBOX")
                else listOf("clock" to "CLOCK", "weather" to "WTHR", "mochi" to "MOCHI", "notify" to "INBOX", "pomodoro" to "POMO"),
                AppState.screen
            ) { id -> AppState.screen = id; DeskBuddyClient.screen(id) }
        }
        if (AppState.isC3) {
            // DeskBuddy C3: link + battery instead of WiFi bars + weather
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatTile("LINK", Modifier.weight(1f)) {
                    TermText(if (AppState.linkMode == "ble") "BLUETOOTH" else "WIFI", 24.sp, maxLines = 1)
                    TermText(AppState.ip.ifEmpty { "--" }, 19.sp, c.sub, maxLines = 1)
                }
                StatTile("BATTERY", Modifier.weight(1f)) {
                    TermText(when {
                        !AppState.connected -> "--"
                        AppState.bat < 0 -> "USB"
                        else -> "${AppState.bat}%"
                    }, 30.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatTile("UNREAD", Modifier.weight(1f)) { TermText("${AppState.unread}", 34.sp) }
                StatTile("DEVICE", Modifier.weight(1f)) {
                    TermText("C3 POCKET", 24.sp, maxLines = 1)
                    TermText(AppState.fw.ifEmpty { "--" }, 19.sp, c.sub, maxLines = 1)
                }
            }
        } else Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatTile("LINK", Modifier.weight(1f)) {
                TermText(AppState.ip.ifEmpty { actions.host }, 24.sp, maxLines = 1)
            }
            StatTile("WIFI", Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    WifiBars(if (AppState.connected) AppState.rssi else -200)
                    TermText(if (AppState.connected) "${AppState.rssi} dBm" else "--", 24.sp, maxLines = 1)
                }
            }
        }
        if (!AppState.isC3) Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatTile("UNREAD", Modifier.weight(1f)) { TermText("${AppState.unread}", 34.sp) }
            StatTile("WEATHER", Modifier.weight(1f)) {
                val t = AppState.temp
                TermText(if (t != null) "$t°C" else "--", 30.sp)
                TermText(AppState.city.ifEmpty { "set a city" }, 19.sp, c.sub, maxLines = 1)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            PixelButton(if (AppState.silent) "MUTED" else "SOUND", Modifier.weight(1f), active = AppState.silent, minHeight = 52.dp) {
                val s = !AppState.silent
                AppState.silent = s
                DeskBuddyClient.set("silent", s)
            }
            PixelButton("PING", Modifier.weight(1f), minHeight = 52.dp) {
                DeskBuddyClient.notify("DeskBuddy", "Ping", "Hello from the app")
            }
            PixelButton("ZZZ", Modifier.weight(1f), minHeight = 52.dp) { DeskBuddyClient.face("sleep") }
        }
    }
}

private fun Modifier.aspectRatio2to1(): Modifier = this.aspectRatio(2f)

@Composable
private fun WifiBars(rssi: Int) {
    val c = LocalPal.current
    val bars = when {
        rssi >= -55 -> 4
        rssi >= -65 -> 3
        rssi >= -75 -> 2
        rssi > -100 -> 1
        else -> 0
    }
    Canvas(Modifier.size(40.dp, 30.dp)) {
        val w = size.width / 16f
        for (i in 0 until 4) {
            val h = size.height * (i + 1) / 4f
            drawRect(if (i < bars) c.ink else c.soft, Offset(i * 4 * w, size.height - h), Size(3 * w, h))
        }
    }
}

// ================================================================ MOODS

@Composable
fun MoodsScreen() {
    val c = LocalPal.current
    ScreenColumn {
        ScreenTitle("MOODS") { TermText("NOW: ${AppState.mood.uppercase()}", 22.sp, c.sub) }
        TermText("Tap a face. Mochi changes instantly.", 21.sp, c.sub)
        MOODS.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                row.forEach { id ->
                    val on = id == AppState.mood
                    MoodTile(id, on, Modifier.weight(1f)) {
                        AppState.mood = id
                        DeskBuddyClient.face(id)
                    }
                }
            }
        }
    }
}

@Composable
private fun MoodTile(id: String, on: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val c = LocalPal.current
    Column(
        modifier
            .pixelFrame(if (on) c.acc else c.panel, c.ink, if (on) null else c.line)
            .semantics { role = Role.Button; contentDescription = "Set mood $id" }
            .pointerInput(id) { detectTapGestures(onTap = { onClick() }) }
            .padding(top = 8.dp, bottom = 6.dp, start = 6.dp, end = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Box(Modifier.fillMaxWidth().border(2.dp, c.ink).padding(2.dp)) {
            MochiFace(id, animate = false, modifier = Modifier.fillMaxWidth().aspectRatio2to1())
        }
        TermText(id.uppercase(), 19.sp, if (on) c.onAcc else c.ink, maxLines = 1)
    }
}

// ================================================================ INBOX

@Composable
fun InboxScreen(actions: Actions) {
    val c = LocalPal.current
    ScreenColumn {
        ScreenTitle("INBOX") {
            if (AppState.inbox.isNotEmpty()) {
                PixelButton("CLEAR", fontSize = 8.sp, minHeight = 40.dp) { AppState.inbox.clear() }
            }
        }
        if (AppState.inbox.isEmpty()) {
            TermText("Nothing yet. Notifications sent to DeskBuddy show up here.", 21.sp, c.sub)
        }
        AppState.inbox.take(20).forEach { n ->
            Column(
                Modifier.fillMaxWidth().pixelFrame(c.panel, c.ink, c.line).padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.background(c.soft).padding(horizontal = 6.dp, vertical = 5.dp)) {
                        PxText(n.app.uppercase().take(14), 8.sp)
                    }
                    Spacer(Modifier.weight(1f))
                    TermText(ago(n.time), 19.sp, c.sub)
                }
                TermText(n.title, 25.sp, maxLines = 1)
                if (n.body.isNotBlank()) TermText(n.body, 20.sp, c.sub, maxLines = 3)
            }
        }
        PixelCard("FORWARD FROM") {
            ToggleRow("All notifications", actions.forward) { actions.forward = it }
            if (AppState.knownApps.isEmpty()) {
                TermText("Apps appear here after their first notification.", 20.sp, c.sub)
            }
            AppState.knownApps.forEach { app ->
                val on = app !in AppState.blockedApps
                ToggleRow(app, on) { actions.setBlocked(app, !it) }
            }
        }
        PixelCard("PHONE ACCESS") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TermText(
                    if (AppState.notifAccess) "Notification access: ON" else "Notification access: OFF",
                    22.sp, modifier = Modifier.weight(1f)
                )
                if (!AppState.notifAccess) {
                    PixelButton("GRANT", fontSize = 8.sp, active = true) { actions.openNotificationAccess() }
                }
            }
        }
    }
}

private fun ago(t: Long): String {
    val s = (System.currentTimeMillis() - t) / 1000
    return when {
        s < 60 -> "now"
        s < 3600 -> "${s / 60}m"
        s < 86400 -> "${s / 3600}h"
        else -> "${s / 86400}d"
    }
}

// ================================================================ VOICE

@Composable
fun VoiceScreen(actions: Actions) {
    val c = LocalPal.current
    var holding by remember { mutableStateOf(false) }
    var sayText by remember { mutableStateOf("Hello Parinith!") }
    var echo by remember { mutableStateOf(actions.echo) }
    val listening = holding || AppState.face == "listen"
    if (AppState.isC3) {
        ScreenColumn {
            ScreenTitle("VOICE")
            PixelCard("NOT ON C3") {
                TermText("DeskBuddy C3 has no mic or speaker, so voice is only on the ESP32 desk version.", 20.sp, c.sub)
                TermText("Switch the device type in SETUP to use voice.", 20.sp, c.sub)
            }
        }
        return
    }
    ScreenColumn {
        ScreenTitle("VOICE")
        Column(
            Modifier.fillMaxWidth().border(3.dp, c.ink).padding(horizontal = 12.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            if (AppState.mic) {
                PxText("MIC READY", 8.sp)
                TermText("Hold the button below, or BTN3 on DeskBuddy.", 20.sp, c.sub)
            } else {
                PxText("MIC OFFLINE", 8.sp)
                TermText("Fit the INMP441, then: set mic_en on", 20.sp, c.sub)
            }
        }
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            Box(Modifier.width(200.dp).border(3.dp, c.ink).padding(3.dp)) {
                MochiFace(AppState.shown, if (holding) "listen" else AppState.face, Modifier.fillMaxWidth().aspectRatio2to1())
            }
        }
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            Column(
                Modifier
                    .size(250.dp, 132.dp)
                    .pixelFrame(if (listening) c.acc else c.panel, c.ink, if (listening) null else c.line, 6.dp, 4.dp)
                    .semantics { role = Role.Button; contentDescription = "Hold to talk" }
                    .pointerInput(Unit) {
                        detectTapGestures(onPress = {
                            holding = true
                            DeskBuddyClient.ptt(true)
                            tryAwaitRelease()
                            holding = false
                            DeskBuddyClient.ptt(false)
                        })
                    },
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                val fg = if (listening) c.onAcc else c.ink
                PixelIcon(Icons.voice, 48.dp, fg)
                PxText(if (listening) "LISTENING..." else "HOLD TO TALK", 11.sp, fg, Modifier.padding(top = 12.dp))
            }
        }
        TermText(
            "MOCHI IS: ${faceLabel()}", 22.sp, c.sub,
            Modifier.fillMaxWidth()
        )
        PixelCard("MAKE MOCHI SAY") {
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                PixelField(sayText, { sayText = it }, "TEXT", Modifier.weight(1f))
                PixelButton("SAY", minHeight = 50.dp) { if (sayText.isNotBlank()) actions.speak(sayText) }
            }
            ToggleRow("Echo test (repeat what I say)", echo) { echo = it; actions.echo = it }
        }
    }
}

// ================================================================ SETUP

@Composable
fun SetupScreen(actions: Actions) {
    val c = LocalPal.current
    val c3 = AppState.isC3
    val ble = c3 && AppState.linkMode == "ble"
    var host by remember(AppState.model) { mutableStateOf(actions.host) }
    var port by remember { mutableStateOf(actions.port.toString()) }
    var city by remember { mutableStateOf(AppState.owmCity) }
    var forward by remember { mutableStateOf(actions.forward) }
    var note by remember { mutableStateOf("") }
    ScreenColumn {
        ScreenTitle("SETUP")
        PixelCard("DEVICE TYPE") {
            OptionRow(listOf("v2" to "ESP32 DESK", "c3" to "C3 POCKET"), AppState.model, term = false) { m ->
                note = ""
                actions.setModel(m)
            }
            TermText(
                if (c3) "DeskBuddy C3: clock, Mochi, notifications. Bluetooth or WiFi."
                else "DeskBuddy v2: all screens, voice and weather. WiFi only.",
                20.sp, c.sub
            )
        }
        if (c3) PixelCard("LINK") {
            OptionRow(listOf("ble" to "BLUETOOTH", "wifi" to "WIFI"), AppState.linkMode, term = false) { m ->
                actions.setLinkMode(m)
            }
            TermText(
                if (ble) "Works anywhere within ~10 m, best battery life."
                else "Phone and DeskBuddy on the same WiFi. First time: join 'DeskBuddy_C3_Setup'.",
                20.sp, c.sub
            )
            TermText("Stuck? Hold both buttons while switching DeskBuddy on to force WiFi.", 19.sp, c.sub)
        }
        PixelCard("CONNECTION") {
            if (!ble) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                PixelField(host, { host = it.trim() }, "HOST", Modifier.weight(1f))
                PixelField(port, { port = it.filter(Char::isDigit).take(5) }, "PORT", Modifier.width(84.dp), number = true)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                PixelButton("LINK", Modifier.weight(1f), active = AppState.connected) {
                    actions.link(host.ifEmpty { if (c3) "deskbuddy-c3.local" else "deskbuddy.local" }, port.toIntOrNull() ?: 81)
                }
                if (!ble) PixelButton("FIND", Modifier.weight(1f)) {
                    note = "searching..."
                    actions.find { h, p -> host = h; port = p.toString(); note = "found $h:$p" }
                }
                PixelButton("STOP", Modifier.weight(1f)) { actions.stop() }
            }
            TermText(if (note.isNotEmpty()) note else AppState.statusText, 20.sp, c.sub)
        }
        PixelCard("DEVICE") {
            val volLevel = (AppState.volume / 10f).roundToInt().coerceIn(0, 10)
            SegmentBar(if (c3) "BUZZER" else "VOLUME", volLevel, "${AppState.volume}%") { i ->
                AppState.volume = i * 10
                DeskBuddyClient.set("volume", i * 10)
            }
            val briLevel = (AppState.bright / 25.5f).roundToInt().coerceIn(0, 10)
            SegmentBar("BRIGHTNESS", briLevel, "${briLevel * 10}%") { i ->
                val v = if (i == 10) 255 else i * 25
                AppState.bright = v
                DeskBuddyClient.set("brightness", v)
            }
            ToggleRow("Silent mode", AppState.silent) { AppState.silent = it; DeskBuddyClient.set("silent", it) }
            ToggleRow("Forward notifications", forward) { forward = it; actions.forward = it }
            if (c3) PixelButton("POWER OFF DESKBUDDY", Modifier.fillMaxWidth()) {
                DeskBuddyClient.send(org.json.JSONObject().put("type", "power_off"))
                note = "powering off - hold BTN1 for 3 s to wake"
            }
        }
        PixelCard("SLEEP AFTER") {
            val cur = when (AppState.sleepSec) { 0 -> "0"; in 1..90 -> "60"; in 91..600 -> "300"; else -> "900" }
            OptionRow(listOf("0" to "OFF", "60" to "1M", "300" to "5M", "900" to "15M"), cur) { v ->
                AppState.sleepSec = v.toInt()
                DeskBuddyClient.set("sleep_sec", v.toInt())
            }
        }
        PixelCard("THEME") {
            OptionRow(listOf("light" to "LIGHT", "dark" to "DARK", "auto" to "AUTO"), AppState.theme, term = false) {
                actions.setTheme(it)
            }
            TermText("AUTO follows your phone's dark mode.", 20.sp, c.sub)
        }
        if (!c3) {
            PixelCard("WEATHER") {
                PixelField(city, { city = it }, "CITY")
                TermText("One word works best, e.g. Bengaluru or Bangalore,IN", 19.sp, c.sub)
            }
            PixelButton("SAVE TO DESKBUDDY", Modifier.fillMaxWidth(), active = true, fontSize = 11.sp, minHeight = 60.dp) {
                if (city.isNotBlank()) DeskBuddyClient.set("owm_city", city.trim())
                note = if (AppState.connected) "saved to DeskBuddy" else "not linked - nothing saved"
            }
        }
        if (AppState.fw.isNotEmpty()) {
            TermText("DeskBuddy firmware ${AppState.fw}", 19.sp, c.sub, Modifier.fillMaxWidth())
        }
    }
}

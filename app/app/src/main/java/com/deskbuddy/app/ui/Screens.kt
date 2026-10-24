package com.deskbuddy.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.deskbuddy.app.AppState
import com.deskbuddy.app.DeskBuddyClient
import com.deskbuddy.app.R
import kotlin.math.roundToInt

/** Things the screens need from the Activity (phone features). */
interface Actions {
    val host: String
    val port: Int
    var forward: Boolean
    var echo: Boolean
    var keepInBackground: Boolean        // keep the link alive after the app is swiped away
    fun link(host: String, port: Int)
    fun stop()
    fun find(onFound: (String, Int) -> Unit)
    fun openNotificationAccess()
    fun speak(text: String)
    fun setTheme(theme: String)
    fun setBlocked(app: String, blocked: Boolean)
    fun setModel(model: String)          // "v2" (ESP32 desk) | "c3" (ESP32-C3 pocket)
    fun setLinkMode(mode: String)        // C3 only: "ble" | "wifi"
    fun changeWifi()                     // C3 only: restart into the WiFi setup portal
    fun clearNotifications()             // the app's list, and DeskBuddy's (C3 firmware 2.3.1+)
}

@Composable
private fun ScreenColumn(content: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(start = 16.dp, top = 6.dp, end = 16.dp, bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) { content() }
}

@Composable
private fun OfflineBanner(onGoSetup: () -> Unit) {
    if (AppState.connected) return
    val c = LocalPal.current
    KCard("Not linked") {
        BodyText(AppState.statusText, 14.sp, c.sub)
        KButton("Go to Setup", Modifier.fillMaxWidth(), Kind.PRIMARY) { onGoSetup() }
    }
}

/** Two equal-height tiles side by side. */
@Composable
private fun TileRow(content: @Composable (Modifier) -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(IntrinsicSize.Min),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) { content(Modifier.weight(1f).fillMaxHeight()) }
}

// ================================================================ HOME

@Composable
fun HomeScreen(actions: Actions, goSetup: () -> Unit) {
    val c = LocalPal.current
    ScreenColumn {
        OfflineBanner(goSetup)
        KCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                HeadText("Mochi live", 17.sp, modifier = Modifier.weight(1f))
                Chip(faceLabel(AppState.face, AppState.shown), c.surface2, c.accent)
            }
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(132.dp)
                    .background(c.oled, RoundedCornerShape(20.dp)),
                contentAlignment = Alignment.Center
            ) {
                MochiFace(
                    AppState.shown, AppState.face,
                    Modifier.fillMaxHeight(0.78f).aspectRatio(2f, matchHeightConstraintsFirst = true)
                )
            }
            Segmented(
                if (AppState.isC3) listOf("clock" to "Clock", "mochi" to "Mochi", "notify" to "Inbox")
                else listOf("clock" to "Clock", "weather" to "Wthr", "mochi" to "Mochi", "notify" to "Inbox", "pomodoro" to "Pomo"),
                AppState.screen
            ) { id -> AppState.screen = id; DeskBuddyClient.screen(id) }
        }
        if (AppState.isC3) {
            // DeskBuddy C3: link + battery instead of WiFi bars + weather
            val ble = AppState.linkMode == "ble"
            TileRow { m ->
                StatTile(if (ble) R.drawable.ic_bluetooth else R.drawable.ic_wifi, "Link", c.sky, m) {
                    TileValue(if (ble) "Bluetooth" else "WiFi", if (ble) null else AppState.ip)
                }
                StatTile(R.drawable.ic_battery, "Battery", c.mint, m) {
                    TileValue(when {
                        !AppState.connected -> "--"
                        AppState.bat < 0 -> "USB"
                        else -> "${AppState.bat}%"
                    })
                }
            }
            TileRow { m ->
                StatTile(R.drawable.ic_mail, "Unread", c.butter, m) { TileValue("${AppState.unread}") }
                StatTile(R.drawable.ic_chip, "Device", c.lavender, m) { TileValue("C3 Pocket", AppState.fw) }
            }
        } else {
            TileRow { m ->
                StatTile(R.drawable.ic_wifi, "Link", c.sky, m) { TileValue(AppState.ip.ifEmpty { actions.host }, size = 15.sp) }
                StatTile(R.drawable.ic_wifi, "WiFi", c.mint, m) {
                    Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        WifiBars(if (AppState.connected) AppState.rssi else -200)
                        HeadText(if (AppState.connected) "${AppState.rssi} dBm" else "--", 19.sp, maxLines = 1)
                    }
                }
            }
            TileRow { m ->
                StatTile(R.drawable.ic_mail, "Unread", c.butter, m) { TileValue("${AppState.unread}") }
                StatTile(R.drawable.ic_sun, "Weather", c.lavender, m) {
                    val t = AppState.temp
                    TileValue(if (t != null) "$t°C" else "--", AppState.city.ifEmpty { "set a city" })
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            ActionTile(
                if (AppState.silent) R.drawable.ic_speaker_off else R.drawable.ic_speaker,
                if (AppState.silent) "Muted" else "Sound", Modifier.weight(1f), active = AppState.silent
            ) {
                val s = !AppState.silent
                AppState.silent = s
                DeskBuddyClient.set("silent", s)
            }
            ActionTile(R.drawable.ic_bell, "Ping", Modifier.weight(1f)) {
                DeskBuddyClient.notify("DeskBuddy", "Ping", "Hello from the app")
            }
            ActionTile(R.drawable.ic_moon, "Zzz", Modifier.weight(1f)) { DeskBuddyClient.face("sleep") }
        }
    }
}

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
    Canvas(Modifier.size(26.dp, 20.dp)) {
        val w = size.width / 15f
        for (i in 0 until 4) {
            val h = size.height * (i + 1) / 4f
            drawRoundRect(
                if (i < bars) c.ink else c.ink.copy(alpha = 0.2f),
                Offset(i * 4 * w, size.height - h), Size(3 * w, h), CornerRadius(w)
            )
        }
    }
}

// ================================================================ MOODS

@Composable
fun MoodsScreen() {
    val c = LocalPal.current
    ScreenColumn {
        ScreenTitle("Moods") { Chip("Now: ${AppState.mood}", c.surface2, c.accent) }
        BodyText("Tap a face. Mochi changes instantly.", 14.sp, c.sub)
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            MOODS.chunked(3).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    row.forEach { id ->
                        MoodTile(id, id == AppState.mood, Modifier.weight(1f)) {
                            AppState.mood = id
                            DeskBuddyClient.face(id)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MoodTile(id: String, on: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val c = LocalPal.current
    val shape = RoundedCornerShape(20.dp)
    Column(
        modifier
            .background(if (on) c.accent else c.surface, shape)
            .border(1.5.dp, if (on) c.accent else c.line, shape)
            .clip(shape)
            .clickable(role = Role.Button, onClickLabel = "Set mood $id") { onClick() }
            .padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        Box(
            Modifier
                .size(60.dp, 42.dp)
                .background(c.oled, RoundedCornerShape(12.dp)),
            contentAlignment = Alignment.Center
        ) {
            Image(painterResource(faceRes(id)), contentDescription = null, modifier = Modifier.size(48.dp, 32.dp))
        }
        BodyText(id, 13.sp, if (on) c.accentInk else c.ink, bold = true, maxLines = 1)
    }
}

// ================================================================ INBOX

@Composable
fun InboxScreen(actions: Actions) {
    val c = LocalPal.current
    var forward by remember { mutableStateOf(actions.forward) }
    ScreenColumn {
        ScreenTitle("Inbox") {
            if (AppState.inbox.isNotEmpty() || (AppState.connected && AppState.deviceNotifs > 0)) {
                KButton("Clear all") { actions.clearNotifications() }
            }
        }
        if (AppState.inbox.isEmpty()) {
            BodyText("Nothing yet. Notifications sent to DeskBuddy show up here.", 14.sp, c.sub)
        }
        AppState.inbox.take(20).forEach { n -> NotificationCard(n.app, n.title, n.body, n.time) }
        KCard("Forward from") {
            SettingRow("All notifications", forward) { forward = it; actions.forward = it }
            if (AppState.knownApps.isEmpty()) {
                BodyText("Apps appear here after their first notification.", 13.sp, c.sub)
            }
            AppState.knownApps.forEach { app ->
                SettingRow(app, app !in AppState.blockedApps) { actions.setBlocked(app, !it) }
            }
        }
        KCard("Phone access") {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                BodyText(
                    if (AppState.notifAccess) "Notification access is on" else "Notification access is off",
                    15.sp, modifier = Modifier.weight(1f)
                )
                if (!AppState.notifAccess) KButton("Grant", kind = Kind.PRIMARY) { actions.openNotificationAccess() }
            }
        }
    }
}

@Composable
private fun NotificationCard(app: String, title: String, body: String, time: Long) {
    val c = LocalPal.current
    val shape = RoundedCornerShape(20.dp)
    val tint = listOf(c.mint, c.sky, c.butter, c.lavender)[tintIndex(app)]
    Row(
        Modifier
            .fillMaxWidth()
            .glow(c, shape, 4.dp)
            .background(c.surface, shape)
            .padding(14.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Box(Modifier.size(40.dp).background(tint, RoundedCornerShape(14.dp)), contentAlignment = Alignment.Center) {
            HeadText(appInitial(app), 18.sp)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                BodyText(app.uppercase(), 11.sp, c.sub, Modifier.weight(1f), bold = true, maxLines = 1)
                BodyText(timeAgo(time), 11.sp, c.sub)
            }
            BodyText(title, 15.sp, bold = true, maxLines = 1)
            if (body.isNotBlank()) BodyText(body, 13.sp, c.sub, maxLines = 3)
        }
    }
}

// ================================================================ VOICE (DeskBuddy v2 only)

@Composable
fun VoiceScreen(actions: Actions) {
    val c = LocalPal.current
    var holding by remember { mutableStateOf(false) }
    var sayText by remember { mutableStateOf("Hello Parinith!") }
    var echo by remember { mutableStateOf(actions.echo) }
    val listening = holding || AppState.face == "listen"
    if (AppState.isC3) {
        ScreenColumn {
            ScreenTitle("Voice")
            KCard("Not on C3") {
                BodyText("DeskBuddy C3 has no mic or speaker, so voice is only on the ESP32 desk version.", 14.sp, c.sub)
                BodyText("Switch the device type in Setup to use voice.", 14.sp, c.sub)
            }
        }
        return
    }
    ScreenColumn {
        ScreenTitle("Voice") { Chip(if (AppState.mic) "Mic ready" else "Mic offline", if (AppState.mic) c.mint else c.surface2, if (AppState.mic) c.accent else c.sub) }
        BodyText(
            if (AppState.mic) "Hold the button below, or BTN3 on DeskBuddy." else "Fit the INMP441, then: set mic_en on",
            14.sp, c.sub
        )
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            Box(
                Modifier
                    .width(220.dp)
                    .height(110.dp)
                    .background(c.oled, RoundedCornerShape(20.dp)),
                contentAlignment = Alignment.Center
            ) {
                MochiFace(
                    AppState.shown, if (holding) "listen" else AppState.face,
                    Modifier.fillMaxHeight(0.8f).aspectRatio(2f, matchHeightConstraintsFirst = true)
                )
            }
        }
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            val shape = RoundedCornerShape(32.dp)
            val fg = if (listening) c.accentInk else c.ink
            Column(
                Modifier
                    .size(250.dp, 132.dp)
                    .glow(c, shape, if (listening) 2.dp else 8.dp)
                    .background(if (listening) c.accent else c.surface, shape)
                    .border(1.5.dp, if (listening) c.accent else c.line, shape)
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
                Glyph(R.drawable.ic_mic, 44.dp, fg)
                HeadText(if (listening) "Listening..." else "Hold to talk", 18.sp, fg, Modifier.padding(top = 10.dp))
            }
        }
        BodyText("Mochi is: ${faceLabel(AppState.face, AppState.shown)}", 14.sp, c.sub, Modifier.fillMaxWidth(), align = TextAlign.Center)
        KCard("Make Mochi say") {
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                KField(sayText, { sayText = it }, "Text", Modifier.weight(1f))
                KButton("Say", kind = Kind.PRIMARY) { if (sayText.isNotBlank()) actions.speak(sayText) }
            }
            SettingRow("Echo test (repeat what I say)", echo) { echo = it; actions.echo = it }
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
    var keepBg by remember { mutableStateOf(actions.keepInBackground) }
    var note by remember { mutableStateOf("") }
    ScreenColumn {
        ScreenTitle("Setup")
        KCard("Device type") {
            Segmented(listOf("c3" to "C3 Pocket", "v2" to "v2 Desk"), AppState.model) { m ->
                note = ""
                actions.setModel(m)
            }
            BodyText(
                if (c3) "DeskBuddy C3: clock, Mochi, notifications. Bluetooth or WiFi."
                else "DeskBuddy v2: all screens, voice and weather. WiFi only.",
                13.sp, c.sub
            )
        }
        if (c3) KCard("Link") {
            Segmented(listOf("ble" to "Bluetooth", "wifi" to "WiFi"), AppState.linkMode) { m -> actions.setLinkMode(m) }
            BodyText(
                if (ble) "Works anywhere within about 10 m, best battery life."
                else "Phone and DeskBuddy on the same WiFi. First time: join 'DeskBuddy_C3_Setup'.",
                13.sp, c.sub
            )
            if (AppState.connected) KButton("Change WiFi", Modifier.fillMaxWidth()) { actions.changeWifi() }
            BodyText(
                "New WiFi? Change WiFi (or hold BTN2 and tap RESET) opens 'DeskBuddy_C3_Setup': join it and pick the network.",
                13.sp, c.sub
            )
            BodyText("Stuck? Hold both buttons on DeskBuddy and tap RESET to switch between Bluetooth and WiFi.", 13.sp, c.sub)
        }
        KCard("Connection") {
            if (!ble) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                KField(host, { host = it.trim() }, "Host", Modifier.weight(1f))
                KField(port, { port = it.filter(Char::isDigit).take(5) }, "Port", Modifier.width(80.dp), number = true)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                KButton("Link", Modifier.weight(1f), Kind.PRIMARY) {
                    actions.link(host.ifEmpty { if (c3) "deskbuddy-c3.local" else "deskbuddy.local" }, port.toIntOrNull() ?: 81)
                }
                if (!ble) KButton("Find", Modifier.weight(1f)) {
                    note = "searching..."
                    actions.find { h, p -> host = h; port = p.toString(); note = "found $h:$p" }
                }
                KButton("Stop", Modifier.weight(1f), Kind.OUTLINE) { actions.stop() }
            }
            BodyText(if (note.isNotEmpty()) note else AppState.statusText, 13.sp, c.sub)
            SettingRow("Stay connected in background", keepBg) { keepBg = it; actions.keepInBackground = it }
            BodyText(
                if (keepBg) "Needed to forward notifications in the background. Stop (here or in the notification) ends it. Searching stops by itself after 10 min."
                else "Closing the app disconnects; opening it reconnects. Notifications are only forwarded while the app is open.",
                13.sp, c.sub
            )
        }
        KCard("Device") {
            val volLevel = (AppState.volume / 10f).roundToInt().coerceIn(0, 10)
            StepSlider(if (c3) "Buzzer" else "Volume", volLevel, "${AppState.volume}%") { i ->
                AppState.volume = i * 10
                DeskBuddyClient.set("volume", i * 10)
            }
            val briLevel = (AppState.bright / 25.5f).roundToInt().coerceIn(0, 10)
            StepSlider("Brightness", briLevel, "${briLevel * 10}%") { i ->
                val v = if (i == 10) 255 else i * 25
                AppState.bright = v
                DeskBuddyClient.set("brightness", v)
            }
            SettingRow("Silent mode", AppState.silent) { AppState.silent = it; DeskBuddyClient.set("silent", it) }
            SettingRow("Forward notifications", forward) { forward = it; actions.forward = it }
            if (c3) KButton("Power off DeskBuddy", Modifier.fillMaxWidth(), Kind.OUTLINE) {
                DeskBuddyClient.send(org.json.JSONObject().put("type", "power_off"))
                note = "powering off - hold BTN1 for 3 s to wake"
            }
        }
        KCard("Sleep after") {
            val cur = when (AppState.sleepSec) { 0 -> "0"; in 1..90 -> "60"; in 91..600 -> "300"; else -> "900" }
            Segmented(listOf("0" to "Off", "60" to "1m", "300" to "5m", "900" to "15m"), cur) { v ->
                AppState.sleepSec = v.toInt()
                DeskBuddyClient.set("sleep_sec", v.toInt())
            }
        }
        KCard("Theme") {
            Segmented(listOf("light" to "Light", "dark" to "Dark", "auto" to "Auto"), AppState.theme) { actions.setTheme(it) }
            BodyText("Auto follows your phone's dark mode.", 13.sp, c.sub)
        }
        if (!c3) {
            KCard("Weather") {
                KField(city, { city = it }, "City")
                BodyText("One word works best, e.g. Bengaluru or Bangalore,IN", 13.sp, c.sub)
            }
            KButton("Save to DeskBuddy", Modifier.fillMaxWidth(), Kind.PRIMARY) {
                if (city.isNotBlank()) DeskBuddyClient.set("owm_city", city.trim())
                note = if (AppState.connected) "saved to DeskBuddy" else "not linked - nothing saved"
            }
        }
        if (AppState.fw.isNotEmpty()) {
            BodyText("DeskBuddy firmware ${AppState.fw}", 12.sp, c.sub, Modifier.fillMaxWidth(), align = TextAlign.Center)
        }
    }
}

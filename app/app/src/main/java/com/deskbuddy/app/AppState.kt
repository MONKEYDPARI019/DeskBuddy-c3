package com.deskbuddy.app

import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONObject

/** One forwarded notification, kept for the Inbox screen. */
data class InboxItem(val app: String, val title: String, val body: String, val time: Long)

/**
 * Everything the UI shows, as Compose state. Updated from DeskBuddyClient
 * (background thread) and always applied on the main thread.
 */
object AppState : DeskBuddyClient.Listener {
    private val main = Handler(Looper.getMainLooper())

    // link
    var connected by mutableStateOf(false)
    var statusText by mutableStateOf("disconnected")

    // device state (from {"type":"state"} messages, see docs/PROTOCOL.md)
    var face by mutableStateOf("idle")        // boot idle listen think speak notify sleep
    var mood by mutableStateOf("default")     // idle expression
    var shown by mutableStateOf("default")    // expression drawn on the OLED right now
    var screen by mutableStateOf("clock")
    var unread by mutableStateOf(0)
    var silent by mutableStateOf(false)
    var volume by mutableStateOf(80)
    var bright by mutableStateOf(220)
    var sleepSec by mutableStateOf(300)
    var mic by mutableStateOf(false)
    var rssi by mutableStateOf(0)
    var ip by mutableStateOf("")
    var temp by mutableStateOf<Int?>(null)
    var city by mutableStateOf("")
    var owmCity by mutableStateOf("")
    var fw by mutableStateOf("")
    var bat by mutableStateOf(-1)             // C3 battery %, -1 = no battery / unknown
    var deviceLink by mutableStateOf("")       // C3: "wifi" | "ble" as reported by the device

    // which DeskBuddy the app is set up for: "v2" (ESP32) or "c3" (ESP32-C3), see Prefs.model
    var model by mutableStateOf("v2")
    var linkMode by mutableStateOf("ble")      // C3 only: "ble" | "wifi"
    val isC3: Boolean get() = model == "c3"

    // app side
    var theme by mutableStateOf("auto")
    var notifAccess by mutableStateOf(false)
    val inbox = mutableStateListOf<InboxItem>()
    val knownApps = mutableStateListOf<String>()
    val blockedApps = mutableStateListOf<String>()

    fun load(prefs: Prefs) {
        theme = prefs.theme
        model = prefs.model
        linkMode = prefs.linkMode
        knownApps.clear(); knownApps.addAll(prefs.knownApps.sorted())
        blockedApps.clear(); blockedApps.addAll(prefs.blockedApps)
    }

    override fun onStatus(connected: Boolean, text: String) {
        main.post {
            this.connected = connected
            statusText = text
        }
    }

    override fun onJson(msg: JSONObject) {
        if (msg.optString("type") != "state") return
        main.post {
            face = msg.optString("face", face)
            mood = msg.optString("mood", mood)
            shown = msg.optString("shown", mood)
            screen = msg.optString("screen", screen)
            unread = msg.optInt("unread", unread)
            silent = msg.optBoolean("silent", silent)
            volume = msg.optInt("volume", volume)
            bright = msg.optInt("bright", bright)
            sleepSec = msg.optInt("sleep", sleepSec)
            mic = msg.optBoolean("mic", mic)
            rssi = msg.optInt("rssi", rssi)
            ip = msg.optString("ip", ip)
            temp = if (msg.has("temp")) msg.optInt("temp") else temp
            city = msg.optString("city", city)
            owmCity = msg.optString("owm_city", owmCity)
            fw = msg.optString("fw", fw)
            bat = msg.optInt("bat", bat)
            deviceLink = msg.optString("link", deviceLink)
        }
    }

    /** Called by NotifListener / test buttons for every notification sent to DeskBuddy. */
    fun logNotification(app: String, title: String, body: String) {
        main.post {
            inbox.add(0, InboxItem(app, title, body, System.currentTimeMillis()))
            while (inbox.size > 50) inbox.removeAt(inbox.size - 1)
        }
    }

    fun rememberApp(prefs: Prefs, app: String) {
        if (app in prefs.knownApps) return
        prefs.knownApps = prefs.knownApps + app
        main.post { if (app !in knownApps) { knownApps.add(app); knownApps.sort() } }
    }

    fun setBlocked(prefs: Prefs, app: String, blocked: Boolean) {
        prefs.blockedApps = if (blocked) prefs.blockedApps + app else prefs.blockedApps - app
        if (blocked) { if (app !in blockedApps) blockedApps.add(app) } else blockedApps.remove(app)
    }
}

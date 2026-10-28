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
    private val inboxSync = InboxSync()

    // link
    var connected by mutableStateOf(false)
    var statusText by mutableStateOf("disconnected")

    // device state (from {"type":"state"} messages, see docs/PROTOCOL.md)
    var face by mutableStateOf("idle")        // boot idle listen think speak notify sleep
    var mood by mutableStateOf("default")     // idle expression
    var shown by mutableStateOf("default")    // expression drawn on the OLED right now
    var screen by mutableStateOf("clock")
    var unread by mutableStateOf(0)
    var deviceNotifs by mutableStateOf(0)     // notifications DeskBuddy holds right now
    var silent by mutableStateOf(false)
    var volume by mutableStateOf(80)
    var bright by mutableStateOf(220)
    var sleepSec by mutableStateOf(300)
    var rssi by mutableStateOf(0)
    var ip by mutableStateOf("")
    var fw by mutableStateOf("")
    var bat by mutableStateOf(-1)             // battery %, -1 = no battery / unknown
    var deviceLink by mutableStateOf("")       // "wifi" | "ble" as reported by the device
    var build by mutableStateOf("")            // "usb" | "battery" (firmware 2.5.0+)
    var otaPass by mutableStateOf(false)       // DeskBuddy has an update password (2.5.0+)

    var linkMode by mutableStateOf("ble")      // how the app looks for DeskBuddy: "ble" | "wifi"

    // "Update DeskBuddy" (OtaUpdater)
    var otaBusy by mutableStateOf(false)
    var otaStep by mutableStateOf("")          // what is happening / what went wrong
    var otaProgress by mutableStateOf(-1f)     // 0..1 while the image is sent, -1 = no bar
    var otaLatest by mutableStateOf("")        // newest release on GitHub, e.g. "2.5.1" ("" = not checked)

    // app side
    var theme by mutableStateOf("auto")
    var notifAccess by mutableStateOf(false)
    var canAnswerCalls by mutableStateOf(false) // ANSWER_PHONE_CALLS granted
    val inbox = mutableStateListOf<InboxItem>()
    val knownApps = mutableStateListOf<String>()
    val blockedApps = mutableStateListOf<String>()

    fun load(prefs: Prefs) {
        theme = prefs.theme
        linkMode = prefs.linkMode
        knownApps.clear(); knownApps.addAll(prefs.knownApps.sorted())
        blockedApps.clear(); blockedApps.addAll(prefs.blockedApps)
    }

    override fun onStatus(connected: Boolean, text: String) {
        if (!connected) inboxSync.reset()        // the next connection starts a new comparison
        main.post {
            this.connected = connected
            statusText = text
        }
    }

    override fun onJson(msg: JSONObject) {
        if (msg.optString("type") == "hello") {
            main.post {
                fw = msg.optString("fw", fw)
                build = msg.optString("build", build)
                otaPass = msg.optBoolean("ota_pass", otaPass)
            }
            return
        }
        if (msg.optString("type") != "state") return
        val count = msg.optInt("notifs", -1)
        // DeskBuddy emptied its list (long BTN2, or Clear here): the app's list follows
        val deviceCleared = count >= 0 && inboxSync.onDeviceCount(count)
        main.post {
            if (count >= 0) deviceNotifs = count
            if (deviceCleared) inbox.clear()
            face = msg.optString("face", face)
            mood = msg.optString("mood", mood)
            shown = msg.optString("shown", mood)
            screen = msg.optString("screen", screen)
            unread = msg.optInt("unread", unread)
            silent = msg.optBoolean("silent", silent)
            volume = msg.optInt("volume", volume)
            bright = msg.optInt("bright", bright)
            sleepSec = msg.optInt("sleep", sleepSec)
            rssi = msg.optInt("rssi", rssi)
            ip = msg.optString("ip", ip)
            fw = msg.optString("fw", fw)
            bat = msg.optInt("bat", bat)
            deviceLink = msg.optString("link", deviceLink)
            build = msg.optString("build", build)
            otaPass = msg.optBoolean("ota_pass", otaPass)
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

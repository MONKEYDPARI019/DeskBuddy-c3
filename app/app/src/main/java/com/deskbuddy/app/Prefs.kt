package com.deskbuddy.app

import android.content.Context

/** Small wrapper around SharedPreferences for the few things the app remembers. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("deskbuddy", Context.MODE_PRIVATE)

    var host: String
        get() = sp.getString("host", "deskbuddy.local") ?: "deskbuddy.local"
        set(v) = sp.edit().putString("host", v).apply()

    var port: Int
        get() = sp.getInt("port", 81)
        set(v) = sp.edit().putInt("port", v).apply()

    /** Which DeskBuddy this app talks to: "v2" (ESP32 desk version) or "c3" (ESP32-C3 pocket version). */
    var model: String
        get() = sp.getString("model", "v2") ?: "v2"
        set(v) = sp.edit().putString("model", v).apply()

    /** How to reach a C3: "ble" (Bluetooth, default) or "wifi". The v2 is always WiFi. */
    var linkMode: String
        get() = sp.getString("link_mode", "ble") ?: "ble"
        set(v) = sp.edit().putString("link_mode", v).apply()

    /** Host for the C3 in WiFi mode (kept separate so switching device type keeps both). */
    var c3Host: String
        get() = sp.getString("c3_host", "deskbuddy-c3.local") ?: "deskbuddy-c3.local"
        set(v) = sp.edit().putString("c3_host", v).apply()

    /** True when the app should use Bluetooth right now (C3 in BLE mode). */
    val useBle: Boolean get() = model == "c3" && linkMode == "ble"

    /** Host the WiFi link should use for the selected device type. */
    val wifiHost: String get() = if (model == "c3") c3Host else host

    /** True after the user tapped LINK; the app reconnects on launch until they tap STOP. */
    var linkOn: Boolean
        get() = sp.getBoolean("link_on", false)
        set(v) = sp.edit().putBoolean("link_on", v).apply()

    /** Forward phone notifications to DeskBuddy. */
    var forwardNotifications: Boolean
        get() = sp.getBoolean("forward", true)
        set(v) = sp.edit().putBoolean("forward", v).apply()

    /** Voice test mode: play the recorded push-to-talk audio straight back. */
    var echoVoice: Boolean
        get() = sp.getBoolean("echo", true)
        set(v) = sp.edit().putBoolean("echo", v).apply()

    /** "auto" (follow the phone), "light" or "dark". */
    var theme: String
        get() = sp.getString("theme", "auto") ?: "auto"
        set(v) = sp.edit().putString("theme", v).apply()

    /** Apps that have posted a notification at least once (shown in the Inbox filter). */
    var knownApps: Set<String>
        get() = sp.getStringSet("known_apps", emptySet())?.toSet() ?: emptySet()
        set(v) = sp.edit().putStringSet("known_apps", v).apply()

    /** Apps whose notifications are NOT forwarded. */
    var blockedApps: Set<String>
        get() = sp.getStringSet("blocked_apps", emptySet())?.toSet() ?: emptySet()
        set(v) = sp.edit().putStringSet("blocked_apps", v).apply()
}

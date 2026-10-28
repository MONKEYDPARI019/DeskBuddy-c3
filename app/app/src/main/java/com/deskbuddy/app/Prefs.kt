package com.deskbuddy.app

import android.content.Context

/** Small wrapper around SharedPreferences for the few things the app remembers. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("deskbuddy", Context.MODE_PRIVATE)

    var port: Int
        get() = sp.getInt("port", 81)
        set(v) = sp.edit().putInt("port", v).apply()

    /** How to reach DeskBuddy: "ble" (Bluetooth, default) or "wifi". */
    var linkMode: String
        get() = sp.getString("link_mode", "ble") ?: "ble"
        set(v) = sp.edit().putString("link_mode", v).apply()

    /** Host in WiFi mode. */
    var c3Host: String
        get() = sp.getString("c3_host", "deskbuddy-c3.local") ?: "deskbuddy-c3.local"
        set(v) = sp.edit().putString("c3_host", v).apply()

    /** True when the app should use Bluetooth right now. */
    val useBle: Boolean get() = linkMode == "ble"

    /** Host the WiFi link uses. */
    val wifiHost: String get() = c3Host

    /** True after the user tapped LINK; the app reconnects on launch until they tap STOP. */
    var linkOn: Boolean
        get() = sp.getBoolean("link_on", false)
        set(v) = sp.edit().putBoolean("link_on", v).apply()

    /**
     * Keep the link running after the app is swiped away (needed to forward
     * notifications in the background). Off: closing the app disconnects, and
     * opening it again reconnects.
     */
    var keepInBackground: Boolean
        get() = sp.getBoolean("keep_bg", true)
        set(v) = sp.edit().putBoolean("keep_bg", v).apply()

    /** Forward phone notifications to DeskBuddy. */
    var forwardNotifications: Boolean
        get() = sp.getBoolean("forward", true)
        set(v) = sp.edit().putBoolean("forward", v).apply()

    /** Show phone calls on DeskBuddy (firmware 2.5.0+): BTN1 answers, BTN2 declines. */
    var callsOnDeskBuddy: Boolean
        get() = sp.getBoolean("calls", true)
        set(v) = sp.edit().putBoolean("calls", v).apply()

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

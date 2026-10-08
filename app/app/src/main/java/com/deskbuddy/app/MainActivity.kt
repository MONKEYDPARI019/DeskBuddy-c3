package com.deskbuddy.app

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.deskbuddy.app.ui.Actions
import com.deskbuddy.app.ui.DeskBuddyApp

class MainActivity : ComponentActivity() {
    companion object { private const val REQ_BLE = 2 }

    private lateinit var prefs: Prefs
    private lateinit var tts: TtsPcm
    private lateinit var discovery: Discovery

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        tts = TtsPcm(this)
        discovery = Discovery(this)
        AppState.load(prefs)

        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
        // reconnect automatically if the user linked last time
        if (prefs.linkOn) LinkService.start(this)

        val activity = this
        val actions = object : Actions {
            override val host get() = prefs.wifiHost
            override val port get() = prefs.port
            override var forward: Boolean
                get() = prefs.forwardNotifications
                set(v) { prefs.forwardNotifications = v }
            override var echo: Boolean
                get() = prefs.echoVoice
                set(v) { prefs.echoVoice = v }

            override fun link(host: String, port: Int) {
                if (prefs.model == "c3") prefs.c3Host = host else prefs.host = host
                prefs.port = port
                if (prefs.useBle && !ensureBlePermissions()) return
                prefs.linkOn = true
                LinkService.start(activity)         // connects (or reconnects to a new host/port)
            }

            override fun setModel(model: String) {
                if (model == prefs.model) return
                prefs.model = model
                AppState.model = model
                if (prefs.linkOn) {
                    if (prefs.useBle && !ensureBlePermissions()) return
                    LinkService.start(activity)     // reconnect the right way for this device
                }
            }

            override fun setLinkMode(mode: String) {
                if (mode == prefs.linkMode) return
                if (mode == "ble" && !ensureBlePermissions()) return
                if (DeskBuddyClient.connected && AppState.isC3) {
                    // ask the C3 to switch radios; LinkService follows it after it restarts
                    DeskBuddyClient.set("link", mode, save = true)
                    toast(if (mode == "ble") "DeskBuddy is switching to Bluetooth..." else "DeskBuddy is switching to WiFi...")
                } else {
                    // not connected: only change how the app looks for it
                    prefs.linkMode = mode
                    AppState.linkMode = mode
                    if (prefs.linkOn) LinkService.start(activity)
                    toast("App set to ${if (mode == "ble") "Bluetooth" else "WiFi"}. DeskBuddy must be in the same mode.")
                }
            }

            override fun stop() {
                prefs.linkOn = false
                LinkService.stop(activity)
            }

            override fun find(onFound: (String, Int) -> Unit) {
                discovery.find(onFound, if (prefs.model == "c3") "c3" else null) { msg -> toast(msg) }
            }

            override fun openNotificationAccess() {
                startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
            }

            override fun speak(text: String) {
                if (!DeskBuddyClient.connected) toast("Not linked to DeskBuddy") else tts.speak(text)
            }

            override fun setTheme(theme: String) {
                prefs.theme = theme
                AppState.theme = theme
            }

            override fun setBlocked(app: String, blocked: Boolean) = AppState.setBlocked(prefs, app, blocked)
        }

        setContent { DeskBuddyApp(actions) }
    }

    override fun onResume() {
        super.onResume()
        AppState.notifAccess = notificationAccessGranted()
    }

    override fun onDestroy() {
        discovery.stop()
        tts.shutdown()
        super.onDestroy()
    }

    /** Bluetooth permissions: SCAN + CONNECT on Android 12+, location before that. */
    private fun ensureBlePermissions(): Boolean {
        val needed = if (Build.VERSION.SDK_INT >= 31) {
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        }
        val missing = needed.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isEmpty()) return true
        requestPermissions(missing.toTypedArray(), REQ_BLE)
        toast("Allow Bluetooth, then tap again")
        return false
    }

    private fun toast(msg: String) = runOnUiThread { Toast.makeText(this, msg, Toast.LENGTH_SHORT).show() }

    private fun notificationAccessGranted(): Boolean {
        val enabled = Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: return false
        return enabled.contains(ComponentName(this, NotifListener::class.java).flattenToString())
    }
}

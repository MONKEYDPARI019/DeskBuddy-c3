package com.deskbuddy.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import org.json.JSONObject

/**
 * Foreground service that keeps the DeskBuddy connection (and voice loop)
 * running while the app is in the background.
 */
class LinkService : Service(), DeskBuddyClient.Listener {
    private var voice: VoiceLoop? = null
    private val main = Handler(Looper.getMainLooper())

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            DeskBuddyClient.disconnect()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }
        startForegroundCompat("Connecting…")

        val prefs = Prefs(this)
        if (voice == null) {
            voice = VoiceLoop(this, prefs).also { DeskBuddyClient.addListener(it) }
            DeskBuddyClient.addListener(this)
        }
        connectFromPrefs(prefs)
        return START_STICKY
    }

    private var discovery: Discovery? = null

    /** Pick the transport for the selected device type: v2 = WiFi, C3 = Bluetooth or WiFi. */
    private fun connectFromPrefs(prefs: Prefs) {
        DeskBuddyClient.isC3 = prefs.model == "c3"
        if (prefs.useBle) {
            DeskBuddyClient.connectBle(this)
            return
        }
        val host = prefs.wifiHost
        if (host.endsWith(".local", ignoreCase = true)) {
            // Many Android phones cannot resolve ".local" names, so look DeskBuddy up
            // with mDNS service discovery (_deskbuddy._tcp) and connect to its IP.
            // If that fails, still try the name (works on phones that support it).
            val d = discovery ?: Discovery(this).also { discovery = it }
            d.find(
                onFound = { ip, port -> DeskBuddyClient.connect(ip, port) },
                onFail = { DeskBuddyClient.connect(host, prefs.port) },
                nameHint = if (prefs.model == "c3") "c3" else null
            )
        } else {
            DeskBuddyClient.connect(host, prefs.port)
        }
    }

    override fun onJson(msg: JSONObject) {
        val prefs = Prefs(this)
        when (msg.optString("type")) {
            // the device tells us what it is: keep the app's device type in step
            "hello" -> {
                val model = if (msg.optString("model") == "c3") "c3" else "v2"
                if (model != prefs.model) {
                    prefs.model = model
                    DeskBuddyClient.isC3 = model == "c3"
                    main.post { AppState.model = model }
                    if (model == "c3") DeskBuddyClient.sendTime()
                }
            }
            // a C3 is restarting with the other radio: follow it after it reboots
            "link_switch" -> {
                val link = if (msg.optString("link") == "wifi") "wifi" else "ble"
                prefs.linkMode = link
                main.post { AppState.linkMode = link }
                main.postDelayed({ if (Prefs(this).linkOn) connectFromPrefs(Prefs(this)) }, 4000)
            }
        }
    }

    override fun onStatus(connected: Boolean, text: String) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(NOTIF_ID, buildNotification(text))
    }

    override fun onDestroy() {
        voice?.let { DeskBuddyClient.removeListener(it); it.shutdown() }
        DeskBuddyClient.removeListener(this)
        voice = null
        discovery?.stop()
        super.onDestroy()
    }

    private fun startForegroundCompat(text: String) {
        val n = buildNotification(text)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        } else {
            startForeground(NOTIF_ID, n)
        }
    }

    private fun buildNotification(text: String): Notification {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "DeskBuddy link", NotificationManager.IMPORTANCE_LOW))
        }
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("DeskBuddy")
            .setContentText(text)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }

    companion object {
        const val ACTION_STOP = "com.deskbuddy.app.STOP"
        private const val CHANNEL = "link"
        private const val NOTIF_ID = 1

        fun start(context: Context) {
            context.startForegroundService(Intent(context, LinkService::class.java))
        }

        fun stop(context: Context) {
            context.startService(Intent(context, LinkService::class.java).setAction(ACTION_STOP))
        }
    }
}

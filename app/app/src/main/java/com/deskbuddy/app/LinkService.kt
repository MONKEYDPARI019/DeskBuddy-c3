package com.deskbuddy.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.bluetooth.BluetoothAdapter
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.content.pm.ServiceInfo
import android.graphics.drawable.Icon
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import org.json.JSONObject

/**
 * Foreground service that keeps the DeskBuddy connection (and voice loop)
 * running while the app is in the background.
 *
 * It never searches forever:
 *  - the notification has a STOP button (same as STOP in the app);
 *  - if DeskBuddy cannot be found for [GIVE_UP_MS], the service stops and leaves
 *    a normal, swipe-away notification "DeskBuddy not found" (tap: search again);
 *  - with "Stay connected when app is closed" off, swiping the app away stops it.
 * Opening the app reconnects while LINK is on (MainActivity).
 */
class LinkService : Service(), DeskBuddyClient.Listener {
    private var voice: VoiceLoop? = null
    private val main = Handler(Looper.getMainLooper())

    /** True while shutting down: late status callbacks must not re-post the notification. */
    private var stopping = false
    private val giveUp = Runnable { giveUpSearching() }
    private var giveUpPending = false

    /**
     * Reconnect at once when a reconnect is likely to work, instead of waiting for the backoff
     * timer (up to 30 s): Bluetooth switched back on, the screen came on (phone woke up).
     */
    private val wakeReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                BluetoothAdapter.ACTION_STATE_CHANGED ->
                    if (intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, -1) == BluetoothAdapter.STATE_ON) {
                        DeskBuddyClient.kick()
                    }
                Intent.ACTION_SCREEN_ON -> DeskBuddyClient.kick()
            }
        }
    }

    /** A WiFi network became available (back in range, or the phone switched networks). */
    private val wifiCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) { main.post { DeskBuddyClient.kick() } }
    }
    private var watching = false

    private fun startWatching() {
        if (watching) return
        watching = true
        val filter = IntentFilter().apply {
            addAction(BluetoothAdapter.ACTION_STATE_CHANGED)
            addAction(Intent.ACTION_SCREEN_ON)
        }
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(wakeReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        else registerReceiver(wakeReceiver, filter)
        try {
            val request = NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_WIFI).build()
            connectivity().registerNetworkCallback(request, wifiCallback)
        } catch (e: Exception) { /* only a speed-up: reconnecting still works without it */ }
    }

    private fun stopWatching() {
        if (!watching) return
        watching = false
        try { unregisterReceiver(wakeReceiver) } catch (_: Exception) {}
        try { connectivity().unregisterNetworkCallback(wifiCallback) } catch (_: Exception) {}
    }

    private fun connectivity() = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            // STOP from the notification or the app: stay off until the user taps LINK again
            Prefs(this).linkOn = false
            shutdown()
            return START_NOT_STICKY
        }
        // a fresh start (LINK, app opened, or "search again" from the not-found notification)
        stopping = false
        notificationManager().cancel(NOT_FOUND_ID)
        startForegroundCompat("Connecting…")
        running = true

        val prefs = Prefs(this)
        prefs.linkOn = true
        if (voice == null) {
            voice = VoiceLoop(this, prefs).also { DeskBuddyClient.addListener(it) }
            DeskBuddyClient.addListener(this)
        }
        connectFromPrefs(prefs)
        startWatching()
        scheduleGiveUp()
        return START_STICKY
    }

    /** The user swiped the app away from the recent apps list. */
    override fun onTaskRemoved(rootIntent: Intent?) {
        if (!Prefs(this).keepInBackground) shutdown()   // LINK stays on: opening the app reconnects
        super.onTaskRemoved(rootIntent)
    }

    /** Stop searching/connecting, remove the notification and end the service. */
    private fun shutdown() {
        stopping = true
        running = false
        cancelGiveUp()
        stopWatching()
        main.removeCallbacksAndMessages(null)
        discovery?.stop()
        DeskBuddyClient.disconnect()
        stopForeground(STOP_FOREGROUND_REMOVE)
        notificationManager().cancel(NOTIF_ID)
        stopSelf()
    }

    /** Not found for a long time: stop draining the battery, leave a tap-to-retry note. */
    private fun giveUpSearching() {
        giveUpPending = false
        if (DeskBuddyClient.connected || stopping) return
        shutdown()
        notificationManager().notify(NOT_FOUND_ID, buildNotFoundNotification())
    }

    private fun scheduleGiveUp() {
        if (giveUpPending || DeskBuddyClient.connected) return
        giveUpPending = true
        main.postDelayed(giveUp, GIVE_UP_MS)
    }

    private fun cancelGiveUp() {
        giveUpPending = false
        main.removeCallbacks(giveUp)
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
            "link_switch" -> followRestart(prefs, if (msg.optString("link") == "wifi") "wifi" else "ble")
            // "Change WiFi": the C3 restarts in WiFi mode with its setup portal open. The app
            // keeps looking for it on WiFi; it is found once it has joined the new network.
            "wifi_setup" -> followRestart(prefs, "wifi")
        }
    }

    /** The C3 restarts with [link]: look for it that way once it is back up. */
    private fun followRestart(prefs: Prefs, link: String) {
        prefs.linkMode = link
        main.post { AppState.linkMode = link }
        main.postDelayed({ if (Prefs(this).linkOn) connectFromPrefs(Prefs(this)) }, 4000)
    }

    override fun onStatus(connected: Boolean, text: String) {
        // status callbacks arrive on background threads; handle them on the main thread
        main.post {
            if (stopping) return@post               // shutting down: don't bring the notification back
            if (connected) cancelGiveUp() else scheduleGiveUp()
            notificationManager().notify(NOTIF_ID, buildNotification(text))
        }
    }

    override fun onDestroy() {
        stopping = true
        running = false
        cancelGiveUp()
        stopWatching()
        voice?.let { DeskBuddyClient.removeListener(it); it.shutdown() }
        DeskBuddyClient.removeListener(this)
        voice = null
        discovery?.stop()
        notificationManager().cancel(NOTIF_ID)
        super.onDestroy()
    }

    private fun notificationManager() = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    private fun startForegroundCompat(text: String) {
        val n = buildNotification(text)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        } else {
            startForeground(NOTIF_ID, n)
        }
    }

    private fun ensureChannel() {
        val nm = notificationManager()
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "DeskBuddy link", NotificationManager.IMPORTANCE_LOW))
        }
    }

    private fun openAppIntent(): PendingIntent = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
    )

    private fun buildNotification(text: String): Notification {
        ensureChannel()
        val stop = PendingIntent.getService(
            this, 1, Intent(this, LinkService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val stopAction = Notification.Action.Builder(
            Icon.createWithResource(this, android.R.drawable.ic_menu_close_clear_cancel), "Stop", stop
        ).build()
        return Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("DeskBuddy")
            .setContentText(text)
            .setContentIntent(openAppIntent())
            .addAction(stopAction)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    /** Shown after giving up: can be swiped away; tap or "Search again" reconnects. */
    private fun buildNotFoundNotification(): Notification {
        ensureChannel()
        val retry = PendingIntent.getForegroundService(
            this, 2, Intent(this, LinkService::class.java).setAction(ACTION_RETRY),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val retryAction = Notification.Action.Builder(
            Icon.createWithResource(this, android.R.drawable.ic_popup_sync), "Search again", retry
        ).build()
        val minutes = GIVE_UP_MS / 60_000
        return Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("DeskBuddy not found")
            .setContentText("Stopped searching after $minutes min to save battery. Tap to search again.")
            .setContentIntent(openAppIntent())
            .addAction(retryAction)
            .setAutoCancel(true)
            .build()
    }

    companion object {
        const val ACTION_STOP = "com.deskbuddy.app.STOP"
        const val ACTION_RETRY = "com.deskbuddy.app.RETRY"
        private const val CHANNEL = "link"
        private const val NOTIF_ID = 1
        private const val NOT_FOUND_ID = 2

        /** Stop searching if DeskBuddy can't be found for this long. */
        private const val GIVE_UP_MS = 10 * 60_000L

        /** True while the service is running (MainActivity reconnects on resume when it isn't). */
        @Volatile var running = false
            private set

        fun start(context: Context) {
            context.startForegroundService(Intent(context, LinkService::class.java))
        }

        fun stop(context: Context) {
            context.startService(Intent(context, LinkService::class.java).setAction(ACTION_STOP))
        }
    }
}

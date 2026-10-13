package com.deskbuddy.app

import android.os.Handler
import android.os.Looper
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * The connection to DeskBuddy (see docs/PROTOCOL.md). Two transports carry the
 * same JSON messages:
 *   - WebSocket over WiFi ([connect]): DeskBuddy v2, and DeskBuddy C3 in WiFi mode
 *   - Bluetooth LE ([connectBle]): DeskBuddy C3 in Bluetooth mode (see BleLink)
 * Only one is active at a time. Both reconnect automatically with backoff.
 * Listener callbacks run on a background thread.
 */
object DeskBuddyClient {
    private const val TAG = "DeskBuddyClient"
    private const val SPEECH_CHUNK_MS = 64

    interface Listener {
        fun onStatus(connected: Boolean, text: String) {}
        fun onJson(msg: JSONObject) {}
        fun onAudio(pcm: ByteArray) {}
    }

    private val http = OkHttpClient.Builder()
        .pingInterval(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private val handler = Handler(Looper.getMainLooper())
    private val speechExecutor = Executors.newSingleThreadExecutor()
    private val listeners = CopyOnWriteArrayList<Listener>()

    @Volatile private var ws: WebSocket? = null
    @Volatile var connected = false
        private set
    @Volatile var lastState: JSONObject? = null
        private set
    @Volatile var statusText = "disconnected"
        private set

    private var url: String? = null
    private var wanted = false
    private var backoffMs = 1000L

    /** "wifi" or "ble": which transport is in use right now. */
    @Volatile var transport = "wifi"
        private set
    private var ble: BleLink? = null

    /** Set by LinkService: the app is talking to a DeskBuddy C3 (sends the time on connect). */
    @Volatile var isC3 = false

    init {
        listeners.add(AppState)   // the UI state always listens
    }

    fun addListener(l: Listener) = listeners.addIfAbsent(l)
    fun removeListener(l: Listener) = listeners.remove(l)

    @Synchronized
    fun connect(host: String, port: Int) {
        val newUrl = "ws://$host:$port/"
        if (transport == "wifi" && wanted && newUrl == url && ws != null) return
        ble?.stop(); ble = null
        transport = "wifi"
        ws?.cancel()
        url = newUrl
        wanted = true
        backoffMs = 1000L
        open()
    }

    /** Connect to a DeskBuddy C3 over Bluetooth LE (scans for it). */
    @Synchronized
    fun connectBle(context: android.content.Context) {
        if (transport == "ble" && ble != null) return
        wanted = false
        handler.removeCallbacksAndMessages(null)
        ws?.close(1000, "switching to bluetooth")
        ws = null
        transport = "ble"
        ble = BleLink(
            context.applicationContext,
            onStatus = { isConnected, text ->
                setStatus(isConnected, text)
                if (isConnected) onConnected()
            },
            onLine = { line ->
                val msg = try { JSONObject(line) } catch (e: Exception) { null }
                if (msg != null) {
                    if (msg.optString("type") == "state") lastState = msg
                    listeners.forEach { it.onJson(msg) }
                }
            }
        ).also { it.start() }
    }

    @Synchronized
    fun disconnect() {
        wanted = false
        pending.drain(0)                  // STOP: nothing queued may pop up on a later connect
        handler.removeCallbacksAndMessages(null)
        ws?.close(1000, "bye")
        ws = null
        ble?.stop()
        ble = null
        setStatus(false, "disconnected")
    }

    /** First messages after any transport connects: hello, and the clock for a C3. */
    private fun onConnected() {
        send(JSONObject().put("type", "hello").put("name", android.os.Build.MODEL))
        if (isC3) sendTime()
        flushPending()                      // notifications that came in while offline
    }

    /** DeskBuddy C3 has no internet in Bluetooth mode: the phone sets its clock. */
    fun sendTime() = send(
        JSONObject().put("type", "time")
            .put("epoch", System.currentTimeMillis() / 1000)
            .put("tz_min", java.util.TimeZone.getDefault().getOffset(System.currentTimeMillis()) / 60000)
    )

    private fun open() {
        val u = url ?: return
        setStatus(false, "connecting to $u")
        ws = http.newWebSocket(Request.Builder().url(u).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                backoffMs = 1000L
                setStatus(true, "connected to $u")
                onConnected()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val msg = try { JSONObject(text) } catch (e: Exception) { return }
                if (msg.optString("type") == "state") lastState = msg
                listeners.forEach { it.onJson(msg) }
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                val pcm = bytes.toByteArray()
                listeners.forEach { it.onAudio(pcm) }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = lost(webSocket, "closed")

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) =
                lost(webSocket, t.message ?: "failed")
        })
    }

    private fun lost(socket: WebSocket, why: String) {
        if (socket != ws) return            // an old socket we already replaced
        setStatus(false, "offline ($why), retrying in ${backoffMs / 1000}s")
        if (wanted) {
            handler.postDelayed({ synchronized(this) { if (wanted) open() } }, backoffMs)
            backoffMs = (backoffMs * 2).coerceAtMost(30_000L)
        }
    }

    private fun setStatus(isConnected: Boolean, text: String) {
        connected = isConnected
        statusText = text
        Log.i(TAG, text)
        listeners.forEach { it.onStatus(isConnected, text) }
    }

    // ---------------------------------------------------------------- send

    fun send(obj: JSONObject): Boolean =
        if (transport == "ble") ble?.sendLine(obj.toString()) ?: false
        else ws?.send(obj.toString()) ?: false

    private data class Notif(val app: String, val title: String, val body: String)

    /** Notifications are prepared and sent here, never on the main thread. */
    private val notifExecutor = Executors.newSingleThreadExecutor()
    private val pending = PendingNotifs<Notif>()
    @Volatile private var lastKick = 0L
    private const val KICK_MIN_INTERVAL_MS = 5_000L

    /** Hindi, Cyrillic, ... -> Latin letters the OLED can draw (Android 10+; built lazily, it is slow). */
    private val transliterator: ((String) -> String)? by lazy {
        if (android.os.Build.VERSION.SDK_INT < 29) null
        else try {
            val t = android.icu.text.Transliterator.getInstance("Any-Latin; Latin-ASCII")
            val f: (String) -> String = { s -> synchronized(t) { t.transliterate(s) } }
            f
        } catch (e: Exception) { null }
    }

    /**
     * Forward one phone notification. Not connected (phone just woke up, WiFi changing):
     * kept for up to 2 min and sent as soon as the link is back, and a reconnect is tried now.
     */
    fun notify(app: String, title: String, body: String) {
        notifExecutor.execute {
            val n = Notif(
                NotifText.prepare(app, 15, transliterator),
                NotifText.prepare(title, 31, transliterator),
                NotifText.prepare(body, 127, transliterator),
            )
            if (!connected || !sendNotif(n)) {
                pending.add(n, System.currentTimeMillis())
                kick()                      // rate-limited: a burst of notifications is one kick
            }
        }
    }

    private fun sendNotif(n: Notif): Boolean {
        val ok = send(JSONObject().put("type", "notify").put("app", n.app).put("title", n.title).put("body", n.body))
        if (ok) AppState.logNotification(n.app, n.title, n.body)
        return ok
    }

    private fun flushPending() = notifExecutor.execute {
        val now = System.currentTimeMillis()
        for (n in pending.drain(now)) {
            if (!sendNotif(n)) pending.add(n, now)   // link dropped again: keep it for the next connect
        }
    }

    /** C3: restart into WiFi mode with the setup portal open, to join a different network. */
    fun wifiSetup() = send(JSONObject().put("type", "wifi_setup"))

    /**
     * Reconnect now instead of waiting for the backoff timer: the screen came on, WiFi or
     * Bluetooth came back. Does nothing while connected.
     */
    fun kick() {
        if (connected) return
        // Screen-on, WiFi and Bluetooth events and bursts of notifications can arrive close
        // together; restarting the search for each would hit Android's limit of ~5 BLE scans
        // per 30 s and keep the backoff from ever growing.
        val now = android.os.SystemClock.elapsedRealtime()
        if (now - lastKick < KICK_MIN_INTERVAL_MS) return
        lastKick = now
        if (transport == "ble") { handler.post { ble?.kick() }; return }   // BleLink lives on the main thread
        synchronized(this) {
            if (!wanted) return
            handler.removeCallbacksAndMessages(null)
            backoffMs = 1000L
            val old = ws
            ws = null                       // first: the old socket's failure callback must see it is stale
            old?.cancel()
            open()
        }
    }

    fun face(name: String) = send(JSONObject().put("type", "face").put("name", name))
    fun screen(name: String) = send(JSONObject().put("type", "screen").put("name", name))
    fun sound(name: String) = send(JSONObject().put("type", "sound").put("name", name))
    fun ptt(on: Boolean) = send(JSONObject().put("type", "ptt").put("on", on))
    fun think(on: Boolean) = send(JSONObject().put("type", "think").put("on", on))
    fun set(key: String, value: Any, save: Boolean = true) =
        send(JSONObject().put("type", "set").put("key", key).put("value", value).put("save", save))

    /**
     * Stream a spoken reply: 16-bit signed little-endian mono PCM at [rate] Hz.
     * Paced to stay ~200 ms ahead of playback so the device's 0.5 s buffer never overflows.
     */
    fun sayPcm(pcm: ByteArray, rate: Int) {
        if (transport == "ble") return          // no speaker on the C3
        speechExecutor.execute {
            val socket = ws ?: return@execute
            socket.send(JSONObject().put("type", "say_start").put("rate", rate).toString())
            val chunk = rate * 2 * SPEECH_CHUNK_MS / 1000
            val start = System.nanoTime()
            var i = 0
            while (i < pcm.size) {
                val end = (i + chunk).coerceAtMost(pcm.size)
                if (!socket.send(pcm.toByteString(i, end - i))) return@execute
                val playedSec = (System.nanoTime() - start) / 1e9
                val aheadSec = (i / 2.0 / rate) - playedSec
                if (aheadSec > 0.2) Thread.sleep(((aheadSec - 0.2) * 1000).toLong())
                i = end
            }
            socket.send(JSONObject().put("type", "say_end").toString())
        }
    }
}

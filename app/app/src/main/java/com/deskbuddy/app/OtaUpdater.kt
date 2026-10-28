package com.deskbuddy.app

import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * "Update DeskBuddy" (firmware 2.5.0+), and setting / changing the update password.
 *
 * An update: find the newest release on GitHub, download the update image for this DeskBuddy's
 * build (deskbuddy-c3-ota-<usb|battery>-v<x.y.z>.bin), check it against the release's SHA256SUMS,
 * prove the password (it never leaves the phone, see OtaCrypto), wait while the person presses
 * BTN1 on DeskBuddy, then send the image in 1 KB chunks over the normal link (Bluetooth or WiFi),
 * two at a time, each acknowledged. DeskBuddy checks the SHA-256 before it boots the new firmware;
 * anything going wrong leaves the old one running. Messages: firmware/docs/PROTOCOL.md.
 *
 * One job at a time on its own thread; what is happening goes to AppState.ota*.
 */
object OtaUpdater : DeskBuddyClient.Listener {
    private const val TAG = "OtaUpdater"
    private const val REPO = "MONKEYDPARI019/DeskBuddy-C3"
    private const val MAX_IMAGE = 2 * 1024 * 1024
    private const val BUTTON_WAIT_MS = 35_000L

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val inbox = LinkedBlockingQueue<JSONObject>()
    @Volatile private var cancelled = false

    private class Fail(message: String) : Exception(message)

    private class Release(val version: String, val assets: Map<String, String>)   // file name -> URL

    // ---------------------------------------------------------------- listener (link thread)

    override fun onJson(msg: JSONObject) {
        if (msg.optString("type").startsWith("ota_")) inbox.offer(msg)
    }

    override fun onStatus(connected: Boolean, text: String) {
        if (!connected) inbox.offer(JSONObject().put("type", "_lost"))
    }

    // ---------------------------------------------------------------- what the UI calls

    /** Look up the newest release (no password, nothing sent to DeskBuddy). */
    fun check() = job("Looking for updates...") {
        val rel = latestRelease()
        post { AppState.otaLatest = rel.version }
        val cmp = FwVersion.compare(AppState.fw, rel.version)
        when {
            cmp == null -> "Newest firmware: v${rel.version}."
            cmp < 0 -> "v${rel.version} is out (DeskBuddy has ${AppState.fw.removePrefix("c3-")})."
            else -> "DeskBuddy is up to date (v${rel.version})."
        }
    }

    fun update(password: String) = job("Looking for updates...") { runUpdate(password) }

    fun setPassword(newPassword: String) = job("Asking DeskBuddy...") { runSetPassword(newPassword) }

    fun changePassword(oldPassword: String, newPassword: String) =
        job("Asking DeskBuddy...") { runChangePassword(oldPassword, newPassword) }

    /** Stop a running update: DeskBuddy throws the partial image away. */
    fun cancel() {
        cancelled = true
        inbox.offer(JSONObject().put("type", "_cancel"))
    }

    // ---------------------------------------------------------------- jobs

    private fun job(first: String, work: () -> String) {
        if (AppState.otaBusy) return
        AppState.otaBusy = true
        AppState.otaStep = first
        AppState.otaProgress = -1f
        worker.execute {
            cancelled = false
            inbox.clear()
            DeskBuddyClient.addListener(this)
            val result = try {
                work()
            } catch (e: Fail) {
                e.message ?: "Failed."
            } catch (e: Exception) {
                Log.w(TAG, "failed", e)
                "Failed: ${e.message ?: e.javaClass.simpleName}"
            } finally {
                DeskBuddyClient.removeListener(this)
                DeskBuddyClient.fastLink(false)
            }
            post {
                AppState.otaStep = result
                AppState.otaBusy = false
                if (AppState.otaProgress < 1f) AppState.otaProgress = -1f
            }
        }
    }

    private fun runUpdate(password: String): String {
        needLink()
        val build = AppState.build.ifEmpty { throw Fail("DeskBuddy did not say which build it runs. Reconnect and try again.") }
        val rel = latestRelease()
        post { AppState.otaLatest = rel.version }
        val name = OtaRules.imageName(build, rel.version)
        val imageUrl = rel.assets[name] ?: throw Fail("Release v${rel.version} has no update image for the $build build.")
        val sumsUrl = rel.assets["SHA256SUMS"] ?: throw Fail("Release v${rel.version} has no SHA256SUMS.")

        step("Downloading v${rel.version}...")
        val want = Sha256Sums.parse(String(download(sumsUrl, 64 * 1024), Charsets.UTF_8))[name]
            ?: throw Fail("SHA256SUMS does not list $name.")
        val image = download(imageUrl, MAX_IMAGE)
        val sha = OtaCrypto.hex(OtaCrypto.sha256(image))
        if (sha != want) throw Fail("The download was damaged (checksum). Try again.")
        if (!OtaRules.looksLikeImage(image)) throw Fail("That file is not a DeskBuddy firmware image.")

        step("Asking DeskBuddy...")
        val nonce = challenge(needPassword = true)
        val key = OtaCrypto.key(password)
        send(
            JSONObject().put("type", "ota_begin").put("size", image.size).put("sha256", sha)
                .put("version", rel.version).put("proof", OtaCrypto.updateProof(key, nonce, sha))
        )
        await(setOf("ota_confirm"), 8_000L, button = false)
        step("Press BTN1 on DeskBuddy to start (BTN2 = no).")
        val ready = await(setOf("ota_ready"), BUTTON_WAIT_MS, button = true)

        val chunk = ready.optInt("chunk", 1024).coerceIn(256, 1024)
        val total = OtaRules.chunkCount(image.size, chunk)
        val window = OtaWindow(total, 2)
        DeskBuddyClient.fastLink(true)
        step("Sending v${rel.version} to DeskBuddy... keep the phone close.")
        val started = System.currentTimeMillis()
        try {
            while (!window.done) {
                while (true) {
                    val seq = window.next() ?: break
                    val from = seq * chunk
                    val data = Base64.encodeToString(image, from, minOf(chunk, image.size - from), Base64.NO_WRAP)
                    if (!DeskBuddyClient.sendQuick(JSONObject().put("type", "ota_data").put("seq", seq).put("data", data))) {
                        throw Fail("The link to DeskBuddy dropped. Its old firmware still runs; try again.")
                    }
                }
                val ack = await(setOf("ota_ack"), 15_000L, button = false)
                if (!window.ack(ack.optInt("seq", -1))) throw Fail(OtaRules.errorText("bad_seq", 0, 0, false))
                val done = window.acked
                if (done % 8 == 0 || window.done) post { AppState.otaProgress = done.toFloat() / total }
            }
        } catch (e: Fail) {
            send(JSONObject().put("type", "ota_abort"))
            throw e
        }
        step("DeskBuddy is checking the image...")
        send(JSONObject().put("type", "ota_end"))
        await(setOf("ota_done"), 20_000L, button = false)
        val secs = (System.currentTimeMillis() - started) / 1000
        post { AppState.otaProgress = 1f }
        return "Updated to v${rel.version} in ${secs}s. DeskBuddy restarts and the app reconnects by itself."
    }

    private fun runSetPassword(newPassword: String): String {
        needLink()
        send(JSONObject().put("type", "ota_pass").put("key", OtaCrypto.hex(OtaCrypto.key(newPassword))))
        val first = await(setOf("ota_confirm", "ota_pass_ok"), 8_000L, button = false)
        if (first.optString("type") == "ota_confirm") {
            step("Press BTN1 on DeskBuddy to save the password (BTN2 = no).")
            await(setOf("ota_pass_ok"), BUTTON_WAIT_MS, button = true)
        }
        post { AppState.otaPass = true }
        return "Password set. DeskBuddy asks for it (and BTN1) for every update."
    }

    private fun runChangePassword(oldPassword: String, newPassword: String): String {
        needLink()
        val nonce = challenge(needPassword = true)
        val (hidden, proof) = OtaCrypto.passwordChange(OtaCrypto.key(oldPassword), nonce, OtaCrypto.key(newPassword))
        send(JSONObject().put("type", "ota_pass").put("key", hidden).put("proof", proof))
        await(setOf("ota_pass_ok"), 8_000L, button = false)
        return "Password changed."
    }

    // ---------------------------------------------------------------- talking to DeskBuddy

    private fun needLink() {
        if (!DeskBuddyClient.connected) throw Fail("Link DeskBuddy first (Setup > Link).")
        if (!DeviceFw.supportsOta(AppState.fw)) {
            throw Fail("DeskBuddy runs ${AppState.fw.ifEmpty { "older firmware" }}: install 2.5.0 once with DeskBuddy.exe (USB). After that, updates come from here.")
        }
    }

    /** "ota_nonce" -> the 16 random bytes for the next proof. */
    private fun challenge(needPassword: Boolean): ByteArray {
        send(JSONObject().put("type", "ota_nonce"))
        val c = await(setOf("ota_challenge"), 8_000L, button = false)
        if (needPassword && !c.optBoolean("pass_set")) throw Fail(OtaRules.errorText("no_password", 0, 0, false))
        val locked = c.optInt("locked", 0)
        if (locked > 0) throw Fail(OtaRules.errorText("locked", 0, locked, false))
        val nonce = OtaCrypto.unhex(c.optString("nonce"))
        if (nonce == null || nonce.size != 16) throw Fail("DeskBuddy sent a bad challenge. Try again.")
        return nonce
    }

    private fun send(msg: JSONObject) {
        if (!DeskBuddyClient.send(msg)) throw Fail("The link to DeskBuddy dropped. Try again.")
    }

    /** Wait for one of [types]; an ota_error, the link dropping or Cancel end the job. */
    private fun await(types: Set<String>, timeoutMs: Long, button: Boolean): JSONObject {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (true) {
            val left = deadline - System.currentTimeMillis()
            if (left <= 0) {
                throw Fail(if (button) OtaRules.errorText("timeout", 0, 0, true) else "DeskBuddy did not answer. Try again.")
            }
            val m = inbox.poll(left, TimeUnit.MILLISECONDS) ?: continue
            when (val type = m.optString("type")) {
                in types -> return m
                "ota_error" -> throw Fail(
                    OtaRules.errorText(m.optString("code"), m.optInt("left", 0), m.optInt("wait", 0), button)
                )
                "_lost" -> throw Fail("The link to DeskBuddy dropped. Its old firmware still runs; try again.")
                "_cancel" -> if (cancelled) throw Fail("Cancelled. DeskBuddy keeps its old firmware.")
                else -> Log.d(TAG, "ignored $type")
            }
        }
    }

    // ---------------------------------------------------------------- GitHub

    private fun latestRelease(): Release {
        val body = String(download("https://api.github.com/repos/$REPO/releases/latest", 1024 * 1024), Charsets.UTF_8)
        val json = JSONObject(body)
        val tag = json.optString("tag_name")
        val version = FwVersion.parse(tag)?.joinToString(".") ?: throw Fail("No release found on GitHub.")
        val assets = mutableMapOf<String, String>()
        val list = json.optJSONArray("assets")
        if (list != null) {
            for (i in 0 until list.length()) {
                val a = list.optJSONObject(i) ?: continue
                assets[a.optString("name")] = a.optString("browser_download_url")
            }
        }
        return Release(version, assets)
    }

    private fun download(url: String, max: Int): ByteArray {
        val request = Request.Builder().url(url)
            .header("User-Agent", "DeskBuddy-app")
            .header("Accept", if (url.startsWith("https://api.github.com")) "application/vnd.github+json" else "application/octet-stream")
            .build()
        try {
            http.newCall(request).execute().use { r ->
                if (r.code == 403 || r.code == 429) throw Fail("GitHub says: too many requests from this network. Try again later.")
                if (!r.isSuccessful) throw Fail("Download failed (HTTP ${r.code}).")
                val body = r.body ?: throw Fail("Download failed (empty).")
                val len = body.contentLength()
                if (len > max) throw Fail("Download is too big.")
                val bytes = body.bytes()
                if (bytes.size > max) throw Fail("Download is too big.")
                return bytes
            }
        } catch (e: Fail) {
            throw e
        } catch (e: java.io.IOException) {
            throw Fail("No internet connection to GitHub (${e.message}).")
        }
    }

    // ---------------------------------------------------------------- UI state

    private fun step(text: String) = post { AppState.otaStep = text }

    private fun post(block: () -> Unit) {
        main.post(block)
    }
}

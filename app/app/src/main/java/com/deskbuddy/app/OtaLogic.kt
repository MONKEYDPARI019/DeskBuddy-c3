package com.deskbuddy.app

import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

// "Update DeskBuddy" (firmware 2.5.0+): the parts with no Android dependencies, unit-tested in
// OtaLogicTest. OtaUpdater does the downloading and the talking. The device side is
// firmware/src/logic/ota_core.h; both must compute exactly the same bytes.

/** The update password, the way DeskBuddy checks it. The password itself never leaves the phone. */
object OtaCrypto {
    /** K = SHA-256("deskbuddy-ota:" + password): what DeskBuddy stores. */
    fun key(password: String): ByteArray = sha256("deskbuddy-ota:$password".toByteArray(Charsets.UTF_8))

    fun sha256(data: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").digest(data)

    fun hmac(key: ByteArray, vararg parts: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        parts.forEach { mac.update(it) }
        return mac.doFinal()
    }

    /** HMAC-SHA256(K, nonce || purpose || detail) in hex. */
    fun proof(key: ByteArray, nonce: ByteArray, purpose: String, detail: String): String =
        hex(hmac(key, nonce, purpose.toByteArray(Charsets.US_ASCII), detail.toByteArray(Charsets.US_ASCII)))

    /** "ota_begin": the proof also vouches for the image (its SHA-256, lowercase hex). */
    fun updateProof(key: ByteArray, nonce: ByteArray, imageSha256: String): String =
        proof(key, nonce, "update:", imageSha256)

    /**
     * "ota_pass" when a password is already set: the new key hidden with the old one
     * (new K xor HMAC(old K, nonce || "mask")) and the proof made with the old one.
     */
    fun passwordChange(oldKey: ByteArray, nonce: ByteArray, newKey: ByteArray): Pair<String, String> {
        val mask = hmac(oldKey, nonce, "mask".toByteArray(Charsets.US_ASCII))
        val hidden = hex(ByteArray(newKey.size) { (newKey[it].toInt() xor mask[it].toInt()).toByte() })
        return hidden to proof(oldKey, nonce, "pass:", hidden)
    }

    fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }

    /** Even-length hex (either case) -> bytes, or null. */
    fun unhex(s: String): ByteArray? {
        if (s.length % 2 != 0) return null
        val out = ByteArray(s.length / 2)
        for (i in out.indices) {
            val hi = Character.digit(s[2 * i], 16)
            val lo = Character.digit(s[2 * i + 1], 16)
            if (hi < 0 || lo < 0) return null
            out[i] = (hi * 16 + lo).toByte()
        }
        return out
    }
}

object OtaRules {
    /** Same limits as DeskBuddy's 'otapass set'. null = fine. */
    fun passwordProblem(password: String): String? = when {
        password.length < 4 -> "Use at least 4 characters"
        password.length > 63 -> "Use at most 63 characters"
        else -> null
    }

    /** The update image in a release: deskbuddy-c3-ota-<usb|battery>-v<version>.bin */
    fun imageName(build: String, version: String): String = "deskbuddy-c3-ota-$build-v$version.bin"

    /** A real ESP32 app image starts with the magic byte 0xE9. */
    fun looksLikeImage(bytes: ByteArray): Boolean = bytes.size > 1024 && bytes[0] == 0xE9.toByte()

    fun chunkCount(size: Int, chunk: Int): Int = (size + chunk - 1) / chunk

    /** One line of the {"type":"ota_error"} DeskBuddy sent, for people. */
    fun errorText(code: String, left: Int, wait: Int, waitingForButton: Boolean): String = when (code) {
        "no_password" -> "DeskBuddy has no update password yet: set one below first."
        "bad_password" ->
            if (left > 0) "Wrong password ($left ${if (left == 1) "try" else "tries"} left)."
            else "Wrong password. Updates are locked for a minute."
        "locked" -> "Too many wrong passwords: try again in ${wait.coerceAtLeast(1)} s."
        "declined" -> "BTN2 was pressed on DeskBuddy: nothing changed."
        "timeout" ->
            if (waitingForButton) "Nobody pressed BTN1 on DeskBuddy in time: nothing changed."
            else "DeskBuddy stopped waiting (the link was too slow). Try again closer to it."
        "busy" -> "DeskBuddy is already busy with an update. Try again in a minute."
        "too_big" -> "This image is too big for DeskBuddy."
        "flash" -> "DeskBuddy could not write the update. Its old firmware still runs."
        "bad_hash" -> "The image arrived damaged, so DeskBuddy threw it away. Try again."
        "bad_seq", "bad_data", "incomplete" -> "A piece got lost on the way. Try again."
        "no_challenge" -> "That took too long. Try again."
        "cancelled" -> "Cancelled on DeskBuddy (long BTN2)."
        "link_lost" -> "DeskBuddy lost the link to the phone."
        else -> "DeskBuddy said: $code"
    }
}

/** Release versions: "c3-2.5.0", "v2.5.0" and "2.5.0" all mean 2.5.0. */
object FwVersion {
    private val NUMBERS = Regex("""(\d+)\.(\d+)\.(\d+)""")

    fun parse(s: String): List<Int>? = NUMBERS.find(s)?.destructured?.toList()?.map { it.toInt() }

    /** <0, 0, >0 like compareTo; null if either is not a version. */
    fun compare(a: String, b: String): Int? {
        val x = parse(a) ?: return null
        val y = parse(b) ?: return null
        for (i in 0 until 3) if (x[i] != y[i]) return x[i].compareTo(y[i])
        return 0
    }

    fun atLeast(fw: String, version: String): Boolean = (compare(fw, version) ?: -1) >= 0
}

/** SHA256SUMS lines: "<64 hex>  <file name>" (or " *<name>"). File name -> lowercase hash. */
object Sha256Sums {
    private val LINE = Regex("""^([0-9a-fA-F]{64}) [ *](\S.*)$""")

    fun parse(text: String): Map<String, String> = text.lineSequence()
        .mapNotNull { LINE.matchEntire(it.trim()) }
        .associate { it.groupValues[2].trim() to it.groupValues[1].lowercase() }
}

/**
 * Which chunks to send next: at most [window] unacknowledged at a time (DeskBuddy's inbox holds
 * four messages, and a notification may arrive in between), acknowledged strictly in order.
 */
class OtaWindow(private val total: Int, private val window: Int = 2) {
    var acked = 0
        private set
    private var sent = 0

    val done: Boolean get() = acked >= total

    /** The next chunk number to send now, or null to wait for an ack. */
    fun next(): Int? = if (sent < total && sent - acked < window) sent++ else null

    /** False if [seq] is not the chunk DeskBuddy should have confirmed next. */
    fun ack(seq: Int): Boolean {
        if (seq != acked || seq >= sent) return false
        acked++
        return true
    }
}

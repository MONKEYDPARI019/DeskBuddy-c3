package com.deskbuddy.app

import java.io.ByteArrayOutputStream

/**
 * Turns a byte stream (Bluetooth LE notifications) into text lines.
 *
 * Lines are cut at the byte level and only then decoded as UTF-8: a BLE packet
 * can end in the middle of a multi-byte character, and decoding each packet on
 * its own turned such a character into garbage. A line longer than [maxLen]
 * bytes without a newline is dropped (it can only be noise).
 */
class ByteLineSplitter(private val maxLen: Int = 4096) {
    private val buf = ByteArrayOutputStream()
    private var dropping = false

    @Synchronized
    fun feed(bytes: ByteArray): List<String> {
        val lines = mutableListOf<String>()
        for (b in bytes) {
            if (b == '\n'.code.toByte()) {
                if (!dropping) {
                    val line = buf.toString(Charsets.UTF_8.name()).trim()
                    if (line.isNotEmpty()) lines.add(line)
                }
                buf.reset()
                dropping = false
            } else if (!dropping) {
                if (buf.size() >= maxLen) { buf.reset(); dropping = true } else buf.write(b.toInt())
            }
        }
        return lines
    }

    @Synchronized
    fun reset() { buf.reset(); dropping = false }
}

/** Notification text for the OLED: readable, short, never cut in the middle of a character. */
object NotifText {
    private val SPACES = Regex("\\s+")

    /** Whitespace folded, trimmed, at most [max] UTF-16 chars, no half emoji at the end. */
    fun clip(s: String, max: Int): String {
        val folded = s.replace(SPACES, " ").trim()
        if (folded.length <= max) return folded
        var end = max
        if (end > 0 && Character.isHighSurrogate(folded[end - 1])) end--
        return folded.substring(0, end).trimEnd()
    }

    /**
     * [transliterate] (Android's ICU "Any-Latin; Latin-ASCII", API 29+) turns Hindi and other
     * scripts the OLED font can't draw into Latin letters: "नमस्ते" -> "namaste".
     */
    fun prepare(s: String, max: Int, transliterate: ((String) -> String)?): String {
        val latin = try { transliterate?.invoke(s) ?: s } catch (e: Exception) { s }
        return clip(latin, max)
    }
}

/**
 * Notifications that arrive while DeskBuddy is not connected (phone just woke up,
 * reconnecting after a WiFi change): the newest [max] are kept for [maxAgeMs] and
 * sent as soon as the link is back, instead of being lost.
 */
class PendingNotifs<T>(private val max: Int = 5, private val maxAgeMs: Long = 120_000) {
    private val items = ArrayDeque<Pair<Long, T>>()

    @Synchronized
    fun add(item: T, now: Long) {
        items.addLast(now to item)
        while (items.size > max) items.removeFirst()
    }

    @Synchronized
    fun drain(now: Long): List<T> {
        val fresh = items.filter { now - it.first <= maxAgeMs }.map { it.second }
        items.clear()
        return fresh
    }
}

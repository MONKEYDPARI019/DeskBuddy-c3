package com.deskbuddy.app

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale

/**
 * Turns text into PCM with Android's built-in TextToSpeech and streams it to
 * DeskBuddy, so Mochi "speaks" through its own speaker.
 */
class TtsPcm(context: Context) {
    private val appContext = context.applicationContext
    @Volatile private var ready = false
    private lateinit var tts: TextToSpeech

    init {
        tts = TextToSpeech(appContext) { status ->
            ready = status == TextToSpeech.SUCCESS
            if (ready) tts.language = Locale.getDefault()
        }
    }

    fun speak(text: String) {
        if (!ready) { Log.w("TtsPcm", "TTS not ready yet"); return }
        val out = File(appContext.cacheDir, "reply.wav")
        val id = "reply-${System.currentTimeMillis()}"
        tts.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}
            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) { DeskBuddyClient.think(false) }
            override fun onDone(utteranceId: String?) {
                val wav = readWav(out)
                if (wav == null) { DeskBuddyClient.think(false); return }
                DeskBuddyClient.sayPcm(wav.first, wav.second)
            }
        })
        tts.synthesizeToFile(text, null, out, id)
    }

    fun shutdown() = tts.shutdown()

    companion object {
        /** Returns (16-bit mono PCM, sample rate) from a RIFF/WAVE file, or null. */
        fun readWav(file: File): Pair<ByteArray, Int>? {
            val bytes = try { file.readBytes() } catch (e: Exception) { return null }
            if (bytes.size < 44 || String(bytes, 0, 4) != "RIFF" || String(bytes, 8, 4) != "WAVE") return null
            val bb = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            var pos = 12
            var rate = 16000
            var channels = 1
            var bits = 16
            while (pos + 8 <= bytes.size) {
                val id = String(bytes, pos, 4)
                val size = bb.getInt(pos + 4)
                val body = pos + 8
                if (id == "fmt ") {
                    channels = bb.getShort(body + 2).toInt()
                    rate = bb.getInt(body + 4)
                    bits = bb.getShort(body + 14).toInt()
                } else if (id == "data") {
                    if (bits != 16) return null
                    val end = (body + size).coerceAtMost(bytes.size)
                    val data = bytes.copyOfRange(body, end)
                    return Pair(if (channels == 2) downmix(data) else data, rate)
                }
                pos = body + size + (size and 1)
            }
            return null
        }

        private fun downmix(stereo: ByteArray): ByteArray {
            val out = ByteArray(stereo.size / 2)
            var o = 0
            var i = 0
            while (i + 3 < stereo.size) {       // keep the left sample of each frame
                out[o++] = stereo[i]; out[o++] = stereo[i + 1]
                i += 4
            }
            return out
        }
    }
}

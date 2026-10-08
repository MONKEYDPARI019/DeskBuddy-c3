package com.deskbuddy.app

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.RandomAccessFile

/**
 * Handles push-to-talk from the device:
 *   ptt_start -> collect binary mic frames -> ptt_end -> answer.
 *
 * Today the "answer" is either an echo of what you said (hardware test) or a
 * short spoken TTS line. Plug a real assistant in at [answer]: run
 * speech-to-text on the PCM, ask your assistant, then call tts.speak(reply).
 */
class VoiceLoop(context: Context, private val prefs: Prefs) : DeskBuddyClient.Listener {
    private val appContext = context.applicationContext
    private val tts = TtsPcm(appContext)
    private val buffer = ByteArrayOutputStream()
    private var rate = 16000
    @Volatile private var recording = false

    override fun onJson(msg: JSONObject) {
        when (msg.optString("type")) {
            "ptt_start" -> synchronized(buffer) {
                buffer.reset()
                rate = msg.optInt("rate", 16000)
                recording = true
            }
            "ptt_end" -> {
                val pcm = synchronized(buffer) { recording = false; buffer.toByteArray() }
                Log.i("VoiceLoop", "utterance: ${pcm.size / 2.0 / rate} s")
                saveWav(pcm, rate)
                answer(pcm, rate)
            }
        }
    }

    override fun onAudio(pcm: ByteArray) {
        if (recording) synchronized(buffer) { buffer.write(pcm) }
    }

    private fun answer(pcm: ByteArray, rate: Int) {
        when {
            pcm.isEmpty() -> DeskBuddyClient.think(false)
            prefs.echoVoice -> DeskBuddyClient.sayPcm(pcm, rate)
            else -> tts.speak("I heard you, but my brain isn't connected yet.")
        }
    }

    fun speak(text: String) = tts.speak(text)

    fun shutdown() = tts.shutdown()

    /** Keeps the last utterance as last_ptt.wav in the app cache (handy for debugging the mic). */
    private fun saveWav(pcm: ByteArray, rate: Int) {
        try {
            val f = File(appContext.cacheDir, "last_ptt.wav")
            RandomAccessFile(f, "rw").use { raf ->
                raf.setLength(0)
                fun le32(v: Int) { raf.write(v and 0xff); raf.write(v shr 8 and 0xff); raf.write(v shr 16 and 0xff); raf.write(v shr 24 and 0xff) }
                fun le16(v: Int) { raf.write(v and 0xff); raf.write(v shr 8 and 0xff) }
                raf.writeBytes("RIFF"); le32(36 + pcm.size); raf.writeBytes("WAVE")
                raf.writeBytes("fmt "); le32(16); le16(1); le16(1); le32(rate); le32(rate * 2); le16(2); le16(16)
                raf.writeBytes("data"); le32(pcm.size); raf.write(pcm)
            }
        } catch (e: Exception) {
            Log.w("VoiceLoop", "could not save wav", e)
        }
    }
}

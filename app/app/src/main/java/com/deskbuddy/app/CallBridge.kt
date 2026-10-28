package com.deskbuddy.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.ActivityOptions
import android.app.Notification
import android.app.PendingIntent
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.service.notification.StatusBarNotification
import android.telecom.TelecomManager
import android.util.Log
import org.json.JSONObject

/**
 * Phone calls on DeskBuddy (firmware 2.5.0+).
 *
 * NotifListener hands over every call notification (category "call": the phone app's, WhatsApp's,
 * ...). DeskBuddy shows the caller; BTN1 / BTN2 come back as {"type":"call_action"} (LinkService),
 * and the phone answers, declines or hangs up. The sound stays on the phone: DeskBuddy C3 has no
 * microphone or speaker.
 *
 * How the phone acts, best first:
 *  - normal SIM calls (the notification comes from the phone app): TelecomManager, with the
 *    "answer phone calls" permission (Inbox > Phone access);
 *  - Android 12+ call notifications (CallStyle) carry their Answer / Decline / Hang up intents;
 *  - otherwise the notification's own buttons, found by their English names.
 * Some apps (WhatsApp...) open a screen to answer; Android may block that while the app is in the
 * background, and then the call is answered on the phone.
 */
object CallBridge {
    private const val TAG = "CallBridge"

    // Notification.EXTRA_CALL_TYPE etc. (Android 12, API 31); plain strings so older SDKs compile
    private const val EXTRA_CALL_TYPE = "android.callType"
    private const val EXTRA_ANSWER = "android.answerIntent"
    private const val EXTRA_DECLINE = "android.declineIntent"
    private const val EXTRA_HANG_UP = "android.hangUpIntent"
    private const val CALL_INCOMING = 1
    private const val CALL_ONGOING = 2
    private const val CALL_SCREENING = 3

    private val ANSWER_WORDS = listOf("answer", "accept", "pick up")
    private val DECLINE_WORDS = listOf("decline", "reject", "dismiss")
    private val HANG_UP_WORDS = listOf("hang up", "end call", "hangup", "end")

    private class Call(
        val key: String,
        val id: String,
        val state: String,              // "ringing" | "active"
        val name: String,
        val app: String,
        val fromDialer: Boolean,        // the phone app's own (SIM) call
        val answer: PendingIntent?,
        val decline: PendingIntent?,
        val hangUp: PendingIntent?,
    )

    @Volatile private var current: Call? = null

    fun isCall(n: Notification): Boolean = n.category == Notification.CATEGORY_CALL

    /** A call notification was posted or updated (NotifListener's worker thread). */
    fun onPosted(context: Context, sbn: StatusBarNotification, app: String) {
        val n = sbn.notification
        val extras = n.extras
        val answer = intentExtra(n, EXTRA_ANSWER) ?: action(n, ANSWER_WORDS)
        val decline = intentExtra(n, EXTRA_DECLINE) ?: action(n, DECLINE_WORDS)
        val hangUp = intentExtra(n, EXTRA_HANG_UP) ?: action(n, HANG_UP_WORDS)
        val state = when (extras.getInt(EXTRA_CALL_TYPE, 0)) {
            CALL_INCOMING, CALL_SCREENING -> "ringing"
            CALL_ONGOING -> "active"
            else -> if (answer != null) "ringing" else "active"
        }
        val name = (extras.getCharSequence(Notification.EXTRA_TITLE)
            ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString()?.trim().orEmpty()
        val call = Call(
            sbn.key, idFor(sbn.key), state, NotifText.clip(name, 31), NotifText.clip(app, 15),
            sbn.packageName in dialers(context), answer, decline, hangUp,
        )
        val before = current
        current = call
        // apps re-post the same notification every few seconds: only send real changes
        if (before != null && before.key == call.key && before.state == call.state && before.name == call.name) return
        send(call.state, call)
    }

    /** A notification went away: if it was the call, the call is over. */
    fun onRemoved(key: String) {
        val c = current ?: return
        if (c.key != key) return
        current = null
        send("ended", c)
    }

    /** BTN1 / BTN2 on DeskBuddy ({"type":"call_action"}), from LinkService. */
    @Suppress("DEPRECATION")      // acceptRingingCall / endCall: still the way for SIM calls
    fun onAction(context: Context, action: String, id: String) {
        val c = current
        if (c == null || c.id != id) {
            Log.i(TAG, "$action for a call that is gone")
            return
        }
        val done = when (action) {
            "answer" -> (c.fromDialer && telecom(context) { it.acceptRingingCall() }) || fire(c.answer)
            "decline" -> (c.fromDialer && telecomEnd(context)) || fire(c.decline) || fire(c.hangUp)
            "hangup" -> (c.fromDialer && telecomEnd(context)) || fire(c.hangUp) || fire(c.decline)
            else -> false
        }
        Log.i(TAG, "$action: ${if (done) "done" else "nothing to press"}")
    }

    /** The phone app(s) whose notifications are SIM calls. */
    private fun dialers(context: Context): Set<String> {
        val tm = context.getSystemService(Context.TELECOM_SERVICE) as? TelecomManager ?: return emptySet()
        return try {
            setOfNotNull(tm.defaultDialerPackage, tm.systemDialerPackage)
        } catch (e: Exception) {
            emptySet()
        }
    }

    private fun canAnswer(context: Context): Boolean =
        context.checkSelfPermission(Manifest.permission.ANSWER_PHONE_CALLS) == PackageManager.PERMISSION_GRANTED

    @SuppressLint("MissingPermission")
    private fun telecom(context: Context, act: (TelecomManager) -> Unit): Boolean {
        if (!canAnswer(context)) return false
        val tm = context.getSystemService(Context.TELECOM_SERVICE) as? TelecomManager ?: return false
        return try {
            act(tm)
            true
        } catch (e: Exception) {
            Log.w(TAG, "TelecomManager refused: $e")
            false
        }
    }

    @SuppressLint("MissingPermission")
    @Suppress("DEPRECATION")
    private fun telecomEnd(context: Context): Boolean =
        Build.VERSION.SDK_INT >= 28 && telecom(context) { it.endCall() }

    @Suppress("DEPRECATION")
    private fun intentExtra(n: Notification, key: String): PendingIntent? = try {
        n.extras.getParcelable<PendingIntent>(key)
    } catch (e: Exception) {
        null
    }

    private fun action(n: Notification, words: List<String>): PendingIntent? =
        n.actions?.firstOrNull { a ->
            val title = a.title?.toString()?.lowercase()?.trim() ?: return@firstOrNull false
            words.any { w -> title == w || title.startsWith("$w ") }
        }?.actionIntent

    private fun fire(pi: PendingIntent?): Boolean {
        if (pi == null) return false
        return try {
            if (Build.VERSION.SDK_INT >= 34) {
                // let it open the call screen if Android allows it
                val options = ActivityOptions.makeBasic()
                    .setPendingIntentBackgroundActivityStartMode(ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED)
                pi.send(null, 0, null, null, null, null, options.toBundle())
            } else {
                pi.send()
            }
            true
        } catch (e: Exception) {
            Log.w(TAG, "could not press the button: $e")
            false
        }
    }

    /** Short id DeskBuddy sends back (letters and digits only). */
    private fun idFor(key: String): String = Integer.toHexString(key.hashCode())

    private fun send(state: String, c: Call) {
        if (!DeviceFw.supportsCalls(AppState.fw)) return
        DeskBuddyClient.send(
            JSONObject().put("type", "call").put("state", state)
                .put("name", c.name).put("app", c.app).put("id", c.id)
        )
    }
}

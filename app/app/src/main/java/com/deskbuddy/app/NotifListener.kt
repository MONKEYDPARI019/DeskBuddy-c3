package com.deskbuddy.app

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * Forwards phone notifications to DeskBuddy — replaces the v1 Automate/HTTP
 * setup. Enable it in Settings > Notification access (button in the app).
 */
class NotifListener : NotificationListenerService() {
    private var lastKey = ""
    private var lastText = ""
    private var lastTime = 0L

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (!Prefs(this).forwardNotifications) return
        if (sbn.packageName == packageName) return
        val n = sbn.notification
        if (sbn.isOngoing || n.flags and Notification.FLAG_GROUP_SUMMARY != 0) return

        val extras = n.extras
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: return
        val text = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString() ?: ""

        // messaging apps often re-post the same notification; skip duplicates for 3 s
        val now = System.currentTimeMillis()
        if (sbn.key == lastKey && text == lastText && now - lastTime < 3000) return
        lastKey = sbn.key; lastText = text; lastTime = now

        val app = try {
            packageManager.getApplicationLabel(packageManager.getApplicationInfo(sbn.packageName, 0)).toString()
        } catch (e: Exception) {
            sbn.packageName.substringAfterLast('.')
        }
        val prefs = Prefs(this)
        AppState.rememberApp(prefs, app)          // shows up in the Inbox filter list
        if (app in prefs.blockedApps) return     // user switched this app off
        if (!DeskBuddyClient.connected) return
        DeskBuddyClient.notify(app, title, text)
    }
}

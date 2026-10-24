package com.deskbuddy.app.ui

// Small text helpers with no Android or Compose dependencies (unit-tested in UiTextTest).

/** "now", "5m ago", "2h ago", "3d ago". */
fun timeAgo(time: Long, now: Long = System.currentTimeMillis()): String {
    val s = (now - time).coerceAtLeast(0L) / 1000
    return when {
        s < 60 -> "now"
        s < 3600 -> "${s / 60}m ago"
        s < 86400 -> "${s / 3600}h ago"
        else -> "${s / 86400}d ago"
    }
}

/** First letter or digit of an app name, for its notification avatar. */
fun appInitial(app: String): String =
    app.firstOrNull { it.isLetterOrDigit() }?.uppercaseChar()?.toString() ?: "?"

/** Which of the four pastel colours an app's avatar gets (always the same one for an app). */
fun tintIndex(key: String): Int = Math.floorMod(key.hashCode(), 4)

/** What Mochi is doing, for the chip on Home: "Happy", "Listening", ... */
fun faceLabel(face: String, shown: String): String = when (face) {
    "listen" -> "Listening"
    "think" -> "Thinking"
    "speak" -> "Speaking"
    "notify" -> "New message!"
    "sleep" -> "Asleep"
    else -> shown.replaceFirstChar { it.uppercaseChar() }
}

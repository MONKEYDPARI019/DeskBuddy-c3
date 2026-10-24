package com.deskbuddy.app.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class UiTextTest {
    private val now = 1_800_000_000_000L

    @Test
    fun timeAgoBuckets() {
        assertEquals("now", timeAgo(now - 30_000, now))
        assertEquals("now", timeAgo(now + 5_000, now))          // clock skew never shows a negative time
        assertEquals("2m ago", timeAgo(now - 120_000, now))
        assertEquals("59m ago", timeAgo(now - 3_599_000, now))
        assertEquals("1h ago", timeAgo(now - 3_600_000, now))
        assertEquals("3d ago", timeAgo(now - 3 * 86_400_000L, now))
    }

    @Test
    fun avatarInitial() {
        assertEquals("W", appInitial("WhatsApp"))
        assertEquals("G", appInitial("  gmail"))
        assertEquals("9", appInitial("9GAG"))
        assertEquals("?", appInitial(""))
        assertEquals("?", appInitial("  ..."))
    }

    @Test
    fun avatarTintIsStableAndInRange() {
        for (app in listOf("WhatsApp", "Gmail", "Calendar", "", "x".repeat(200), "Ünïcödé")) {
            val i = tintIndex(app)
            assertTrue("$app -> $i", i in 0..3)
            assertEquals(i, tintIndex(app))
        }
    }

    @Test
    fun faceLabels() {
        assertEquals("Happy", faceLabel("idle", "happy"))
        assertEquals("Default", faceLabel("boot", "default"))
        assertEquals("Listening", faceLabel("listen", "happy"))
        assertEquals("New message!", faceLabel("notify", "sad"))
        assertEquals("Asleep", faceLabel("sleep", "sleeping"))
    }
}

package com.deskbuddy.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ByteLineSplitterTest {
    @Test fun splitsLinesAndKeepsThePartialOne() {
        val s = ByteLineSplitter()
        assertEquals(listOf("{\"a\":1}"), s.feed("{\"a\":1}\n{\"b\"".toByteArray()))
        assertEquals(listOf("{\"b\":2}"), s.feed(":2}\r\n".toByteArray()))
    }

    @Test fun multiByteCharacterSplitAcrossPacketsSurvives() {
        // BLE delivers (MTU - 3)-byte pieces: a UTF-8 character can be cut in two
        val bytes = "{\"t\":\"€ ok\"}\n".toByteArray(Charsets.UTF_8)
        val cut = bytes.indexOf(0xE2.toByte()) + 1           // in the middle of '€'
        val s = ByteLineSplitter()
        assertEquals(emptyList<String>(), s.feed(bytes.copyOfRange(0, cut)))
        assertEquals(listOf("{\"t\":\"€ ok\"}"), s.feed(bytes.copyOfRange(cut, bytes.size)))
    }

    @Test fun blankLinesAreSkippedAndGarbageIsCapped() {
        val s = ByteLineSplitter(maxLen = 16)
        assertEquals(emptyList<String>(), s.feed("\n\r\n".toByteArray()))
        assertEquals(emptyList<String>(), s.feed(ByteArray(40) { 'x'.code.toByte() }))   // no newline: dropped
        assertEquals(listOf("ok"), s.feed("\nok\n".toByteArray()))
    }
}

class NotifTextTest {
    @Test fun clipNeverSplitsAnEmoji() {
        val s = "ab😀cd"                 // the emoji is 2 UTF-16 chars
        assertEquals("ab", NotifText.clip(s, 3))
        assertEquals("ab😀", NotifText.clip(s, 4))
        assertEquals("ab😀cd", NotifText.clip(s, 99))
    }

    @Test fun clipTrimsAndFoldsWhitespace() {
        assertEquals("Hi there", NotifText.clip("  Hi\n\nthere  ", 50))
    }

    @Test fun prepareUsesTheTransliteratorWhenThereIsOne() {
        val upper: (String) -> String = { it.uppercase() }
        assertEquals("NAMASTE", NotifText.prepare("namaste", 10, upper))
        assertEquals("namaste", NotifText.prepare("namaste", 10, null))
    }

    @Test fun prepareSurvivesABrokenTransliterator() {
        val broken: (String) -> String = { throw IllegalStateException("icu") }
        assertEquals("text", NotifText.prepare("text", 10, broken))
    }
}

class PendingNotifsTest {
    @Test fun keepsTheNewestFewAndDropsOldOnes() {
        val p = PendingNotifs<String>(max = 3, maxAgeMs = 1000)
        for (i in 1..5) p.add("n$i", now = i.toLong())
        assertEquals(listOf("n3", "n4", "n5"), p.drain(now = 10))
        assertTrue(p.drain(now = 10).isEmpty())                 // drained
        p.add("old", now = 0)
        p.add("new", now = 900)
        assertEquals(listOf("new"), p.drain(now = 1500))         // "old" waited too long
    }
}

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

class DeviceFwTest {
    @Test fun clearNeedsC3Firmware231OrNewer() {
        assertTrue(DeviceFw.supportsClear("c3-2.3.1"))
        assertTrue(DeviceFw.supportsClear("c3-2.4.0"))
        assertTrue(DeviceFw.supportsClear("c3-3.0.0"))
        assertTrue(DeviceFw.supportsClear("c3-2.3.10"))
        assertEquals(false, DeviceFw.supportsClear("c3-2.3.0"))   // released before "clear" existed
        assertEquals(false, DeviceFw.supportsClear("c3-2.2.1"))
        assertEquals(false, DeviceFw.supportsClear(""))            // not known yet
        assertEquals(false, DeviceFw.supportsClear("2.3.1"))       // DeskBuddy v2 firmware: not a C3
        assertEquals(false, DeviceFw.supportsClear("c3-garbage"))
    }

    @Test fun updatesAndCallsNeedC3Firmware250OrNewer() {
        assertTrue(DeviceFw.supportsOta("c3-2.5.0"))
        assertTrue(DeviceFw.supportsCalls("c3-2.5.0"))
        assertTrue(DeviceFw.supportsOta("c3-2.10.0"))
        assertEquals(false, DeviceFw.supportsOta("c3-2.4.1"))      // needs one USB install of 2.5.0
        assertEquals(false, DeviceFw.supportsCalls("c3-2.4.1"))
        assertEquals(false, DeviceFw.supportsOta(""))
        assertEquals(false, DeviceFw.supportsOta("2.5.0"))
    }
}

class InboxSyncTest {
    @Test fun clearsTheAppListWhenTheDeviceCountDropsToZero() {
        val s = InboxSync()
        assertEquals(false, s.onDeviceCount(0))   // first state after connecting: nothing to compare with
        assertEquals(false, s.onDeviceCount(2))
        assertEquals(false, s.onDeviceCount(3))
        assertTrue(s.onDeviceCount(0))             // long BTN2 or "clear": the device emptied its list
        assertEquals(false, s.onDeviceCount(0))   // only once
    }

    @Test fun aNewConnectionStartsOver() {
        val s = InboxSync()
        s.onDeviceCount(4)
        s.reset()                                  // disconnected; the device may have restarted meanwhile
        assertEquals(false, s.onDeviceCount(0))   // a restart empties the device: keep the app's history
    }
}

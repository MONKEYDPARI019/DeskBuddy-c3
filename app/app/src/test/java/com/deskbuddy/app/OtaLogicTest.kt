package com.deskbuddy.app

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OtaCryptoTest {
    private val nonce = ByteArray(16) { it.toByte() }

    // The same numbers are checked on the firmware side (firmware/test/host/test_logic.cpp):
    // if either side changes how it computes them, updates stop working.
    @Test fun matchesTheFirmware() {
        val key = OtaCrypto.key("deskbuddy")
        assertEquals("05dd5680fdbca13dc03653ea432914e9cc28f8af416d8e6d263233dfd6ce0d0b", OtaCrypto.hex(key))
        val image = OtaCrypto.hex(OtaCrypto.sha256("hello image".toByteArray()))
        assertEquals("84d8fd5280a5162aaf5c5d9aeb069b2660500eabeeda58ce2bb10595827e08ad", image)
        assertEquals(
            "b025ce285f67ad287d99d0b7665f847d30c9ece8f80bfe2f1ef0442bdebad246",
            OtaCrypto.updateProof(key, nonce, image),
        )
        val (hidden, proof) = OtaCrypto.passwordChange(key, nonce, OtaCrypto.key("new pass"))
        assertEquals("592f22a6119d848699d787527d8311ced778e0c1764d8705403f0ea35da6c0c9", hidden)
        assertEquals("0ae55bbf5a30104ea6ee2922c770e2c526a3ebfb38e37d53a7087efe1a4d138c", proof)
    }

    @Test fun hmacMatchesRfc4231() {
        val mac = OtaCrypto.hmac("Jefe".toByteArray(), "what do ya want ".toByteArray(), "for nothing?".toByteArray())
        assertEquals("5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843", OtaCrypto.hex(mac))
    }

    @Test fun hexRoundTrip() {
        val bytes = byteArrayOf(0, 1, 0x7f, -128, -1)
        assertEquals("00017f80ff", OtaCrypto.hex(bytes))
        assertArrayEquals(bytes, OtaCrypto.unhex("00017F80ff"))
        assertNull(OtaCrypto.unhex("abc"))
        assertNull(OtaCrypto.unhex("zz"))
    }
}

class OtaRulesTest {
    @Test fun passwordLength() {
        assertEquals("Use at least 4 characters", OtaRules.passwordProblem("abc"))
        assertNull(OtaRules.passwordProblem("abcd"))
        assertNull(OtaRules.passwordProblem("x".repeat(63)))
        assertEquals("Use at most 63 characters", OtaRules.passwordProblem("x".repeat(64)))
    }

    @Test fun imageNameMatchesTheRelease() {
        // written by tool/src/deskbuddy/envs.py ota_image_filename()
        assertEquals("deskbuddy-c3-ota-battery-v2.5.0.bin", OtaRules.imageName("battery", "2.5.0"))
        assertEquals("deskbuddy-c3-ota-usb-v2.5.0.bin", OtaRules.imageName("usb", "2.5.0"))
    }

    @Test fun onlyRealImages() {
        assertTrue(OtaRules.looksLikeImage(ByteArray(2000).also { it[0] = 0xE9.toByte() }))
        assertFalse(OtaRules.looksLikeImage(ByteArray(2000)))                       // e.g. an HTML error page
        assertFalse(OtaRules.looksLikeImage(byteArrayOf(0xE9.toByte(), 1, 2)))
    }

    @Test fun chunks() {
        assertEquals(1, OtaRules.chunkCount(1, 1024))
        assertEquals(1, OtaRules.chunkCount(1024, 1024))
        assertEquals(2, OtaRules.chunkCount(1025, 1024))
    }

    @Test fun errorsReadWell() {
        assertEquals("Wrong password (2 tries left).", OtaRules.errorText("bad_password", 2, 0, false))
        assertEquals("Wrong password (1 try left).", OtaRules.errorText("bad_password", 1, 0, false))
        assertTrue(OtaRules.errorText("bad_password", 0, 60, false).contains("locked"))
        assertEquals("Too many wrong passwords: try again in 42 s.", OtaRules.errorText("locked", 0, 42, false))
        assertTrue(OtaRules.errorText("timeout", 0, 0, true).contains("BTN1"))
        assertTrue(OtaRules.errorText("timeout", 0, 0, false).contains("slow"))
        assertEquals("DeskBuddy said: something_new", OtaRules.errorText("something_new", 0, 0, false))
    }
}

class FwVersionTest {
    @Test fun parsesEveryForm() {
        assertEquals(listOf(2, 5, 0), FwVersion.parse("c3-2.5.0"))
        assertEquals(listOf(2, 5, 0), FwVersion.parse("v2.5.0"))
        assertEquals(listOf(2, 10, 3), FwVersion.parse("2.10.3"))
        assertNull(FwVersion.parse("c3-garbage"))
    }

    @Test fun compares() {
        assertEquals(0, FwVersion.compare("c3-2.5.0", "v2.5.0"))
        assertTrue(FwVersion.compare("c3-2.4.1", "2.5.0")!! < 0)
        assertTrue(FwVersion.compare("c3-2.10.0", "2.9.9")!! > 0)
        assertNull(FwVersion.compare("", "2.5.0"))
        assertTrue(FwVersion.atLeast("c3-2.5.0", "2.5.0"))
        assertFalse(FwVersion.atLeast("", "2.5.0"))
    }
}

class Sha256SumsTest {
    @Test fun parsesSha256sumOutput() {
        val a = "a".repeat(64)
        val b = "B".repeat(64)
        val sums = Sha256Sums.parse("$a  deskbuddy-c3-ota-usb-v2.5.0.bin\n$b *DeskBuddy.exe\r\nnot a line\n\n")
        assertEquals(a, sums["deskbuddy-c3-ota-usb-v2.5.0.bin"])
        assertEquals("b".repeat(64), sums["DeskBuddy.exe"])
        assertEquals(2, sums.size)
    }
}

class OtaWindowTest {
    @Test fun keepsTwoChunksInFlightInOrder() {
        val w = OtaWindow(total = 5, window = 2)
        assertEquals(0, w.next())
        assertEquals(1, w.next())
        assertNull(w.next())                 // two waiting for an ack
        assertFalse(w.ack(1))                // out of order: refused
        assertTrue(w.ack(0))
        assertEquals(2, w.next())
        assertNull(w.next())
        assertTrue(w.ack(1))
        assertTrue(w.ack(2))
        assertEquals(3, w.next())
        assertEquals(4, w.next())
        assertNull(w.next())                 // all sent
        assertFalse(w.ack(4))
        assertTrue(w.ack(3))
        assertFalse(w.done)
        assertTrue(w.ack(4))
        assertTrue(w.done)
        assertFalse(w.ack(5))                // never sent
        assertEquals(5, w.acked)
    }
}

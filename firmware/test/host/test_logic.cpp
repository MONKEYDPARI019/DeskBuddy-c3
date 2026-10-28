// Unit tests for the pure logic in src/logic (runs on a PC, no board needed):
//   g++ -std=c++17 -Wall -Wextra -I../../src test_logic.cpp -o t && ./t
#include "logic/framing.h"
#include "logic/text.h"
#include "logic/notif_store.h"
#include "logic/tz.h"
#include "logic/battery_curve.h"
#include "logic/debounce.h"
#include "logic/dirty_tiles.h"
#include "config.h"
#include "logic/protocol_types.h"
#include "logic/sha256.h"
#include "logic/codec.h"
#include "logic/ota_core.h"
#include "logic/call_state.h"
#include <cstdio>
#include <string>
#include <vector>

static int fails = 0, checks = 0;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); } } while (0)
#define EQ(a, b) do { checks++; std::string _a = (a), _b = (b); if (_a != _b) { fails++; printf("FAIL %s:%d  \"%s\" != \"%s\"\n", __FILE__, __LINE__, _a.c_str(), _b.c_str()); } } while (0)

static std::string fold(const char* s, size_t n = 128) { char b[256]; asciiFold(s, b, n); return b; }

static void testFraming() {
    LineAssembler<32> la;
    std::vector<std::string> got;
    auto cb = [&](const char* l, size_t n) { got.emplace_back(l, n); };
    const char* p1 = "{\"a\":1}\n{\"b\"";
    const char* p2 = ":2}\r\n\n";
    la.push(p1, strlen(p1), cb);
    la.push(p2, strlen(p2), cb);
    CHECK(got.size() == 2);
    EQ(got[0], "{\"a\":1}"); EQ(got[1], "{\"b\":2}");
    got.clear();
    std::string longLine(40, 'x');                  // too long: dropped whole
    la.push(longLine.c_str(), longLine.size(), cb);
    la.push("\nok\n", 4, cb);
    CHECK(got.size() == 1); if (!got.empty()) EQ(got[0], "ok");
    CHECK(la.overflows() == 1);
    // every byte separately
    got.clear();
    const char* m = "{\"type\":\"hello\"}\n";
    for (const char* p = m; *p; p++) la.push(p, 1, cb);
    CHECK(got.size() == 1);
    got.clear();                                    // stray NUL bytes are ignored
    la.push("{\"n\":1}\0\n", 9, cb);
    CHECK(got.size() == 1); if (!got.empty()) EQ(got[0], "{\"n\":1}");

    // chunking + reassembly round trip at several MTUs
    for (size_t chunk : {1u, 7u, 20u, 244u, 400u}) {
        std::string msg = "{\"type\":\"state\",\"face\":\"idle\",\"mood\":\"happy\",\"x\":\"" + std::string(100, 'z') + "\"}";
        LineAssembler<512> rx;
        std::vector<std::string> out;
        size_t maxPiece = 0;
        size_t pieces = frameChunks(msg.c_str(), chunk, [&](const char* p, size_t n) {
            if (n > maxPiece) maxPiece = n;
            rx.push(p, n, [&](const char* l, size_t k) { out.emplace_back(l, k); });
        });
        size_t eff = chunk > 256 ? 256 : chunk;
        CHECK(maxPiece <= eff);
        CHECK(pieces == (msg.size() + 1 + eff - 1) / eff);
        CHECK(out.size() == 1);
        if (!out.empty()) EQ(out[0], msg);
    }
    CHECK(frameChunks(nullptr, 20, [](const char*, size_t) {}) == 0);
    CHECK(frameChunks("x", 0, [](const char*, size_t) {}) == 0);
}

static void testText() {
    EQ(fold("Hello"), "Hello");
    EQ(fold("  lots   of\n\nspace\t "), "lots of space");
    EQ(fold("it\xE2\x80\x99s \xE2\x80\x9C" "fine\xE2\x80\x9D \xE2\x80\x94 ok\xE2\x80\xA6"), "it's \"fine\" - ok...");
    EQ(fold("Caf\xC3\xA9 na\xC3\xAFve \xC3\x91" "o\xC3\xB1o"), "Cafe naive Nono");
    EQ(fold("Party \xF0\x9F\x8E\x89\xF0\x9F\x8E\x89!"), "Party **!");
    EQ(fold("thumbs \xF0\x9F\x91\x8D\xF0\x9F\x8F\xBD up"), "thumbs * up");      // skin tone dropped
    EQ(fold("\xE2\x9D\xA4\xEF\xB8\x8F you"), "* you");                       // heart + VS16
    EQ(fold("\xE0\xA4\xA8\xE0\xA4\xAE"), "?");                               // Hindi word: one ?
    // "namaste dost" in Devanagari: one ? per word, not a screen full of them
    EQ(fold("\xE0\xA4\xA8\xE0\xA4\xAE\xE0\xA4\xB8\xE0\xA5\x8D\xE0\xA4\xA4\xE0\xA5\x87 "
            "\xE0\xA4\xA6\xE0\xA5\x8B\xE0\xA4\xB8\xE0\xA5\x8D\xE0\xA4\xA4"), "? ?");
    EQ(fold("Mom: \xE0\xA4\x96\xE0\xA4\xBE\xE0\xA4\xA8\xE0\xA4\xBE ready"), "Mom: ? ready");
    EQ(fold("what?? ok?"), "what?? ok?");                                    // real ? marks stay
    EQ(fold("\xE2\x82\xB9" "500"), "Rs500");
    EQ(fold("bad \xFF\xFE bytes \xE2\x82"), "bad ? bytes ?");
    EQ(fold(nullptr), "");
    EQ(fold("abcdefghij", 5), "abcd");                                      // always terminated
    EQ(fold("ab\xE2\x80\xA6", 5), "ab..");                                   // multi-char replacement cut
    char tiny[1]; asciiFold("x", tiny, 1); CHECK(tiny[0] == 0);
    CHECK(asciiFold("x", nullptr, 4) == 0);

    char rows[6][11];
    int n = wrapText("the quick brown fox jumps over the lazy dog", 10, &rows[0][0], 6);
    CHECK(n == 5);
    EQ(rows[0], "the quick"); EQ(rows[1], "brown fox"); EQ(rows[2], "jumps over");
    EQ(rows[3], "the lazy"); EQ(rows[4], "dog");
    n = wrapText("supercalifragilistic word", 10, &rows[0][0], 6);   // long word is cut
    CHECK(n == 3); EQ(rows[0], "supercalif"); EQ(rows[1], "ragilistic"); EQ(rows[2], "word");
    n = wrapText("exactly10c next", 10, &rows[0][0], 6);
    CHECK(n == 2); EQ(rows[0], "exactly10c"); EQ(rows[1], "next");
    n = wrapText("a b c d e f g h i j k l m n o p q r s t u v w x y z", 3, &rows[0][0], 2);  // maxLines
    CHECK(n == 2); EQ(rows[0], "a b");
    CHECK(wrapText("", 10, &rows[0][0], 6) == 0);
    CHECK(wrapText("   ", 10, &rows[0][0], 6) == 0);
    CHECK(wrapText(nullptr, 10, &rows[0][0], 6) == 0);
    for (int w = 1; w <= 10; w++) {                 // no row ever exceeds the width
        char r[40 * 11];                            // rows are (w + 1) bytes apart
        int k = wrapText("Mom: dinner is ready, come down now please!!", w, r, 40);
        CHECK(k > 0);
        for (int i = 0; i < k; i++) {
            const char* row = r + i * (w + 1);
            CHECK(strlen(row) <= (size_t)w && strlen(row) > 0);
        }
    }
}

static void testNotifs() {
    NotifStore<3> s;
    CHECK(s.count() == 0 && s.current() == nullptr);
    s.push("WA", "Mom", "Dinner", 1, false);
    s.push("", "", nullptr, 2, false);
    CHECK(s.count() == 2 && s.unread() == 2);
    EQ(s.at(0)->app, "Phone"); EQ(s.at(0)->title, "Notification"); EQ(s.at(0)->body, "");
    EQ(s.at(1)->title, "Mom");
    s.next(); EQ(s.current()->title, "Mom");
    s.next(); EQ(s.current()->title, "Notification");          // wraps
    s.push("A", "3", "", 3, true);                               // viewing: not unread
    CHECK(s.unread() == 2);
    s.push("A", "4", "", 4, false);                              // ring: oldest dropped
    CHECK(s.count() == 3);
    EQ(s.at(0)->title, "4"); EQ(s.at(2)->title, "Notification");
    CHECK(s.at(3) == nullptr && s.at(-1) == nullptr);
    CHECK(s.unread() <= s.count());
    s.markRead(); CHECK(s.unread() == 0);
    std::string big(300, 'b');
    s.push(big.c_str(), big.c_str(), big.c_str(), 5, false);       // truncated, terminated
    CHECK(strlen(s.at(0)->app) == 15 && strlen(s.at(0)->title) == 31 && strlen(s.at(0)->body) == 127);
    s.clear(); CHECK(s.count() == 0 && s.unread() == 0 && s.current() == nullptr);
    s.next(); CHECK(s.selected() == 0);
}

static void testTz() {
    char b[40];
    tzFromOffsetMinutes(330, b, sizeof(b));  EQ(b, "UTC-5:30");
    tzFromOffsetMinutes(0, b, sizeof(b));    EQ(b, "UTC+0");
    tzFromOffsetMinutes(-300, b, sizeof(b)); EQ(b, "UTC+5");
    tzFromOffsetMinutes(345, b, sizeof(b));  EQ(b, "UTC-5:45");
    tzFromOffsetMinutes(-210, b, sizeof(b)); EQ(b, "UTC+3:30");
    tzFromOffsetMinutes(9999, b, sizeof(b)); EQ(b, "UTC+0");
}

static void testBattery() {
    CHECK(batteryPercentFromMv(0) == -1);           // floating / no battery
    CHECK(batteryPercentFromMv(1500) == -1);
    CHECK(batteryPercentFromMv(2999) == -1);
    CHECK(batteryPercentFromMv(5000) == -1);        // nonsense high reading
    CHECK(batteryPercentFromMv(3000) == 0);
    CHECK(batteryPercentFromMv(3300) == 0);
    CHECK(batteryPercentFromMv(4200) == 100);
    CHECK(batteryPercentFromMv(4400) == 100);
    CHECK(batteryPercentFromMv(3870) == 50);
    int last = -1;
    for (int mv = 3000; mv <= 4500; mv += 5) {      // monotonic
        int p = batteryPercentFromMv(mv);
        CHECK(p >= last && p >= 0 && p <= 100);
        last = p;
    }
}

static void testDebounce() {
    // a real press: steady LOW for 30 ms with the loop sampling every ms
    Debouncer d;
    int changes = 0;
    for (uint32_t t = 0; t < 40; t++) changes += d.update(true, t, 30, 3);
    CHECK(changes == 1 && d.stable);
    for (uint32_t t = 40; t < 80; t++) changes += d.update(false, t, 30, 3);
    CHECK(changes == 2 && !d.stable);

    // phantom: two noisy LOW samples on both sides of a 40 ms loop stall must not count
    Debouncer p;
    CHECK(!p.update(true, 0, 30, 3));
    CHECK(!p.update(true, 40, 30, 3));             // 40 ms "held", but only 2 samples
    CHECK(!p.update(false, 41, 30, 3));
    CHECK(!p.stable);

    // a press seen across a stall is still accepted once enough samples agree
    Debouncer s;
    CHECK(!s.update(true, 0, 30, 3));
    CHECK(!s.update(true, 40, 30, 3));
    CHECK(s.update(true, 41, 30, 3) && s.stable);

    // bouncing contacts restart the count
    Debouncer b;
    bool seq[] = {true, false, true, false, true};
    for (int i = 0; i < 5; i++) CHECK(!b.update(seq[i], (uint32_t)i * 2, 30, 3));
    CHECK(!b.stable);

    // millis() wrap-around
    Debouncer w;
    uint32_t t0 = 0xFFFFFFF0u;
    for (uint32_t i = 0; i < 40; i++) w.update(true, t0 + i, 30, 3);
    CHECK(w.stable);

    // start state (a button held at boot)
    Debouncer h(true, 5);
    CHECK(h.stable);
    CHECK(!h.update(true, 6, 30, 3));
}

static void testDirtyTiles() {
    const int W = 128, PAGES = 8;
    static uint8_t cur[W * PAGES], shadow[W * PAGES];
    struct Span { int page, tx, tw; };
    std::vector<Span> spans;
    auto rec = [&](int page, int tx, int tw) { spans.push_back({page, tx, tw}); };

    memset(cur, 0, sizeof(cur)); memset(shadow, 0, sizeof(shadow));
    CHECK(diffTiles(cur, shadow, W, PAGES, rec) == 0);   // nothing changed: nothing sent
    CHECK(spans.empty());

    cur[0] = 1;                                          // page 0, column 0 -> tile 0
    cur[3 * W + 70] = 0x80;                              // page 3, column 70 -> tile 8
    cur[3 * W + 100] = 0x01;                             // page 3, column 100 -> tile 12
    CHECK(diffTiles(cur, shadow, W, PAGES, rec) == 2);
    CHECK(spans.size() == 2);
    if (spans.size() == 2) {
        CHECK(spans[0].page == 0 && spans[0].tx == 0 && spans[0].tw == 1);
        CHECK(spans[1].page == 3 && spans[1].tx == 8 && spans[1].tw == 5);   // tiles 8..12
    }
    CHECK(memcmp(cur, shadow, sizeof(cur)) == 0);        // shadow now matches
    spans.clear();
    CHECK(diffTiles(cur, shadow, W, PAGES, rec) == 0);   // second time: nothing

    cur[7 * W + 127] ^= 0xFF;                            // last tile of the last page
    CHECK(diffTiles(cur, shadow, W, PAGES, rec) == 1);
    CHECK(spans.size() == 1 && spans[0].page == 7 && spans[0].tx == 15 && spans[0].tw == 1);

    spans.clear();                                       // everything changed: 8 full rows
    for (int i = 0; i < W * PAGES; i++) cur[i] = (uint8_t)~shadow[i];
    CHECK(diffTiles(cur, shadow, W, PAGES, rec) == 8);
    bool full = spans.size() == 8;
    for (auto& sp : spans) full = full && sp.tx == 0 && sp.tw == 16;
    CHECK(full);
}

static void testConfig() {
    // regression: a 0 ms USB serial timeout froze the whole loop when nobody read the port
    CHECK(SERIAL_TX_TIMEOUT_MS > 0);
    CHECK(SERIAL_TX_TIMEOUT_MS + 10 < FRAME_MS + 17);   // one worst-case wait stays under 50 ms per loop
    CHECK(FRAME_MS < FRAME_MS_SLEEPING);
}

static void testProtocolTypes() {
    CHECK(msgTypeFromName("clear") == MsgType::Clear);          // 2.3.1: clear all notifications
    CHECK(msgTypeFromName("ota_nonce") == MsgType::OtaNonce);   // 2.5.0: updates and calls
    CHECK(msgTypeFromName("ota_begin") == MsgType::OtaBegin);
    CHECK(msgTypeFromName("ota_data") == MsgType::OtaData);
    CHECK(msgTypeFromName("ota_end") == MsgType::OtaEnd);
    CHECK(msgTypeFromName("ota_abort") == MsgType::OtaAbort);
    CHECK(msgTypeFromName("ota_pass") == MsgType::OtaPass);
    CHECK(msgTypeFromName("call") == MsgType::Call);
    CHECK(msgTypeFromName("hello") == MsgType::Hello);
    CHECK(msgTypeFromName("notify") == MsgType::Notify);
    CHECK(msgTypeFromName("set") == MsgType::Set);
    CHECK(msgTypeFromName("wifi_setup") == MsgType::WifiSetup);
    CHECK(msgTypeFromName("power_off") == MsgType::PowerOff);
    CHECK(msgTypeFromName("ptt") == MsgType::NoAudio);           // DeskBuddy v2 voice messages
    CHECK(msgTypeFromName("think") == MsgType::NoAudio);
    CHECK(msgTypeFromName("say_start") == MsgType::NoAudio);
    CHECK(msgTypeFromName("Clear") == MsgType::Unknown);         // exact names only
    CHECK(msgTypeFromName("") == MsgType::Unknown);
    CHECK(msgTypeFromName(nullptr) == MsgType::Unknown);
    CHECK(msgTypeFromName("bogus") == MsgType::Unknown);
    // every known name maps back to itself
    for (int i = 0; i < (int)MsgType::Unknown; i++) {
        const char* n = msgTypeName((MsgType)i);
        CHECK(n && msgTypeFromName(n) == (MsgType)i);
    }
}

static std::string hexOf(const uint8_t* b, size_t n) { std::string s(2 * n, '?'); hexEncode(b, n, &s[0]); return s; }

static std::string sha(const std::string& m) {
    Sha256 s;
    s.update(m.data(), m.size());
    uint8_t out[32];
    s.finish(out);
    return hexOf(out, 32);
}

static void testSha256() {
    // FIPS 180-4 examples
    EQ(sha(""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    EQ(sha("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    EQ(sha("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"),
       "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1");
    EQ(sha(std::string(1000000, 'a')), "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
    // fed in odd pieces: same result (the image arrives in 1 KB chunks)
    std::string msg(3000, 'q');
    for (size_t i = 0; i < msg.size(); i++) msg[i] = (char)(i * 7);
    Sha256 s;
    for (size_t off = 0, step = 1; off < msg.size(); off += step, step = step * 3 % 97 + 1) {
        s.update(msg.data() + off, std::min(step, msg.size() - off));
    }
    uint8_t out[32];
    s.finish(out);
    EQ(hexOf(out, 32), sha(msg));
    EQ(sha("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");   // reusable after finish

    // RFC 4231 test cases 1, 2 and 6 (key longer than a block)
    auto hmac = [](const std::string& key, const std::string& m) {
        HmacSha256 h((const uint8_t*)key.data(), key.size());
        h.update(m.data(), m.size());
        uint8_t o[32];
        h.finish(o);
        return hexOf(o, 32);
    };
    EQ(hmac(std::string(20, '\x0b'), "Hi There"), "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7");
    EQ(hmac("Jefe", "what do ya want for nothing?"), "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
    EQ(hmac(std::string(131, '\xaa'), "Test Using Larger Than Block-Size Key - Hash Key First"),
       "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54");
    uint8_t a[4] = {1, 2, 3, 4}, b[4] = {1, 2, 3, 4};
    CHECK(equalBytes(a, b, 4));
    b[3] = 5;
    CHECK(!equalBytes(a, b, 4));
}

static void testCodec() {
    uint8_t out[8];
    CHECK(hexDecode("00ff10Ab", out, 4));
    CHECK(out[0] == 0 && out[1] == 255 && out[2] == 16 && out[3] == 0xab);
    CHECK(!hexDecode("00ff10A", out, 4));            // too short
    CHECK(!hexDecode("00ff10Abcc", out, 4));         // too long
    CHECK(!hexDecode("00fg10ab", out, 4));           // not hex
    CHECK(!hexDecode(nullptr, out, 4));
    EQ(hexOf(out, 4), "00ff10ab");

    auto b64 = [](const char* s, size_t cap = 64) {
        uint8_t o[64];
        int n = base64Decode(s, strlen(s), o, cap);
        return n < 0 ? std::string("ERR") : std::string((const char*)o, (size_t)n);
    };
    EQ(b64(""), "");                                  // RFC 4648 vectors
    EQ(b64("Zg=="), "f");
    EQ(b64("Zm8="), "fo");
    EQ(b64("Zm9v"), "foo");
    EQ(b64("Zm9vYg=="), "foob");
    EQ(b64("Zm9vYmE="), "fooba");
    EQ(b64("Zm9vYmFy"), "foobar");
    EQ(b64("Zm9vYg"), "foob");                        // padding left out: fine
    EQ(b64("+/+/"), std::string("\xfb\xff\xbf", 3));
    EQ(b64("Zm9v YmFy"), "ERR");                      // no spaces
    EQ(b64("Zm9vY"), "ERR");                          // impossible length
    EQ(b64("Zh=="), "ERR");                           // non-zero leftover bits
    EQ(b64("Zm9vYmFy", 5), "ERR");                    // more than fits
    CHECK(base64Decode(nullptr, 0, out, 8) == -1);
}

// The update flow against a fake flash.
struct FakeHal : OtaHal {
    bool beginOk = true, writeOk = true, endOk = true, saveOk = true;
    uint32_t begun = 0;
    std::string written;
    int ended = 0, aborted = 0, saves = 0;
    bool keySet = false;
    uint8_t key[OTA_KEY_LEN] = {0};
    bool begin(uint32_t size) override { begun = size; written.clear(); return beginOk; }
    bool write(const uint8_t* d, size_t n) override { if (!writeOk) return false; written.append((const char*)d, n); return true; }
    bool end() override { ended++; return endOk; }
    void abort() override { aborted++; }
    bool saveKey(const uint8_t* k) override {
        if (!saveOk) return false;
        saves++;
        keySet = k != nullptr;
        if (k) memcpy(key, k, OTA_KEY_LEN);
        return true;
    }
};

static const uint8_t NONCE[OTA_NONCE_LEN] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15};

static std::string b64enc(const std::string& in) {
    static const char T[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    for (size_t i = 0; i < in.size(); i += 3) {
        uint32_t v = (uint8_t)in[i] << 16;
        if (i + 1 < in.size()) v |= (uint8_t)in[i + 1] << 8;
        if (i + 2 < in.size()) v |= (uint8_t)in[i + 2];
        out += T[v >> 18 & 63];
        out += T[v >> 12 & 63];
        out += i + 1 < in.size() ? T[v >> 6 & 63] : '=';
        out += i + 2 < in.size() ? T[v & 63] : '=';
    }
    return out;
}

static std::string proofFor(const char* password, const char* purpose, const std::string& detail) {
    uint8_t k[OTA_KEY_LEN], p[32];
    otaKeyFromPassword(password, k);
    otaProof(k, NONCE, purpose, detail.c_str(), p);
    return hexOf(p, 32);
}

static void testOtaCrypto() {
    // the same numbers are in the app's OtaCryptoTest: the phone and DeskBuddy must agree
    uint8_t k[OTA_KEY_LEN];
    otaKeyFromPassword("deskbuddy", k);
    EQ(hexOf(k, 32), "05dd5680fdbca13dc03653ea432914e9cc28f8af416d8e6d263233dfd6ce0d0b");
    std::string img = sha("hello image");
    EQ(img, "84d8fd5280a5162aaf5c5d9aeb069b2660500eabeeda58ce2bb10595827e08ad");
    EQ(proofFor("deskbuddy", "update:", img), "b025ce285f67ad287d99d0b7665f847d30c9ece8f80bfe2f1ef0442bdebad246");
}

static void testOtaUpdate() {
    FakeHal hal;
    OtaCore ota(hal, 4096);
    std::string image(2500, '\0');
    for (size_t i = 0; i < image.size(); i++) image[i] = (char)(i * 31 + 7);
    image[0] = (char)0xE9;
    std::string imgSha = sha(image);
    uint32_t now = 1000;

    // no password yet: nothing can start
    CHECK(ota.begin(2500, imgSha.c_str(), proofFor("pw12", "update:", imgSha).c_str(), now) == OtaErr::NoPassword);

    // first password: no proof, but BTN1 must confirm it
    uint8_t k[OTA_KEY_LEN];
    otaKeyFromPassword("pw12", k);
    bool saved = true;
    CHECK(ota.setPassword(hexOf(k, 32).c_str(), nullptr, now, &saved) == OtaErr::None);
    CHECK(!saved && ota.phase() == OtaPhase::ConfirmPassword && !hal.keySet);
    CHECK(ota.confirm(false, now) == OtaErr::Declined);           // BTN2: nothing saved
    CHECK(!ota.hasKey() && ota.phase() == OtaPhase::Idle);
    CHECK(ota.setPassword(hexOf(k, 32).c_str(), nullptr, now, &saved) == OtaErr::None);
    CHECK(ota.tick(now + OTA_CONFIRM_MS) == OtaErr::Timeout);     // nobody pressed anything
    CHECK(!ota.hasKey());
    CHECK(ota.setPassword("not hex", nullptr, now, &saved) == OtaErr::BadRequest);
    CHECK(ota.setPassword(hexOf(k, 32).c_str(), nullptr, now, &saved) == OtaErr::None);
    CHECK(ota.confirm(true, now) == OtaErr::None);
    CHECK(ota.hasKey() && hal.keySet && equalBytes(hal.key, k, 32));

    // the proof needs a fresh nonce, used once
    CHECK(ota.begin(2500, imgSha.c_str(), proofFor("pw12", "update:", imgSha).c_str(), now) == OtaErr::NoChallenge);
    ota.newChallenge(NONCE, now);
    CHECK(ota.begin(2500, imgSha.c_str(), proofFor("pw12", "update:", imgSha).c_str(), now + OTA_NONCE_MS + 1) ==
          OtaErr::NoChallenge);                                       // too old
    ota.newChallenge(NONCE, now);
    CHECK(ota.begin(5000, imgSha.c_str(), "", now) == OtaErr::TooBig);
    CHECK(ota.begin(0, imgSha.c_str(), "", now) == OtaErr::BadRequest);
    CHECK(ota.begin(2500, "abc", "", now) == OtaErr::BadRequest);
    // a proof for another image does not start this one
    std::string other = sha("other");
    CHECK(ota.begin(2500, imgSha.c_str(), proofFor("pw12", "update:", other).c_str(), now) == OtaErr::BadPassword);
    CHECK(ota.triesLeft() == 2);
    ota.newChallenge(NONCE, now);
    std::string proof = proofFor("pw12", "update:", imgSha);
    CHECK(ota.begin(2500, imgSha.c_str(), proof.c_str(), now) == OtaErr::None);
    CHECK(ota.triesLeft() == OTA_MAX_FAILS);                         // right password resets the count
    CHECK(ota.phase() == OtaPhase::ConfirmUpdate);
    CHECK(ota.confirmLeft(now + 1000) == OTA_CONFIRM_MS - 1000);
    ota.newChallenge(NONCE, now);
    CHECK(ota.begin(2500, imgSha.c_str(), proof.c_str(), now) == OtaErr::Busy);
    CHECK(ota.data(0, "AAAA", 4, now) == OtaErr::BadRequest);       // not before BTN1
    CHECK(ota.confirm(true, now) == OtaErr::None);
    CHECK(ota.phase() == OtaPhase::Receiving && hal.begun == 2500);

    // chunks in order; base64 of 1 KB is 1368 characters and fits a protocol line
    std::vector<std::string> parts;
    for (size_t off = 0; off < image.size(); off += OTA_CHUNK) parts.push_back(b64enc(image.substr(off, OTA_CHUNK)));
    CHECK(parts[0].size() == 1368);
    std::string line = "{\"type\":\"ota_data\",\"seq\":4294967295,\"data\":\"" + parts[0] + "\"}";
    CHECK(line.size() + 1 < (size_t)MAX_LINE);
    for (size_t i = 0; i < parts.size(); i++) {
        CHECK(ota.data((uint32_t)i, parts[i].c_str(), parts[i].size(), now + (uint32_t)i) == OtaErr::None);
    }
    CHECK(ota.received() == 2500 && ota.percent() == 100 && hal.written == image);
    CHECK(ota.finish() == OtaErr::None);
    CHECK(ota.phase() == OtaPhase::Done && hal.ended == 1 && hal.aborted == 0);
    ota.newChallenge(NONCE, now);
    CHECK(ota.begin(2500, imgSha.c_str(), proof.c_str(), now) == OtaErr::Busy);   // restarting now
}

static OtaCore* receiving(FakeHal& hal, OtaCore& ota, const std::string& imgSha, uint32_t size, uint32_t now) {
    uint8_t k[OTA_KEY_LEN];
    otaKeyFromPassword("pw12", k);
    ota.loadKey(k);
    ota.newChallenge(NONCE, now);
    CHECK(ota.begin(size, imgSha.c_str(), proofFor("pw12", "update:", imgSha).c_str(), now) == OtaErr::None);
    CHECK(ota.confirm(true, now) == OtaErr::None);
    (void)hal;
    return &ota;
}

static void testOtaFailures() {
    std::string image(1500, 'x');
    std::string imgSha = sha(image);
    std::string c0 = b64enc(image.substr(0, 1024)), c1 = b64enc(image.substr(1024));
    {   // a lost chunk stops it, the partial image is thrown away
        FakeHal hal; OtaCore ota(hal, 4096);
        receiving(hal, ota, imgSha, 1500, 0);
        CHECK(ota.data(1, c1.c_str(), c1.size(), 1) == OtaErr::BadSeq);
        CHECK(ota.phase() == OtaPhase::Idle && hal.aborted == 1 && hal.ended == 0);
    }
    {   // garbage in a chunk
        FakeHal hal; OtaCore ota(hal, 4096);
        receiving(hal, ota, imgSha, 1500, 0);
        CHECK(ota.data(0, "!!!!", 4, 1) == OtaErr::BadData);
        CHECK(hal.aborted == 1);
    }
    {   // more bytes than announced
        FakeHal hal; OtaCore ota(hal, 4096);
        receiving(hal, ota, imgSha, 1000, 0);
        CHECK(ota.data(0, c0.c_str(), c0.size(), 1) == OtaErr::BadData);
    }
    {   // ota_end too early
        FakeHal hal; OtaCore ota(hal, 4096);
        receiving(hal, ota, imgSha, 1500, 0);
        CHECK(ota.data(0, c0.c_str(), c0.size(), 1) == OtaErr::None);
        CHECK(ota.finish() == OtaErr::Incomplete);
        CHECK(hal.aborted == 1 && hal.ended == 0);
    }
    {   // a damaged byte: the SHA-256 does not match, never made bootable
        FakeHal hal; OtaCore ota(hal, 4096);
        receiving(hal, ota, imgSha, 1500, 0);
        std::string bad = image;
        bad[1400] ^= 1;
        std::string b1 = b64enc(bad.substr(1024));
        CHECK(ota.data(0, c0.c_str(), c0.size(), 1) == OtaErr::None);
        CHECK(ota.data(1, b1.c_str(), b1.size(), 2) == OtaErr::None);
        CHECK(ota.finish() == OtaErr::BadHash);
        CHECK(hal.ended == 0 && hal.aborted == 1);
    }
    {   // the flash refuses: begin, write, end
        FakeHal hal; OtaCore ota(hal, 4096);
        uint8_t k[OTA_KEY_LEN];
        otaKeyFromPassword("pw12", k);
        ota.loadKey(k);
        ota.newChallenge(NONCE, 0);
        CHECK(ota.begin(1500, imgSha.c_str(), proofFor("pw12", "update:", imgSha).c_str(), 0) == OtaErr::None);
        hal.beginOk = false;
        CHECK(ota.confirm(true, 0) == OtaErr::Flash && ota.phase() == OtaPhase::Idle);
        hal.beginOk = true;
        receiving(hal, ota, imgSha, 1500, 0);
        hal.writeOk = false;
        CHECK(ota.data(0, c0.c_str(), c0.size(), 1) == OtaErr::Flash);
        hal.writeOk = true;
        receiving(hal, ota, imgSha, 1500, 0);
        hal.endOk = false;
        CHECK(ota.data(0, c0.c_str(), c0.size(), 1) == OtaErr::None);
        CHECK(ota.data(1, c1.c_str(), c1.size(), 1) == OtaErr::None);
        CHECK(ota.finish() == OtaErr::Flash && ota.phase() == OtaPhase::Idle);
    }
    {   // silence for 20 s, cancel, BTN2
        FakeHal hal; OtaCore ota(hal, 4096);
        receiving(hal, ota, imgSha, 1500, 100);
        CHECK(ota.tick(100 + OTA_IDLE_MS) == OtaErr::None);
        CHECK(ota.tick(100 + OTA_IDLE_MS + 1) == OtaErr::Timeout);
        CHECK(hal.aborted == 1);
        receiving(hal, ota, imgSha, 1500, 0);
        CHECK(ota.cancel() && hal.aborted == 2);
        CHECK(!ota.cancel());
        uint8_t k[OTA_KEY_LEN];
        otaKeyFromPassword("pw12", k);
        ota.newChallenge(NONCE, 0);
        CHECK(ota.begin(1500, imgSha.c_str(), proofFor("pw12", "update:", imgSha).c_str(), 0) == OtaErr::None);
        CHECK(ota.confirm(false, 0) == OtaErr::Declined && hal.begun == 1500 && ota.phase() == OtaPhase::Idle);
    }
}

static void testOtaLockout() {
    FakeHal hal;
    OtaCore ota(hal, 4096);
    uint8_t k[OTA_KEY_LEN];
    otaKeyFromPassword("right", k);
    ota.loadKey(k);
    std::string s = sha("img");
    uint32_t now = 5000;
    for (int i = 0; i < OTA_MAX_FAILS; i++) {
        ota.newChallenge(NONCE, now);
        CHECK(ota.begin(100, s.c_str(), proofFor("wrong", "update:", s).c_str(), now) == OtaErr::BadPassword);
    }
    CHECK(ota.lockedFor(now) == OTA_LOCK_MS);
    ota.newChallenge(NONCE, now + 1000);
    CHECK(ota.begin(100, s.c_str(), proofFor("right", "update:", s).c_str(), now + 1000) == OtaErr::Locked);
    bool saved;
    CHECK(ota.setPassword(hexOf(k, 32).c_str(), "00", now + 1000, &saved) == OtaErr::Locked);
    // after the minute: three new tries, and the right password works
    uint32_t later = now + OTA_LOCK_MS;
    CHECK(ota.lockedFor(later) == 0 && ota.triesLeft() == OTA_MAX_FAILS);
    ota.newChallenge(NONCE, later);
    CHECK(ota.begin(100, s.c_str(), proofFor("right", "update:", s).c_str(), later) == OtaErr::None);
    // no proof at all counts as a wrong password
    FakeHal hal2;
    OtaCore ota2(hal2, 4096);
    ota2.loadKey(k);
    ota2.newChallenge(NONCE, 0);
    CHECK(ota2.begin(100, s.c_str(), nullptr, 0) == OtaErr::BadPassword && ota2.triesLeft() == 2);
    // USB 'otapass clear' / 'otapass set' work without the old password and end a lock
    CHECK(ota2.setKeyDirect(nullptr) && !ota2.hasKey() && !hal2.keySet);
    CHECK(ota2.setKeyDirect(k) && ota2.hasKey() && ota2.triesLeft() == OTA_MAX_FAILS);
}

static void testOtaChangePassword() {
    FakeHal hal;
    OtaCore ota(hal, 4096);
    uint8_t oldK[OTA_KEY_LEN], newK[OTA_KEY_LEN], mask[32];
    otaKeyFromPassword("deskbuddy", oldK);
    otaKeyFromPassword("new pass", newK);
    ota.loadKey(oldK);
    otaProof(oldK, NONCE, "mask", "", mask);
    uint8_t enc[OTA_KEY_LEN];
    for (size_t i = 0; i < OTA_KEY_LEN; i++) enc[i] = newK[i] ^ mask[i];
    std::string encHex = hexOf(enc, 32);
    // the same numbers are in the app's OtaCryptoTest
    EQ(encHex, "592f22a6119d848699d787527d8311ced778e0c1764d8705403f0ea35da6c0c9");
    std::string proof = proofFor("deskbuddy", "pass:", encHex);
    EQ(proof, "0ae55bbf5a30104ea6ee2922c770e2c526a3ebfb38e37d53a7087efe1a4d138c");

    bool saved = false;
    ota.newChallenge(NONCE, 0);
    CHECK(ota.setPassword(encHex.c_str(), proofFor("guess", "pass:", encHex).c_str(), 0, &saved) == OtaErr::BadPassword);
    CHECK(!saved && hal.saves == 0);
    ota.newChallenge(NONCE, 0);
    CHECK(ota.setPassword(encHex.c_str(), proof.c_str(), 0, &saved) == OtaErr::None);
    CHECK(saved && hal.saves == 1 && equalBytes(hal.key, newK, 32));   // no BTN1 needed to change it
    CHECK(ota.phase() == OtaPhase::Idle);
    // the old password no longer works, the new one does
    std::string s = sha("img");
    ota.newChallenge(NONCE, 0);
    CHECK(ota.begin(100, s.c_str(), proofFor("deskbuddy", "update:", s).c_str(), 0) == OtaErr::BadPassword);
    ota.newChallenge(NONCE, 0);
    CHECK(ota.begin(100, s.c_str(), proofFor("new pass", "update:", s).c_str(), 0) == OtaErr::None);
    // flash full: reported, key unchanged
    FakeHal hal2;
    OtaCore ota2(hal2, 4096);
    ota2.loadKey(oldK);
    hal2.saveOk = false;
    ota2.newChallenge(NONCE, 0);
    CHECK(ota2.setPassword(encHex.c_str(), proof.c_str(), 0, &saved) == OtaErr::Flash);
    ota2.newChallenge(NONCE, 0);
    CHECK(ota2.begin(100, s.c_str(), proofFor("deskbuddy", "update:", s).c_str(), 0) == OtaErr::None);
    // every error has a wire code and a short screen text
    for (int e = 0; e <= (int)OtaErr::LinkLost; e++) {
        CHECK(strcmp(otaErrCode((OtaErr)e), "?") != 0);
        CHECK(strlen(otaErrText((OtaErr)e)) <= 21);
    }
}

static void testCalls() {
    CallState c;
    CHECK(c.phase() == CallPhase::None && !c.visible());
    CHECK(c.onButton(1, 0) == CallBtn::NotMine);                 // no call: buttons work as usual
    CHECK(!c.onPhone("bogus", "x", "y", "1", 0));
    CHECK(!c.onPhone(nullptr, "x", "y", "1", 0));

    // ringing, answered with BTN1, then the phone says it is active
    CHECK(c.onPhone("ringing", "Mom", "Phone", "k1", 1000));
    CHECK(c.ringing() && c.visible());
    EQ(c.name(), "Mom"); EQ(c.app(), "Phone"); EQ(c.id(), "k1");
    CHECK(c.onButton(1, 2000) == CallBtn::Answer);
    EQ(callBtnAction(CallBtn::Answer), "answer");
    CHECK(c.phase() == CallPhase::Answering);
    CHECK(c.onButton(2, 2100) == CallBtn::Consumed);              // waiting for the phone
    CHECK(c.onPhone("ringing", "Mom", "Phone", "k1", 2200));       // late repost: still answering
    CHECK(c.phase() == CallPhase::Answering);
    CHECK(c.onPhone("active", "Mom", "Phone", "k1", 3000));
    CHECK(c.phase() == CallPhase::Active && c.visible());
    CHECK(c.activeSeconds(65000) == 62);
    CHECK(c.onButton(1, 4000) == CallBtn::Consumed);              // BTN1 hides the call screen
    CHECK(!c.visible());
    CHECK(c.onButton(2, 4100) == CallBtn::NotMine);               // hidden: BTN2 is "next screen" again
    CHECK(c.onPhone("active", "Mom", "Phone", "k1", 5000));       // updates do not bring it back
    CHECK(!c.visible());
    CHECK(c.onPhone("ended", "", "", "k1", 9000));
    CHECK(c.phase() == CallPhase::Ended && c.visible());
    c.tick(9000 + CALL_ENDED_MS);
    CHECK(c.phase() == CallPhase::Ended);
    c.tick(9001 + CALL_ENDED_MS);
    CHECK(c.phase() == CallPhase::None);

    // declined with BTN2
    CHECK(c.onPhone("ringing", "", "WhatsApp", "k2", 0));
    EQ(c.name(), "Unknown");
    CHECK(c.onButton(2, 10) == CallBtn::Decline);
    EQ(callBtnAction(CallBtn::Decline), "decline");
    CHECK(c.phase() == CallPhase::Declining);
    c.tick(10 + CALL_ACTION_MS + 1);                             // phone never answered: hide anyway
    CHECK(c.phase() == CallPhase::None);

    // hang up an active call with BTN2
    CHECK(c.onPhone("active", "Bob", "Phone", "k3", 0));
    CHECK(c.onButton(2, 100) == CallBtn::HangUp);
    EQ(callBtnAction(CallBtn::HangUp), "hangup");
    CHECK(c.phase() == CallPhase::HangingUp);
    CHECK(c.onPhone("active", "Bob", "Phone", "k3", 200));        // still "hanging up..."
    CHECK(c.phase() == CallPhase::HangingUp);
    CHECK(c.onPhone("ended", "Bob", "Phone", "k3", 300));
    CHECK(c.phase() == CallPhase::Ended);
    CHECK(c.onButton(1, 400) == CallBtn::Consumed && c.phase() == CallPhase::None);

    // a ringing call nobody touches disappears after a minute without news
    CHECK(c.onPhone("ringing", "Ann", "Phone", "k4", 0));
    c.tick(CALL_RING_MS);
    CHECK(c.ringing());
    c.tick(CALL_RING_MS + 1);
    CHECK(c.phase() == CallPhase::None);

    // call waiting: another call's "ended" leaves this one alone; a new id is a new call
    CHECK(c.onPhone("active", "Ann", "Phone", "k5", 0));
    CHECK(c.onPhone("ended", "", "", "other", 10));
    CHECK(c.phase() == CallPhase::Active);
    CHECK(c.onPhone("ringing", "Zed", "Phone", "k6", 20));
    CHECK(c.ringing());
    EQ(c.name(), "Zed");
    c.clear();                                                    // the phone disconnected
    CHECK(c.phase() == CallPhase::None);
    std::string longName(80, 'n');
    CHECK(c.onPhone("ringing", longName.c_str(), longName.c_str(), longName.c_str(), 0));
    CHECK(strlen(c.name()) == CallState::NAME - 1 && strlen(c.app()) == CallState::APP - 1);
}

int main() {
    testFraming();
    testText();
    testNotifs();
    testTz();
    testBattery();
    testDebounce();
    testDirtyTiles();
    testConfig();
    testProtocolTypes();
    testSha256();
    testCodec();
    testOtaCrypto();
    testOtaUpdate();
    testOtaFailures();
    testOtaLockout();
    testOtaChangePassword();
    testCalls();
    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}

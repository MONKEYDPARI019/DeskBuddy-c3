// Unit tests for the pure logic in src/logic (runs on a PC, no board needed):
//   g++ -std=c++17 -Wall -Wextra -I../../src test_logic.cpp -o t && ./t
#include "logic/framing.h"
#include "logic/text.h"
#include "logic/notif_store.h"
#include "logic/tz.h"
#include "logic/battery_curve.h"
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
    EQ(fold("\xE0\xA4\xA8\xE0\xA4\xAE"), "??");                              // Hindi: 2 chars
    EQ(fold("\xE2\x82\xB9" "500"), "Rs500");
    EQ(fold("bad \xFF\xFE bytes \xE2\x82"), "bad ?? bytes ?");
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

int main() {
    testFraming();
    testText();
    testNotifs();
    testTz();
    testBattery();
    printf("%d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}

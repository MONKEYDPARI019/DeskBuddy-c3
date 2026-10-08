#include "ui.h"
#include "app.h"
#include "oled.h"
#include "face.h"
#include "settings.h"
#include "battery.h"
#include "buttons.h"
#include "power.h"
#include "link.h"
#include "logic/text.h"
#include <Arduino.h>
#include <time.h>

namespace {

void center(const char* s, int y) { gfx.drawStr(64 - gfx.getStrWidth(s) / 2, y, s); }

// ---- status bar: link on the left, silent / battery on the right ----------
void drawStatus() {
    gfx.setFont(u8g2_font_4x6_tf);
    const char* name = settings.link == LINK_BLE ? "BT" : "WIFI";
    gfx.drawStr(0, 6, name);
    int x = gfx.getStrWidth(name) + 4;
    if (linkClients() > 0) gfx.drawDisc(x, 3, 2);
    else                   gfx.drawCircle(x, 3, 2);

    int right = 127;
    int pct = batteryPercent();
    if (pct >= 0) {
        gfx.drawFrame(right - 14, 0, 13, 7);
        gfx.drawBox(right - 1, 2, 2, 3);
        int w = (pct * 11 + 50) / 100;
        if (w > 0) gfx.drawBox(right - 13, 1, w, 5);
        char b[12];
        snprintf(b, sizeof(b), "%d%%", pct);
        right -= 16 + gfx.getStrWidth(b);
        gfx.drawStr(right, 6, b);
        right -= 4;
    }
    if (settings.silent) {                     // small crossed-out speaker
        gfx.drawBox(right - 9, 2, 2, 3);
        gfx.drawTriangle(right - 7, 3, right - 4, 0, right - 4, 6);
        gfx.drawLine(right - 2, 1, right, 5);
        gfx.drawLine(right, 1, right - 2, 5);
    }
}

void drawClock() {
    drawStatus();
    time_t now = time(nullptr);
    if (!appTimeValid()) {
        gfx.setFont(u8g2_font_logisoso24_tf);
        center("--:--", 42);
        gfx.setFont(u8g2_font_5x8_tf);
        const char* hint = "connect the app";
        if (settings.link == LINK_WIFI) {
            LinkState s = linkState();
            hint = s == LinkState::Portal ? "join " SETUP_AP : s == LinkState::Online ? "getting the time..." : "connecting to WiFi...";
        }
        center(hint, 58);
        return;
    }
    struct tm t;
    localtime_r(&now, &t);

    char date[20];
    strftime(date, sizeof(date), "%a %d %b", &t);
    gfx.setFont(u8g2_font_6x10_tf);
    center(date, 18);

    char hhmm[8];
    int h = t.tm_hour % 12;
    snprintf(hhmm, sizeof(hhmm), "%d:%02d", h ? h : 12, t.tm_min);
    gfx.setFont(u8g2_font_logisoso28_tf);
    int tw = gfx.getStrWidth(hhmm);
    gfx.setFont(u8g2_font_6x10_tf);
    int aw = gfx.getStrWidth("AM");
    int x = 64 - (tw + 3 + aw) / 2;
    gfx.setFont(u8g2_font_logisoso28_tf);
    gfx.drawStr(x, 54, hhmm);
    gfx.setFont(u8g2_font_6x10_tf);
    gfx.drawStr(x + tw + 3, 54, t.tm_hour < 12 ? "AM" : "PM");

    gfx.drawHLine(0, 63, (t.tm_sec + 1) * 128 / 60);   // seconds bar
}

void drawMochi() {
    faceDraw();
    int unread = appUnread();
    if (unread > 0 && !appSleeping()) {               // little badge: unread messages
        char b[4];
        snprintf(b, sizeof(b), "%d", unread > 9 ? 9 : unread);
        gfx.setFont(u8g2_font_5x8_tf);
        gfx.setDrawColor(1);
        gfx.drawRBox(117, 0, 11, 10, 3);
        gfx.setDrawColor(0);
        gfx.drawStr(120, 8, b);
        gfx.setDrawColor(1);
    }
}

// ---- notification screen with word wrap and slow auto-scroll -------------
constexpr int WRAP_W = 25;            // 5x8 font: 25 characters per line
constexpr int MAX_ROWS = 8;
constexpr int VISIBLE = 3;
char rows[MAX_ROWS][WRAP_W + 1];
int rowCount = 0;
const Notification* wrapped = nullptr;
uint32_t wrappedAt = 0;               // receivedMs of the wrapped one (identity)
uint32_t scrollStart = 0;

void drawNotify() {
    const auto& store = appNotifs();
    gfx.setFont(u8g2_font_6x10_tf);
    gfx.drawStr(0, 9, "INBOX");
    gfx.drawHLine(0, 11, 128);
    if (store.count() == 0) {
        gfx.setFont(u8g2_font_5x8_tf);
        center("No notifications yet", 36);
        gfx.setFont(u8g2_font_4x6_tf);
        center("BTN2: next screen", 60);
        return;
    }
    char pos[24];
    snprintf(pos, sizeof(pos), "%d/%d", store.selected() + 1, store.count());
    gfx.setFont(u8g2_font_5x8_tf);
    gfx.drawStr(128 - gfx.getStrWidth(pos), 9, pos);

    const Notification* n = store.current();
    if (n != wrapped || n->receivedMs != wrappedAt) {          // new one: wrap it once
        wrapped = n;
        wrappedAt = n->receivedMs;
        rowCount = wrapText(n->body, WRAP_W, &rows[0][0], MAX_ROWS);
        scrollStart = millis();
    }

    gfx.setFont(u8g2_font_6x10_tf);
    gfx.drawStr(0, 22, n->app);
    gfx.setFont(u8g2_font_5x8_tf);
    gfx.drawStr(0, 32, n->title);
    gfx.drawHLine(0, 35, 128);

    // more than 3 lines: pause 2 s, scroll one line every 1.2 s, pause at the end, repeat
    int first = 0;
    if (rowCount > VISIBLE) {
        int steps = rowCount - VISIBLE;
        uint32_t cycle = 2000 + steps * 1200 + 2000;
        uint32_t t = (millis() - scrollStart) % cycle;
        if (t > 2000) first = (t - 2000) / 1200;
        if (first > steps) first = steps;
    }
    for (int i = 0; i < VISIBLE && first + i < rowCount; i++) gfx.drawStr(0, 45 + i * 9, rows[first + i]);
}

void drawPopup(const Notification* n) {
    gfx.setDrawColor(0);
    gfx.drawBox(0, 40, 128, 24);
    gfx.setDrawColor(1);
    gfx.drawRFrame(0, 40, 128, 24, 3);
    gfx.setFont(u8g2_font_5x8_tf);
    char line[64];
    snprintf(line, sizeof(line), "%s: %s", n->app, n->title);
    line[25] = '\0';                                // 25 characters fit
    gfx.drawStr(4, 50, line);
    gfx.setFont(u8g2_font_4x6_tf);
    char body[31];
    strlcpy(body, n->body, sizeof(body));
    gfx.drawStr(4, 59, body);
}

void drawMessage(const char* title, const char* sub) {
    gfx.setDrawColor(0);
    gfx.drawBox(6, 14, 116, 36);
    gfx.setDrawColor(1);
    gfx.drawRFrame(6, 14, 116, 36, 4);
    gfx.setFont(u8g2_font_7x14B_tf);
    center(title, 30);
    gfx.setFont(u8g2_font_5x8_tf);
    center(sub, 43);
}

void drawPowerHold() {
    if (!powerSupported()) return;
    uint32_t held = buttonHeldMs(1);
    if (held < POWER_CANCEL_MS) return;            // shorter holds are clicks / silent toggle
    uint32_t pct = held >= POWER_HOLD_MS ? 100 : held * 100 / POWER_HOLD_MS;
    gfx.setDrawColor(0);
    gfx.drawBox(8, 16, 112, 32);
    gfx.setDrawColor(1);
    gfx.drawRFrame(8, 16, 112, 32, 4);
    gfx.setFont(u8g2_font_6x10_tf);
    center("Power off...", 30);
    gfx.drawFrame(16, 36, 96, 7);
    gfx.drawBox(18, 38, 92 * pct / 100, 3);
}

}  // namespace

void uiSplash(const char* title, const char* sub) {
    gfx.clearBuffer();
    gfx.setFont(u8g2_font_7x14B_tf);
    center(title, 28);
    gfx.setFont(u8g2_font_6x10_tf);
    center(sub, 46);
    oledSend();
}

void uiOtaProgress(int pct) {
    gfx.clearBuffer();
    gfx.setFont(u8g2_font_7x14B_tf);
    center(pct < 0 ? "OTA FAILED" : "OTA UPDATE", 22);
    if (pct >= 0) {
        gfx.setFont(u8g2_font_5x8_tf);
        center(pct >= 100 ? "done, restarting" : "do not unplug", 38);
        gfx.drawFrame(10, 46, 108, 10);
        gfx.drawBox(12, 48, 104 * pct / 100, 6);
    }
    oledSend();
}

void uiRender() {
    gfx.clearBuffer();
    gfx.setDrawColor(1);
    switch (appScreen()) {
        case Screen::Clock:  drawClock(); break;
        case Screen::Mochi:  drawMochi(); break;
        case Screen::Notify: drawNotify(); break;
        default: break;
    }
    const Notification* n;
    if (appPopup(&n)) drawPopup(n);
    const char *t, *s;
    if (appMessageActive(&t, &s)) drawMessage(t, s);
    drawPowerHold();
    oledSend();
}

void uiTestPattern() {
    gfx.clearBuffer();
    gfx.drawFrame(0, 0, 128, 64);
    gfx.setFont(u8g2_font_7x14B_tf);
    center("OLED TEST", 20);
    gfx.drawBox(10, 30, 40, 24);
    gfx.drawDisc(88, 42, 12);
    oledSend();
}

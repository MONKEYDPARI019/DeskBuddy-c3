#include "cli.h"
#include "app.h"
#include "settings.h"
#include "face.h"
#include "oled.h"
#include "ui.h"
#include "leds.h"
#include "buzzer.h"
#include "battery.h"
#include "power.h"
#include "buttons.h"
#include "link.h"
#include "protocol.h"
#include <Arduino.h>
#include <sys/time.h>
#include <esp_system.h>

static char line[MAX_LINE];
static size_t len = 0;

static const char* resetReason() {
    switch (esp_reset_reason()) {
        case ESP_RST_POWERON:   return "power on";
        case ESP_RST_SW:        return "restart";
        case ESP_RST_PANIC:     return "CRASH (panic)";
        case ESP_RST_INT_WDT:   return "CRASH (interrupt watchdog)";
        case ESP_RST_TASK_WDT:  return "CRASH (task watchdog)";
        case ESP_RST_WDT:       return "watchdog";
        case ESP_RST_DEEPSLEEP: return "woke from deep sleep";
        case ESP_RST_BROWNOUT:  return "BROWNOUT (power dipped)";
        default:                return "other";
    }
}

static void help() {
    Serial.print(
        "\n--- DeskBuddy C3 ---\n"
        "status                 overview (link, OLED, time, memory)\n"
        "get                    all settings\n"
        "set <key> <value>      change + save a setting (see 'get')\n"
        "defaults               factory settings\n"
        "link wifi|ble          switch radio (restarts)\n"
        "screen clock|mochi|notify|next\n"
        "face <name>            happy love star wink dizzy angry sad sleepy\n"
        "                       surprised smug nervous cat sleeping cute default sleep\n"
        "notify <text>          fake a notification\n"
        "sound <name>           hello bye screen notify mood happy sad surprised purr\n"
        "                       link error silent_on silent_off low_battery\n"
        "time <unix seconds>    set the clock by hand\n"
        "test oled|leds|buzzer|buttons|battery\n"
        "i2c                    scan the I2C bus (OLED = 0x3C)\n"
        "oled reinit            send the OLED init sequence again\n"
        "press 1|2 [ms]         press a button in software\n"
        "state                  the JSON the app receives\n"
        "app <json>             handle one message as if the app sent it\n"
        "wifi forget            erase the saved WiFi network\n"
        "off                    power off (battery build)\n"
        "reboot\n\n");
}

static void status() {
    time_t now = time(nullptr);
    struct tm t;
    localtime_r(&now, &t);
    char ts[24];
    strftime(ts, sizeof(ts), "%Y-%m-%d %H:%M:%S", &t);
    Serial.printf("\n%s %s (%s build)\n", FW_NAME, FW_VERSION, FEATURE_BATTERY ? "battery" : "USB");
    Serial.printf("link     %s, %s, %d app(s), %s\n", linkName(settings.link), linkStateName(), linkClients(), linkAddress().c_str());
    if (oledPresent()) Serial.printf("oled     OK at 0x%02X\n", oledAddress());
    else               Serial.println("oled     NOT FOUND (type 'i2c')");
    Serial.printf("time     %s %s\n", appTimeValid() ? ts : "not set", settings.tz);
    Serial.printf("screen   %s, face %s/%s%s\n", screenName(appScreen()), faceStateName(faceGetState()),
                  faceMoodName(faceGetMood()), appSleeping() ? " (asleep)" : "");
    Serial.printf("notifs   %d, %d unread\n", appNotifs().count(), appUnread());
    if (FEATURE_BATTERY) Serial.printf("battery  %d %%, %d mV (raw %d mV)\n", batteryPercent(), batteryMv(), batteryRawMv());
    Serial.printf("memory   %u free, lowest %u\n", (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMinFreeHeap());
    Serial.printf("uptime   %lu s, last reset: %s\n\n", (unsigned long)(millis() / 1000), resetReason());
}

static void printReply(const char* json) { Serial.printf("[reply] %s\n", json); }

static void testButtons() {
    Serial.println("press BTN1 / BTN2 for 10 s...");
    bool l1 = false, l2 = false;
    for (uint32_t end = millis() + 10000; millis() < end; delay(10)) {
        bool a = buttonDown(1), b = buttonDown(2);
        if (a != l1) Serial.printf("BTN1 %s\n", a ? "down" : "up");
        if (b != l2) Serial.printf("BTN2 %s\n", b ? "down" : "up");
        l1 = a; l2 = b;
    }
    Serial.println("done");
}

void cliRun(const char* in) {
    char cmd[16] = "", a1[48] = "", a2[64] = "";
    if (sscanf(in, "%15s %47s %63[^\n]", cmd, a1, a2) < 1) return;
    const char* rest = in + strlen(cmd);
    while (*rest == ' ') rest++;

    if (!strcmp(cmd, "help") || !strcmp(cmd, "?")) help();
    else if (!strcmp(cmd, "status")) status();
    else if (!strcmp(cmd, "get")) settingsPrint();
    else if (!strcmp(cmd, "set")) {
        if (!strcmp(a1, "link")) { uint8_t m; if (linkFromName(a2, &m)) appSwitchLink(m); else Serial.println("link wifi|ble"); return; }
        if (settingsSet(a1, a2)) { settingsSave(); appSettingsChanged(); Serial.printf("%s = %s\n", a1, a2); }
        else Serial.println("unknown setting or bad value (see 'get')");
    }
    else if (!strcmp(cmd, "defaults")) { uint8_t l = settings.link; settingsDefaults(); settings.link = l; settingsSave(); appSettingsChanged(); Serial.println("defaults restored (link kept)"); }
    else if (!strcmp(cmd, "link")) {
        uint8_t m;
        if (!linkFromName(a1, &m)) Serial.println("link wifi|ble");
        else if (m == settings.link) Serial.printf("already %s\n", linkName(m));
        else appSwitchLink(m);
    }
    else if (!strcmp(cmd, "screen")) {
        Screen s;
        if (!*a1 || !strcmp(a1, "next")) appNextScreen();
        else if (screenFromName(a1, &s)) appSetScreen(s);
        else Serial.println("screen clock|mochi|notify|next");
    }
    else if (!strcmp(cmd, "face")) { if (!appFace(a1)) Serial.println("unknown face"); }
    else if (!strcmp(cmd, "notify")) appNotify("CLI", "Test", *rest ? rest : "Hello from the serial monitor!");
    else if (!strcmp(cmd, "sound")) { if (!buzzerPlayName(a1, true)) Serial.println("unknown sound"); }
    else if (!strcmp(cmd, "time")) appSetClock(atoll(a1), nullptr, false, 0);
    else if (!strcmp(cmd, "i2c")) oledScan(true);
    else if (!strcmp(cmd, "oled")) { if (!strcmp(a1, "reinit")) oledReinit(); else Serial.println("oled reinit"); }
    else if (!strcmp(cmd, "press")) {
        int b = atoi(a1);
        if (b == 1 || b == 2) buttonSimulate(b, *a2 ? atol(a2) : 100);
        else Serial.println("press 1|2 [ms]");
    }
    else if (!strcmp(cmd, "state")) { char buf[512]; protocolState(buf, sizeof(buf)); Serial.println(buf); }
    else if (!strcmp(cmd, "app")) protocolHandle(rest, printReply);
    else if (!strcmp(cmd, "test")) {
        if (!strcmp(a1, "oled")) { uiTestPattern(); delay(2000); Serial.println(oledPresent() ? "pattern shown for 2 s" : "OLED not found"); }
        else if (!strcmp(a1, "leds")) { ledsTest(); Serial.println("red, yellow, green, all"); }
        else if (!strcmp(a1, "buzzer")) {
            for (uint16_t f = 500; f <= 4000; f += 500) { buzzerTone(f, 120); while (buzzerBusy()) { buzzerUpdate(); delay(2); } }
            Serial.println("500 Hz -> 4 kHz");
        }
        else if (!strcmp(a1, "buttons")) testButtons();
        else if (!strcmp(a1, "battery")) {
            if (!FEATURE_BATTERY) Serial.println("USB build: battery code is off (use env c3-battery)");
            else Serial.printf("raw %d mV, filtered %d mV, %d %%\n", batteryRawMv(), batteryMv(), batteryPercent());
        }
        else Serial.println("test oled|leds|buzzer|buttons|battery");
    }
    else if (!strcmp(cmd, "wifi") && !strcmp(a1, "forget")) { linkForgetWifi(); Serial.println("WiFi forgotten: the setup portal opens next time in WiFi mode"); }
    else if (!strcmp(cmd, "off")) { if (!appPowerOff("serial")) Serial.println("power off needs the battery build (env c3-battery)"); }
    else if (!strcmp(cmd, "reboot")) { linkShutdown(); delay(100); ESP.restart(); }
    else Serial.printf("unknown command '%s' (type help)\n", cmd);
}

void cliService() {
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\r') continue;
        if (c == '\n') {
            line[len] = '\0';
            if (len) cliRun(line);
            len = 0;
        } else if (len < sizeof(line) - 1) {
            line[len++] = c;
        }
    }
}

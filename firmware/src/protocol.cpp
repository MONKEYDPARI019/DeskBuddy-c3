#include "protocol.h"
#include "app.h"
#include "face.h"
#include "settings.h"
#include "battery.h"
#include "link.h"
#include <ArduinoJson.h>
#include <Arduino.h>

static void error(ReplyFn reply, const char* msg) {
    char buf[96];
    snprintf(buf, sizeof(buf), "{\"type\":\"error\",\"msg\":\"%s\"}", msg);
    reply(buf);
}

size_t protocolHello(char* buf, size_t n) {
    JsonDocument d;
    d["type"]   = "hello";
    d["device"] = FW_NAME;
    d["model"]  = "c3";
    d["fw"]     = FW_VERSION;
    d["link"]   = linkName(settings.link);
    d["mic"]    = false;
    JsonArray s = d["screens"].to<JsonArray>();
    for (int i = 0; i < (int)Screen::Count; i++) s.add(screenName((Screen)i));
    return serializeJson(d, buf, n);
}

size_t protocolState(char* buf, size_t n) {
    JsonDocument d;
    d["type"]     = "state";
    d["model"]    = "c3";
    d["fw"]       = FW_VERSION;
    d["face"]     = faceStateName(faceGetState());
    d["mood"]     = faceMoodName(faceGetMood());
    d["shown"]    = faceMoodName(faceShownMood());
    d["screen"]   = screenName(appScreen());
    d["unread"]   = appUnread();
    d["notifs"]   = appNotifs().count();
    d["silent"]   = settings.silent;
    d["volume"]   = settings.volume;
    d["bright"]   = settings.brightness;
    d["sleep"]    = settings.sleepSec;
    d["auto_off"] = settings.autoOffMin;
    d["leds"]     = settings.leds;
    d["link"]     = linkName(settings.link);
    d["bat"]      = batteryPercent();
    d["bat_mv"]   = batteryMv();
    d["mic"]      = false;
    d["rssi"]     = linkRssi();
    d["ip"]       = linkAddress();
    d["time_ok"]  = appTimeValid();
    d["uptime"]   = millis() / 1000;
    return serializeJson(d, buf, n);
}

void protocolButton(char* buf, size_t n, int btn, const char* action) {
    snprintf(buf, n, "{\"type\":\"button\",\"btn\":%d,\"action\":\"%s\"}", btn, action);
}

// "value" may arrive as a string, a number or a bool
static void valueToString(JsonVariantConst v, char* out, size_t n) {
    if (v.is<const char*>())  strlcpy(out, v.as<const char*>(), n);
    else if (v.is<bool>())    strlcpy(out, v.as<bool>() ? "1" : "0", n);
    else if (v.is<long>())    snprintf(out, n, "%ld", v.as<long>());
    else if (v.is<float>())   snprintf(out, n, "%ld", (long)lroundf(v.as<float>()));
    else                      out[0] = '\0';
}

static void handleSet(JsonDocument& d, ReplyFn reply) {
    const char* key = d["key"] | "";
    char val[48];
    valueToString(d["value"], val, sizeof(val));

    if (!strcmp(key, "link")) {
        uint8_t m;
        if (!linkFromName(val, &m)) { error(reply, "link must be wifi or ble"); return; }
        if (m == settings.link) {                     // already on it: nothing restarts
            char st[512];
            protocolState(st, sizeof(st));
            reply(st);
            return;
        }
        char buf[96];
        snprintf(buf, sizeof(buf), "{\"type\":\"link_switch\",\"link\":\"%s\",\"restart_ms\":1500}", linkName(m));
        reply(buf);
        appSwitchLink(m);
        return;
    }
    if (!strcmp(key, "owm_city")) return;             // weather is a DeskBuddy v2 feature: ignore quietly
    if (!settingsSet(key, val)) { error(reply, "unknown setting or bad value"); return; }
    if (d["save"] | true) settingsSave();
    appSettingsChanged();
}

void protocolHandle(const char* line, ReplyFn reply) {
    JsonDocument d;
    if (deserializeJson(d, line)) { error(reply, "bad json"); return; }
    const char* type = d["type"] | "";
    char buf[512];

    if (!strcmp(type, "hello")) {
        protocolHello(buf, sizeof(buf));  reply(buf);
        protocolState(buf, sizeof(buf));  reply(buf);
    } else if (!strcmp(type, "ping")) {
        reply("{\"type\":\"pong\"}");
    } else if (!strcmp(type, "get")) {
        protocolState(buf, sizeof(buf));
        reply(buf);
    } else if (!strcmp(type, "time")) {
        bool hasTzMin = d["tz_min"].is<int>();
        appSetClock(d["epoch"] | 0LL, d["tz"] | (const char*)nullptr, hasTzMin, d["tz_min"] | 0);
    } else if (!strcmp(type, "notify")) {
        appNotify(d["app"] | "Phone", d["title"] | "Notification", d["body"] | "");
    } else if (!strcmp(type, "face")) {
        if (!appFace(d["name"] | "")) error(reply, "unknown face");
    } else if (!strcmp(type, "screen")) {
        const char* name = d["name"] | "next";
        Screen s;
        if (!strcmp(name, "next")) appNextScreen();
        else if (screenFromName(name, &s)) appSetScreen(s);
        else error(reply, "unknown screen");
    } else if (!strcmp(type, "sound")) {
        if (!appSound(d["name"] | "")) error(reply, "unknown sound");
    } else if (!strcmp(type, "set")) {
        handleSet(d, reply);
    } else if (!strcmp(type, "power_off")) {
        if (!appPowerOff("app")) error(reply, "power off needs the battery build");
    } else if (!strcmp(type, "ptt") || !strcmp(type, "think") || !strncmp(type, "say_", 4)) {
        error(reply, "no microphone or speaker on DeskBuddy C3");
    } else {
        error(reply, "unknown type");
    }
}

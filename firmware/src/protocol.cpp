#include "protocol.h"
#include "app.h"
#include "face.h"
#include "settings.h"
#include "battery.h"
#include "link.h"
#include "logic/protocol_types.h"
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
    char buf[512];

    switch (msgTypeFromName(d["type"] | "")) {
        case MsgType::Hello:
            protocolHello(buf, sizeof(buf));  reply(buf);
            protocolState(buf, sizeof(buf));  reply(buf);
            break;
        case MsgType::Ping:
            reply("{\"type\":\"pong\"}");
            break;
        case MsgType::Get:
            protocolState(buf, sizeof(buf));
            reply(buf);
            break;
        case MsgType::Time: {
            bool hasTzMin = d["tz_min"].is<int>();
            appSetClock(d["epoch"] | 0LL, d["tz"] | (const char*)nullptr, hasTzMin, d["tz_min"] | 0);
            break;
        }
        case MsgType::Notify:
            appNotify(d["app"] | "Phone", d["title"] | "Notification", d["body"] | "");
            break;
        case MsgType::Face:
            if (!appFace(d["name"] | "")) error(reply, "unknown face");
            break;
        case MsgType::Screen: {
            const char* name = d["name"] | "next";
            Screen s;
            if (!strcmp(name, "next")) appNextScreen();
            else if (screenFromName(name, &s)) appSetScreen(s);
            else error(reply, "unknown screen");
            break;
        }
        case MsgType::Sound:
            if (!appSound(d["name"] | "")) error(reply, "unknown sound");
            break;
        case MsgType::Set:
            handleSet(d, reply);
            break;
        case MsgType::WifiSetup:
            reply("{\"type\":\"wifi_setup\",\"ap\":\"" SETUP_AP "\",\"restart_ms\":1500}");
            appWifiSetup();
            break;
        case MsgType::Clear:
            // exactly what a long BTN2 press does; the new state goes back at once, so the
            // app sees unread 0 without waiting for the next periodic "state"
            appClearAll();
            protocolState(buf, sizeof(buf));
            reply(buf);
            break;
        case MsgType::PowerOff:
            if (!appPowerOff("app")) error(reply, "power off needs the battery build");
            break;
        case MsgType::NoAudio:
            error(reply, "no microphone or speaker on DeskBuddy C3");
            break;
        case MsgType::Unknown:
            error(reply, "unknown type");
            break;
    }
}

#include "settings.h"
#include <Arduino.h>
#include <Preferences.h>

Settings settings;
static Settings saved;                     // what is in flash right now
static const char* NS = "dbc3";

static const Settings DEFAULTS = {
    "UTC-5:30",  // tz (India; the app overwrites it with the phone's zone)
    LINK_BLE,    // Bluetooth by default: works anywhere, no WiFi setup
    false,       // silent
    200,         // brightness
    70,          // volume
    true,        // leds
    120,         // sleepSec
    0,           // autoOffMin
    0,           // batOffsetMv
    true,        // httpEnabled
    80,          // httpPort
    81,          // wsPort
};

const char* linkName(uint8_t mode) { return mode == LINK_WIFI ? "wifi" : "ble"; }

bool linkFromName(const char* n, uint8_t* out) {
    if (!n) return false;
    if (!strcasecmp(n, "wifi")) { *out = LINK_WIFI; return true; }
    if (!strcasecmp(n, "ble") || !strcasecmp(n, "bt") || !strcasecmp(n, "bluetooth")) { *out = LINK_BLE; return true; }
    return false;
}

void settingsDefaults() { settings = DEFAULTS; }

void settingsLoad() {
    settings = DEFAULTS;
    Preferences p;
    if (p.begin(NS, true)) {               // read-only; fails (harmlessly) on first boot
        p.getString("tz", settings.tz, sizeof(settings.tz));
        settings.link        = p.getUChar("link", settings.link);
        settings.silent      = p.getBool("silent", settings.silent);
        settings.brightness  = p.getUChar("bright", settings.brightness);
        settings.volume      = p.getUChar("vol", settings.volume);
        settings.leds        = p.getBool("leds", settings.leds);
        settings.sleepSec    = p.getUShort("sleep", settings.sleepSec);
        settings.autoOffMin  = p.getUShort("autooff", settings.autoOffMin);
        settings.batOffsetMv = p.getShort("batoff", settings.batOffsetMv);
        settings.httpEnabled = p.getBool("http", settings.httpEnabled);
        settings.httpPort    = p.getUShort("httpport", settings.httpPort);
        settings.wsPort      = p.getUShort("wsport", settings.wsPort);
        p.end();
        Serial.println("[Settings] loaded");
    } else {
        Serial.println("[Settings] first boot, using defaults");
    }
    if (settings.link > LINK_BLE) settings.link = LINK_BLE;
    if (settings.volume > 100) settings.volume = 100;
    saved = settings;
}

bool settingsSave() {
    if (memcmp(&saved, &settings, sizeof(Settings)) == 0) return false;   // nothing changed
    Preferences p;
    if (!p.begin(NS, false)) { Serial.println("[Settings] NVS open failed"); return false; }
    p.putString("tz", settings.tz);
    p.putUChar("link", settings.link);
    p.putBool("silent", settings.silent);
    p.putUChar("bright", settings.brightness);
    p.putUChar("vol", settings.volume);
    p.putBool("leds", settings.leds);
    p.putUShort("sleep", settings.sleepSec);
    p.putUShort("autooff", settings.autoOffMin);
    p.putShort("batoff", settings.batOffsetMv);
    p.putBool("http", settings.httpEnabled);
    p.putUShort("httpport", settings.httpPort);
    p.putUShort("wsport", settings.wsPort);
    p.end();
    saved = settings;
    Serial.println("[Settings] saved");
    return true;
}

static bool parseBool(const char* v, bool* out) {
    if (!strcasecmp(v, "1") || !strcasecmp(v, "true") || !strcasecmp(v, "on") || !strcasecmp(v, "yes")) { *out = true; return true; }
    if (!strcasecmp(v, "0") || !strcasecmp(v, "false") || !strcasecmp(v, "off") || !strcasecmp(v, "no")) { *out = false; return true; }
    return false;
}

static bool parseInt(const char* v, long lo, long hi, long* out) {
    char* end;
    long x = strtol(v, &end, 10);
    if (end == v || *end != '\0' || x < lo || x > hi) return false;
    *out = x;
    return true;
}

bool settingsSet(const char* key, const char* v) {
    if (!key || !v) return false;
    long x;
    bool b;
    if (!strcmp(key, "tz")) {
        if (!*v || strlen(v) >= sizeof(settings.tz)) return false;
        strlcpy(settings.tz, v, sizeof(settings.tz));
    } else if (!strcmp(key, "link")) {
        uint8_t m;
        if (!linkFromName(v, &m)) return false;
        settings.link = m;
    } else if (!strcmp(key, "silent")) {
        if (!parseBool(v, &b)) return false;
        settings.silent = b;
    } else if (!strcmp(key, "brightness") || !strcmp(key, "bright")) {
        if (!parseInt(v, 0, 255, &x)) return false;
        settings.brightness = (uint8_t)x;
    } else if (!strcmp(key, "volume")) {
        if (!parseInt(v, 0, 100, &x)) return false;
        settings.volume = (uint8_t)x;
    } else if (!strcmp(key, "leds")) {
        if (!parseBool(v, &b)) return false;
        settings.leds = b;
    } else if (!strcmp(key, "sleep_sec") || !strcmp(key, "sleep")) {
        if (!parseInt(v, 0, 65535, &x)) return false;
        settings.sleepSec = (uint16_t)x;
    } else if (!strcmp(key, "auto_off")) {
        if (!parseInt(v, 0, 1440, &x)) return false;
        settings.autoOffMin = (uint16_t)x;
    } else if (!strcmp(key, "bat_off")) {
        if (!parseInt(v, -500, 500, &x)) return false;
        settings.batOffsetMv = (int16_t)x;
    } else if (!strcmp(key, "http_en")) {
        if (!parseBool(v, &b)) return false;
        settings.httpEnabled = b;
    } else if (!strcmp(key, "http_port")) {
        if (!parseInt(v, 1, 65535, &x)) return false;
        settings.httpPort = (uint16_t)x;
    } else if (!strcmp(key, "ws_port")) {
        if (!parseInt(v, 1, 65535, &x)) return false;
        settings.wsPort = (uint16_t)x;
    } else {
        return false;
    }
    return true;
}

void settingsPrint() {
    Serial.printf("tz          %s\n", settings.tz);
    Serial.printf("link        %s\n", linkName(settings.link));
    Serial.printf("silent      %d\n", settings.silent);
    Serial.printf("brightness  %u\n", settings.brightness);
    Serial.printf("volume      %u\n", settings.volume);
    Serial.printf("leds        %d\n", settings.leds);
    Serial.printf("sleep_sec   %u\n", settings.sleepSec);
    Serial.printf("auto_off    %u   (battery build only)\n", settings.autoOffMin);
    Serial.printf("bat_off     %d   (battery build only)\n", settings.batOffsetMv);
    Serial.printf("http_en     %d\n", settings.httpEnabled);
    Serial.printf("http_port   %u\n", settings.httpPort);
    Serial.printf("ws_port     %u\n", settings.wsPort);
}

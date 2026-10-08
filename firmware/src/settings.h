#pragma once
// User settings, stored in flash (NVS). Saved only when something changed.

#include <stdint.h>
#include <stddef.h>

enum LinkMode : uint8_t { LINK_WIFI = 0, LINK_BLE = 1 };

struct Settings {
    char     tz[40];          // POSIX TZ, e.g. "UTC-5:30" (the app sends it on connect)
    uint8_t  link;            // LinkMode (applied after a restart)
    bool     silent;          // no sounds
    uint8_t  brightness;      // OLED contrast 0-255
    uint8_t  volume;          // buzzer 0-100
    bool     leds;            // status LEDs on/off
    uint16_t sleepSec;        // Mochi sleeps + screen dims after this idle time (0 = never)
    uint16_t autoOffMin;      // battery build: power off after this idle time (0 = never)
    int16_t  batOffsetMv;     // battery reading calibration
    bool     httpEnabled;     // WiFi mode: GET /notify
    uint16_t httpPort;
    uint16_t wsPort;          // WiFi mode WebSocket port (the app uses 81)
};

extern Settings settings;

void settingsLoad();
bool settingsSave();                                  // true if something was written
void settingsDefaults();
bool settingsSet(const char* key, const char* value); // false: unknown key / bad value
void settingsPrint();

const char* linkName(uint8_t mode);
bool        linkFromName(const char* name, uint8_t* out);

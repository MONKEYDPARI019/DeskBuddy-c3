#pragma once
// DeskBuddy C3: pins, constants and feature switches. The ONLY place pins live.

#include <stdint.h>

#define FW_NAME     "DeskBuddy C3"
#define FW_VERSION  "c3-2.0.0"
#define HOSTNAME    "deskbuddy-c3"          // WiFi mode: deskbuddy-c3.local (mDNS, OTA)
#define BLE_NAME    "DeskBuddy-C3"          // Bluetooth name
#define SETUP_AP    "DeskBuddy_C3_Setup"    // WiFi setup portal

// Battery features (battery icon, low-battery warning, auto power-off, 3 s
// power button). Off in the USB build; the "c3-battery" environment in
// platformio.ini turns it on. With it off, GPIO0 is never read, so a floating
// pin can never switch the device off.
#ifndef FEATURE_BATTERY
#define FEATURE_BATTERY 0
#endif

// ---------------------------------------------------------------------------
// Pins (ESP32-C3 Super Mini)
// Keep away from: GPIO 2/8/9 (boot strapping, 8 = blue LED, 9 = BOOT button),
//                 18/19 (USB), 21 (serial TX).
// ---------------------------------------------------------------------------
constexpr int PIN_BAT_ADC = 0;    // battery through 2 x 220k divider (battery build only)
constexpr int PIN_BTN1    = 1;    // to GND. GPIO 0-5 only: it wakes the C3 from deep sleep
constexpr int PIN_LED_RED = 3;    // silent mode / low battery
constexpr int PIN_LED_YEL = 4;    // unread notifications
constexpr int PIN_LED_GRN = 5;    // app link
constexpr int PIN_SDA     = 6;    // OLED
constexpr int PIN_SCL     = 7;    // OLED
constexpr int PIN_BUZZER  = 10;   // passive buzzer through ~220 ohm
constexpr int PIN_BTN2    = 20;   // to GND

// ---------------------------------------------------------------------------
// Timing
// ---------------------------------------------------------------------------
constexpr uint32_t FRAME_MS          = 33;      // ~30 fps
constexpr uint32_t FRAME_MS_SLEEPING = 100;
constexpr uint32_t OLED_CHECK_MS     = 3000;    // re-probe the OLED (loose wire recovery)
constexpr uint32_t STATE_PUSH_MS     = 15000;   // periodic "state" to the app
constexpr uint32_t POWER_HOLD_MS     = 3000;    // BTN1 hold to power off / on
constexpr uint32_t LONG_PRESS_MS     = 800;
constexpr uint32_t POWER_CANCEL_MS   = 1500;    // battery build: BTN1 held longer = power-off gesture
constexpr uint32_t POPUP_MS          = 4000;    // notification popup on other screens

constexpr int  MAX_NOTIFS   = 8;
constexpr int  MAX_LINE     = 1536;             // longest JSON line from the app (emoji/Hindi text is long in UTF-8)
constexpr float BAT_DIVIDER = 2.0f;

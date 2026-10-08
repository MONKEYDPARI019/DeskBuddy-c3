#include "leds.h"
#include "config.h"
#include <Arduino.h>

static const int PINS[3] = {PIN_LED_RED, PIN_LED_YEL, PIN_LED_GRN};
static LedPattern pattern[3] = {LedPattern::Off, LedPattern::Off, LedPattern::Off};
static bool state[3] = {false, false, false};

static void write(int i, bool on) {
    if (state[i] == on) return;
    state[i] = on;
    digitalWrite(PINS[i], on ? HIGH : LOW);
}

void ledsBegin() {
    for (int i = 0; i < 3; i++) {
        pinMode(PINS[i], OUTPUT);
        digitalWrite(PINS[i], LOW);
    }
}

void ledsSet(Led led, LedPattern p) { pattern[(int)led] = p; }

void ledsUpdate(bool enabled) {
    uint32_t t = millis();
    for (int i = 0; i < 3; i++) {
        bool on = false;
        if (enabled) {
            switch (pattern[i]) {
                case LedPattern::Off:       on = false; break;
                case LedPattern::On:        on = true; break;
                case LedPattern::BlinkFast: on = (t / 150) % 2; break;
                case LedPattern::BlinkSlow: on = (t / 600) % 2; break;
                case LedPattern::Heartbeat: on = (t % 2000) < 60; break;   // short flash every 2 s
            }
        }
        write(i, on);
    }
}

void ledsTest() {
    for (int i = 0; i < 3; i++) { write(i, true); delay(400); write(i, false); }
    for (int i = 0; i < 3; i++) write(i, true);
    delay(400);
    for (int i = 0; i < 3; i++) write(i, false);
}

void ledsAllOff() { for (int i = 0; i < 3; i++) write(i, false); }

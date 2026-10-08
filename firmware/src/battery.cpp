#include "battery.h"
#include "config.h"

#if FEATURE_BATTERY
#include "settings.h"
#include "logic/battery_curve.h"
#include <Arduino.h>

static float filtered = -1;
static int raw = -1;
static uint8_t goodRun = 0;          // consecutive plausible readings
static bool valid = false;
static uint32_t lastSample = 0;
static uint32_t lowSince = 0;

constexpr int EMPTY_MV = 3350;
constexpr uint32_t EMPTY_HOLD_MS = 30000;

void batteryBegin() {
    analogSetPinAttenuation(PIN_BAT_ADC, ADC_11db);
    pinMode(PIN_BAT_ADC, INPUT);
}

void batteryUpdate() {
    if (millis() - lastSample < 500) return;
    lastSample = millis();
    uint32_t sum = 0;
    for (int i = 0; i < 8; i++) sum += analogReadMilliVolts(PIN_BAT_ADC);
    raw = (int)(sum / 8 * BAT_DIVIDER) + settings.batOffsetMv;

    // To START trusting the pin it must read like a real cell (3.0-4.5 V) for 3 s.
    // Once trusted, a sagging, nearly empty cell (down to 1 V) still counts, so it
    // ends with a clean power-off instead of a brownout. Only clearly bogus values
    // (unplugged, floating) make us forget it.
    bool sane = valid ? (raw >= 1000 && raw <= BATTERY_MAX_VALID_MV) : batteryMvPlausible(raw);
    if (sane) {
        if (goodRun < 255) goodRun++;
        filtered = filtered < 0 ? raw : filtered * 0.9f + raw * 0.1f;
        if (goodRun >= 6) valid = true;
    } else {
        goodRun = 0;
        valid = false;
        filtered = -1;
        lowSince = 0;
    }

    if (valid && filtered < EMPTY_MV) {
        if (!lowSince) lowSince = millis();
    } else {
        lowSince = 0;
    }
}

int  batteryMv()      { return valid ? (int)filtered : -1; }
int  batteryPercent() { return valid ? batteryPercentFromMv(max((int)filtered, BATTERY_MIN_VALID_MV)) : -1; }
bool batteryLow()     { int p = batteryPercent(); return p >= 0 && p <= 10; }
bool batteryEmpty()   { return valid && lowSince && millis() - lowSince >= EMPTY_HOLD_MS; }
int  batteryRawMv()   { return raw; }

#else   // USB build: no battery

void batteryBegin() {}
void batteryUpdate() {}
int  batteryMv()      { return -1; }
int  batteryPercent() { return -1; }
bool batteryLow()     { return false; }
bool batteryEmpty()   { return false; }
int  batteryRawMv()   { return -1; }

#endif

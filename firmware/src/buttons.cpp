#include "buttons.h"
#include "config.h"
#include <Arduino.h>

namespace {

constexpr uint32_t DEBOUNCE_MS = 30;

struct Button {
    int pin;
    bool stable = false;         // debounced "down"
    bool lastRaw = false;
    uint32_t rawSince = 0;
    uint32_t downAt = 0;
    bool powerFired = false;
    uint32_t simUntil = 0;       // software press active until this time

    bool raw() const {
        if (simUntil && (int32_t)(simUntil - millis()) > 0) return true;
        return digitalRead(pin) == LOW;
    }
};

Button b[2] = {{PIN_BTN1}, {PIN_BTN2}};

BtnEvent update(Button& k, bool isBtn1) {
    uint32_t now = millis();
    bool r = k.raw();
    if (k.simUntil && (int32_t)(k.simUntil - now) <= 0) k.simUntil = 0;
    if (r != k.lastRaw) { k.lastRaw = r; k.rawSince = now; }
    if (r == k.stable || now - k.rawSince < DEBOUNCE_MS) {
        // no change; check the power hold while BTN1 is down
        if (isBtn1 && k.stable && !k.powerFired && now - k.downAt >= POWER_HOLD_MS) {
            k.powerFired = true;
#if FEATURE_BATTERY
            return BtnEvent::Power;
#endif
        }
        return BtnEvent::None;
    }
    k.stable = r;
    if (r) {                                   // pressed
        k.downAt = now;
        k.powerFired = false;
        return BtnEvent::None;
    }
    uint32_t held = now - k.downAt;            // released
    if (k.powerFired) return BtnEvent::None;   // already handled as power (or ignored)
#if FEATURE_BATTERY
    // BTN1 held past POWER_CANCEL_MS shows "Power off..."; letting go then cancels
    if (isBtn1 && held >= POWER_CANCEL_MS) return BtnEvent::None;
#endif
    return held >= LONG_PRESS_MS ? BtnEvent::Long : BtnEvent::Click;
}

}  // namespace

void buttonsBegin() {
    for (auto& k : b) {
        pinMode(k.pin, INPUT_PULLUP);
        k.lastRaw = k.stable = k.raw();       // a button held at boot does not "click"
        k.rawSince = k.downAt = millis();
        k.powerFired = k.stable;              // and does not trigger power off either
    }
}

ButtonPress buttonsPoll() {
    for (uint8_t i = 0; i < 2; i++) {
        BtnEvent e = update(b[i], i == 0);
        if (e != BtnEvent::None) return {(uint8_t)(i + 1), e};
    }
    return {0, BtnEvent::None};
}

bool buttonDown(uint8_t btn) {
    if (btn < 1 || btn > 2) return false;
    return b[btn - 1].raw();
}

uint32_t buttonHeldMs(uint8_t btn) {
    if (btn < 1 || btn > 2) return 0;
    const Button& k = b[btn - 1];
    return k.stable && !k.powerFired ? millis() - k.downAt : 0;
}

void buttonSimulate(uint8_t btn, uint32_t ms) {
    if (btn < 1 || btn > 2) return;
    b[btn - 1].simUntil = millis() + (ms ? ms : 1);
}

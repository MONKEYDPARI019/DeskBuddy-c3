#pragma once
// Button debouncing (pure C++, unit-tested on a PC).
//
// A new level is accepted only when it has lasted `ms` milliseconds AND at
// least `minSamples` reads in a row agree. Time alone is not enough: when the
// main loop stalls (a full OLED frame, a WiFi call), two noise spikes read on
// both sides of the stall looked like a 30 ms press (a phantom click).

#include <stdint.h>

struct Debouncer {
    bool stable = false;       // debounced level (true = pressed)
    bool last = false;         // last raw read
    uint32_t since = 0;        // when `last` started
    uint8_t agree = 0;         // reads in a row that saw `last`

    Debouncer() = default;
    Debouncer(bool level, uint32_t now) : stable(level), last(level), since(now), agree(255) {}

    // Feed one raw read. Returns true when the debounced level changes.
    bool update(bool raw, uint32_t now, uint32_t ms, uint8_t minSamples) {
        if (raw != last) {
            last = raw;
            since = now;
            agree = 1;
        } else if (agree < 255) {
            agree++;
        }
        if (raw == stable || now - since < ms || agree < minSamples) return false;
        stable = raw;
        return true;
    }
};

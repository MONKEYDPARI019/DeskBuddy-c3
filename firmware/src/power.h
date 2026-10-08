#pragma once
// Soft power switch (battery build): deep sleep, woken by holding BTN1.

#include <stdint.h>

bool powerSupported();               // false in the USB build
void powerWakeCheck();               // first thing in setup(): after a wake, BTN1 must be held 3 s
bool powerWokeByButton();
void powerOff(const char* reason);   // shows "Bye", then deep sleep. Does not return.

#pragma once
// Three status LEDs with simple patterns, driven from the main loop.

#include <stdint.h>

enum class Led : uint8_t { Red = 0, Yellow, Green };
enum class LedPattern : uint8_t { Off, On, BlinkFast, BlinkSlow, Heartbeat };

void ledsBegin();
void ledsSet(Led led, LedPattern p);
void ledsUpdate(bool enabled);           // call every loop; enabled = settings.leds
void ledsTest();                         // blocking walk through all LEDs (CLI)
void ledsAllOff();                       // before deep sleep

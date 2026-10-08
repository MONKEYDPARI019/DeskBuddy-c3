#pragma once
// Passive buzzer: short melodies played in the background from the main loop
// (no task, no delay). LEDC PWM on PIN_BUZZER.

#include <stdint.h>

enum class Sound : uint8_t {
    None = 0, Hello, Bye, Screen, Notify, Mood, Happy, Sad, Surprised, Purr,
    Link, Error, SilentOn, SilentOff, LowBattery, Count
};

void        buzzerBegin();
void        buzzerUpdate();                         // call every loop
void        buzzerPlay(Sound s, bool force = false); // force = even in silent mode
bool        buzzerPlayName(const char* name, bool force = false);
void        buzzerTone(uint16_t hz, uint16_t ms);   // single tone (CLI test)
const char* buzzerName(Sound s);
bool        buzzerBusy();
void        buzzerOff();                            // stop and release the pin

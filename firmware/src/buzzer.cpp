#include "buzzer.h"
#include "config.h"
#include "settings.h"
#include <Arduino.h>
#include <driver/gpio.h>

// Silence during flashing and restarts
// -------------------------------------
// While no sound plays, the pin is driven LOW and *held* (gpio_hold_en). The
// hold lives in the always-on part of the chip, so it survives the resets that
// flashing does: esptool restarts the C3 into its ROM bootloader, this code
// stops running, and without the hold GPIO10 would be left undriven and the
// buzzer could sound for the whole upload. The hold keeps it LOW (silent) until
// the next firmware starts and buzzerBegin() takes the pin back. The hold is
// released only while a sound plays (LEDC needs the pin then).

namespace {

struct Note { uint16_t hz; uint16_t ms; };     // hz 0 = rest

const Note S_HELLO[]      = {{659, 80}, {0, 20}, {784, 80}, {0, 20}, {1047, 140}};
const Note S_BYE[]        = {{1047, 90}, {0, 20}, {784, 90}, {0, 20}, {523, 180}};
const Note S_SCREEN[]     = {{1568, 25}};
const Note S_NOTIFY[]     = {{1760, 60}, {0, 30}, {2349, 100}};
const Note S_MOOD[]       = {{1976, 35}, {0, 15}, {2637, 55}};
const Note S_HAPPY[]      = {{1568, 50}, {1976, 50}, {2349, 80}};
const Note S_SAD[]        = {{1319, 110}, {1175, 110}, {1047, 180}};
const Note S_SURPRISED[]  = {{1760, 40}, {3520, 80}};
const Note S_PURR[]       = {{1047, 45}, {1109, 45}, {1175, 45}, {1245, 55}};
const Note S_LINK[]       = {{1319, 50}, {1760, 50}, {2637, 90}};
const Note S_ERROR[]      = {{622, 120}, {0, 40}, {466, 180}};
const Note S_SILENT_ON[]  = {{1760, 60}, {1319, 90}};
const Note S_SILENT_OFF[] = {{1319, 60}, {1760, 90}};
const Note S_LOW_BAT[]    = {{988, 150}, {0, 80}, {740, 250}};

struct Melody { const char* name; const Note* notes; uint8_t count; };
#define M(n, a) {n, a, (uint8_t)(sizeof(a) / sizeof(a[0]))}
const Melody MELODIES[(int)Sound::Count] = {
    {"none", nullptr, 0},
    M("hello", S_HELLO), M("bye", S_BYE), M("screen", S_SCREEN), M("notify", S_NOTIFY),
    M("mood", S_MOOD), M("happy", S_HAPPY), M("sad", S_SAD), M("surprised", S_SURPRISED),
    M("purr", S_PURR), M("link", S_LINK), M("error", S_ERROR),
    M("silent_on", S_SILENT_ON), M("silent_off", S_SILENT_OFF), M("low_battery", S_LOW_BAT),
};
#undef M

constexpr uint8_t RES_BITS = 10;
bool attached = false;           // LEDC drives the pin (only while a sound plays)
bool attachFailed = false;       // report a broken LEDC once, not on every sound

const Note* notes = nullptr;     // what is playing
uint8_t count = 0, noteIdx = 0;
uint32_t noteEnd = 0;
Note single;                     // storage for buzzerTone

// Silent: LEDC off, pin driven LOW and held there (also through resets).
void park() {
    if (attached) { ledcWrite(PIN_BUZZER, 0); ledcDetach(PIN_BUZZER); attached = false; }
    pinMode(PIN_BUZZER, OUTPUT);
    digitalWrite(PIN_BUZZER, LOW);
    gpio_hold_en((gpio_num_t)PIN_BUZZER);
}

// Ready to play: release the hold and give the pin to LEDC.
bool unpark() {
    if (attached) return true;
    pinMode(PIN_BUZZER, OUTPUT);             // known LOW level before the hold lets go
    digitalWrite(PIN_BUZZER, LOW);
    gpio_hold_dis((gpio_num_t)PIN_BUZZER);
    attached = ledcAttach(PIN_BUZZER, 2000, RES_BITS);
    if (!attached) {
        if (!attachFailed) Serial.println("[Buzzer] LEDC attach failed");
        attachFailed = true;
        park();
        return false;
    }
    ledcWrite(PIN_BUZZER, 0);
    return true;
}

void out(uint16_t hz) {
    if (!attached) return;
    if (hz == 0 || settings.volume == 0) { ledcWrite(PIN_BUZZER, 0); return; }
    ledcWriteTone(PIN_BUZZER, hz);                         // sets 50 % duty (loudest)
    uint32_t duty = (1UL << (RES_BITS - 1)) * settings.volume / 100;
    ledcWrite(PIN_BUZZER, duty);
}

void startNote() {
    out(notes[noteIdx].hz);
    noteEnd = millis() + notes[noteIdx].ms;
}

void play(const Note* n, uint8_t c) {
    if (!n || !c || !unpark()) return;
    notes = n; count = c; noteIdx = 0;
    startNote();
}

}  // namespace

// First thing in setup(): after flashing or a restart the pin is still held LOW
// from before; this keeps it LOW and silent. After power-on it drives it LOW at once.
void buzzerBegin() {
    notes = nullptr;
    park();
}

void buzzerUpdate() {
    if (!notes) return;
    if ((int32_t)(millis() - noteEnd) < 0) return;
    if (++noteIdx >= count) { notes = nullptr; park(); return; }
    startNote();
}

void buzzerPlay(Sound s, bool force) {
    if (s == Sound::None || s >= Sound::Count) return;
    if (settings.silent && !force) return;
    const Melody& m = MELODIES[(int)s];
    play(m.notes, m.count);                  // a new sound replaces the current one
}

bool buzzerPlayName(const char* name, bool force) {
    for (int i = 1; i < (int)Sound::Count; i++) {
        if (!strcasecmp(name, MELODIES[i].name)) { buzzerPlay((Sound)i, force); return true; }
    }
    return false;
}

void buzzerTone(uint16_t hz, uint16_t ms) {
    single = {hz, ms};
    play(&single, 1);
}

const char* buzzerName(Sound s) { return s < Sound::Count ? MELODIES[(int)s].name : "?"; }
bool buzzerBusy() { return notes != nullptr; }

void buzzerOff() {
    notes = nullptr;
    park();
}

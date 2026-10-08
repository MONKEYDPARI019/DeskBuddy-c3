#include "buzzer.h"
#include "config.h"
#include "settings.h"
#include <Arduino.h>

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
bool attached = false;

const Note* notes = nullptr;     // what is playing
uint8_t count = 0, noteIdx = 0;
uint32_t noteEnd = 0;
Note single;                     // storage for buzzerTone

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
    if (!attached || !n || !c) return;
    notes = n; count = c; noteIdx = 0;
    startNote();
}

}  // namespace

void buzzerBegin() {
    attached = ledcAttach(PIN_BUZZER, 2000, RES_BITS);
    if (attached) ledcWrite(PIN_BUZZER, 0);
    else Serial.println("[Buzzer] LEDC attach failed");
}

void buzzerUpdate() {
    if (!notes) return;
    if ((int32_t)(millis() - noteEnd) < 0) return;
    if (++noteIdx >= count) { notes = nullptr; out(0); return; }
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
    if (attached) { ledcWrite(PIN_BUZZER, 0); ledcDetach(PIN_BUZZER); attached = false; }
    pinMode(PIN_BUZZER, OUTPUT);
    digitalWrite(PIN_BUZZER, LOW);
}

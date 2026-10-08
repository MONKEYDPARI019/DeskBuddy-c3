#ifndef FACE_H
#define FACE_H

// Mochi's face as a state machine.
//
//   BOOT ──1.5s──> IDLE <──────────────┐
//                   │  any input        │ timeouts / app events
//                   ├──> NOTIFY ──3s────┤
//                   ├──> LISTENING ─PTT release─> THINKING ─reply─> SPEAKING ─done─┘
//                   └──> SLEEP (inactivity) ──any input──> IDLE
//
// The *state* says what Mochi is doing; the *mood* is the expression used
// while idle (chosen by BTN1, CLI or the app). States that imply an
// expression (sleep, listening...) override the mood while active.
// Everything runs in the main loop, so no locking is needed.

#include <Arduino.h>

enum FaceState : uint8_t {
    FACE_STATE_BOOT = 0,
    FACE_STATE_IDLE,
    FACE_STATE_LISTENING,
    FACE_STATE_THINKING,
    FACE_STATE_SPEAKING,
    FACE_STATE_NOTIFY,
    FACE_STATE_SLEEP,
    FACE_STATE_COUNT
};

enum FaceMood : uint8_t {
    MOOD_DEFAULT = 0,
    MOOD_HAPPY,
    MOOD_LOVE,
    MOOD_STAR,
    MOOD_WINK,
    MOOD_DIZZY,
    MOOD_ANGRY,
    MOOD_SAD,
    MOOD_SLEEPY,
    MOOD_SURPRISED,
    MOOD_SMUG,
    MOOD_NERVOUS,
    MOOD_CAT,
    MOOD_SLEEPING,
    MOOD_CUTE,
    MOOD_COUNT
};

struct Sparkle {
    int8_t x, y;
    uint8_t speed;
    bool alive;
};

struct Eye {
    float x, y, w, h;
    float targetX, targetY, targetW, targetH;
    float pupilX, pupilY, targetPupilX, targetPupilY;
    bool  blinking;
    unsigned long lastBlink, nextBlinkTime;
    void init(float _x, float _y, float _w, float _h) {
        x = _x; y = _y; w = _w; h = _h;
        targetX = _x; targetY = _y; targetW = _w; targetH = _h;
        pupilX = 0; pupilY = 0; targetPupilX = 0; targetPupilY = 0;
        blinking = false; lastBlink = 0; nextBlinkTime = 2000;
    }
};

void        faceInit();
void        faceSetState(FaceState state);
FaceState   faceGetState();
void        faceSetMood(FaceMood mood);          // sets idle expression
FaceMood    faceGetMood();                       // idle expression
FaceMood    faceShownMood();                     // what is actually drawn now
void        faceNextMood();
void        faceReact(FaceMood mood, uint32_t ms); // temporary expression, e.g. on a pat
bool        faceApplyName(const char* name);     // mood or state by name; false if unknown
const char* faceMoodName(FaceMood mood);
const char* faceStateName(FaceState state);
void        faceUpdate();                        // animation + timed transitions, call every frame
void        faceDraw();

#endif // FACE_H

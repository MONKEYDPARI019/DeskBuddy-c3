#include "face.h"
#include "oled.h"
#include <math.h>

// ===========================================================================
// Mochi v2 face
//
// Every expression is built from the same parts, so moods blend smoothly:
//   - two rounded-rect eyes (size, vertical offset, corner radius)
//   - a black pupil with a white highlight (size + gaze)
//   - eyelids: black wedges from the top, separately for the inner and outer
//     corner (angry = inner low, sad = outer low, sleepy = both)
//   - cheeks: a black ellipse from below that turns an eye into a "^" smile
// Some moods swap the eye for a shape (hearts, stars, spirals, closed arcs)
// and every mood has its own mouth and a small idle animation.
// Mood changes are hidden behind a quick blink, and the numeric eye
// parameters glide to their new targets.
// ===========================================================================

// ---------------------------------------------------------------------------
// State (only touched with the UI lock held)
// ---------------------------------------------------------------------------
static FaceState currentFaceState = FACE_STATE_BOOT;
static FaceMood  idleMood = MOOD_DEFAULT;       // expression chosen by the user
static FaceMood  currentMood = MOOD_DEFAULT;    // expression drawn this frame
static FaceMood  reactMood = MOOD_DEFAULT;
static uint32_t  reactUntil = 0;
static uint32_t  stateSince = 0;

static const uint32_t BOOT_MS     = 1500;
static const uint32_t NOTIFY_MS   = 3000;
static const uint32_t THINK_MAXMS = 20000;   // give up waiting for a reply

static const char* const MOOD_NAMES[MOOD_COUNT] = {
    "default", "happy", "love", "star", "wink", "dizzy", "angry", "sad",
    "sleepy", "surprised", "smug", "nervous", "cat", "sleeping", "cute"
};
static const char* const STATE_NAMES[FACE_STATE_COUNT] = {
    "boot", "idle", "listen", "think", "speak", "notify", "sleep"
};

// ---------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------
static const int EYE_CY   = 27;   // eye centre line
static const int EYE_LX   = 38;   // left eye centre x
static const int EYE_RX   = 90;   // right eye centre x
static const int MOUTH_Y  = 55;   // mouth centre line

enum EyeShape : uint8_t { SHAPE_EYE = 0, SHAPE_HEART, SHAPE_STAR, SHAPE_SPIRAL, SHAPE_CLOSED_HAPPY, SHAPE_CLOSED_SLEEP };
enum MouthShape : uint8_t {
    MOUTH_NONE = 0, MOUTH_SMALL, MOUTH_SMILE, MOUTH_GRIN, MOUTH_FROWN, MOUTH_FLAT,
    MOUTH_O, MOUTH_WAVY, MOUTH_SMIRK, MOUTH_CAT, MOUTH_TALK, MOUTH_TINY_O
};

// Numeric eye parameters (these glide between moods)
struct EyeP {
    float w, h;        // eye box size
    float dy;          // vertical offset from EYE_CY
    float r;           // corner radius
    float lidIn;       // 0..1 of h covered from the top at the inner corner
    float lidOut;      // 0..1 of h covered from the top at the outer corner
    float cheek;       // 0..1 of h covered from below (curved) -> "^" eyes
    float pupR;        // pupil radius (0 = no pupil)
    float pupDX, pupDY;// extra pupil offset on top of the shared gaze
};

struct Look {
    EyeP l, r;
    EyeShape shapeL, shapeR;
    MouthShape mouth;
};

static EyeP curL, curR;            // what is drawn (gliding)
static Look look;                  // target for the current mood/state

// gaze (shared by both eyes)
static float gazeX = 0, gazeY = 0, gazeTX = 0, gazeTY = 0;
static uint32_t nextSaccade = 0;

// blinking + mood-swap blink
static uint32_t nextBlink = 0, blinkStart = 0;
static bool     blinking = false;
static const uint32_t BLINK_MS = 140;
static int      swapPending = -1;       // mood waiting to be shown after the swap blink
static uint32_t swapStart = 0;
static const uint32_t SWAP_MS = 180;

static float t01(uint32_t period) { return (float)(millis() % period) / (float)period; }
static float wave(uint32_t period) { return sinf(t01(period) * 2.0f * PI); }

// ---------------------------------------------------------------------------
// Looks
// ---------------------------------------------------------------------------
static EyeP eye(float w, float h, float r, float pup) {
    EyeP e = {w, h, 0, r, 0, 0, 0, pup, 0, 0};
    return e;
}

static Look lookFor(FaceMood m, FaceState s) {
    Look k;
    k.l = k.r = eye(36, 36, 10, 7);
    k.shapeL = k.shapeR = SHAPE_EYE;
    k.mouth = MOUTH_SMALL;

    // states that have their own look win over the idle mood
    switch (s) {
        case FACE_STATE_LISTENING:
            k.l = k.r = eye(38, 40, 11, 6);
            k.l.pupDY = k.r.pupDY = -5;
            k.mouth = MOUTH_NONE;              // equaliser bars drawn instead
            return k;
        case FACE_STATE_THINKING:
            k.l = k.r = eye(36, 36, 10, 6);
            k.mouth = MOUTH_SMIRK;
            return k;
        case FACE_STATE_SPEAKING:
            k.l = k.r = eye(36, 36, 10, 7);
            k.mouth = MOUTH_TALK;
            return k;
        case FACE_STATE_NOTIFY:
            k.l = k.r = eye(36, 42, 12, 5);
            k.l.dy = k.r.dy = -2;
            k.mouth = MOUTH_O;
            return k;
        case FACE_STATE_SLEEP:
            m = MOOD_SLEEPING;
            break;
        default:
            break;
    }

    switch (m) {
        case MOOD_HAPPY:
            k.shapeL = k.shapeR = SHAPE_CLOSED_HAPPY;   // ^ ^
            k.mouth = MOUTH_GRIN;
            break;
        case MOOD_LOVE:
            k.shapeL = k.shapeR = SHAPE_HEART;
            k.mouth = MOUTH_SMILE;
            break;
        case MOOD_STAR:
            k.shapeL = k.shapeR = SHAPE_STAR;
            k.mouth = MOUTH_GRIN;
            break;
        case MOOD_WINK:
            k.shapeL = SHAPE_CLOSED_HAPPY;
            k.r.pupDX = -2;
            k.mouth = MOUTH_SMIRK;
            break;
        case MOOD_DIZZY:
            k.shapeL = k.shapeR = SHAPE_SPIRAL;
            k.mouth = MOUTH_WAVY;
            break;
        case MOOD_ANGRY:
            k.l = k.r = eye(36, 32, 8, 6);
            k.l.dy = k.r.dy = 2;
            k.l.lidIn = k.r.lidIn = 0.55f; k.l.lidOut = k.r.lidOut = 0.0f;
            k.l.pupDY = k.r.pupDY = 4;
            k.mouth = MOUTH_FROWN;
            break;
        case MOOD_SAD:
            k.l = k.r = eye(34, 32, 10, 6);
            k.l.dy = k.r.dy = 3;
            k.l.lidIn = k.r.lidIn = 0.05f; k.l.lidOut = k.r.lidOut = 0.5f;
            k.l.pupDY = k.r.pupDY = 5;
            k.mouth = MOUTH_FROWN;
            break;
        case MOOD_SLEEPY:
            k.l = k.r = eye(36, 34, 10, 6);
            k.l.lidIn = k.r.lidIn = 0.55f; k.l.lidOut = k.r.lidOut = 0.55f;
            k.l.pupDY = k.r.pupDY = 6;
            k.mouth = MOUTH_TINY_O;
            break;
        case MOOD_SURPRISED:
            k.l = k.r = eye(34, 42, 13, 5);
            k.l.dy = k.r.dy = -2;
            k.mouth = MOUTH_O;
            break;
        case MOOD_SMUG:
            k.l = k.r = eye(36, 34, 10, 6);
            k.l.lidIn = k.r.lidIn = 0.42f; k.l.lidOut = k.r.lidOut = 0.42f;
            k.l.pupDX = k.r.pupDX = 7; k.l.pupDY = k.r.pupDY = 3;
            k.mouth = MOUTH_SMIRK;
            break;
        case MOOD_NERVOUS:
            k.l = k.r = eye(30, 30, 9, 5);
            k.l.dy = k.r.dy = -1;
            k.mouth = MOUTH_WAVY;
            break;
        case MOOD_CAT:
            k.l = k.r = eye(36, 36, 18, 0);    // round eyes, slit pupil drawn separately
            k.mouth = MOUTH_CAT;
            break;
        case MOOD_SLEEPING:
            k.shapeL = k.shapeR = SHAPE_CLOSED_SLEEP;
            k.mouth = MOUTH_NONE;
            break;
        case MOOD_CUTE:
            k.l = k.r = eye(40, 40, 18, 11);
            k.mouth = MOUTH_CAT;
            break;
        default:   // MOOD_DEFAULT
            break;
    }
    return k;
}

// ---------------------------------------------------------------------------
// Drawing helpers (all in screen pixels)
// ---------------------------------------------------------------------------
static inline int ri(float v) { return (int)lroundf(v); }

// Thick quadratic curve from p0 to p2 with control point p1
static void curve(float x0, float y0, float cx, float cy, float x1, float y1, int thick) {
    const int N = 24;
    for (int i = 0; i <= N; i++) {
        float t = (float)i / N, u = 1 - t;
        float x = u * u * x0 + 2 * u * t * cx + t * t * x1;
        float y = u * u * y0 + 2 * u * t * cy + t * t * y1;
        if (thick <= 1) gfx.drawPixel(ri(x), ri(y));
        else gfx.drawBox(ri(x - thick / 2.0f), ri(y - thick / 2.0f), thick, thick);
    }
}

static void tri(float x0, float y0, float x1, float y1, float x2, float y2) {
    gfx.drawTriangle(ri(x0), ri(y0), ri(x1), ri(y1), ri(x2), ri(y2));
}

static void heart(float cx, float cy, float s) {
    // two lobes + a point; s ~ half width
    float lr = s * 0.52f;
    gfx.drawDisc(ri(cx - s * 0.47f), ri(cy - s * 0.25f), ri(lr), U8G2_DRAW_ALL);
    gfx.drawDisc(ri(cx + s * 0.47f), ri(cy - s * 0.25f), ri(lr), U8G2_DRAW_ALL);
    tri(cx - s * 0.98f, cy - s * 0.05f, cx + s * 0.98f, cy - s * 0.05f, cx, cy + s * 0.95f);
}

static void star(float cx, float cy, float R, float rot) {
    float rIn = R * 0.45f;
    float px[10], py[10];
    for (int i = 0; i < 10; i++) {
        float a = -PI / 2 + rot + i * PI / 5;
        float rr = (i % 2 == 0) ? R : rIn;
        px[i] = cx + rr * cosf(a); py[i] = cy + rr * sinf(a);
    }
    for (int i = 0; i < 10; i++) tri(cx, cy, px[i], py[i], px[(i + 1) % 10], py[(i + 1) % 10]);
}

static void spiral(float cx, float cy, float R, float rot) {
    const int N = 60;
    float turns = 2.6f;
    float lx = cx, ly = cy;
    for (int i = 1; i <= N; i++) {
        float t = (float)i / N;
        float a = rot + t * turns * 2 * PI;
        float rr = 2 + t * (R - 2);
        float x = cx + rr * cosf(a), y = cy + rr * sinf(a);
        gfx.drawLine(ri(lx), ri(ly), ri(x), ri(y));
        gfx.drawLine(ri(lx) + 1, ri(ly), ri(x) + 1, ri(y));
        lx = x; ly = y;
    }
}

static void sparkle(float cx, float cy, int s) {
    gfx.drawHLine(ri(cx) - s, ri(cy), 2 * s + 1);
    gfx.drawVLine(ri(cx), ri(cy) - s, 2 * s + 1);
}

static void drop(float cx, float cy, float s) {
    // teardrop: round bottom, pointed top
    gfx.drawDisc(ri(cx), ri(cy), ri(s), U8G2_DRAW_ALL);
    tri(cx - s, cy - 0.3f * s, cx + s, cy - 0.3f * s, cx, cy - 2.4f * s);
}

static void zee(float x, float y, int s) {
    gfx.drawHLine(ri(x), ri(y), s);
    gfx.drawLine(ri(x) + s - 1, ri(y), ri(x), ri(y) + s - 1);
    gfx.drawHLine(ri(x), ri(y) + s - 1, s);
}

// ---------------------------------------------------------------------------
// One eye
// ---------------------------------------------------------------------------
// side: -1 = left eye, +1 = right eye (inner corner faces the middle)
static void drawEye(const EyeP& p, EyeShape shape, float cx, float cy, int side, float blink) {
    float w = p.w, h = p.h;
    float x = cx - w / 2, y = cy - h / 2 + p.dy;

    switch (shape) {
        case SHAPE_HEART: {
            float s = 15.5f * (1.0f + 0.08f * wave(700));
            heart(cx, cy + 1, s);
            return;
        }
        case SHAPE_STAR:
            star(cx, cy + 1, 19, 0.18f * wave(1600));
            return;
        case SHAPE_SPIRAL:
            spiral(cx, cy + 1, 16, (side < 0 ? 1 : -1) * t01(900) * 2 * PI);
            return;
        case SHAPE_CLOSED_HAPPY:   // "^" eye
            curve(cx - 16, cy + 8, cx, cy - 16, cx + 16, cy + 8, 6);
            return;
        case SHAPE_CLOSED_SLEEP:   // relaxed "‿" eye
            curve(cx - 15, cy + 3, cx, cy + 13, cx + 15, cy + 3, 4);
            return;
        default:
            break;
    }

    // 1. eye white
    int rr = ri(min(p.r, min(w, h) / 2 - 1));
    if (rr < 1) rr = 1;
    gfx.setDrawColor(1);
    gfx.drawRBox(ri(x), ri(y), ri(w), ri(h), rr);

    // 2. pupil (black) with highlight
    if (p.pupR > 0.5f) {
        float px = cx + gazeX + p.pupDX;
        float py = y + h / 2 + gazeY + p.pupDY;
        // keep the pupil inside the eye
        float mx = w / 2 - p.pupR - 3, my = h / 2 - p.pupR - 3;
        px = constrain(px, cx - mx, cx + mx);
        py = constrain(py, y + h / 2 - my, y + h / 2 + my);
        gfx.setDrawColor(0);
        gfx.drawDisc(ri(px), ri(py), ri(p.pupR), U8G2_DRAW_ALL);
        gfx.setDrawColor(1);
        int hl = p.pupR >= 9 ? 3 : 2;
        gfx.drawDisc(ri(px - p.pupR * 0.4f), ri(py - p.pupR * 0.4f), hl, U8G2_DRAW_ALL);
        if (p.pupR >= 9) gfx.drawDisc(ri(px + p.pupR * 0.35f), ri(py + p.pupR * 0.3f), 1, U8G2_DRAW_ALL);
    }
    if (currentMood == MOOD_CAT && shape == SHAPE_EYE && currentFaceState == FACE_STATE_IDLE) {
        // vertical slit pupil
        gfx.setDrawColor(0);
        gfx.drawFilledEllipse(ri(cx + gazeX * 0.6f), ri(y + h / 2), 3, ri(h / 2 - 4), U8G2_DRAW_ALL);
        gfx.setDrawColor(1);
    }

    // 3. eyelids (black wedges from the top); blink closes them fully
    float inC = max(p.lidIn, blink), outC = max(p.lidOut, blink);
    if (inC > 0.01f || outC > 0.01f) {
        float xi = side < 0 ? x + w : x;           // inner corner x
        float xo = side < 0 ? x : x + w;           // outer corner x
        float yi = y + inC * h, yo = y + outC * h;
        gfx.setDrawColor(0);
        float top = y - 2;
        float xi2 = xi - side * 2, xo2 = xo + side * 2;   // overlap the eye edges by 2 px
        tri(xo2, top, xi2, top, xi2, yi);
        tri(xo2, top, xi2, yi, xo2, yo);
        gfx.setDrawColor(1);
        if (blink > 0.85f) {                       // fully closed: one lash line
            gfx.setDrawColor(0);
            gfx.drawBox(ri(x) - 2, ri(y) - 2, ri(w) + 4, ri(h) + 4);
            gfx.setDrawColor(1);
            gfx.drawBox(ri(x + 3), ri(y + h * 0.6f), ri(w - 6), 3);
        }
    }

    // 4. cheeks (black ellipse from below) -> "^" shaped eye
    if (p.cheek > 0.01f) {
        float cover = p.cheek * h;
        float ry = h * 0.85f;
        gfx.setDrawColor(0);
        gfx.drawFilledEllipse(ri(cx), ri(y + h + ry - cover), ri(w * 0.82f), ri(ry), U8G2_DRAW_ALL);
        gfx.setDrawColor(1);
    }
}

// ---------------------------------------------------------------------------
// Mouth + extras
// ---------------------------------------------------------------------------
static void drawMouth(MouthShape m) {
    const float cx = 64, y = MOUTH_Y;
    switch (m) {
        case MOUTH_SMALL:  curve(cx - 6, y, cx, y + 3, cx + 6, y, 2); break;
        case MOUTH_SMILE:  curve(cx - 9, y - 2, cx, y + 6, cx + 9, y - 2, 3); break;
        case MOUTH_GRIN: {                                   // open "D" smile
            gfx.drawBox(ri(cx - 10), ri(y - 3), 21, 2);
            curve(cx - 10, y - 3, cx, y + 11, cx + 10, y - 3, 3);
            for (int i = -8; i <= 8; i++) {                  // fill the inside
                float d = 1.0f - (i * i) / 81.0f;
                gfx.drawVLine(ri(cx + i), ri(y - 2), ri(1 + 7 * d));
            }
            break;
        }
        case MOUTH_FROWN:  curve(cx - 8, y + 3, cx, y - 4, cx + 8, y + 3, 3); break;
        case MOUTH_FLAT:   gfx.drawBox(ri(cx - 7), ri(y), 14, 3); break;
        case MOUTH_O:      gfx.drawDisc(ri(cx), ri(y + 1), 5, U8G2_DRAW_ALL);
                           gfx.setDrawColor(0); gfx.drawDisc(ri(cx), ri(y + 1), 2, U8G2_DRAW_ALL);
                           gfx.setDrawColor(1); break;
        case MOUTH_TINY_O: gfx.drawDisc(ri(cx), ri(y + 1), 2, U8G2_DRAW_ALL); break;
        case MOUTH_WAVY: {
            float ph = t01(500) * 2 * PI;
            for (int i = -10; i <= 10; i++) {
                float yy = y + 2.2f * sinf(i * 0.75f + ph);
                gfx.drawBox(ri(cx + i), ri(yy), 1, 2);
            }
            break;
        }
        case MOUTH_SMIRK:  curve(cx - 7, y + 1, cx + 2, y + 3, cx + 9, y - 3, 2); break;
        case MOUTH_CAT:    curve(cx - 8, y - 1, cx - 4, y + 4, cx, y - 1, 2);
                           curve(cx, y - 1, cx + 4, y + 4, cx + 8, y - 1, 2); break;
        case MOUTH_TALK: {
            float open = 2 + 7 * fabsf(sinf(millis() / 95.0f) * sinf(millis() / 230.0f));
            gfx.drawRBox(ri(cx - 7), ri(y - open / 2), 14, ri(open) + 2, 2);
            break;
        }
        default: break;
    }
}

static void drawExtras(FaceMood m, FaceState s) {
    uint32_t now = millis();
    if (s == FACE_STATE_LISTENING) {                // equaliser bars instead of a mouth
        for (int i = 0; i < 3; i++) {
            float hgt = 3 + 7 * fabsf(sinf(now / (110.0f + i * 37) + i));
            gfx.drawBox(56 + i * 7, ri(MOUTH_Y + 5 - hgt), 4, ri(hgt));
        }
        return;
    }
    if (s == FACE_STATE_THINKING) {                 // "..." building up
        int n = (now / 350) % 4;
        for (int i = 0; i < n; i++) gfx.drawDisc(100 + i * 7, 56, 1, U8G2_DRAW_ALL);
        return;
    }
    if (s == FACE_STATE_NOTIFY) {                   // bouncing "!"
        int b = ri(2 * fabsf(wave(400)));
        gfx.drawBox(62, 1 + b, 4, 7);
        gfx.drawBox(62, 10 + b, 4, 3);
        return;
    }
    if (s == FACE_STATE_SPEAKING) return;

    switch (m) {
        case MOOD_LOVE: {                            // tiny hearts floating up
            for (int i = 0; i < 2; i++) {
                float t = t01(2200 + i * 500);
                float x = i == 0 ? 8 + 3 * sinf(t * 6) : 120 + 3 * sinf(t * 6 + 1);
                heart(x, 52 - t * 44, 3);
            }
            break;
        }
        case MOOD_STAR: {                            // twinkles
            for (int i = 0; i < 3; i++) {
                if (((now / 260) + i) % 3 == 0) continue;
                const int sx[3] = {10, 117, 64}, sy[3] = {8, 12, 4};
                sparkle(sx[i], sy[i], 2);
            }
            break;
        }
        case MOOD_SAD: {                             // a tear rolls down every few seconds
            float t = t01(2600);
            if (t < 0.7f) drop(EYE_LX - 10, 44 + t * 26, 2);
            break;
        }
        case MOOD_NERVOUS: {                         // sweat drop sliding down
            float t = t01(1800);
            drop(EYE_RX + 19, 8 + t * 14, 2.2f);
            break;
        }
        case MOOD_ANGRY: {                           // steam puffs
            if ((now / 300) % 2) { gfx.drawCircle(118, 6, 2, U8G2_DRAW_ALL); gfx.drawCircle(124, 11, 1, U8G2_DRAW_ALL); }
            break;
        }
        case MOOD_CUTE: {                            // blush
            for (int i = 0; i < 3; i++) {
                gfx.drawLine(EYE_LX - 12 + i * 5, 50, EYE_LX - 10 + i * 5, 47);
                gfx.drawLine(EYE_RX - 2 + i * 5, 50, EYE_RX + i * 5, 47);
            }
            break;
        }
        case MOOD_SLEEPING: {                        // floating Zs
            for (int i = 0; i < 2; i++) {
                float t = t01(2400 + i * 300);
                zee(104 + i * 9 + t * 4, 22 - t * 18 - i * 4, 4 + i * 2);
            }
            break;
        }
        case MOOD_SLEEPY: {                          // a slow "z"
            float t = t01(3000);
            zee(110 + t * 4, 14 - t * 10, 5);
            break;
        }
        default: break;
    }
}

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------
// Expression reported as "shown" for a state (kept for the app protocol)
static FaceMood moodForState(FaceState s) {
    switch (s) {
        case FACE_STATE_LISTENING: return MOOD_SURPRISED;
        case FACE_STATE_THINKING:  return MOOD_SMUG;
        case FACE_STATE_SPEAKING:  return MOOD_HAPPY;
        case FACE_STATE_NOTIFY:    return MOOD_SURPRISED;
        case FACE_STATE_SLEEP:     return MOOD_SLEEPING;
        default:                   return MOOD_COUNT;
    }
}

void faceInit() {
    currentMood = MOOD_DEFAULT;
    look = lookFor(MOOD_DEFAULT, FACE_STATE_IDLE);
    curL = look.l; curR = look.r;
    curL.h = curR.h = 2;                 // "open your eyes" on boot
    nextBlink = millis() + 2500;
    faceSetState(FACE_STATE_BOOT);
}

void faceSetState(FaceState state) {
    if (state >= FACE_STATE_COUNT) return;
    if (state != currentFaceState) {
        Serial.printf("[Face] %s -> %s\n", STATE_NAMES[currentFaceState], STATE_NAMES[state]);
        swapStart = millis();            // blink through every state change
    }
    currentFaceState = state;
    stateSince = millis();
    reactUntil = 0;
}

FaceState faceGetState() { return currentFaceState; }
FaceMood  faceGetMood()  { return idleMood; }
FaceMood  faceShownMood(){ return currentMood; }

void faceSetMood(FaceMood mood) {
    if (mood >= MOOD_COUNT) return;
    idleMood = mood;
    if (currentFaceState != FACE_STATE_IDLE) faceSetState(FACE_STATE_IDLE);
}

void faceNextMood() {
    // skip MOOD_SLEEPING when cycling: it belongs to the SLEEP state
    FaceMood m = (FaceMood)((idleMood + 1) % MOOD_COUNT);
    if (m == MOOD_SLEEPING) m = (FaceMood)((m + 1) % MOOD_COUNT);
    faceSetMood(m);
}

void faceReact(FaceMood mood, uint32_t ms) {
    if (mood >= MOOD_COUNT) return;
    if (currentFaceState != FACE_STATE_IDLE) faceSetState(FACE_STATE_IDLE);
    reactMood = mood;
    reactUntil = millis() + ms;
}

const char* faceMoodName(FaceMood mood)    { return mood < MOOD_COUNT ? MOOD_NAMES[mood] : "?"; }
const char* faceStateName(FaceState state) { return state < FACE_STATE_COUNT ? STATE_NAMES[state] : "?"; }

bool faceApplyName(const char* name) {
    if (!name) return false;
    for (uint8_t i = 0; i < MOOD_COUNT; i++) {
        if (!strcasecmp(name, MOOD_NAMES[i])) { faceSetMood((FaceMood)i); return true; }
    }
    for (uint8_t i = 0; i < FACE_STATE_COUNT; i++) {
        if (!strcasecmp(name, STATE_NAMES[i])) { faceSetState((FaceState)i); return true; }
    }
    return false;
}

static void glide(EyeP& c, const EyeP& t, float k) {
    c.w += (t.w - c.w) * k;         c.h += (t.h - c.h) * k;
    c.dy += (t.dy - c.dy) * k;      c.r += (t.r - c.r) * k;
    c.lidIn += (t.lidIn - c.lidIn) * k;  c.lidOut += (t.lidOut - c.lidOut) * k;
    c.cheek += (t.cheek - c.cheek) * k;  c.pupR += (t.pupR - c.pupR) * k;
    c.pupDX += (t.pupDX - c.pupDX) * k;  c.pupDY += (t.pupDY - c.pupDY) * k;
}

void faceUpdate() {
    uint32_t now = millis();
    uint32_t inState = now - stateSince;

    // ---- timed transitions ----
    switch (currentFaceState) {
        case FACE_STATE_BOOT:     if (inState > BOOT_MS)     faceSetState(FACE_STATE_IDLE); break;
        case FACE_STATE_NOTIFY:   if (inState > NOTIFY_MS)   faceSetState(FACE_STATE_IDLE); break;
        case FACE_STATE_THINKING: if (inState > THINK_MAXMS) faceSetState(FACE_STATE_IDLE); break;
        default: break;
    }

    // ---- which mood should be showing ----
    FaceMood want;
    FaceMood sm = moodForState(currentFaceState);
    if (sm != MOOD_COUNT)                    want = sm;
    else if (reactUntil && now < reactUntil) want = reactMood;
    else { reactUntil = 0;                   want = idleMood; }

    if (want != currentMood && swapPending < 0) {
        swapPending = want;              // close eyes, swap at the midpoint
        swapStart = now;
    }
    if (swapPending >= 0 && now - swapStart >= SWAP_MS / 2) {
        currentMood = (FaceMood)swapPending;
        swapPending = -1;
    }
    look = lookFor(currentMood, currentFaceState);

    // ---- gaze: saccades while idle, scripted otherwise ----
    if (currentFaceState == FACE_STATE_IDLE || currentFaceState == FACE_STATE_BOOT) {
        if (now > nextSaccade) {
            const float GX[] = {0, 6, -6, 0, 0, 5, -5, 4, -4, 0};
            const float GY[] = {0, 0, 0, -4, 4, -3, -3, 3, 3, 0};
            int d = random(0, 10);
            gazeTX = GX[d]; gazeTY = GY[d];
            nextSaccade = now + random(600, 2400);
        }
        if (currentMood == MOOD_NERVOUS) { gazeTX = ((now / 140) % 2) ? 4 : -4; gazeTY = 0; }
        if (currentMood == MOOD_DIZZY || currentMood == MOOD_SLEEPING) { gazeTX = gazeTY = 0; }
    } else if (currentFaceState == FACE_STATE_THINKING) {
        gazeTX = 5 + 2 * wave(1400); gazeTY = -5;
    } else {
        gazeTX = 0; gazeTY = 0;
    }
    float gk = (currentMood == MOOD_NERVOUS) ? 0.6f : 0.35f;   // saccades are quick
    gazeX += (gazeTX - gazeX) * gk;
    gazeY += (gazeTY - gazeY) * gk;

    // ---- eye parameters glide to the target look ----
    glide(curL, look.l, 0.28f);
    glide(curR, look.r, 0.28f);

    // ---- random blinks (only for open eyes) ----
    if (!blinking && now > nextBlink) {
        blinking = true;
        blinkStart = now;
    }
    if (blinking && now - blinkStart > BLINK_MS) {
        blinking = false;
        uint32_t gap = (currentMood == MOOD_SLEEPY) ? random(900, 2200) : random(2200, 5200);
        nextBlink = now + gap;
        if (random(0, 6) == 0) nextBlink = now + 220;   // occasional double blink
    }
}

static float blinkAmount() {
    uint32_t now = millis();
    float b = 0;
    if (blinking) {
        float t = (float)(now - blinkStart) / BLINK_MS;   // 0..1
        b = t < 0.5f ? t * 2 : (1 - t) * 2;
    }
    // mood/state swap: close then reopen
    float st = (float)(now - swapStart) / SWAP_MS;
    if (st >= 0 && st < 1) b = max(b, st < 0.5f ? st * 2 : (1 - st) * 2);
    return constrain(b, 0.0f, 1.0f);
}

void faceDraw() {
    uint32_t now = millis();
    FaceMood m = currentMood;
    FaceState s = currentFaceState;

    // whole-face motion per mood
    float bob = sinf(now / 900.0f) * 1.0f;                       // breathing
    float ox = 0;
    if (s == FACE_STATE_IDLE) {
        if (m == MOOD_HAPPY || m == MOOD_STAR) bob = -2.0f * fabsf(wave(600));   // bouncy
        if (m == MOOD_SLEEPING) bob = 2.0f * sinf(now / 1600.0f);             // slow breathing
        if (m == MOOD_DIZZY) ox = 3.0f * wave(1300);                         // wobble
        if (m == MOOD_ANGRY && (now / 1500) % 3 == 0) ox = ((now / 40) % 2) ? 1 : -1;   // shaking
        if (m == MOOD_LOVE) bob = -1.5f * fabsf(wave(700));
    }
    if (s == FACE_STATE_SLEEP) bob = 2.0f * sinf(now / 1600.0f);

    float blink = blinkAmount();
    bool eyesOpenShape = look.shapeL == SHAPE_EYE || look.shapeR == SHAPE_EYE;
    // shapes (hearts, stars...) don't blink; plain eyes do
    float bl = eyesOpenShape ? blink : 0;

    // left eye: blinking a closed-arc eye makes no sense, so only plain eyes blink
    drawEye(curL, look.shapeL, EYE_LX + ox, EYE_CY + bob, -1, look.shapeL == SHAPE_EYE ? bl : 0);
    drawEye(curR, look.shapeR, EYE_RX + ox, EYE_CY + bob, +1, look.shapeR == SHAPE_EYE ? bl : 0);

    // shape eyes "squash" during a mood swap so the change still feels like a blink
    if (!eyesOpenShape && blink > 0.05f) {
        gfx.setDrawColor(0);
        int cover = ri(blink * 22);
        gfx.drawBox(0, ri(EYE_CY + bob) - 24, 128, cover);
        gfx.drawBox(0, ri(EYE_CY + bob) + 24 - cover, 128, cover);
        gfx.setDrawColor(1);
    }

    drawMouth(look.mouth);
    drawExtras(m, s);
}

#include "app.h"
#include "settings.h"
#include "face.h"
#include "oled.h"
#include "leds.h"
#include "buzzer.h"
#include "battery.h"
#include "power.h"
#include "link.h"
#include "protocol.h"
#include "ota.h"
#include "logic/text.h"
#include "logic/tz.h"
#include <Arduino.h>
#include <sys/time.h>
#include <time.h>

namespace {

const char* const SCREEN_NAMES[] = {"clock", "mochi", "notify"};

Screen screen = Screen::Mochi;          // say hello with Mochi first
Screen screenBeforeSleep = Screen::Mochi;
bool sleeping = false;
uint32_t lastActivity = 0;

NotifStore<MAX_NOTIFS> notifs;
bool popupActive = false;
uint32_t popupAt = 0;

char msgTitle[24] = "", msgSub[32] = "";
uint32_t msgUntil = 0;

bool stateDirty = true;
uint32_t dirtySince = 0;
uint32_t lastStatePush = 0;
int lastClients = 0;
bool timeAnnounced = false;

uint32_t restartAt = 0;                // link switch: restart at this time (0 = no)
bool lowBatteryWarned = false;

CallState call;                        // a phone call shown on DeskBuddy (2.5.0)
uint32_t lastRing = 0;
constexpr uint32_t RING_EVERY_MS = 2500;

void enterSleep() {
    if (sleeping) return;
    sleeping = true;
    screenBeforeSleep = screen;
    screen = Screen::Mochi;
    faceSetState(FACE_STATE_SLEEP);
    oledContrast(1);
    Serial.println("[App] Mochi fell asleep");
    appStateDirty();
}

// returns true if Mochi was asleep (that press only wakes him up)
bool wake() {
    lastActivity = millis();
    if (!sleeping) return false;
    sleeping = false;
    screen = screenBeforeSleep;
    faceSetState(FACE_STATE_IDLE);
    oledContrast(settings.brightness);
    appStateDirty();
    return true;
}

void updateLeds() {
    // red: low battery (fast blink) beats silent mode (solid)
    if (batteryLow())          ledsSet(Led::Red, LedPattern::BlinkFast);
    else if (settings.silent)  ledsSet(Led::Red, LedPattern::On);
    else                       ledsSet(Led::Red, LedPattern::Off);
    // yellow: a call ringing (fast blink), unread notifications (solid)
    if (call.ringing())          ledsSet(Led::Yellow, LedPattern::BlinkFast);
    else                         ledsSet(Led::Yellow, notifs.unread() > 0 ? LedPattern::On : LedPattern::Off);
    // green: updating (fast blink), app connected (solid), setup portal (fast blink), waiting (short flash)
    if (otaBusy())                               ledsSet(Led::Green, LedPattern::BlinkFast);
    else if (linkClients() > 0)                  ledsSet(Led::Green, LedPattern::On);
    else if (linkState() == LinkState::Portal)   ledsSet(Led::Green, LedPattern::BlinkFast);
    else                                         ledsSet(Led::Green, LedPattern::Heartbeat);
    ledsUpdate(settings.leds && !sleeping);
}

void pushState() {
    char buf[512];
    protocolState(buf, sizeof(buf));
    linkSend(buf);
    stateDirty = false;
    lastStatePush = millis();
}

}  // namespace

// ---------------------------------------------------------------------------
const char* screenName(Screen s) { return s < Screen::Count ? SCREEN_NAMES[(int)s] : "?"; }

bool screenFromName(const char* name, Screen* out) {
    if (!name) return false;
    for (int i = 0; i < (int)Screen::Count; i++) {
        if (!strcasecmp(name, SCREEN_NAMES[i])) { *out = (Screen)i; return true; }
    }
    if (!strcasecmp(name, "inbox") || !strcasecmp(name, "notifications")) { *out = Screen::Notify; return true; }
    return false;
}

void appBegin() {
    lastActivity = millis();
    faceInit();
    oledContrast(settings.brightness);
    setenv("TZ", settings.tz, 1);
    tzset();
}

void appLoop() {
    uint32_t now = millis();

    // pending restart after a link switch
    if (restartAt && (int32_t)(now - restartAt) >= 0) {
        Serial.println("[App] restarting with the new radio");
        linkShutdown();
        delay(100);
        ESP.restart();
    }

    // a call on screen or an update running: stay awake (no sleep, no auto power-off)
    call.tick(now);
    if (call.visible() || otaBusy()) lastActivity = now;
    if (call.ringing() && now - lastRing > RING_EVERY_MS) {
        lastRing = now;
        buzzerPlay(Sound::Ring);
    }

    // Mochi falls asleep when nobody touches DeskBuddy
    if (!sleeping && settings.sleepSec && now - lastActivity > settings.sleepSec * 1000UL) enterSleep();

    // battery build: auto power-off, empty battery, low warning
    if (powerSupported()) {
        if (settings.autoOffMin && now - lastActivity > settings.autoOffMin * 60000UL) appPowerOff("idle");
        if (batteryEmpty()) appPowerOff("battery empty");
        if (batteryLow() && !lowBatteryWarned) {
            lowBatteryWarned = true;
            buzzerPlay(Sound::LowBattery, true);
            appMessage("Battery low", "please charge me", 3000);
        }
        if (!batteryLow()) lowBatteryWarned = false;
    }

    // app (dis)connected
    int c = linkClients();
    if (c != lastClients) {
        if (c > lastClients) {
            buzzerPlay(Sound::Link);
            if (!sleeping) faceReact(MOOD_HAPPY, 1500);
        }
        lastClients = c;
        if (c == 0) call.clear();             // the phone is gone: it can't tell us the call ended
        appStateDirty();
    }

    // the clock became valid (phone or NTP)
    if (!timeAnnounced && appTimeValid()) { timeAnnounced = true; appStateDirty(); }

    // state to the app: soon after a change, and every 15 s
    if (c > 0) {
        if (stateDirty && now - dirtySince > 150) pushState();
        else if (now - lastStatePush > STATE_PUSH_MS) pushState();
    }

    if (popupActive && now - popupAt > POPUP_MS) popupActive = false;
    updateLeds();
}

// ---------------------------------------------------------------------------
// Buttons
//   BTN1 click: next mood (on the notification screen: next notification)
//   BTN1 long : silent mode on/off
//   BTN1 3 s  : power off (battery build)
//   BTN2 click: next screen
//   BTN2 long : clear notifications
// ---------------------------------------------------------------------------
void appButton(const ButtonPress& p) {
    const char* action = p.ev == BtnEvent::Click ? "click" : p.ev == BtnEvent::Long ? "long" : "power";
    Serial.printf("[Button] BTN%u %s\n", p.btn, action);
    char buf[80];
    protocolButton(buf, sizeof(buf), p.btn, action);
    linkSend(buf);

    if (p.ev == BtnEvent::Power) { appPowerOff("button"); return; }

    // an update question or a call on screen gets the press first (BTN1 yes/answer, BTN2 no/decline)
    if (otaButton(p)) { lastActivity = millis(); return; }
    CallBtn cb = call.onButton(p.btn, millis());
    if (cb != CallBtn::NotMine) {
        lastActivity = millis();
        if (const char* what = callBtnAction(cb)) {
            char msg[96];
            snprintf(msg, sizeof(msg), "{\"type\":\"call_action\",\"action\":\"%s\",\"id\":\"%s\"}", what, call.id());
            linkSend(msg);
            buzzerOff();                       // stop the ring at once
            buzzerPlay(Sound::Screen);
            Serial.printf("[Call] %s\n", what);
        }
        return;
    }
    if (wake()) return;                        // the first press only wakes Mochi up

    if (p.btn == 1) {
        if (p.ev == BtnEvent::Click) {
            if (screen == Screen::Notify && notifs.count() > 1) {
                notifs.next();
                buzzerPlay(Sound::Screen);
            } else {
                if (screen != Screen::Mochi) screen = Screen::Mochi;
                faceNextMood();
                buzzerPlay(Sound::Mood);
            }
        } else {
            settings.silent = !settings.silent;
            settingsSave();
            buzzerPlay(settings.silent ? Sound::SilentOn : Sound::SilentOff, true);
            appMessage(settings.silent ? "Silent on" : "Silent off", settings.silent ? "no sounds" : "sounds back on");
        }
    } else {
        if (p.ev == BtnEvent::Click) {
            appNextScreen();
            buzzerPlay(Sound::Screen);
        } else {
            appClearAll();
        }
    }
    appStateDirty();
}

// ---------------------------------------------------------------------------
void appNotify(const char* app, const char* title, const char* body) {
    char a[16], t[32], b[128];
    asciiFold(app, a, sizeof(a));
    asciiFold(title, t, sizeof(t));
    asciiFold(body, b, sizeof(b));
    wake();                                       // first: it may bring the inbox back on screen
    bool viewing = screen == Screen::Notify;
    notifs.push(a, t, b, millis(), viewing);
    Serial.printf("[Notify] %s | %s | %s\n", a, t, b);

    if (!viewing) { popupActive = true; popupAt = millis(); }
    faceSetState(FACE_STATE_NOTIFY);
    buzzerPlay(Sound::Notify);
    appStateDirty();
}

// {"type":"call",...} from the app. The id is made by the app; only safe characters are kept
// because it goes back inside a JSON string.
bool appCall(const char* state, const char* name, const char* app, const char* id) {
    char n[CallState::NAME], a[CallState::APP], k[CallState::ID];
    asciiFold(name ? name : "", n, sizeof(n));
    asciiFold(app ? app : "", a, sizeof(a));
    size_t j = 0;
    for (const char* p = id ? id : ""; *p && j < sizeof(k) - 1; p++) {
        if (isalnum((unsigned char)*p) || *p == '-' || *p == '_') k[j++] = *p;
    }
    k[j] = '\0';
    bool wasRinging = call.ringing();
    if (!call.onPhone(state, n, a, k, millis())) return false;
    if (call.ringing() && !wasRinging) {
        lastRing = 0;                          // ring at once
        Serial.printf("[Call] %s calling (%s)\n", call.name(), call.app());
    }
    if (!call.ringing() && wasRinging) buzzerOff();
    if (call.visible()) wake();
    return true;
}

void appSetScreen(Screen s) {
    if (s >= Screen::Count) return;
    wake();
    screen = s;
    if (s == Screen::Notify) { notifs.markRead(); popupActive = false; }
    appStateDirty();
}

void appNextScreen() { appSetScreen((Screen)(((int)screen + 1) % (int)Screen::Count)); }

bool appFace(const char* name) {
    if (!name || !*name) return false;
    if (!strcasecmp(name, "sleep")) {             // the app's "ZZZ" button
        lastActivity = millis();
        enterSleep();
        return true;
    }
    if (!faceApplyName(name)) return false;
    lastActivity = millis();
    if (sleeping) { sleeping = false; oledContrast(settings.brightness); }
    screen = Screen::Mochi;                       // show the new face
    appStateDirty();
    return true;
}

bool appSound(const char* name) { return buzzerPlayName(name); }

void appNextNotif()   { notifs.next(); appStateDirty(); }
void appClearNotifs() { notifs.clear(); popupActive = false; appStateDirty(); }

// A long BTN2 press, and the app's "clear" message (2.3.1): one place, so they always match.
void appClearAll() {
    wake();                                       // the app's Clear also works while Mochi sleeps
    appClearNotifs();
    appMessage("Cleared", "all notifications");
    buzzerPlay(Sound::Screen);
}

void appSetClock(long long epoch, const char* tzPosix, bool hasTzMin, int tzMin) {
    if (epoch < 1700000000LL) return;
    struct timeval tv = {(time_t)epoch, 0};
    settimeofday(&tv, nullptr);
    char tz[40] = "";
    if (tzPosix && *tzPosix) strlcpy(tz, tzPosix, sizeof(tz));
    else if (hasTzMin) tzFromOffsetMinutes(tzMin, tz, sizeof(tz));
    if (*tz && strcmp(tz, settings.tz)) {
        strlcpy(settings.tz, tz, sizeof(settings.tz));
        settingsSave();                           // only when the zone really changed
    }
    setenv("TZ", settings.tz, 1);
    tzset();
    Serial.printf("[Clock] set by the app (%s)\n", settings.tz);
    appStateDirty();
}

void appSettingsChanged() {
    oledContrast(sleeping ? 1 : settings.brightness);
    setenv("TZ", settings.tz, 1);
    tzset();
    appStateDirty();
}

void appSwitchLink(uint8_t mode) {
    if (mode == settings.link) return;
    settings.link = mode;
    settingsSave();
    Serial.printf("[App] switching to %s\n", mode == LINK_WIFI ? "WiFi" : "Bluetooth");
    appMessage("Switching to", mode == LINK_WIFI ? "WiFi" : "Bluetooth", 5000);
    buzzerPlay(Sound::Screen, true);
    restartAt = millis() + 1500;                  // let the "link_switch" reply reach the app
}

void appWifiSetup() {
    settings.link = LINK_WIFI;
    settingsSave();
    linkRequestWifiSetup();
    Serial.printf("[App] change WiFi: restarting into the setup portal '%s'\n", SETUP_AP);
    appMessage("Change WiFi", "join " SETUP_AP, 5000);
    buzzerPlay(Sound::Screen, true);
    restartAt = millis() + 1500;                  // let the reply reach the app
}

bool appPowerOff(const char* reason) {
    if (!powerSupported()) return false;
    linkShutdown();
    powerOff(reason);                             // does not return
    return true;
}

void appMessage(const char* title, const char* sub, uint32_t ms) {
    strlcpy(msgTitle, title ? title : "", sizeof(msgTitle));
    strlcpy(msgSub, sub ? sub : "", sizeof(msgSub));
    msgUntil = millis() + ms;
    if (!msgUntil) msgUntil = 1;
}

void appActivity() { wake(); }

void appStateDirty() {
    if (!stateDirty) dirtySince = millis();
    stateDirty = true;
}

// ---------------------------------------------------------------------------
Screen appScreen()   { return screen; }
bool   appSleeping() { return sleeping; }
bool   appTimeValid(){ return time(nullptr) > 1700000000; }
const NotifStore<MAX_NOTIFS>& appNotifs() { return notifs; }
int    appUnread()   { return notifs.unread(); }
bool   appRestarting() { return restartAt != 0; }
const CallState& appCallState() { return call; }

bool appPopup(const Notification** n) {
    if (!popupActive || notifs.count() == 0) return false;
    *n = notifs.at(0);
    return true;
}

bool appMessageActive(const char** title, const char** sub) {
    if (!msgUntil) return false;
    if ((int32_t)(msgUntil - millis()) <= 0) { msgUntil = 0; return false; }
    *title = msgTitle;
    *sub = msgSub;
    return true;
}

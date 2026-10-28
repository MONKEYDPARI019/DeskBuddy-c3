#pragma once
// Phone calls on DeskBuddy (2.5.0), pure C++ so it is unit-tested on a PC. The app tells
// DeskBuddy about a call ({"type":"call","state":"ringing|active|ended",...}); BTN1 answers and
// BTN2 declines, and app.cpp sends {"type":"call_action",...} back. The phone does the actual
// answering: the sound stays on the phone (DeskBuddy C3 has no microphone or speaker).

#include <stddef.h>
#include <stdint.h>
#include <string.h>

constexpr uint32_t CALL_RING_MS   = 60000;   // ringing with no news from the phone: hide it
constexpr uint32_t CALL_ACTION_MS = 8000;    // answered/declined/hung up here, phone silent: hide
constexpr uint32_t CALL_ENDED_MS  = 2000;    // "Call ended" stays this long

enum class CallPhase : uint8_t { None, Ringing, Answering, Declining, Active, HangingUp, Ended };

// What a button press meant. NotMine: the press is for the normal screens.
enum class CallBtn : uint8_t { NotMine, Consumed, Answer, Decline, HangUp };

inline const char* callBtnAction(CallBtn b) {
    switch (b) {
        case CallBtn::Answer:  return "answer";
        case CallBtn::Decline: return "decline";
        case CallBtn::HangUp:  return "hangup";
        default:               return nullptr;
    }
}

class CallState {
public:
    static constexpr size_t NAME = 32, APP = 16, ID = 24;

    // From the app. name/app should already be ASCII (app.cpp folds them). False: unknown state.
    bool onPhone(const char* state, const char* name, const char* app, const char* id, uint32_t now) {
        if (!state) return false;
        if (!id) id = "";
        bool same = phase_ != CallPhase::None && phase_ != CallPhase::Ended && !strcmp(id, id_);
        if (!strcmp(state, "ringing")) {
            if (!same) {
                start(name, app, id, now);
                phase_ = CallPhase::Ringing;
            } else if (phase_ == CallPhase::Ringing) {
                copy(name, app);                       // the phone may learn the name a bit later
            }
            lastNews_ = now;                           // answering/declining here: keep waiting
            return true;
        }
        if (!strcmp(state, "active")) {
            if (!same) {
                start(name, app, id, now);             // answered on the phone, or a new call
                phase_ = CallPhase::Active;
            } else if (phase_ != CallPhase::Active && phase_ != CallPhase::HangingUp) {
                phase_ = CallPhase::Active;            // ringing / answering here -> talking
                activeSince_ = now;
                hidden_ = false;
            }
            lastNews_ = now;
            return true;
        }
        if (!strcmp(state, "ended")) {
            // another call's "ended" (call waiting) must not hide this one
            if (phase_ != CallPhase::None && phase_ != CallPhase::Ended && (!*id || same)) {
                phase_ = CallPhase::Ended;
                endedAt_ = now;
            }
            return true;
        }
        return false;
    }

    CallBtn onButton(int btn, uint32_t now) {
        switch (phase_) {
            case CallPhase::Ringing:
                phase_ = btn == 1 ? CallPhase::Answering : CallPhase::Declining;
                actionAt_ = now;
                return btn == 1 ? CallBtn::Answer : CallBtn::Decline;
            case CallPhase::Answering:
            case CallPhase::Declining:
            case CallPhase::HangingUp:
                return CallBtn::Consumed;              // waiting for the phone
            case CallPhase::Active:
                if (hidden_) return CallBtn::NotMine;
                if (btn == 1) { hidden_ = true; return CallBtn::Consumed; }
                phase_ = CallPhase::HangingUp;
                actionAt_ = now;
                return CallBtn::HangUp;
            case CallPhase::Ended:
                phase_ = CallPhase::None;              // any press closes "Call ended"
                return CallBtn::Consumed;
            case CallPhase::None:
                break;
        }
        return CallBtn::NotMine;
    }

    void tick(uint32_t now) {
        switch (phase_) {
            case CallPhase::Ringing:
                if (now - lastNews_ > CALL_RING_MS) phase_ = CallPhase::None;
                break;
            case CallPhase::Answering:
            case CallPhase::Declining:
            case CallPhase::HangingUp:
                if (now - actionAt_ > CALL_ACTION_MS) phase_ = CallPhase::None;
                break;
            case CallPhase::Ended:
                if (now - endedAt_ > CALL_ENDED_MS) phase_ = CallPhase::None;
                break;
            default:
                break;
        }
    }

    void clear() { phase_ = CallPhase::None; }        // the phone disconnected

    CallPhase phase() const { return phase_; }
    bool visible() const { return phase_ != CallPhase::None && !(phase_ == CallPhase::Active && hidden_); }
    bool ringing() const { return phase_ == CallPhase::Ringing; }
    const char* name() const { return name_; }
    const char* app() const { return app_; }
    const char* id() const { return id_; }
    uint32_t activeSeconds(uint32_t now) const { return (now - activeSince_) / 1000; }

private:
    static void copyStr(char* dst, const char* src, size_t cap) {
        size_t n = strlen(src);
        if (n > cap - 1) n = cap - 1;
        memcpy(dst, src, n);
        dst[n] = '\0';
    }

    void start(const char* name, const char* app, const char* id, uint32_t now) {
        copy(name, app);
        copyStr(id_, id, ID);
        hidden_ = false;
        activeSince_ = now;
    }

    void copy(const char* name, const char* app) {
        copyStr(name_, name && *name ? name : "Unknown", NAME);
        copyStr(app_, app && *app ? app : "Phone", APP);
    }

    CallPhase phase_ = CallPhase::None;
    char name_[NAME] = "", app_[APP] = "", id_[ID] = "";
    bool hidden_ = false;
    uint32_t lastNews_ = 0, actionAt_ = 0, endedAt_ = 0, activeSince_ = 0;
};

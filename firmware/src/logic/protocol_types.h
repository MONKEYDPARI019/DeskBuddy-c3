#pragma once
// App -> DeskBuddy message types (pure C++, unit-tested on a PC). protocol.cpp
// switches on these; see docs/PROTOCOL.md for the fields of each message.

#include <string.h>

enum class MsgType : unsigned char {
    Hello = 0, Ping, Get, Time, Notify, Face, Screen, Sound, Set, PowerOff, WifiSetup,
    Clear,      // 2.3.1: clear all notifications, like a long BTN2 press
    OtaNonce, OtaBegin, OtaData, OtaEnd, OtaAbort, OtaPass,   // 2.5.0: updates from the app
    Call,       // 2.5.0: a phone call is ringing / active / ended
    NoAudio,    // DeskBuddy v2 voice messages (ptt, think, say_*): the C3 has no mic or speaker
    Unknown     // keep last
};

inline const char* msgTypeName(MsgType t) {
    switch (t) {
        case MsgType::Hello:     return "hello";
        case MsgType::Ping:      return "ping";
        case MsgType::Get:       return "get";
        case MsgType::Time:      return "time";
        case MsgType::Notify:    return "notify";
        case MsgType::Face:      return "face";
        case MsgType::Screen:    return "screen";
        case MsgType::Sound:     return "sound";
        case MsgType::Set:       return "set";
        case MsgType::PowerOff:  return "power_off";
        case MsgType::WifiSetup: return "wifi_setup";
        case MsgType::Clear:     return "clear";
        case MsgType::OtaNonce:  return "ota_nonce";
        case MsgType::OtaBegin:  return "ota_begin";
        case MsgType::OtaData:   return "ota_data";
        case MsgType::OtaEnd:    return "ota_end";
        case MsgType::OtaAbort:  return "ota_abort";
        case MsgType::OtaPass:   return "ota_pass";
        case MsgType::Call:      return "call";
        case MsgType::NoAudio:   return "ptt";
        case MsgType::Unknown:   break;
    }
    return nullptr;
}

inline MsgType msgTypeFromName(const char* name) {
    if (!name || !*name) return MsgType::Unknown;
    for (int i = 0; i < (int)MsgType::NoAudio; i++) {
        if (!strcmp(name, msgTypeName((MsgType)i))) return (MsgType)i;
    }
    if (!strcmp(name, "ptt") || !strcmp(name, "think") || !strncmp(name, "say_", 4)) return MsgType::NoAudio;
    return MsgType::Unknown;
}

#pragma once
// Firmware updates from the phone app (2.5.0). The app proves the update password, BTN1 on
// DeskBuddy says yes, and the new firmware arrives over the normal link (Bluetooth or WiFi) in
// numbered chunks. The rules live in logic/ota_core.h; this file connects them to the flash
// (Update), NVS, the buttons, the buzzer and the screen. Messages: docs/PROTOCOL.md.

#include <stddef.h>
#include <stdint.h>
#include "buttons.h"
#include "protocol.h"

void otaBegin();                          // after settingsLoad(): load the password
void otaLoop();                           // timeouts, phone gone, restart after success
bool otaButton(const ButtonPress& p);     // true: the press answered an update question
bool otaHasPassword();
bool otaBusy();                           // asking or updating: keep the screen awake

// messages from the app (protocol.cpp)
void otaNonce(ReplyFn reply);
void otaStart(uint32_t size, const char* sha256, const char* proof, const char* version, ReplyFn reply);
void otaPassword(const char* key, const char* proof, ReplyFn reply);
void otaData(uint32_t seq, const char* data, size_t len, ReplyFn reply);
void otaFinish(ReplyFn reply);
void otaCancel();

// serial: otapass [set <password> | clear]
void otaCli(const char* sub, const char* arg);

// for the screen (ui.cpp)
enum class OtaView : uint8_t { None, AskUpdate, AskPassword, Receiving, Done };
OtaView otaView(int* percent, uint32_t* secondsLeft, const char** version);

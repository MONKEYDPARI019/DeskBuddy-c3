#pragma once
// The JSON protocol shared with the DeskBuddy Android app (docs/PROTOCOL.md).
// Same messages over Bluetooth and WiFi.

#include <stddef.h>

typedef void (*ReplyFn)(const char* json);

void   protocolHandle(const char* line, ReplyFn reply);   // one message from the app
size_t protocolHello(char* buf, size_t n);
size_t protocolState(char* buf, size_t n);
void   protocolButton(char* buf, size_t n, int btn, const char* action);

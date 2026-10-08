#include "link.h"
#include "config.h"
#include "settings.h"
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

struct InboxItem { uint16_t len; char text[MAX_LINE]; };
static QueueHandle_t inbox = nullptr;
static uint8_t mode = LINK_BLE;
static uint32_t dropped = 0;

void inboxBegin() {
    if (!inbox) inbox = xQueueCreate(4, sizeof(InboxItem));
}

bool inboxPush(const char* line, size_t len) {
    if (!inbox || len == 0) return false;
    static InboxItem item;                     // pushed from one task at a time per radio
    if (len >= MAX_LINE) { dropped++; return false; }
    item.len = (uint16_t)len;
    memcpy(item.text, line, len);
    item.text[len] = '\0';
    if (xQueueSend(inbox, &item, 0) != pdTRUE) { dropped++; return false; }
    return true;
}

bool linkReceive(char* buf, size_t n) {
    static InboxItem item;
    if (!inbox || xQueueReceive(inbox, &item, 0) != pdTRUE) return false;
    strlcpy(buf, item.text, n);
    return true;
}

void linkBegin(uint8_t m) {
    mode = m;
    inboxBegin();
    if (mode == LINK_WIFI) wifiBegin(); else bleBegin();
}

void linkService()            { if (mode == LINK_WIFI) wifiService(); else bleService(); }
void linkSend(const char* j)  { if (mode == LINK_WIFI) wifiSend(j); else bleSend(j); }
int  linkClients()            { return mode == LINK_WIFI ? wifiClients() : bleClients(); }
LinkState linkState()         { return mode == LINK_WIFI ? wifiState() : bleState(); }
String linkAddress()          { return mode == LINK_WIFI ? wifiAddress() : bleAddress(); }
int  linkRssi()               { return mode == LINK_WIFI ? wifiRssi() : 0; }
bool linkTimeFromNetwork()    { return mode == LINK_WIFI && wifiTimeSynced(); }
void linkForgetWifi()         { wifiForget(); }
void linkShutdown()           { if (mode == LINK_WIFI) wifiStop(); else bleStop(); }

const char* linkStateName() {
    switch (linkState()) {
        case LinkState::Off:         return "off";
        case LinkState::Portal:      return "wifi setup portal";
        case LinkState::Connecting:  return "connecting";
        case LinkState::Online:      return "online";
        case LinkState::Advertising: return "bluetooth advertising";
    }
    return "?";
}

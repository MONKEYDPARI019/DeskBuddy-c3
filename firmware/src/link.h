#pragma once
// The phone link. Exactly one radio runs: Bluetooth LE or WiFi (switching
// saves the choice and restarts, because both radios together leave too
// little RAM on the C3 and drain the battery).
//
// Incoming JSON lines from either radio (and from HTTP /notify) go into one
// inbox queue; the main loop takes them out with linkReceive(). Nothing in the
// radio callbacks touches the display or app state, so there are no races.

#include <Arduino.h>

enum class LinkState : uint8_t { Off, Portal, Connecting, Online, Advertising };

void        linkBegin(uint8_t mode);           // LINK_BLE or LINK_WIFI
void        linkService();                     // call every loop
bool        linkReceive(char* buf, size_t n);  // next incoming line, false if none
void        linkSend(const char* json);        // to every connected app
int         linkClients();                     // connected apps
LinkState   linkState();
const char* linkStateName();
String      linkAddress();                     // IP or Bluetooth MAC
int         linkRssi();                        // WiFi RSSI (0 in Bluetooth mode)
bool        linkTimeFromNetwork();             // WiFi: NTP time arrived
void        linkForgetWifi();                  // erase saved WiFi credentials
void        linkShutdown();                    // before restart / deep sleep

// shared by the two radios (link.cpp)
bool inboxPush(const char* line, size_t len);  // safe from any task
void inboxBegin();

// radio implementations
void bleBegin();   void bleService();   void bleSend(const char*);  int bleClients();
void bleStop();    LinkState bleState(); String bleAddress();
void wifiBegin();  void wifiService();  void wifiSend(const char*); int wifiClients();
void wifiStop();   LinkState wifiState(); String wifiAddress(); int wifiRssi();
bool wifiTimeSynced(); void wifiForget();

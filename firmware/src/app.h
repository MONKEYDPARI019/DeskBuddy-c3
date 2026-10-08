#pragma once
// DeskBuddy's behaviour: screens, notifications, sleep, LEDs, sounds, timers.
// Every input (buttons, phone, serial) ends up calling these functions from
// the main loop, so the state below is only ever touched by one task.

#include <stdint.h>
#include "config.h"
#include "buttons.h"
#include "logic/notif_store.h"

enum class Screen : uint8_t { Clock = 0, Mochi, Notify, Count };

const char* screenName(Screen s);
bool        screenFromName(const char* name, Screen* out);

void appBegin();
void appLoop();                              // timers, LEDs, state pushes

// ---- actions --------------------------------------------------------------
void appButton(const ButtonPress& p);
void appNotify(const char* app, const char* title, const char* body);
void appSetScreen(Screen s);
void appNextScreen();
bool appFace(const char* name);              // mood or state name
bool appSound(const char* name);
void appNextNotif();
void appClearNotifs();
void appSetClock(long long epoch, const char* tzPosix, bool hasTzMin, int tzMin);
void appSettingsChanged();                   // re-apply brightness etc.
void appSwitchLink(uint8_t mode);            // saves, tells the app, restarts
bool appPowerOff(const char* reason);        // false if this build has no power switch
void appMessage(const char* title, const char* sub, uint32_t ms = 2000);
void appActivity();                          // any user input: wake Mochi, reset timers
void appStateDirty();                        // push "state" to the app soon

// ---- read by the UI and the protocol --------------------------------------
Screen appScreen();
bool   appSleeping();
bool   appTimeValid();
const NotifStore<MAX_NOTIFS>& appNotifs();
int    appUnread();
bool   appPopup(const Notification** n);     // a fresh notification to pop up?
bool   appMessageActive(const char** title, const char** sub);
bool   appRestarting();

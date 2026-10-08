// DeskBuddy C3 - pocket DeskBuddy on an ESP32-C3 Super Mini
//
// One loop does everything, in this order: serial commands, radio, incoming
// app messages, buttons, app logic, sound, LEDs, display. Only the Bluetooth
// stack runs in its own task, and it only hands complete messages to the
// inbox queue (link.cpp). So there are no locks and no shared-state races.

#include <Arduino.h>
#include "config.h"
#include "settings.h"
#include "oled.h"
#include "ui.h"
#include "app.h"
#include "buttons.h"
#include "leds.h"
#include "buzzer.h"
#include "battery.h"
#include "power.h"
#include "link.h"
#include "protocol.h"
#include "cli.h"
#include "face.h"

static void replyToApp(const char* json) { linkSend(json); }

void setup() {
    powerWakeCheck();                          // battery build: woken by BTN1? must be held 3 s
    Serial.begin(115200);
    Serial.setTxTimeoutMs(0);                  // never block when no serial monitor is reading
    uint32_t t0 = millis();
    while (!Serial && millis() - t0 < 1000) delay(10);   // let the USB monitor attach
    Serial.printf("\n\n=== %s %s (%s build) ===\n", FW_NAME, FW_VERSION, FEATURE_BATTERY ? "battery" : "USB");

    settingsLoad();
    ledsBegin();
    buttonsBegin();
    buzzerBegin();
    batteryBegin();

    oledBegin();
    uiSplash("DeskBuddy C3", settings.link == LINK_BLE ? "Bluetooth" : "WiFi");

    // Switch radio without a PC or the app: hold BOTH buttons while pressing
    // RESET (or switching on) -> Bluetooth <-> WiFi. Hold ~1 s, then let go.
    if (buttonDown(1) && buttonDown(2)) {
        delay(300);                                   // make sure it is a real hold
        if (buttonDown(1) && buttonDown(2)) {
            settings.link = settings.link == LINK_BLE ? LINK_WIFI : LINK_BLE;
            settingsSave();
            const char* name = settings.link == LINK_BLE ? "Bluetooth" : "WiFi";
            uiSplash(settings.link == LINK_BLE ? "Bluetooth mode" : "WiFi mode", "let go of the buttons");
            Serial.printf("[Boot] both buttons held: switched to %s\n", name);
            while (buttonDown(1) || buttonDown(2)) delay(10);
            uiSplash("DeskBuddy C3", name);
            delay(600);
        }
    }

    appBegin();
    linkBegin(settings.link);
    buzzerPlay(Sound::Hello);
    Serial.printf("[Boot] ready in %lu ms. Type 'help'.\n", (unsigned long)millis());
}

void loop() {
    static uint32_t lastFrame = 0;
    static char msg[MAX_LINE];

    cliService();
    linkService();
    while (linkReceive(msg, sizeof(msg))) protocolHandle(msg, replyToApp);

    ButtonPress p = buttonsPoll();
    if (p.ev != BtnEvent::None) appButton(p);

    batteryUpdate();
    appLoop();
    buzzerUpdate();
    oledService();

    uint32_t frame = appSleeping() ? FRAME_MS_SLEEPING : FRAME_MS;
    if (millis() - lastFrame >= frame) {
        lastFrame = millis();
        faceUpdate();
        uiRender();
    }
    delay(1);                                  // let the idle task run (watchdog)
}

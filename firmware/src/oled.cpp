#include "oled.h"
#include "config.h"
#include <Arduino.h>
#include <Wire.h>

Display gfx(U8G2_R0, U8X8_PIN_NONE, PIN_SCL, PIN_SDA);

static uint8_t addr = 0;
static bool present = false;
static uint8_t contrast = 200;
static uint8_t misses = 0;
static uint32_t lastCheck = 0;

static bool ack(uint8_t a) {
    Wire.beginTransmission(a);
    return Wire.endTransmission() == 0;
}

// 100 kHz works even with weak pull-ups. u8g2 switches to its own speed
// (400 kHz) at the start of every transfer, so this does not slow drawing.
static uint8_t probe() {
    Wire.setClock(100000);
    if (ack(0x3C)) return 0x3C;
    if (ack(0x3D)) return 0x3D;
    return 0;
}

static void start(uint8_t a) {
    addr = a;
    gfx.setI2CAddress(a * 2);
    gfx.begin();
    gfx.setContrast(contrast);
    present = true;
    misses = 0;
}

int oledScan(bool print) {
    Wire.setClock(100000);
    int n = 0;
    for (uint8_t a = 1; a < 127; a++) {
        if (ack(a)) {
            n++;
            if (print) Serial.printf("  I2C device at 0x%02X%s\n", a, (a == 0x3C || a == 0x3D) ? "  <- OLED" : "");
        }
    }
    if (print) Serial.printf("  %d device(s) on SDA=GPIO%d SCL=GPIO%d\n", n, PIN_SDA, PIN_SCL);
    return n;
}

void oledBegin() {
    while (millis() < 500) delay(10);          // OLED power-up time after a cold start
    Wire.begin(PIN_SDA, PIN_SCL);
    Wire.setTimeOut(10);                       // a stuck bus must not stall the loop for long
    uint8_t a = 0;
    for (int i = 0; i < 10 && !a; i++) {       // up to ~1 s
        a = probe();
        if (!a) delay(100);
    }
    if (a) {
        start(a);
        Serial.printf("[OLED] found at 0x%02X\n", a);
    } else {
        Serial.printf("[OLED] NOT FOUND (SDA=GPIO%d, SCL=GPIO%d). Bus scan:\n", PIN_SDA, PIN_SCL);
        if (oledScan(true) == 0) Serial.println("  nothing answers: check VCC->3.3V, GND->G, SDA->6, SCL->7");
        Serial.println("[OLED] retrying every 3 s; it starts by itself once it answers");
    }
    lastCheck = millis();
}

void oledService() {
    if (millis() - lastCheck < OLED_CHECK_MS) return;
    lastCheck = millis();
    uint8_t a = probe();
    if (present) {
        if (a) {
            if (misses) {                      // it blinked out: a power blip leaves an
                start(a);                      // SSD1306 dark, so always initialise it again
                Serial.println("[OLED] answered again, re-initialised");
            }
            misses = 0;
            return;
        }
        if (++misses >= 2) {                   // two misses in a row: really gone
            present = false;
            Serial.println("[OLED] lost (loose wire?), waiting for it to come back");
        }
    } else if (a) {
        start(a);
        Serial.printf("[OLED] back at 0x%02X, re-initialised\n", a);
    }
}

void oledSend()          { if (present && !misses) gfx.sendBuffer(); }   // skip while it is not answering
bool oledPresent()       { return present; }
uint8_t oledAddress()    { return addr; }
void oledContrast(uint8_t c) { contrast = c; if (present) gfx.setContrast(c); }
void oledPower(bool on)  { if (present) gfx.setPowerSave(on ? 0 : 1); }

void oledReinit() {
    uint8_t a = probe();
    if (a) { start(a); Serial.printf("[OLED] re-initialised at 0x%02X\n", a); }
    else   { present = false; Serial.println("[OLED] not answering"); }
}

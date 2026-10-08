#pragma once
// The SSD1306 OLED. Handles the problems we hit on the bench:
//  - it may not answer right after power-on  -> waits, probes slowly, retries
//  - a loose jumper can drop it              -> re-probes every few seconds and
//                                               re-initialises it when it comes back
// Drawing always goes to the RAM buffer, so the rest of the firmware never cares.

#include <U8g2lib.h>

using Display = U8G2_SSD1306_128X64_NONAME_F_HW_I2C;
extern Display gfx;

void    oledBegin();                 // call once in setup()
void    oledService();               // call every loop: hot-plug check
void    oledSend();                  // send the buffer (skipped while the OLED is missing)
bool    oledPresent();
uint8_t oledAddress();               // 0x3C / 0x3D (0 if never found)
void    oledContrast(uint8_t c);
void    oledPower(bool on);          // false = panel off (deep sleep)
void    oledReinit();                // full init sequence again (CLI: oled reinit)
int     oledScan(bool print);        // I2C scan at 100 kHz, returns number of devices

#pragma once
// Battery reading (battery build only). Every value is "not a battery" (-1)
// until several plausible readings in a row were seen, so a floating or
// unwired GPIO0 can never trigger a low-battery shutdown.

#include <stdint.h>

void batteryBegin();
void batteryUpdate();          // call every loop (samples every 500 ms)
int  batteryMv();              // filtered battery voltage, -1 = no battery
int  batteryPercent();         // 0-100, -1 = no battery / USB build
bool batteryLow();             // <= 10 %
bool batteryEmpty();           // below the cut-off for 30 s: time to power off
int  batteryRawMv();           // last raw reading (CLI)

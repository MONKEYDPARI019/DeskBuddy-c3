#pragma once
// Serial command line at 115200 baud (PlatformIO Serial Monitor). Type 'help'.

void cliService();                    // call every loop: reads and runs whole lines
void cliRun(const char* line);

#include <stdint.h>
void loopStats(uint32_t* loopUs, uint32_t* frameUs);   // main.cpp: longest loop / frame since last call

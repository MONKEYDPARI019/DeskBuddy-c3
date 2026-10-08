#pragma once
// Serial command line at 115200 baud (PlatformIO Serial Monitor). Type 'help'.

void cliService();                    // call every loop: reads and runs whole lines
void cliRun(const char* line);

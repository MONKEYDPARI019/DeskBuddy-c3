#pragma once
// Two buttons to GND (internal pull-ups), debounced, polled from the main loop.
//   click  = press + release before LONG_PRESS_MS
//   long   = released after LONG_PRESS_MS (battery build: BTN1 only up to POWER_CANCEL_MS)
//   power  = BTN1 still held at POWER_HOLD_MS (fires once, while held)

#include <stdint.h>

enum class BtnEvent : uint8_t { None, Click, Long, Power };

struct ButtonPress { uint8_t btn; BtnEvent ev; };

void        buttonsBegin();
ButtonPress buttonsPoll();                 // at most one event per call
bool        buttonDown(uint8_t btn);       // raw state (1 or 2)
uint32_t    buttonHeldMs(uint8_t btn);     // how long it has been down (0 if up)
void        buttonSimulate(uint8_t btn, uint32_t ms);   // CLI: press in software

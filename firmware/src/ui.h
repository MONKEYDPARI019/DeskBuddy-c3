#pragma once
// Drawing: screens, popups and overlays. Reads the app state, changes nothing.

void uiRender();                                  // one frame
void uiSplash(const char* title, const char* sub);
void uiOtaProgress(int pct);                      // -1 = failed
void uiTestPattern();

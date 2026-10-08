#pragma once
// Phone UTC offset in minutes (India = +330) -> POSIX TZ string. POSIX uses the
// opposite sign: UTC+5:30 is "UTC-5:30". Pure C++, unit-tested.

#include <stdio.h>
#include <stdlib.h>

inline void tzFromOffsetMinutes(int offsetMin, char* out, size_t n) {
    if (offsetMin < -14 * 60 || offsetMin > 14 * 60) offsetMin = 0;
    int a = abs(offsetMin);
    char sign = offsetMin > 0 ? '-' : '+';
    if (a % 60) snprintf(out, n, "UTC%c%d:%02d", sign, a / 60, a % 60);
    else        snprintf(out, n, "UTC%c%d", sign, a / 60);
}

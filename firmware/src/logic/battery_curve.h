#pragma once
// Single-cell LiPo voltage -> percent (estimate under light load). Pure C++, unit-tested.

#include <stdint.h>

struct CurvePoint { uint16_t mv; uint8_t pct; };

static const CurvePoint BATTERY_CURVE[] = {
    {3300, 0},  {3500, 3},  {3600, 6},  {3700, 12}, {3750, 20}, {3790, 30},
    {3830, 40}, {3870, 50}, {3920, 60}, {3980, 70}, {4060, 80}, {4130, 90},
    {4200, 100},
};

// A reading outside this window is not a battery (floating pin, USB only, bad wiring).
static const int BATTERY_MIN_VALID_MV = 3000;
static const int BATTERY_MAX_VALID_MV = 4500;

inline bool batteryMvPlausible(int mv) { return mv >= BATTERY_MIN_VALID_MV && mv <= BATTERY_MAX_VALID_MV; }

// 0..100, or -1 when the reading is not a battery.
inline int batteryPercentFromMv(int mv) {
    if (!batteryMvPlausible(mv)) return -1;
    const int n = sizeof(BATTERY_CURVE) / sizeof(BATTERY_CURVE[0]);
    if (mv <= BATTERY_CURVE[0].mv) return 0;
    if (mv >= BATTERY_CURVE[n - 1].mv) return 100;
    for (int i = 1; i < n; i++) {
        if (mv <= BATTERY_CURVE[i].mv) {
            const CurvePoint& a = BATTERY_CURVE[i - 1];
            const CurvePoint& b = BATTERY_CURVE[i];
            return a.pct + (int)((long)(mv - a.mv) * (b.pct - a.pct) / (b.mv - a.mv));
        }
    }
    return 100;
}

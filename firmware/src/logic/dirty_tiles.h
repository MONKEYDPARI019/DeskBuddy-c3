#pragma once
// Which parts of the OLED changed since the last frame (pure C++, unit-tested on a PC).
//
// The SSD1306 frame buffer is `pages` rows of `width` bytes; each byte is a
// column of 8 pixels and a "tile" is 8 such columns. Sending all 1024 bytes
// over I2C at 400 kHz takes ~25 ms, most of a 33 ms frame. Mochi's eyes, the
// clock's seconds bar or a scrolling line change only a few tiles, so only
// those are sent: per page, one span from the first to the last changed tile.

#include <stddef.h>
#include <stdint.h>
#include <string.h>

// Compares `cur` with `shadow`, copies every change into `shadow`, and calls
// emit(page, firstTile, tileCount) once per page that changed. Returns the
// number of spans emitted (0 = nothing to send).
template <typename F>
int diffTiles(const uint8_t* cur, uint8_t* shadow, int width, int pages, F emit) {
    int spans = 0;
    const int tiles = width / 8;
    for (int page = 0; page < pages; page++) {
        const uint8_t* c = cur + (size_t)page * width;
        uint8_t* s = shadow + (size_t)page * width;
        int first = -1, last = -1;
        for (int t = 0; t < tiles; t++) {
            if (memcmp(c + t * 8, s + t * 8, 8) != 0) {
                if (first < 0) first = t;
                last = t;
            }
        }
        if (first < 0) continue;
        memcpy(s + first * 8, c + first * 8, (size_t)(last - first + 1) * 8);
        emit(page, first, last - first + 1);
        spans++;
    }
    return spans;
}

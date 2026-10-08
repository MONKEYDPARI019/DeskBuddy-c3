#pragma once
// Text helpers for the OLED (pure C++, unit-tested on a PC).
//
// asciiFold: phone notifications are UTF-8 (emoji, curly quotes, accents...).
//   The OLED fonts are ASCII, so foreign bytes would show as garbage. Common
//   punctuation is mapped to ASCII, Latin accents lose their accent, and
//   anything else (emoji, other scripts) becomes a single '?' per character.
// wrapText: word wrap into fixed-width lines; words longer than a line are cut.

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace text_detail {

// Decode one UTF-8 sequence at s. Returns its length (>= 1) and the code point
// (0xFFFD for invalid bytes).
inline size_t decodeUtf8(const unsigned char* s, uint32_t* cp) {
    unsigned char c = s[0];
    if (c < 0x80) { *cp = c; return 1; }
    size_t len = (c & 0xE0) == 0xC0 ? 2 : (c & 0xF0) == 0xE0 ? 3 : (c & 0xF8) == 0xF0 ? 4 : 0;
    if (len == 0) { *cp = 0xFFFD; return 1; }
    uint32_t v = c & (0x7F >> len);
    for (size_t i = 1; i < len; i++) {
        if ((s[i] & 0xC0) != 0x80) { *cp = 0xFFFD; return i; }   // truncated sequence
        v = (v << 6) | (s[i] & 0x3F);
    }
    *cp = v;
    return len;
}

// ASCII replacement for a non-ASCII code point ("" = drop it).
inline const char* foldCodePoint(uint32_t cp) {
    switch (cp) {
        case 0x2018: case 0x2019: case 0x201A: case 0x2032: return "'";
        case 0x201C: case 0x201D: case 0x201E: case 0x2033: return "\"";
        case 0x2013: case 0x2014: case 0x2212: return "-";
        case 0x2026: return "...";
        case 0x2022: case 0x00B7: return "*";
        case 0x00A0: case 0x2002: case 0x2003: case 0x2009: return " ";
        case 0x20B9: return "Rs";
        case 0x20AC: return "EUR";
        case 0x00A3: return "GBP";
        case 0x00D7: return "x";
        case 0x200B: case 0x200C: case 0x200D: case 0xFE0F: case 0xFE0E: return "";  // invisible joiners
    }
    if (cp >= 0x1F3FB && cp <= 0x1F3FF) return "";                // skin-tone modifiers
    if ((cp >= 0x1F000 && cp <= 0x1FAFF) || (cp >= 0x2600 && cp <= 0x27BF)) return "*";  // emoji
    // Latin-1 letters with accents -> base letter
    static const char* const LATIN1 =
        "AAAAAAACEEEEIIII"   // C0-CF
        "DNOOOOOxOUUUUYTs"   // D0-DF
        "aaaaaaaceeeeiiii"   // E0-EF
        "dnooooo/ouuuuyty";  // F0-FF
    if (cp >= 0xC0 && cp <= 0xFF) {
        static char one[2];
        one[0] = LATIN1[cp - 0xC0];
        one[1] = '\0';
        return one;
    }
    return "?";
}

}  // namespace text_detail

// Copies src into dst (size n, always terminated) as printable ASCII.
// Newlines/tabs become spaces; repeated spaces collapse to one. Returns the length.
inline size_t asciiFold(const char* src, char* dst, size_t n) {
    if (!dst || n == 0) return 0;
    size_t o = 0;
    bool lastSpace = true;                 // also trims leading spaces
    const unsigned char* s = (const unsigned char*)(src ? src : "");
    while (*s && o + 1 < n) {
        uint32_t cp;
        s += text_detail::decodeUtf8(s, &cp);
        const char* rep;
        char one[2] = {0, 0};
        if (cp < 0x80) {
            if (cp == '\n' || cp == '\r' || cp == '\t') cp = ' ';
            if (cp < 0x20 || cp == 0x7F) continue;      // other control characters
            one[0] = (char)cp;
            rep = one;
        } else {
            rep = text_detail::foldCodePoint(cp);
        }
        for (; *rep && o + 1 < n; rep++) {
            if (*rep == ' ') {
                if (lastSpace) continue;
                lastSpace = true;
            } else {
                lastSpace = false;
            }
            dst[o++] = *rep;
        }
    }
    while (o > 0 && dst[o - 1] == ' ') o--;             // trailing space
    dst[o] = '\0';
    return o;
}

// Word-wraps text into lines of at most `width` characters.
// lines: maxLines rows of (width + 1) chars each, laid out contiguously.
// Returns the number of lines produced (text that does not fit is dropped).
inline int wrapText(const char* text, size_t width, char* lines, int maxLines) {
    if (!text || !lines || width == 0 || maxLines <= 0) return 0;
    int count = 0;
    const char* p = text;
    while (*p == ' ') p++;
    while (*p && count < maxLines) {
        size_t remain = strlen(p);
        size_t take;
        if (remain <= width) {
            take = remain;
        } else {
            take = width;
            size_t brk = width;                    // last space within the line
            while (brk > 0 && p[brk] != ' ') brk--;
            if (brk > 0) take = brk;               // break at the space, else cut the word
        }
        size_t len = take;
        while (len > 0 && p[len - 1] == ' ') len--;
        char* row = lines + (size_t)count * (width + 1);
        memcpy(row, p, len);
        row[len] = '\0';
        count++;
        p += take;
        while (*p == ' ') p++;
    }
    return count;
}

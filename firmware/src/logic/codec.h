#pragma once
// Hex and base64 for the update messages (pure C++, unit-tested on a PC).

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace codec_detail {
inline int hexValue(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

inline int base64Value(char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}
}  // namespace codec_detail

// Exactly 2*n hex digits (either case) -> n bytes. False for anything else.
inline bool hexDecode(const char* s, uint8_t* out, size_t n) {
    if (!s || strlen(s) != 2 * n) return false;
    for (size_t i = 0; i < n; i++) {
        int hi = codec_detail::hexValue(s[2 * i]), lo = codec_detail::hexValue(s[2 * i + 1]);
        if (hi < 0 || lo < 0) return false;
        out[i] = (uint8_t)(hi << 4 | lo);
    }
    return true;
}

// n bytes -> 2*n lowercase hex digits + NUL (out must hold 2*n + 1 chars).
inline void hexEncode(const uint8_t* in, size_t n, char* out) {
    static const char D[] = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) { out[2 * i] = D[in[i] >> 4]; out[2 * i + 1] = D[in[i] & 15]; }
    out[2 * n] = '\0';
}

// Standard base64 (RFC 4648, '+' '/', '=' padding optional). Returns the number of bytes
// written, or -1 for a bad character, a bad length or more than cap bytes.
inline int base64Decode(const char* in, size_t len, uint8_t* out, size_t cap) {
    if (!in) return -1;
    while (len > 0 && in[len - 1] == '=') len--;      // padding: at most two
    if (len % 4 == 1) return -1;
    size_t o = 0;
    uint32_t acc = 0;
    int bits = 0;
    for (size_t i = 0; i < len; i++) {
        int v = codec_detail::base64Value(in[i]);
        if (v < 0) return -1;
        acc = (acc << 6) | (uint32_t)v;
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            if (o >= cap) return -1;
            out[o++] = (uint8_t)(acc >> bits);
        }
    }
    if (acc & ((1u << bits) - 1)) return -1;           // leftover bits must be zero (canonical)
    return (int)o;
}

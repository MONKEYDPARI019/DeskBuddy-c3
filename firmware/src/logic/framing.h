#pragma once
// Bluetooth LE message framing (pure C++, unit-tested on a PC).
// One message = one JSON object + '\n'. BLE carries at most (MTU - 3) bytes per
// packet, so a message may arrive in pieces (LineAssembler joins them) and is
// sent in pieces (frameChunks splits it).

#include <stddef.h>
#include <string.h>

template <size_t CAP>
class LineAssembler {
public:
    // onLine(const char* line, size_t len) for every complete line (without '\n').
    // '\r' and NUL bytes are ignored. Lines longer than CAP-1 are dropped whole.
    template <typename F>
    void push(const char* data, size_t len, F onLine) {
        for (size_t i = 0; i < len; i++) {
            char c = data[i];
            if (c == '\r' || c == '\0') continue;
            if (c == '\n') {
                if (!dropping_ && n_ > 0) { buf_[n_] = '\0'; onLine(buf_, n_); }
                n_ = 0;
                dropping_ = false;
                continue;
            }
            if (dropping_) continue;
            if (n_ >= CAP - 1) { dropping_ = true; overflows_++; n_ = 0; continue; }
            buf_[n_++] = c;
        }
    }
    void reset() { n_ = 0; dropping_ = false; }
    size_t pending() const { return n_; }
    unsigned overflows() const { return overflows_; }

private:
    char buf_[CAP];
    size_t n_ = 0;
    bool dropping_ = false;
    unsigned overflows_ = 0;
};

// emit(const char* piece, size_t len) for each piece of msg + '\n' (each <= chunk bytes).
// Returns the number of pieces.
template <typename F>
size_t frameChunks(const char* msg, size_t chunk, F emit) {
    if (!msg || chunk == 0) return 0;
    char piece[256];
    if (chunk > sizeof(piece)) chunk = sizeof(piece);
    size_t len = strlen(msg), total = len + 1, pieces = 0;
    for (size_t off = 0; off < total; off += chunk) {
        size_t n = total - off < chunk ? total - off : chunk;
        for (size_t i = 0; i < n; i++) piece[i] = off + i < len ? msg[off + i] : '\n';
        emit(piece, n);
        pieces++;
    }
    return pieces;
}

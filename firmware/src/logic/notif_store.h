#pragma once
// The last N notifications, newest first (pure C++, unit-tested on a PC).

#include <stdint.h>
#include <stdio.h>

struct Notification {
    char app[16];
    char title[32];
    char body[128];
    uint32_t receivedMs;
};

template <int N>
class NotifStore {
public:
    // Fields are copied as given; fold them to ASCII before calling.
    void push(const char* app, const char* title, const char* body, uint32_t now, bool viewing) {
        Notification& n = buf_[head_];
        snprintf(n.app,   sizeof(n.app),   "%s", (app && *app) ? app : "Phone");
        snprintf(n.title, sizeof(n.title), "%s", (title && *title) ? title : "Notification");
        snprintf(n.body,  sizeof(n.body),  "%s", body ? body : "");
        n.receivedMs = now;
        head_ = (head_ + 1) % N;
        if (count_ < N) count_++;
        if (!viewing && unread_ < count_) unread_++;
        selected_ = 0;                        // show the newest
    }
    void next()     { if (count_ > 0) selected_ = (selected_ + 1) % count_; }
    void clear()    { count_ = head_ = selected_ = unread_ = 0; }
    void markRead() { unread_ = 0; }

    int count() const    { return count_; }
    int selected() const { return selected_; }
    int unread() const   { return unread_; }
    const Notification* at(int i) const {          // 0 = newest
        if (i < 0 || i >= count_) return nullptr;
        return &buf_[(head_ - 1 - i + 2 * N) % N];
    }
    const Notification* current() const { return at(selected_); }

private:
    Notification buf_[N] = {};
    int head_ = 0, count_ = 0, selected_ = 0, unread_ = 0;
};

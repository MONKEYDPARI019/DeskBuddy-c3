#pragma once
// Firmware updates from the phone app ("Update DeskBuddy", 2.5.0), pure C++ so every rule is
// unit-tested on a PC. ota.cpp connects it to the flash (Update), NVS, the buttons and the screen.
// The messages are in docs/PROTOCOL.md.
//
//  - An update password must be set first: in the app, confirmed with BTN1 on DeskBuddy (or with
//    'otapass set' over USB). DeskBuddy keeps only K = SHA-256("deskbuddy-ota:" + password).
//  - The password itself never travels. Each request carries a proof
//    HMAC-SHA256(K, nonce || purpose || detail), where the nonce is 16 random bytes from
//    DeskBuddy ("ota_nonce"), used once and valid for 60 s. For an update the detail is the
//    image's SHA-256, so the proof also vouches for the image.
//  - 3 wrong passwords in a row lock updates for 60 s.
//  - BTN1 on DeskBuddy must be pressed for every update (BTN2, or 30 s without an answer: no).
//  - The image arrives in numbered chunks; it is made bootable only if every byte arrived and its
//    SHA-256 matches. Anything else (link lost, 20 s of silence, a bad chunk) leaves the old
//    firmware running.

#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "sha256.h"
#include "codec.h"

constexpr size_t   OTA_KEY_LEN    = 32;
constexpr size_t   OTA_NONCE_LEN  = 16;
constexpr size_t   OTA_CHUNK      = 1024;      // image bytes per "ota_data" (base64: 1368 chars)
constexpr uint32_t OTA_NONCE_MS   = 60000;
constexpr uint32_t OTA_CONFIRM_MS = 30000;
constexpr uint32_t OTA_IDLE_MS    = 20000;
constexpr int      OTA_MAX_FAILS  = 3;
constexpr uint32_t OTA_LOCK_MS    = 60000;

enum class OtaPhase : uint8_t { Idle, ConfirmUpdate, ConfirmPassword, Receiving, Done };

enum class OtaErr : uint8_t {
    None, NoPassword, Locked, BadPassword, NoChallenge, Busy, BadRequest, TooBig,
    Declined, Timeout, Flash, BadSeq, BadData, Incomplete, BadHash, Cancelled, LinkLost
};

// Wire code for {"type":"ota_error","code":...}
inline const char* otaErrCode(OtaErr e) {
    switch (e) {
        case OtaErr::None:        return "none";
        case OtaErr::NoPassword:  return "no_password";
        case OtaErr::Locked:      return "locked";
        case OtaErr::BadPassword: return "bad_password";
        case OtaErr::NoChallenge: return "no_challenge";
        case OtaErr::Busy:        return "busy";
        case OtaErr::BadRequest:  return "bad_request";
        case OtaErr::TooBig:      return "too_big";
        case OtaErr::Declined:    return "declined";
        case OtaErr::Timeout:     return "timeout";
        case OtaErr::Flash:       return "flash";
        case OtaErr::BadSeq:      return "bad_seq";
        case OtaErr::BadData:     return "bad_data";
        case OtaErr::Incomplete:  return "incomplete";
        case OtaErr::BadHash:     return "bad_hash";
        case OtaErr::Cancelled:   return "cancelled";
        case OtaErr::LinkLost:    return "link_lost";
    }
    return "?";
}

// Short text for the OLED (fits the 5x8 font line, <= 21 chars).
inline const char* otaErrText(OtaErr e) {
    switch (e) {
        case OtaErr::None:        return "";
        case OtaErr::NoPassword:  return "no password set";
        case OtaErr::Locked:      return "locked for 1 min";
        case OtaErr::BadPassword: return "wrong password";
        case OtaErr::NoChallenge: return "request expired";
        case OtaErr::Busy:        return "already updating";
        case OtaErr::BadRequest:  return "bad request";
        case OtaErr::TooBig:      return "image too big";
        case OtaErr::Declined:    return "declined";
        case OtaErr::Timeout:     return "timed out";
        case OtaErr::Flash:       return "flash write failed";
        case OtaErr::BadSeq:      return "chunk lost";
        case OtaErr::BadData:     return "bad chunk";
        case OtaErr::Incomplete:  return "image incomplete";
        case OtaErr::BadHash:     return "image damaged";
        case OtaErr::Cancelled:   return "cancelled";
        case OtaErr::LinkLost:    return "phone disconnected";
    }
    return "";
}

// What the update needs from the device. Update + Preferences on the C3, a fake in the tests.
class OtaHal {
public:
    virtual ~OtaHal() = default;
    virtual bool begin(uint32_t size) = 0;                        // open the free update slot
    virtual bool write(const uint8_t* data, size_t len) = 0;
    virtual bool end() = 0;                                       // check the image, boot it next time
    virtual void abort() = 0;                                     // throw the partial image away
    virtual bool saveKey(const uint8_t* key) = 0;                 // OTA_KEY_LEN bytes; nullptr = remove
};

// K = SHA-256("deskbuddy-ota:" + password): what DeskBuddy stores and the app derives.
inline void otaKeyFromPassword(const char* password, uint8_t key[OTA_KEY_LEN]) {
    Sha256 s;
    s.update("deskbuddy-ota:");
    s.update(password ? password : "");
    s.finish(key);
}

// HMAC-SHA256(key, nonce || purpose || detail)
inline void otaProof(const uint8_t* key, const uint8_t* nonce, const char* purpose, const char* detail,
                     uint8_t out[Sha256::SIZE]) {
    HmacSha256 h(key, OTA_KEY_LEN);
    h.update(nonce, OTA_NONCE_LEN);
    h.update(purpose);
    h.update(detail ? detail : "");
    h.finish(out);
}

class OtaCore {
public:
    OtaCore(OtaHal& hal, uint32_t maxSize) : hal_(hal), maxSize_(maxSize) {}

    void setMaxSize(uint32_t maxSize) { maxSize_ = maxSize; }

    // ---- the password ---------------------------------------------------------------------
    void loadKey(const uint8_t* key) {                 // at boot, from NVS (nullptr = none set)
        hasKey_ = key != nullptr;
        if (key) memcpy(key_, key, OTA_KEY_LEN);
    }
    bool hasKey() const { return hasKey_; }

    // Over USB (physical access): set or remove the password without the old one.
    bool setKeyDirect(const uint8_t* key) {
        if (!hal_.saveKey(key)) return false;
        loadKey(key);
        fails_ = 0;
        lockUntil_ = 0;
        return true;
    }

    // "ota_nonce": the caller fills nonce with random bytes; the previous one is forgotten.
    void newChallenge(const uint8_t* nonce, uint32_t now) {
        memcpy(nonce_, nonce, OTA_NONCE_LEN);
        nonceAt_ = now;
        nonceValid_ = true;
    }

    // Milliseconds until wrong-password lock ends (0 = not locked).
    uint32_t lockedFor(uint32_t now) {
        refreshLock(now);
        return lockUntil_ ? lockUntil_ - now : 0;
    }
    int triesLeft() const { return OTA_MAX_FAILS - fails_; }

    // ---- requests from the app ------------------------------------------------------------
    // "ota_begin": size and SHA-256 (64 hex) of the app image, proof over "update:" + sha.
    OtaErr begin(uint32_t size, const char* shaHex, const char* proofHex, uint32_t now) {
        if (phase_ != OtaPhase::Idle) return OtaErr::Busy;            // Done: restarting into the new one
        if (!hasKey_) return OtaErr::NoPassword;
        if (lockedFor(now)) return OtaErr::Locked;
        uint8_t sha[Sha256::SIZE];
        if (!shaHex || !hexDecode(shaHex, sha, sizeof(sha)) || size == 0) return OtaErr::BadRequest;
        if (size > maxSize_) return OtaErr::TooBig;
        uint8_t nonce[OTA_NONCE_LEN];
        OtaErr err = checkProof(proofHex, "update:", shaHex, now, nonce);
        if (err != OtaErr::None) return err;
        memcpy(expected_, sha, sizeof(sha));
        size_ = size;
        received_ = 0;
        nextSeq_ = 0;
        phase_ = OtaPhase::ConfirmUpdate;
        confirmUntil_ = now + OTA_CONFIRM_MS;
        return OtaErr::None;
    }

    // "ota_pass": set the first password (keyHex = K in hex, no proof; needs BTN1), or change it
    // (keyHex = new K XOR HMAC(old K, nonce || "mask"), proof over "pass:" + keyHex; no button).
    // *saved tells which: true = changed now, false = waiting for BTN1.
    OtaErr setPassword(const char* keyHex, const char* proofHex, uint32_t now, bool* saved) {
        *saved = false;
        if (phase_ != OtaPhase::Idle) return OtaErr::Busy;
        uint8_t key[OTA_KEY_LEN];
        if (!keyHex || !hexDecode(keyHex, key, sizeof(key))) return OtaErr::BadRequest;
        if (!hasKey_) {
            memcpy(pendingKey_, key, sizeof(key));
            phase_ = OtaPhase::ConfirmPassword;
            confirmUntil_ = now + OTA_CONFIRM_MS;
            return OtaErr::None;
        }
        if (lockedFor(now)) return OtaErr::Locked;
        uint8_t nonce[OTA_NONCE_LEN];
        OtaErr err = checkProof(proofHex, "pass:", keyHex, now, nonce);
        if (err != OtaErr::None) return err;
        uint8_t mask[Sha256::SIZE];
        otaProof(key_, nonce, "mask", "", mask);
        for (size_t i = 0; i < OTA_KEY_LEN; i++) key[i] ^= mask[i];
        if (!hal_.saveKey(key)) return OtaErr::Flash;
        memcpy(key_, key, sizeof(key));
        *saved = true;
        return OtaErr::None;
    }

    // BTN1 (yes) or BTN2 (no) while DeskBuddy asks. ConfirmUpdate + yes -> Receiving.
    OtaErr confirm(bool yes, uint32_t now) {
        OtaPhase was = phase_;
        if (was != OtaPhase::ConfirmUpdate && was != OtaPhase::ConfirmPassword) return OtaErr::BadRequest;
        phase_ = OtaPhase::Idle;
        if (!yes) return OtaErr::Declined;
        if (was == OtaPhase::ConfirmPassword) {
            if (!hal_.saveKey(pendingKey_)) return OtaErr::Flash;
            loadKey(pendingKey_);
            fails_ = 0;
            return OtaErr::None;
        }
        if (!hal_.begin(size_)) return OtaErr::Flash;
        sha_.reset();
        phase_ = OtaPhase::Receiving;
        lastData_ = now;
        return OtaErr::None;
    }

    // "ota_data": chunk number seq (0, 1, 2...), base64.
    OtaErr data(uint32_t seq, const char* b64, size_t b64Len, uint32_t now) {
        if (phase_ != OtaPhase::Receiving) return OtaErr::BadRequest;
        if (seq != nextSeq_) return fail(OtaErr::BadSeq);
        int n = base64Decode(b64, b64Len, chunk_, sizeof(chunk_));
        if (n <= 0 || received_ + (uint32_t)n > size_) return fail(OtaErr::BadData);
        if (!hal_.write(chunk_, (size_t)n)) return fail(OtaErr::Flash);
        sha_.update(chunk_, (size_t)n);
        received_ += (uint32_t)n;
        nextSeq_++;
        lastData_ = now;
        return OtaErr::None;
    }

    // "ota_end": every byte there and the SHA-256 right -> the new firmware boots next time.
    OtaErr finish() {
        if (phase_ != OtaPhase::Receiving) return OtaErr::BadRequest;
        if (received_ != size_) return fail(OtaErr::Incomplete);
        uint8_t got[Sha256::SIZE];
        sha_.finish(got);
        if (!equalBytes(got, expected_, sizeof(got))) return fail(OtaErr::BadHash);
        if (!hal_.end()) return fail(OtaErr::Flash);
        phase_ = OtaPhase::Done;
        return OtaErr::None;
    }

    // "ota_abort", the phone disconnecting, power off. True if something was stopped.
    bool cancel() {
        if (phase_ == OtaPhase::Idle || phase_ == OtaPhase::Done) return false;
        if (phase_ == OtaPhase::Receiving) hal_.abort();
        phase_ = OtaPhase::Idle;
        return true;
    }

    // Call often: ends a question nobody answered or a transfer that stalled.
    OtaErr tick(uint32_t now) {
        if ((phase_ == OtaPhase::ConfirmUpdate || phase_ == OtaPhase::ConfirmPassword) &&
            (int32_t)(now - confirmUntil_) >= 0) {
            phase_ = OtaPhase::Idle;
            return OtaErr::Timeout;
        }
        if (phase_ == OtaPhase::Receiving && now - lastData_ > OTA_IDLE_MS) return fail(OtaErr::Timeout);
        return OtaErr::None;
    }

    // ---- read by the screen and the replies -----------------------------------------------
    OtaPhase phase() const { return phase_; }
    uint32_t size() const { return size_; }
    uint32_t received() const { return received_; }
    uint32_t nextSeq() const { return nextSeq_; }
    int percent() const { return size_ ? (int)((uint64_t)received_ * 100 / size_) : 0; }
    uint32_t confirmLeft(uint32_t now) const {
        int32_t left = (int32_t)(confirmUntil_ - now);
        return left > 0 ? (uint32_t)left : 0;
    }

private:
    void refreshLock(uint32_t now) {
        if (lockUntil_ && (int32_t)(now - lockUntil_) >= 0) { lockUntil_ = 0; fails_ = 0; }
    }

    // Uses up the nonce (right or wrong). nonceOut gets it for a follow-up HMAC.
    OtaErr checkProof(const char* proofHex, const char* purpose, const char* detail, uint32_t now,
                      uint8_t nonceOut[OTA_NONCE_LEN]) {
        if (!nonceValid_ || now - nonceAt_ > OTA_NONCE_MS) { nonceValid_ = false; return OtaErr::NoChallenge; }
        nonceValid_ = false;
        memcpy(nonceOut, nonce_, OTA_NONCE_LEN);
        uint8_t got[Sha256::SIZE], want[Sha256::SIZE];
        otaProof(key_, nonce_, purpose, detail, want);
        if (!proofHex || !hexDecode(proofHex, got, sizeof(got)) || !equalBytes(got, want, sizeof(want))) {
            if (++fails_ >= OTA_MAX_FAILS) {
                lockUntil_ = now + OTA_LOCK_MS;
                if (!lockUntil_) lockUntil_ = 1;
            }
            return OtaErr::BadPassword;
        }
        fails_ = 0;
        return OtaErr::None;
    }

    OtaErr fail(OtaErr e) {
        if (phase_ == OtaPhase::Receiving) hal_.abort();
        phase_ = OtaPhase::Idle;
        return e;
    }

    OtaHal& hal_;
    uint32_t maxSize_;
    bool hasKey_ = false;
    uint8_t key_[OTA_KEY_LEN] = {0};
    uint8_t pendingKey_[OTA_KEY_LEN] = {0};
    uint8_t nonce_[OTA_NONCE_LEN] = {0};
    bool nonceValid_ = false;
    uint32_t nonceAt_ = 0;
    int fails_ = 0;
    uint32_t lockUntil_ = 0;

    OtaPhase phase_ = OtaPhase::Idle;
    uint32_t confirmUntil_ = 0;
    uint32_t size_ = 0, received_ = 0, nextSeq_ = 0, lastData_ = 0;
    uint8_t expected_[Sha256::SIZE] = {0};
    Sha256 sha_;
    uint8_t chunk_[OTA_CHUNK];
};

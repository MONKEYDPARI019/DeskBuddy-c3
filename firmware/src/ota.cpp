#include "ota.h"
#include "config.h"
#include "app.h"
#include "buzzer.h"
#include "link.h"
#include "logic/ota_core.h"
#include <Arduino.h>
#include <Preferences.h>
#include <Update.h>
#include <esp_ota_ops.h>
#include <esp_random.h>
#include <sdkconfig.h>

namespace {

const char* const NS = "dbc3ota";              // own NVS namespace: 'defaults' keeps the password
const char* const KEY = "key";
constexpr uint32_t RESTART_MS = 1500;           // after success: let "ota_done" reach the phone
constexpr uint32_t KEEP_AFTER_MS = 5000;        // a new firmware that runs this long is kept

class FlashHal : public OtaHal {
public:
    bool begin(uint32_t size) override {
        if (Update.isRunning()) Update.abort();
        if (Update.begin(size, U_FLASH)) return true;
        Serial.printf("[OTA] cannot start: %s\n", Update.errorString());
        return false;
    }
    bool write(const uint8_t* data, size_t len) override {
        return Update.write(const_cast<uint8_t*>(data), len) == len;
    }
    bool end() override {
        if (Update.end(false)) return true;       // false: every byte must be there
        Serial.printf("[OTA] image rejected: %s\n", Update.errorString());
        return false;
    }
    void abort() override {
        if (Update.isRunning()) Update.abort();
    }
    bool saveKey(const uint8_t* key) override {
        Preferences p;
        if (!p.begin(NS, false)) return false;
        bool ok = key ? p.putBytes(KEY, key, OTA_KEY_LEN) == OTA_KEY_LEN : (!p.isKey(KEY) || p.remove(KEY));
        p.end();
        return ok;
    }
};

FlashHal hal;
OtaCore core(hal, 0);
char version[16] = "";
uint32_t doneAt = 0;
int lastLogged = -1;
bool keptChecked = false;

void toApp(const char* json) { linkSend(json); }

void sendError(ReplyFn reply, OtaErr e) {
    char buf[160];
    int n = snprintf(buf, sizeof(buf), "{\"type\":\"ota_error\",\"code\":\"%s\",\"msg\":\"%s\"", otaErrCode(e), otaErrText(e));
    if (e == OtaErr::BadPassword) n += snprintf(buf + n, sizeof(buf) - n, ",\"left\":%d", core.triesLeft());
    uint32_t locked = core.lockedFor(millis());
    if (locked) n += snprintf(buf + n, sizeof(buf) - n, ",\"wait\":%lu", (unsigned long)((locked + 999) / 1000));
    snprintf(buf + n, sizeof(buf) - n, "}");
    reply(buf);
}

// A question or an update ended without success: say why on the screen and the serial port.
void ended(OtaPhase was, OtaErr e) {
    linkFast(false);
    Serial.printf("[OTA] stopped: %s\n", otaErrText(e));
    if (was == OtaPhase::ConfirmPassword) appMessage("Password not set", otaErrText(e), 3000);
    else appMessage(e == OtaErr::Cancelled ? "Update cancelled" : "Update stopped", otaErrText(e), 4000);
    if (e != OtaErr::Declined && e != OtaErr::Cancelled) buzzerPlay(Sound::Error);
}

// With rollback in the bootloader, a new firmware is "pending" until it says it works; if it
// crashes before that, the next start goes back to the old one. Arduino would say so before
// setup() even runs; verifyRollbackLater() below makes it wait until 5 s of normal running.
// (A restart in those 5 s also goes back.) Without rollback this does nothing.
void keepIfRunningFine() {
    const esp_partition_t* running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (running && esp_ota_get_state_partition(running, &state) == ESP_OK && state == ESP_OTA_IMG_PENDING_VERIFY) {
        esp_ota_mark_app_valid_cancel_rollback();
        Serial.println("[OTA] the new firmware runs fine: kept");
    }
}

}  // namespace

#ifdef CONFIG_APP_ROLLBACK_ENABLE
extern "C" bool verifyRollbackLater() { return true; }
#endif

void otaBegin() {
    const esp_partition_t* slot = esp_ota_get_next_update_partition(nullptr);
    core.setMaxSize(slot ? slot->size : 0);
    Preferences p;
    uint8_t key[OTA_KEY_LEN];
    bool have = false;
    if (p.begin(NS, true)) {                     // read-only: fails harmlessly before the first save
        have = p.getBytes(KEY, key, sizeof(key)) == sizeof(key);
        p.end();
    }
    core.loadKey(have ? key : nullptr);
    Serial.printf("[OTA] update password %s, update slot %lu KB\n", have ? "set" : "not set",
                  (unsigned long)((slot ? slot->size : 0) / 1024));
}

bool otaHasPassword() { return core.hasKey(); }
bool otaBusy() { return core.phase() != OtaPhase::Idle; }

void otaLoop() {
    uint32_t now = millis();
    OtaPhase was = core.phase();
    OtaErr e = core.tick(now);
    if (e != OtaErr::None) {
        sendError(toApp, e);
        ended(was, e);
    }
    // the phone went away in the middle: nobody can finish it
    was = core.phase();
    if (was != OtaPhase::Idle && was != OtaPhase::Done && linkClients() == 0) {
        core.cancel();
        ended(was, OtaErr::LinkLost);
    }
    if (was == OtaPhase::Done && now - doneAt > RESTART_MS) {
        Serial.println("[OTA] restarting into the new firmware");
        linkShutdown();
        delay(100);
        ESP.restart();
    }
    if (!keptChecked && now > KEEP_AFTER_MS) {
        keptChecked = true;
        keepIfRunningFine();
    }
}

bool otaButton(const ButtonPress& p) {
    OtaPhase ph = core.phase();
    if (ph == OtaPhase::ConfirmUpdate || ph == OtaPhase::ConfirmPassword) {
        OtaErr e = core.confirm(p.btn == 1, millis());
        if (e != OtaErr::None) {
            sendError(toApp, e);
            ended(ph, e);
        } else if (ph == OtaPhase::ConfirmUpdate) {
            linkFast(true);                       // Bluetooth: short connection interval while it runs
            lastLogged = -1;
            char buf[64];
            snprintf(buf, sizeof(buf), "{\"type\":\"ota_ready\",\"chunk\":%u}", (unsigned)OTA_CHUNK);
            toApp(buf);
            buzzerPlay(Sound::Link);
            Serial.printf("[OTA] BTN1: receiving %lu bytes\n", (unsigned long)core.size());
        } else {
            toApp("{\"type\":\"ota_pass_ok\"}");
            appMessage("Password set", "for updates", 3000);
            buzzerPlay(Sound::Happy);
            appStateDirty();
            Serial.println("[OTA] update password set");
        }
        return true;
    }
    if (ph == OtaPhase::Receiving) {
        if (p.btn == 2 && p.ev == BtnEvent::Long) {    // long BTN2: stop it
            core.cancel();
            sendError(toApp, OtaErr::Cancelled);
            ended(ph, OtaErr::Cancelled);
        }
        return true;                                  // other presses: ignored while updating
    }
    return ph == OtaPhase::Done;
}

void otaNonce(ReplyFn reply) {
    uint8_t nonce[OTA_NONCE_LEN];
    esp_fill_random(nonce, sizeof(nonce));            // hardware RNG (the radio is on)
    uint32_t now = millis();
    core.newChallenge(nonce, now);
    char hex[2 * OTA_NONCE_LEN + 1];
    hexEncode(nonce, sizeof(nonce), hex);
    char buf[192];
    snprintf(buf, sizeof(buf),
             "{\"type\":\"ota_challenge\",\"nonce\":\"%s\",\"pass_set\":%s,\"locked\":%lu,\"build\":\"%s\",\"fw\":\"%s\"}",
             hex, core.hasKey() ? "true" : "false", (unsigned long)((core.lockedFor(now) + 999) / 1000), BUILD_NAME,
             FW_VERSION);
    reply(buf);
}

void otaStart(uint32_t size, const char* sha256, const char* proof, const char* ver, ReplyFn reply) {
    OtaErr e = core.begin(size, sha256, proof, millis());
    if (e != OtaErr::None) {
        sendError(reply, e);
        if (e == OtaErr::BadPassword || e == OtaErr::Locked) appMessage("Update refused", otaErrText(e), 3000);
        return;
    }
    strlcpy(version, ver ? ver : "", sizeof(version));
    appActivity();                                    // wake Mochi: the question must be readable
    buzzerPlay(Sound::Notify);
    reply("{\"type\":\"ota_confirm\",\"timeout\":30}");
    Serial.printf("[OTA] update to %s (%lu bytes) asked: BTN1 = yes, BTN2 = no\n", version, (unsigned long)size);
}

void otaPassword(const char* key, const char* proof, ReplyFn reply) {
    bool saved = false;
    OtaErr e = core.setPassword(key, proof, millis(), &saved);
    if (e != OtaErr::None) {
        sendError(reply, e);
        if (e == OtaErr::BadPassword || e == OtaErr::Locked) appMessage("Password refused", otaErrText(e), 3000);
        return;
    }
    if (saved) {
        reply("{\"type\":\"ota_pass_ok\"}");
        appMessage("Password changed", "for updates", 3000);
        buzzerPlay(Sound::Happy);
        Serial.println("[OTA] update password changed");
        return;
    }
    appActivity();
    buzzerPlay(Sound::Notify);
    reply("{\"type\":\"ota_confirm\",\"timeout\":30}");
    Serial.println("[OTA] set the update password? BTN1 = yes, BTN2 = no");
}

void otaData(uint32_t seq, const char* data, size_t len, ReplyFn reply) {
    OtaPhase was = core.phase();
    OtaErr e = core.data(seq, data, len, millis());
    if (e != OtaErr::None) {
        sendError(reply, e);
        if (was == OtaPhase::Receiving) ended(was, e);
        return;
    }
    char buf[80];
    snprintf(buf, sizeof(buf), "{\"type\":\"ota_ack\",\"seq\":%lu,\"got\":%lu}", (unsigned long)seq,
             (unsigned long)core.received());
    reply(buf);
    int pct = core.percent() / 10 * 10;
    if (pct != lastLogged) {
        lastLogged = pct;
        Serial.printf("[OTA] %d %%\n", pct);
    }
}

void otaFinish(ReplyFn reply) {
    OtaPhase was = core.phase();
    OtaErr e = core.finish();
    if (e != OtaErr::None) {
        sendError(reply, e);
        if (was == OtaPhase::Receiving) ended(was, e);
        return;
    }
    char buf[64];
    snprintf(buf, sizeof(buf), "{\"type\":\"ota_done\",\"restart_ms\":%lu}", (unsigned long)RESTART_MS);
    reply(buf);
    doneAt = millis();
    buzzerPlay(Sound::Happy, true);
    Serial.printf("[OTA] image OK (SHA-256 checked), %s boots next\n", version);
}

void otaCancel() {
    OtaPhase was = core.phase();
    if (core.cancel()) ended(was, OtaErr::Cancelled);
}

void otaCli(const char* sub, const char* arg) {
    if (!strcmp(sub, "set")) {
        size_t n = strlen(arg);
        if (n < 4 || n > 63) { Serial.println("otapass set <password>  (4-63 characters)"); return; }
        uint8_t key[OTA_KEY_LEN];
        otaKeyFromPassword(arg, key);
        Serial.println(core.setKeyDirect(key) ? "update password set" : "could not save it (NVS)");
        appStateDirty();
    } else if (!strcmp(sub, "clear")) {
        Serial.println(core.setKeyDirect(nullptr) ? "update password removed: set a new one in the app"
                                                  : "could not remove it (NVS)");
        appStateDirty();
    } else if (!*sub || !strcmp(sub, "status")) {
        const esp_partition_t* running = esp_ota_get_running_partition();
        Serial.printf("update password %s; running from %s\n", core.hasKey() ? "set" : "not set",
                      running ? running->label : "?");
    } else {
        Serial.println("otapass [set <password> | clear]");
    }
}

OtaView otaView(int* percent, uint32_t* secondsLeft, const char** ver) {
    *percent = core.percent();
    *secondsLeft = (core.confirmLeft(millis()) + 999) / 1000;
    *ver = version;
    switch (core.phase()) {
        case OtaPhase::ConfirmUpdate:   return OtaView::AskUpdate;
        case OtaPhase::ConfirmPassword: return OtaView::AskPassword;
        case OtaPhase::Receiving:       return OtaView::Receiving;
        case OtaPhase::Done:            return OtaView::Done;
        case OtaPhase::Idle:            break;
    }
    return OtaView::None;
}

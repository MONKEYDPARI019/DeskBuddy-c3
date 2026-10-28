// Bluetooth LE: Nordic UART Service (works with the DeskBuddy app and with
// generic apps such as nRF Connect / Serial Bluetooth Terminal).
//   RX 6E400002: the app writes JSON lines      TX 6E400003: we notify JSON lines
// Written for NimBLE-Arduino 2.x (pinned in platformio.ini).

#include "link.h"
#include "config.h"
#include "logic/framing.h"
#include <NimBLEDevice.h>

#define NUS_SERVICE "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_RX      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_TX      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

static NimBLEServer* server = nullptr;
static NimBLECharacteristic* tx = nullptr;
static volatile int clients = 0;
static volatile bool subscribed = false;
static volatile uint16_t mtu = 23;
static bool running = false;
static LineAssembler<MAX_LINE> rxLines;        // only used in the NimBLE host task

// connection interval in 1.25 ms units, supervision timeout in 10 ms units
constexpr uint16_t NORMAL_MIN = 24, NORMAL_MAX = 48, NORMAL_LATENCY = 4;   // 30-60 ms: frugal
constexpr uint16_t FAST_MIN = 6, FAST_MAX = 12;                            // 7.5-15 ms, no latency: updates
constexpr uint16_t SUPERVISION = 400;

class ServerCb : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* s, NimBLEConnInfo& info) override {
        clients = 1;
        mtu = 23;
        rxLines.reset();
        // 30-60 ms interval, latency 4, 4 s supervision timeout: quick but frugal
        s->updateConnParams(info.getConnHandle(), NORMAL_MIN, NORMAL_MAX, NORMAL_LATENCY, SUPERVISION);
        Serial.printf("[BLE] phone connected (%s)\n", info.getAddress().toString().c_str());
    }
    void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int reason) override {
        clients = 0;
        subscribed = false;
        Serial.printf("[BLE] phone disconnected (reason 0x%02X), advertising\n", reason);
        if (running) NimBLEDevice::startAdvertising();
    }
    void onMTUChange(uint16_t m, NimBLEConnInfo&) override { mtu = m; }
};

class TxCb : public NimBLECharacteristicCallbacks {
    void onSubscribe(NimBLECharacteristic*, NimBLEConnInfo&, uint16_t subValue) override {
        subscribed = subValue != 0;
    }
};

class RxCb : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* c, NimBLEConnInfo&) override {
        NimBLEAttValue v = c->getValue();
        rxLines.push((const char*)v.data(), v.length(),
                     [](const char* line, size_t len) { inboxPush(line, len); });
    }
};

static ServerCb serverCb;
static TxCb txCb;
static RxCb rxCb;

void bleBegin() {
    NimBLEDevice::init(BLE_NAME);
    NimBLEDevice::setMTU(247);
    NimBLEDevice::setPower(3);                     // dBm; plenty for a desk, saves battery

    server = NimBLEDevice::createServer();
    server->setCallbacks(&serverCb, false);       // static object: NimBLE must NOT delete it (it did -> crash)
    NimBLEService* svc = server->createService(NUS_SERVICE);
    tx = svc->createCharacteristic(NUS_TX, NIMBLE_PROPERTY::NOTIFY);
    tx->setCallbacks(&txCb);
    NimBLECharacteristic* rx = svc->createCharacteristic(NUS_RX, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
    rx->setCallbacks(&rxCb);

    NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
    adv->addServiceUUID(NUS_SERVICE);              // the app scans for this UUID
    adv->enableScanResponse(true);                 // before setName: name goes in the scan response
    adv->setName(BLE_NAME);
    adv->setMinInterval(160);                      // 100-200 ms
    adv->setMaxInterval(320);
    running = NimBLEDevice::startAdvertising();
    Serial.printf("[BLE] %s as '%s' (%s)\n", running ? "advertising" : "FAILED to advertise",
                  BLE_NAME, NimBLEDevice::getAddress().toString().c_str());
    running = true;
}

void bleService() {}

void bleSend(const char* json) {
    if (!tx || !clients || !subscribed) return;
    size_t chunk = mtu > 3 ? mtu - 3 : 20;
    // notify(data, len) copies each piece into its own buffer at once. (setValue() +
    // notify() only flags the value as changed and the stack reads it later, by when
    // the next piece may already have overwritten it: garbled JSON at the phone.)
    static bool failed;
    failed = false;
    frameChunks(json, chunk, [](const char* piece, size_t n) {
        if (failed) return;
        for (int tries = 0; tries < 10; tries++) {
            if (tx->notify((const uint8_t*)piece, n)) return;
            if (!clients) break;
            delay(2);                              // out of buffers: let the stack send some
        }
        failed = true;                             // drop the rest; the app asks again
    });
}

// During an update the phone sends ~1.4 MB: ask for the shortest interval and no slave latency
// (with latency 4 every write could wait up to 5 intervals). Back to frugal afterwards.
void bleFast(bool on) {
    if (!server || !clients) return;
    for (uint16_t h : server->getPeerDevices()) {
        if (on) server->updateConnParams(h, FAST_MIN, FAST_MAX, 0, SUPERVISION);
        else    server->updateConnParams(h, NORMAL_MIN, NORMAL_MAX, NORMAL_LATENCY, SUPERVISION);
    }
}

int bleClients() { return clients; }
LinkState bleState() { return !running ? LinkState::Off : clients ? LinkState::Online : LinkState::Advertising; }
String bleAddress() { return running ? String(NimBLEDevice::getAddress().toString().c_str()) : String(); }

void bleStop() {
    // Only used right before a restart or deep sleep, so just go quiet: stop
    // advertising and drop the phone. A full NimBLE deinit is not needed and
    // was the source of a crash when switching to WiFi.
    if (!running) return;
    running = false;
    NimBLEDevice::stopAdvertising();
    if (server) {
        for (uint16_t h : server->getPeerDevices()) server->disconnect(h);
    }
    delay(100);
    clients = 0;
    subscribed = false;
}

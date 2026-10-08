// WiFi mode: WebSocket server (the app), HTTP /notify, mDNS, OTA and NTP.
// Everything runs from the main loop; nothing here blocks for long:
//  - saved WiFi: connect in the background (no 20 s freeze at boot)
//  - no saved WiFi, or it fails for 30 s: the "DeskBuddy_C3_Setup" portal opens

#include "link.h"
#include "config.h"
#include "settings.h"
#include "ui.h"
#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <ArduinoOTA.h>
#include <WiFiManager.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include <time.h>

static WiFiManager* wm = nullptr;
static WebServer* http = nullptr;
static WebSocketsServer* ws = nullptr;
static bool running = false;
static bool services = false;
static bool portal = false;
static bool timeSynced = false;
static uint32_t connectStart = 0;
static int clients = 0;

constexpr uint32_t CONNECT_TIMEOUT_MS = 30000;

static void onWs(uint8_t num, WStype_t type, uint8_t* payload, size_t len) {
    switch (type) {
        case WStype_CONNECTED:
            clients = ws->connectedClients();
            Serial.printf("[WiFi] app #%u connected (%d)\n", num, clients);
            break;
        case WStype_DISCONNECTED:
            clients = ws->connectedClients();
            Serial.printf("[WiFi] app #%u left (%d)\n", num, clients);
            break;
        case WStype_TEXT:
            if (!inboxPush((const char*)payload, len)) Serial.println("[WiFi] message dropped (too long or busy)");
            break;
        default:
            break;
    }
}

// GET/POST /notify?app=WhatsApp&title=Mom&msg=Dinner  ->  same path as an app "notify"
static void handleNotify() {
    if (!settings.httpEnabled) { http->send(403, "text/plain", "disabled"); return; }
    JsonDocument doc;
    doc["type"]  = "notify";
    doc["app"]   = http->hasArg("app") ? http->arg("app") : "HTTP";
    doc["title"] = http->hasArg("title") ? http->arg("title") : "Notification";
    doc["body"]  = http->hasArg("msg") ? http->arg("msg") : http->arg("body");
    char line[MAX_LINE];
    size_t n = serializeJson(doc, line, sizeof(line));
    bool ok = n > 0 && n < sizeof(line) && inboxPush(line, n);
    http->send(ok ? 200 : 503, "text/plain", ok ? "OK" : "busy");
}

static void handleRoot() {
    char buf[200];
    snprintf(buf, sizeof(buf), "{\"device\":\"%s\",\"fw\":\"%s\",\"ip\":\"%s\",\"ws_port\":%u,\"clients\":%d}",
             FW_NAME, FW_VERSION, WiFi.localIP().toString().c_str(), settings.wsPort, clients);
    http->send(200, "application/json", buf);
}

static void startServices() {
    services = true;
    configTzTime(settings.tz, "pool.ntp.org", "time.google.com");
    if (MDNS.begin(HOSTNAME)) {                // deskbuddy-c3.local
        MDNS.setInstanceName(HOSTNAME);        // the app's FIND matches "c3" in this name
        MDNS.addService("http", "tcp", settings.httpPort);
        MDNS.addService("deskbuddy", "tcp", settings.wsPort);    // the app discovers _deskbuddy._tcp
        MDNS.addServiceTxt("deskbuddy", "tcp", "model", "c3");
        MDNS.addServiceTxt("deskbuddy", "tcp", "fw", FW_VERSION);
    } else {
        Serial.println("[WiFi] mDNS failed: use the IP address in the app");
    }
    ArduinoOTA.setHostname(HOSTNAME);
    // OTA blocks the loop while it runs, so the progress is drawn from here
    ArduinoOTA.onStart([]() { Serial.println("[OTA] update started"); uiOtaProgress(0); });
    ArduinoOTA.onProgress([](unsigned int done, unsigned int total) {
        static int last = -1;
        int pct = total ? (int)(done * 100ULL / total) : 0;
        if (pct != last) { last = pct; uiOtaProgress(pct); }
    });
    ArduinoOTA.onEnd([]() { uiOtaProgress(100); });
    ArduinoOTA.onError([](ota_error_t e) { Serial.printf("[OTA] error %u\n", e); uiOtaProgress(-1); });
    ArduinoOTA.begin();

    http = new WebServer(settings.httpPort);
    http->on("/", HTTP_GET, handleRoot);
    http->on("/notify", HTTP_GET, handleNotify);
    http->on("/notify", HTTP_POST, handleNotify);
    http->begin();

    ws = new WebSocketsServer(settings.wsPort);
    ws->onEvent(onWs);
    ws->enableHeartbeat(15000, 3000, 2);
    ws->begin();
    Serial.printf("[WiFi] online: %s  ws://%s.local:%u  (%s, %d dBm)\n", WiFi.localIP().toString().c_str(),
                  HOSTNAME, settings.wsPort, WiFi.SSID().c_str(), WiFi.RSSI());
}

// ESP32-C3 Super Mini boards have a poorly matched antenna: at full power
// (~20 dBm) the radio distorts, so phones cannot see its setup network and it
// often fails to join a router. 8.5 dBm is the well-known fix and still reaches
// across a room. Must be re-applied after every WiFi.mode() change.
static void radioPower() { WiFi.setTxPower(WIFI_POWER_8_5dBm); }

static void openPortal() {
    portal = true;
    wm->setConfigPortalBlocking(false);
    // with a saved network the portal closes after 3 min and the saved network is
    // tried again (a router that boots slowly after a power cut); without one it stays open
    wm->setConfigPortalTimeout(wm->getWiFiIsSaved() ? 180 : 0);
    wm->startConfigPortal(SETUP_AP);
    radioPower();
    Serial.printf("[WiFi] setup portal: join '%s' and open 192.168.4.1\n", SETUP_AP);
}

void wifiBegin() {
    running = true;
    WiFi.persistent(true);
    WiFi.setHostname(HOSTNAME);                // core 3: must come before WiFi.mode()
    WiFi.mode(WIFI_STA);
    radioPower();
    WiFi.setAutoReconnect(true);
    // No modem sleep: with it the C3 misses many multicast packets, so the app's
    // FIND (mDNS) and "deskbuddy-c3.local" fail and WebSocket replies lag.
    // Costs ~20 mA more; Bluetooth mode is the battery-friendly one.
    WiFi.setSleep(false);
    wm = new WiFiManager();
    wm->setDebugOutput(false);
    wm->setTitle("DeskBuddy C3");
    wm->setConnectTimeout(15);                 // a wrong password freezes the loop at most 15 s
    wm->setSaveConnectTimeout(15);
    if (wm->getWiFiIsSaved()) {
        WiFi.begin();                          // saved network, in the background
        radioPower();
        connectStart = millis();
        Serial.printf("[WiFi] connecting to '%s'...\n", wm->getWiFiSSID().c_str());
    } else {
        openPortal();
    }
}

void wifiService() {
    if (!running) return;
    bool up = WiFi.status() == WL_CONNECTED;

    if (portal) {
        wm->process();
        if (up) {
            if (wm->getConfigPortalActive()) wm->stopConfigPortal();
            portal = false;
            WiFi.mode(WIFI_STA);
            radioPower();
        } else if (!wm->getConfigPortalActive()) {   // portal timed out: try the saved network again
            Serial.println("[WiFi] portal closed, retrying the saved network");
            portal = false;
            WiFi.mode(WIFI_STA);
            radioPower();
            WiFi.begin();
            radioPower();
            connectStart = millis();
        }
    } else if (!up && !services && connectStart && millis() - connectStart > CONNECT_TIMEOUT_MS) {
        Serial.println("[WiFi] saved network not reachable, opening the setup portal");
        openPortal();                          // STA keeps retrying in the background
    }

    if (up && !services) startServices();
    if (services) {
        ArduinoOTA.handle();
        http->handleClient();
        ws->loop();
        if (!timeSynced && time(nullptr) > 1700000000) {
            timeSynced = true;
            Serial.println("[WiFi] time from NTP");
        }
    }
}

void wifiSend(const char* json) {
    if (ws && clients) ws->broadcastTXT(json);
}

int wifiClients() { return clients; }

LinkState wifiState() {
    if (!running) return LinkState::Off;
    if (portal) return LinkState::Portal;
    return WiFi.status() == WL_CONNECTED ? LinkState::Online : LinkState::Connecting;
}

String wifiAddress()  { return WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : String(); }
int    wifiRssi()     { return WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0; }
bool   wifiTimeSynced() { return timeSynced; }

void wifiForget() {
    if (!running) WiFi.mode(WIFI_STA);
    WiFi.disconnect(true, true);               // erase saved credentials (also turns the radio off)
    if (running) { Serial.println("[WiFi] restarting into the setup portal"); delay(200); ESP.restart(); }
    WiFi.mode(WIFI_OFF);
}

void wifiStop() {
    if (!running) return;
    running = false;
    if (ws) ws->close();
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    clients = 0;
}

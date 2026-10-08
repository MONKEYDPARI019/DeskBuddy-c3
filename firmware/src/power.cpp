#include "power.h"
#include "config.h"
#include "oled.h"
#include "leds.h"
#include "buzzer.h"
#include <Arduino.h>
#include <esp_sleep.h>
#include <driver/gpio.h>

static bool wokeByButton = false;

bool powerSupported() { return FEATURE_BATTERY; }
bool powerWokeByButton() { return wokeByButton; }

void powerWakeCheck() {
#if FEATURE_BATTERY
    gpio_hold_dis((gpio_num_t)PIN_BTN1);
    if (esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_GPIO) return;
    pinMode(PIN_BTN1, INPUT_PULLUP);
    uint32_t start = millis();
    while (digitalRead(PIN_BTN1) == LOW) {               // keep holding...
        if (millis() - start >= POWER_HOLD_MS) { wokeByButton = true; return; }
        delay(10);
    }
    // released too early: a bump in the pocket, go back to sleep
    esp_deep_sleep_enable_gpio_wakeup(1ULL << PIN_BTN1, ESP_GPIO_WAKEUP_GPIO_LOW);
    gpio_pullup_en((gpio_num_t)PIN_BTN1);
    gpio_hold_en((gpio_num_t)PIN_BTN1);
    esp_deep_sleep_start();
#endif
}

void powerOff(const char* reason) {
    Serial.printf("[Power] off: %s\n", reason);
    buzzerPlay(Sound::Bye, true);
    gfx.clearBuffer();
    gfx.setFont(u8g2_font_7x14B_tf);
    gfx.drawStr(64 - gfx.getStrWidth("Bye!") / 2, 30, "Bye!");
    gfx.setFont(u8g2_font_5x8_tf);
    const char* hint = "hold BTN1 3 s to wake";
    gfx.drawStr(64 - gfx.getStrWidth(hint) / 2, 50, hint);
    oledSend();
    uint32_t t = millis();
    while (millis() - t < 1200) { buzzerUpdate(); delay(5); }

    // wait for BTN1 to be released, or the chip wakes straight up again
    pinMode(PIN_BTN1, INPUT_PULLUP);
    t = millis();
    while (digitalRead(PIN_BTN1) == LOW && millis() - t < 10000) delay(10);
    delay(50);

    oledPower(false);
    ledsAllOff();
    buzzerOff();
    Serial.flush();
    esp_deep_sleep_enable_gpio_wakeup(1ULL << PIN_BTN1, ESP_GPIO_WAKEUP_GPIO_LOW);
    gpio_pullup_en((gpio_num_t)PIN_BTN1);
    gpio_hold_en((gpio_num_t)PIN_BTN1);              // keep the pull-up during deep sleep
    esp_deep_sleep_start();
}

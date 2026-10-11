# Hardware

DeskBuddy C3 fits on a small perfboard (zero board). This page lists the parts, shows where everything connects, and explains the battery build.

## Parts list

| Qty | Part | Notes |
|---|---|---|
| 1 | **ESP32-C3 Super Mini** | The tiny board with a USB-C port and a BOOT and a RESET button |
| 1 | **0.96" OLED, SSD1306, 128×64, I2C** | 4 pins: VCC, GND, SCL, SDA. Address 0x3C (0x3D also works). |
| 2 | Tactile push buttons (6×6 mm) | BTN1 and BTN2 |
| 2–3 | 3 mm or 5 mm LEDs: red, yellow, (green) | Green is optional |
| 2–3 | 330 Ω resistors | One per LED |
| 1 | **Passive** buzzer | Not an active one (see the note below) |
| 1 | 220 Ω resistor | For the buzzer |
| | Perfboard, wire, pin headers | |

**For the battery build, add:**

| Qty | Part | Notes |
|---|---|---|
| 1 | Single-cell Li-ion/LiPo, 3.7–3.8 V, ~1000–1500 mAh | Must have its protection board. A phone or hotspot battery works. |
| 1 | **TP4056 charger module with protection** | The 6-pad version (IN+, IN−, B+, B−, OUT+, OUT−) |
| 1 | SPDT slide switch | On/off for the battery |
| 2 | 220 kΩ resistors | Battery voltage divider |

> **Passive or active buzzer?** A passive buzzer usually has an open bottom (you can see the green circuit board) and no sticker. An active buzzer has a sealed bottom and often a "Remove seal after washing" sticker. An active buzzer can only make one fixed beep, so DeskBuddy's tunes need a passive one.

## Super Mini pinout

Seen from the top, with the USB-C port facing up. Check the labels on your board, because some clones differ.

```
              USB-C
          ┌───────────┐
     5V ──┤ ●       ● ├── GPIO5   green LED (optional)
      G ──┤ ●       ● ├── GPIO6   OLED SDA
    3V3 ──┤ ●       ● ├── GPIO7   OLED SCL
  GPIO4 ──┤ ●       ● ├── GPIO8   (onboard blue LED, keep free)
  GPIO3 ──┤ ●       ● ├── GPIO9   (BOOT button, keep free)
  GPIO2 ──┤ ●       ● ├── GPIO10  buzzer
  GPIO1 ──┤ ●       ● ├── GPIO20  BTN2
  GPIO0 ──┤ ●       ● ├── GPIO21  (serial TX, keep free)
          └───────────┘
  GPIO4 yellow LED · GPIO3 red LED · GPIO1 BTN1 · GPIO0 battery sense
  GPIO2: keep free (boot pin)
```

Don't use **GPIO 2, 8 or 9**: the chip reads them while starting up. **GPIO 18/19** carry the USB connection and aren't on the header.

## Wiring

| Part | Part pin | Connect to |
|---|---|---|
| **OLED** | VCC | **3V3**. Not 5V. |
| | GND | **G** |
| | SDA | **GPIO6** |
| | SCL | **GPIO7** |
| **BTN1** | one leg | **GPIO1** |
| | diagonally opposite leg | **G** |
| **BTN2** | one leg | **GPIO20** |
| | diagonally opposite leg | **G** |
| **Red LED** | long leg (+) | **GPIO3** through 330 Ω |
| | short leg (−) | **G** |
| **Yellow LED** | long leg (+) | **GPIO4** through 330 Ω |
| | short leg (−) | **G** |
| **Green LED** (optional) | long leg (+) | **GPIO5** through 330 Ω |
| | short leg (−) | **G** |
| **Buzzer** | + | **GPIO10** through 220 Ω |
| | − | **G** |

All the **G** connections go to one shared ground. The buttons need no resistors, because the firmware turns on the chip's internal pull-ups.

### Buttons: use diagonal legs

A 4-leg tactile button is really two pairs of legs. Each pair is joined inside the button all the time, and pressing the button connects the two pairs together.

```
   ┌─────────┐
 1 ┤         ├ 2      Diagonally opposite legs (1 + 4, or 2 + 3) are never in
   │    ○    │        the same pair, so they always work:
 3 ┤         ├ 4      one to the GPIO, the other to G.
   └─────────┘
```

Wiring two legs of the **same** pair makes the board think the button is held forever, or flickering. Mochi then changes face by himself, screens jump back to Mochi, and the radio may switch at boot. Use **diagonal legs**. If you're unsure, put a multimeter in beep mode: two legs that beep *without* pressing are the same pair.

### Build and test in this order

Test each part as you add it. It's much easier than debugging everything at once.

| Step | Add | Test with |
|---|---|---|
| 1 | Super Mini + OLED | `deskbuddy flash`, then `deskbuddy cmd i2c` should list **0x3C**, and Mochi appears |
| 2 | Buttons | In `deskbuddy monitor`, type `test buttons` and press each one: one `down`/`up` per press, nothing when untouched |
| 3 | LEDs | `test leds`: red, yellow, green, then all |
| 4 | Buzzer | `test buzzer`: rising beeps |
| 5 | Battery (optional) | See below |

## Battery build

The battery build adds a power switch, a battery icon on the clock screen, a low-battery warning (red LED fast blink and a sound), automatic power-off when the battery is empty, and **hold BTN1 for 3 s to switch off and on**.

### Battery wiring

```
            ┌──────────── TP4056 ────────────┐
 LiPo + ────┤ B+                        OUT+ ├──── slide switch ──── 5V  (Super Mini)
 LiPo − ────┤ B−                        OUT− ├───────────────────── G   (Super Mini)
            │      (charge via its own USB)  │
            └────────────────────────────────┘

 Battery sense:  TP4056 B+ ── 220 kΩ ──┬── 220 kΩ ── G
                                       └── GPIO0
```

| From | To |
|---|---|
| Battery + | TP4056 **B+** |
| Battery − | TP4056 **B−** |
| TP4056 **OUT+** | slide switch, then Super Mini **5V** |
| TP4056 **OUT−** | Super Mini **G** |
| TP4056 **B+** | 220 kΩ → **GPIO0** → 220 kΩ → **G** |

**Important rules:**

- **Use the 5V pin, never 3V3.** A full cell is 4.2 V, and the 3V3 pin goes straight to the chip, whose maximum is 3.6 V. The 5V pin feeds the board's own regulator.
- **Turn the slide switch OFF before plugging the Super Mini into a PC.** On many Super Minis, the USB 5 V connects straight to the 5V pin. With the switch on, the PC would push current back into the TP4056 and the battery.
- **Charge through the TP4056's own USB port**, not the Super Mini's.
- **Batteries with 3 contacts** (+, −, and T/ID/NTC, common in phone and hotspot batteries): use only + and −, and leave the middle one unconnected.
- **Keep the protection board** taped to the battery. Don't use a swollen battery, or one that reads below about 2.5 V.

### Then flash the battery build

```bash
deskbuddy flash --env battery
```

Check the reading with the serial command `test battery`, and compare it with a multimeter on the battery. If it's off, correct it with `set bat_off <difference in mV>`, for example `set bat_off 40` when the board reads 40 mV low.

### How it behaves

| Battery | What happens |
|---|---|
| 4.2 V → ~3.5 V | Normal. The board gets a steady 3.3 V. |
| ≤ 10 % | Red LED fast blink, a warning tone, and "Battery low" on screen |
| Below 3.35 V for 30 s | "Bye!", then it switches itself off (deep sleep) |
| Switched off | Hold **BTN1 for 3 s** to switch on. A shorter press goes back to sleep. |

A "3.8 V" cell (a high-voltage type from phones and hotspots) is fine. The TP4056 charges it to 4.2 V, which is safe; you just get about 10 % less capacity than its maximum.

**Rough runtime on 1500 mAh:**

| Mode | Runtime |
|---|---|
| Bluetooth, screen on | 25–35 h |
| WiFi | 12–18 h |
| Switched off | weeks (the Super Mini's power LED keeps drawing a little; use the slide switch for storage) |

> **Battery build without the divider?** Then GPIO0 is left floating and reads random voltages. The firmware ignores readings until they look like a real cell for 3 seconds, but the safest fix is a single 100 kΩ resistor from GPIO0 to G, until you fit the divider. If you don't want battery features at all, flash the USB build. The slide switch still works as an on/off switch.

## Notes and gotchas

- **WiFi range:** the Super Mini's small antenna is weak. The firmware lowers the WiFi transmit power to 8.5 dBm, which makes the signal cleaner, and is the known fix for its setup network being invisible. Keep metal and fingers away from the antenna end (the end opposite the USB port).
- **OLED power:** the OLED must be on **3V3**. If it ever goes blank because of a loose wire, the firmware notices within about 3 s and restarts it by itself when it answers again.
- **The red power LED** on the Super Mini can stay. It costs a little battery when switched off, but removing it risks damaging the board.

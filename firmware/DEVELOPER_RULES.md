# Captor Core — Firmware Developer Rules & Guidelines

> [!IMPORTANT]
> **CRITICAL PROTOCOL REQUIREMENT**  
> Do **NOT** revert the firmware to the old `Adafruit_SSD1306` library, the `115200` baud rate, or the ASCII-hex text parser (`incomingWord.length() == 2048`). The host application has been fully migrated to stream high-frame-rate **raw binary graphics** (20 FPS) using a custom packet format. Changing the protocol or baud rate in the firmware will break the connection entirely.

---

## 1. Serial Protocol Specification

The host application communicates using a **binary framing protocol** (instead of newlines or ASCII strings) to maximize throughput and minimize processing overhead on the ESP32-C3.

### Packet Format
All incoming data packets are structured as follows:

| Byte Index | Field | Value / Type | Description |
| :--- | :--- | :--- | :--- |
| `0` | Magic Byte 1 | `0xAA` | Frame Synchronization Header |
| `1` | Magic Byte 2 | `0x55` | Frame Synchronization Header |
| `2` | Magic Byte 3 | `0xAA` | Frame Synchronization Header |
| `3` | Magic Byte 4 | `0x55` | Frame Synchronization Header |
| `4` | Packet Type | `0x01` or `0x02` | `0x01`: Raw Binary Frame (1024 bytes)<br>`0x02`: ASCII Command String |
| `5` | Length High | `uint8_t` | High byte of payload length (`length >> 8`) |
| `6` | Length Low | `uint8_t` | Low byte of payload length (`length & 0xFF`) |
| `7+` | Payload | `bytes` | Binary image data (1024 bytes) or null-terminated command string |

### Packet Types
1. **`0x01` (Binary Frame)**: Contains exactly `1024` bytes representing the 128x64 display buffer (1 bit per pixel). Upon receiving a complete frame, the display buffer must draw the bitmap and print `[ACK]\n` to the serial port.
2. **`0x02` (Command String)**: A string payload for control operations:
   - `PING`: Board must reply with `[PONG]\n` immediately.
   - `BRIGHT:<val>`: Contrast control (`val` between `0` and `255`).
   - `INVERT:<val>`: Invert display colors (`1` = Inverted, `0` = Normal).

---

## 2. Baud Rate & Buffer Optimizations

To render smooth, real-time animations at 20 FPS, the serial connection must remain stable and lag-free:

*   **Baud Rate**: **Must be set to `460800`** (both in the firmware and the host scripts).
*   **Hardware Buffer Size**: The default 256-byte serial buffer will overflow during the I2C update cycle (which blocks the CPU for ~25ms). **`Serial.setRxBufferSize(4096);` must be called in `setup()` prior to `Serial.begin(BAUD);`**. This allocates a 4KB hardware buffer so no bytes are dropped while the display is writing.

---

## 3. Parser Watchdog Timer

If a byte is dropped or corrupted, the state machine can get desynchronized. 
*   A `packetStartTime` tracker is recorded when the magic sequence starts parsing.
*   If the parser stays in a non-idle state for **more than 100ms**, it must automatically reset to `STATE_MAGIC_1`. 
*   *Do not check byte-arrival intervals for the watchdog*, as a continuous flow of corrupt data will reset the interval timer and trap the parser indefinitely.

---

## 4. Hardware Display Configuration

*   **Driver & Library**: Use the **`U8g2`** library with the **`SSD1309`** hardware driver. Adafruit_SSD1306 does not initialize the 2.4" Waveshare OLED module correctly due to address and pre-charge differences.
*   **Initialization Constructor**: 
    ```cpp
    U8G2_SSD1309_128X64_NONAME0_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);
    ```
*   **I2C Addressing**: The 2.4" Waveshare display is strapped to address `0x3D` (7-bit), which translates to **`0x7A` in U8g2's 8-bit addressing model**. Use `u8g2.setI2CAddress(0x7A);`.
*   **Pins**: SDA must be mapped to **GPIO 8** and SCL to **GPIO 9** for the ESP32-C3 SuperMini board.

### SSD1309 Hardware Register Override Rules
Standard SSD1306 registers cause horizontal banding and dimming on SSD1309 panels. The following commands **must** be sent to the display in `setup()` immediately after `u8g2.begin()`:
```cpp
u8g2.sendF("ca", 0xD9, 0xF1); // Max Pre-charge Period (Phase 1 = 1 clock, Phase 2 = 15 clocks) to equalize column brightness
u8g2.sendF("ca", 0xDB, 0x40); // High VCOMH Deselect Level (0.83 x VCC) to prevent row/column crosstalk
u8g2.sendF("ca", 0xD5, 0x70); // Standard Display Clock Frequency for stable, flicker-free rendering
```

---

## 5. Momentary Switch & State Rules

A tactile mechanical switch on **GPIO 3** toggles display power:
*   Use internal pull-up (`INPUT_PULLUP`).
*   **Sleep Mode**: Clears the display buffer, writes it to clear the screen, and sends `SSD1306_DISPLAYOFF` (`u8g2.setPowerSave(1)`) to put the screen into hardware deep sleep.
*   **Wake Mode**: Wakes the display (`u8g2.setPowerSave(0)`) and immediately redraws the last frame stored in `imgBuffer`.
*   **Background Processing**: While the button loop blocks waiting for a button release (`while (digitalRead(SWITCH_PIN) == LOW)`), it **must continue running `handleSerial()`** to ensure the RX buffer does not overflow and drop frames.

---

## 6. Welcome Boot Animation (BOSE Jackpot Slot Machine Reels)

*   **3D Cylinder Projection (Circular Disk Perspective)**: The welcome screen projects the characters' positions using a linear cylinder mapping:
    *   **Projected Position**: `y_proj = Y_CENTER + diff_y` (linear vertical mapping).
    *   **Back-face Culling**: Characters are only drawn when on the front half of the cylinder (`abs(diff_y) <= 80.0`).
    *   **Custom Vin Mono Pro Bitmaps (Multi-Size)**: The character bitmaps are embedded in `vin_mono_reels.h` in three sizes and selected based on `diff = abs(y_proj - 32.0)` to fake a 3D perspective:
        *   **Large (16x24)**: Drawn close to the active center line (`diff <= 10.0`).
        *   **Medium (12x18)**: Drawn in the transition zone (`10.0 < diff <= 22.0`).
        *   **Small (8x12)**: Drawn near the top/bottom edges (`diff > 22.0`), faking a cylinder compression.
*   **Gridless Layout**: Rejects all slot frames, borders, divider lines, arrows, and viewport boxes, rendering 4 clean, floating vertical reels aligned horizontally.
*   **Jackpot Rollers Physics**: Simulates 4 independent vertical slot machine rollers brought closer horizontally with a **4px gap** (column centers at `34`, `54`, `74`, and `94` pixels).
    *   **Ease-In Acceleration**: Rollers start at `0` speed and accelerate smoothly to their individual randomized max speeds (`12.0` to `20.0` pixels/frame).
    *   **Spin Forever**: While disconnected, the reels spin endlessly in a smooth `40 FPS` animation.
*   **Staggered Stopping Sequence**: When the PC software connects:
    *   Reels begin decelerating sequentially (staggered by `300ms` intervals: Reel 0 stops first, then Reel 1, Reel 2, Reel 3).
    *   Each reel uses exact physics calculations to determine the deceleration path, shifting position dynamically on trigger to align and stop **perfectly** on the target letters: **`B`**, **`O`**, **`S`**, **`E`** (index 9 on the 10-char strips).
    *   Once all reels have come to a complete stop, the display holds the static "BOSE" jackpot line for exactly `800ms` before seamlessly transitioning to host graphics.
    *   If connection is lost, all reels reset and begin spinning again.
*   **Optimization**: Drawing is throttled to exactly `25ms` per frame (40 FPS) to ensure buttery smooth animation while preventing CPU starvation. During deceleration and idle phases, screen updates are only drawn when reels move or connection state transitions.




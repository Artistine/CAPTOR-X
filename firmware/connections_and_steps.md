# Captor X (ESP32-C3 SuperMini) Connections & Flashing Guide

This document provides a visual pinout diagram, hardware wiring schematics, and step-by-step flashing instructions for the **Captor X** display client.

---

## 1. ESP32-C3 SuperMini Pinout & Wiring Diagram

Below is the physical pinout mapping for the ESP32-C3 SuperMini development board.

##### Physical Pin Layout (ASCII Diagram)
```
                  ESP32-C3 SuperMini
                     +------------+
                G5 | [ ]    [ ] | 5V
                G6 | [ ]    [ ] | G   (GND - OLED/Switch GND)
                G7 | [ ]    [ ] | 3.3 (3.3V - OLED VCC)
(OLED SDA/LED)  G8 | [ ]    [ ] | G4
(OLED SCL/BOOT) G9 | [ ]    [ ] | G3  (Button Pin 1)
               G10 | [ ]    [ ] | G2
               G20 | [ ]    [ ] | G1
               G21 | [ ]    [ ] | G0
                     +---[USB-C]--+
```

### Wiring Table
Connect your 0.96-inch OLED screen and momentary mechanical switch (like a blue keyboard switch) to the board as follows:

| Component | Component Pin | ESP32-C3 Pin | Location on Board |
| :--- | :--- | :--- | :--- |
| **OLED Display** | VCC | 3.3V | `3.3` (Right side, 3rd pin from top) |
| **OLED Display** | GND | GND | `G` (Right side, 2nd pin from top) |
| **OLED Display** | SDA | GPIO 8 | `G8` (Left side, 4th pin from top) |
| **OLED Display** | SCL | GPIO 9 | `G9` (Left side, 5th pin from top) |
| **Momentary Switch** | Pin 1 | GPIO 3 | `G3` (Right side, 5th pin from top) |
| **Momentary Switch** | Pin 2 | GND | `G` (Right side, 2nd pin from top) |

---

## 2. Flashing Steps

### Option A: VS Code & PlatformIO (Recommended)
1. Launch **VS Code**.
2. Make sure the **PlatformIO IDE** extension is installed.
3. Open the folder: `firmware/CAPTION CAST/`
4. Connect the ESP32-C3 SuperMini to your computer with a USB-C data cable.
5. Compile and build the code: Press **`Ctrl+Alt+B`** (or click the Checkmark icon in the bottom status bar).
6. Upload the firmware: Press **`Ctrl+Alt+U`** (or click the Arrow icon in the bottom status bar).

### Option B: Arduino IDE
1. Open the Arduino IDE.
2. Go to **File > Preferences** and add the following URL under "Additional boards manager URLs":
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. Go to **Tools > Board > Boards Manager...**, search for `esp32`, and click **Install**.
4. Install libraries under **Sketch > Include Library > Manage Libraries...**:
   * Search for and install **Adafruit SSD1306**
   * Search for and install **Adafruit GFX Library**
5. Configure your settings under **Tools**:
   * **Board**: `ESP32C3 Dev Module`
   * **USB CDC On Boot**: `Enabled` *(Critical for communication!)*
   * **Flash Size**: `4MB`
   * **Partition Scheme**: `Default 4MB with spiffs`
   * **Port**: Select the COM port corresponding to your connected ESP32-C3.
6. Open the sketch [captioncast_esp32.ino](file:///d:/downloads/captioncast/captioncast/captioncast_esp32/captioncast_esp32.ino) and click **Upload** (right arrow).

> [!TIP]
> **If Upload Fails to Connect:**
> If you see `Failed to connect to ESP32-C3: No serial data received.`, enter ROM bootloader mode manually:
> 1. Press and hold the physical **BOOT** button on the SuperMini board.
> 2. Click the physical **RESET** button once.
> 3. Release the **BOOT** button.
> 4. Click **Upload** in PlatformIO/Arduino IDE again.
> 5. After the upload finishes, press the **RESET** button once to start the app.

---

## 3. How to Connect with the PC Software

1. **Verify Startup State**:
   * When powered on, the OLED display should show only a **spinning loading animation** (indicating it is waiting for PC serial communication).
   * Click your mechanical switch once to test the screen power toggle (the display should turn off completely). Click it again to turn it back ON.
2. **Launch the Software**:
   * Go to the project root directory and double-click **`run_webview.bat`** to start the high-fidelity HTML/React Webview interface.
3. **Connect the App**:
   * In the desktop application interface, click **AUTO CONNECT ↗** (or select the COM port of your ESP32-C3 SuperMini and click apply settings).
   * The status indicator at the bottom will turn green: **● Connected COMx**.
   * The OLED screen will instantly transition from the loading animation and begin **casting** the active app view (your live captions, PC stats dashboard, or animated dithered GIFs!).

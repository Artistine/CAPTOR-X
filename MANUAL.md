# CaptionCast - Hardware Build & Assembly Manual

This document details the exact Bill of Materials (BOM), wiring pinouts, firmware compilation, and desktop software setup required to build and run the **CaptionCast** desktop display device.

---

## 1. Bill of Materials (BOM)

To build the physical CaptionCast desktop screen, you need the following components:

| Item | Component | Qty | Description | Approx. Price |
| :--- | :--- | :---: | :--- | :---: |
| 1 | **ESP32-C3 SuperMini** | 1 | A compact, low-cost microcontroller board with built-in USB-C. | \$3.00 |
| 2 | **SSD1309 OLED Display (128x64)** | 1 | 2.42-inch monochrome OLED module with an I2C interface. | \$10.00 |
| 3 | **Momentary Keyboard Switches** | 2 | Mechanical keyboard switches (e.g. Cherry MX, Outemu Red) for manual inputs. | \$1.00 |
| 4 | **3D Printed Enclosure** | 1 | A desktop casing to mount the ESP32, switches, and OLED module. | - |
| 5 | **Connecting Wires & Solder** | - | 28 AWG wire for internal hookups. | - |

---

## 2. Wiring & Pinout Diagram

Connect the components according to the pin mapping below:

```
                  ┌───────────────────────┐
                  │   ESP32-C3 SuperMini  │
                  └───────────┬───────────┘
         ┌────────────┬───────┴───────┬────────────┐
         │            │               │            │
      [Pin 8]      [Pin 9]         [Pin 3]      [Pin 20]
         │            │               │            │
     (OLED SDA)   (OLED SCL)      (Power SW)   (Mode Cycle SW)
         │            │               │            │
         ▼            ▼               ▼            ▼
   ┌───────────┐┌───────────┐   ┌───────────┐┌───────────┐
   │ SSD1309   ││ SSD1309   │   │ Momentary ││ Momentary │
   │ SDA Pin   ││ SCL Pin   │   │ Switch 1  ││ Switch 2  │
   └───────────┘└───────────┘   └─────┬─────┘└─────┬─────┘
                                     │            │
                                  [ GND ]      [ GND ]
```

### Pinout Table

| ESP32-C3 Pin | Target Component Pin | Description |
| :---: | :--- | :--- |
| **3V3 / 5V** | OLED `VCC` | Power supply for the OLED screen |
| **GND** | OLED `GND` | Common ground path |
| **GPIO 8** | OLED `SDA` | I2C Data line |
| **GPIO 9** | OLED `SCL` | I2C Clock line |
| **GPIO 3** | Switch 1 `Pin 1` | Shutter / Power engine toggle (internal pull-up enabled) |
| **GPIO 20** | Switch 2 `Pin 1` | Display mode cycle (internal pull-up enabled) |
| **GND** | Switch 1 & 2 `Pin 2` | Active-low ground returns for switches |

---

## 3. Firmware Installation

The firmware runs on PlatformIO (using the Arduino framework).

### Steps to flash the ESP32-C3:
1. **Install VS Code & PlatformIO Extension**: Download and install Visual Studio Code, then add the **PlatformIO IDE** extension.
2. **Open the Firmware Project**: Open the folder [`firmware/CAPTION CAST`](file:///d:/downloads/captioncast/captioncast/firmware/CAPTION%20CAST) inside VS Code.
3. **Configure `platformio.ini`**: Ensure your config matches the following:
   ```ini
   [env:supermini-c3]
   platform = espressif32
   board = esp32-c3-devkitm-1
   framework = arduino
   monitor_speed = 460800
   lib_deps =
       olikraus/U8g2@^2.35.9
   ```
4. **Compile & Upload**:
   - Connect the ESP32-C3 SuperMini to your PC via a USB-C cable.
   - Click the **Upload** arrow at the bottom status bar in VS Code/PlatformIO.
   - Once successfully flashed, the OLED screen will display the boot roll screen.

---

## 4. Desktop Client Setup

The host-side controller runs on Python 3.11 and packages into a standalone executable.

### Setup Steps:
1. **Install Python**: Download and install Python 3.11. Ensure "Add Python to PATH" is checked.
2. **Install Dependencies**: Open a terminal in the project directory and run:
   ```powershell
   pip install -r requirements.txt
   ```
3. **Build the Web Control Panel**:
   ```powershell
   cd gui/captor-hub
   npm install
   npm run build
   cd ../..
   ```
4. **Compile the Standalone Windows Executable**:
   ```powershell
   python -m PyInstaller -y captioncast.spec
   ```
   The compiled executable will be located in [`dist/CaptorCoreRelease/CaptorCore.exe`](file:///d:/downloads/captioncast/captioncast/dist/CaptorCoreRelease/CaptorCore.exe).

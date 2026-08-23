# Captor Core — ESP32-C3 SuperMini Setup & Flashing Walkthrough

This guide details how to wire, configure, flash, and verify the **Captor Core** (formerly CaptionCast Pro) client-side firmware on the **ESP32-C3 SuperMini** paired with a **0.96-inch 128x64 I2C SSD1306 OLED display** and a **momentary mechanical switch** (e.g., a blue mechanical keyboard switch).

---

## 1. Summary of Firmware Modifications

To support your hardware and provide a seamless client-casting experience, the PlatformIO firmware in [main.cpp](file:///d:/downloads/captioncast/captioncast/firmware/CAPTION%20CAST/src/main.cpp) has been configured as follows:

*   **Client Casting Model**: The OLED display acts purely as a client casting the PC app's preview screen.
*   **Buffering Animation**: If the PC app is not connected or stops streaming (no data for >2 seconds), the ESP32 will locally render a spinning retro loading animation on the screen.
*   **Momentary Switch Display Toggle**: A keyboard switch (like a blue mechanical switch) connected to **GPIO 3** toggles the display power state:
    *   **First Press**: Clears the screen and puts the OLED into hardware deep sleep (`SSD1306_DISPLAYOFF`), reducing power consumption to zero.
    *   **Second Press**: Wakes the OLED (`SSD1306_DISPLAYON`) and immediately restores the active cast screen or the loading animation.
    *   **Background Processing**: While the button is held down, the ESP32 continues to process serial data in the background to prevent dropping any data packets.
*   **I2C Pin Selection**: Pins are configured to **GPIO 8 (SDA)** and **GPIO 9 (SCL)** to match the hardware defaults labeled on the ESP32-C3 SuperMini pinout. Connecting the OLED display using these pins is safe because their default I2C pull-up states satisfy the required strapping voltage levels at reset.
*   **Onboard LED Sharing**:
    *   GPIO 8 functions as both I2C SDA and the onboard blue LED. Consequently, the LED will naturally flicker as data streams to the screen, providing a built-in activity indicator.
    *   To avoid bus lockups, dedicated error blinking on GP8 has been disabled. If the OLED display is not connected or fails to initialize, the board will output diagnostic warnings over the USB serial connection.

---

## 2. Hardware Wiring Diagram

Connect the 0.96-inch OLED screen and the momentary mechanical switch to the ESP32-C3 SuperMini using the following pins:

### OLED Screen to ESP32-C3
| OLED Screen Pin | ESP32-C3 SuperMini Pin | Location on Board | Description |
| :--- | :--- | :--- | :--- |
| **VCC** | **3.3V** | `3.3` (Right side, 3rd pin from top) | Power supply (3.3V) |
| **GND** | **GND** | `G` (Right side, 2nd pin from top) | Ground |
| **SDA** | **GPIO 8** | `G8` (Left side, 4th pin from top) | I2C Data Line |
| **SCL** | **GPIO 9** | `G9` (Left side, 5th pin from top) | I2C Clock Line |

### Mechanical Switch to ESP32-C3
| Switch Terminal | ESP32-C3 SuperMini Pin | Location on Board | Description |
| :--- | :--- | :--- | :--- |
| **Terminal 1** | **GPIO 3** | `G3` (Right side, 5th pin from top) | Button Input Pin (Internal Pull-Up enabled) |
| **Terminal 2** | **GND** | `G` (Right side, 2nd pin from top) | Ground pin |

---

## 3. VS Code / PlatformIO Setup & Configuration (Recommended)

A pre-configured PlatformIO project is available in the [firmware/CAPTION CAST/](file:///d:/downloads/captioncast/captioncast/firmware/CAPTION%20CAST/) directory.

### Step A: Open the Project in VS Code
1. Open **VS Code**.
2. Install the **PlatformIO IDE** extension from the Extensions panel (`Ctrl+Shift+X`).
3. Click the PlatformIO Home icon in the status bar (or side panel) and select **Open Project**.
4. Navigate to and open the `firmware/CAPTION CAST/` folder.

### Step B: Project Configuration
The project is configured in [platformio.ini](file:///d:/downloads/captioncast/captioncast/firmware/CAPTION%20CAST/platformio.ini) as follows:
* **Board Profile**: `board = esp32-c3-devkitm-1`
* **USB-CDC Build Flags**: 
  ```ini
  build_flags = 
      -DARDUINO_USB_MODE=1
      -DARDUINO_USB_CDC_ON_BOOT=1
  ```
  *(These flags enable hardware CDC serial port mapping directly on boot. This is critical for the ESP32-C3's native USB port to register as a COM port on your PC.)*
* **Libraries**: `lib_deps` defines the required `olikraus/U8g2` library which PlatformIO will download and configure automatically.

### Step C: Build and Upload
1. Connect your ESP32-C3 SuperMini to your PC via a USB-C data cable.
2. Click the **Build** (checkmark) icon in the PlatformIO status bar (or use `Ctrl+Alt+B`).
3. Click the **Upload** (right arrow) icon (or use `Ctrl+Alt+U`) to compile and flash the firmware.

## 4. Troubleshooting Upload Failures

If the upload fails to connect to the chip:
1. Press and hold the physical **BOOT** button on the SuperMini board.
2. Press the physical **RESET** button once.
3. Release the **BOOT** button. (This forces the ESP32-C3 into ROM bootloader upload mode).
4. Trigger the **Upload** command again.
5. Once flashing completes, press the **RESET** button once to boot the board normally.

---

## 5. Verification & Testing

Once flashed, check the physical board:
1. **OLED Startup**: When the board boots with the switch ON, the OLED display should turn on and show the spinning dot buffering animation.
2. **Toggle Button Test**:
   * Click the mechanical button once. The OLED should turn off completely (black screen).
   * Click the button again. The OLED should turn on and resume showing the animation.
3. **Onboard LED Status**:
   * If the onboard blue LED **is off** (or steady high/low without flashing), the OLED initialized successfully and is waiting for data.
   * If the onboard blue LED **is flashing rapidly**, there is an I2C communication error. Check your wiring connections (SDA/SCL) and make sure VCC and GND are securely connected.
4. **PC App Connection**:
   * Open the Python GUI controller by running `python captioncast.py` (or `python captioncast_webview.py` for the Webview GUI).
   * Click **RE-SCAN ↗** or choose the COM port matching your ESP32-C3.
   * Alternatively, click **AUTO CONNECT ↗**. The PC app will send a `[PING]\n` command, and the ESP32-C3 SuperMini will instantly reply with `[PONG]\n`, establishing a connection.
   * The status bar at the bottom will display **● Connected COMx** in green.
   * Once connected, the screen instantly switches from the loading animation to cast the active display (captions, PC stats, or GIF).
   * Turning the display OFF via the toggle button does not disrupt serial data parsing; turning it back ON instantly restores the active screen.

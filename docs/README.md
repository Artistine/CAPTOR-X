# Captor Core

Realtime speech → OLED display. The PC app captures system playback audio directly, transcribes it to text locally using machine learning models, and streams pixel-perfect graphics over a USB serial connection to a physical Captor X driven SSD1306 OLED screen (128x64).

---

## Features

- **Native System Loopback Capture**: Captures PC speaker output directly using Windows WASAPI loopback (no microphones required).
- **GPU-Accelerated Transcription**: Uses `faster-whisper` running on CUDA 12 (falling back to CPU automatically).
- **Premium Retro-Brutalist GUI**: Styled with the custom **Vin Mono Pro** font family (Regular, Bold, Thin) in a portrait vertical layout (geometry `740x740`) with rounded corner fillets, a solid black backdrop (`#000000`), and borderless deep gray panels (`#121212`).
- **Upscaled Realtime Preview**: A 3x upscaled `384x192` simulation of the OLED display showing layouts, active waveforms, and VU meters.
- **English Focus**: Speech auto-detect filters out non-English languages and displays the idle waveform.
- **Nudge Text Controls**: ◄, ▲, ▼, ► direction D-pad buttons to adjust the X and Y coordinates of custom fonts by ±1px increments.
- **Music Mode & Visualizer Selector**: Includes a Music Mode toggle to disable silence clearing timeout and Whisper VAD, alongside selector dropdowns for idle visualizers (Sine Wave, Stereo Bars, Radial Ring).
- **GIF Player Mode**: Load and play custom animated GIFs on the physical OLED screen with controls for scaling (aspect ratio vs. stretch), playback speed multiplier (0.25x to 3.0x), dithering (Threshold vs. Floyd-Steinberg), threshold level, and color inversion.
- **PC Stats Dashboard**: Display live PC performance metrics in a custom retro-brutalist layout: Ryzen CPU Name, Frequency, CPU Temperature (native driver-level query via bundled dll), GPU Name, Temp, Core Clock, GPU utilization, and Video Memory (VRAM) usage in Gigabytes (e.g. `Mem: 2.4GB`). Falls back to RAM, Disk usage, and local time if GPU monitoring is disabled.
- **Settings Persistence**: Saves all configurations to `%APPDATA%\CaptorCore\config.json` and auto-reconnects to the last used serial port on start.

---

## PC App Setup (Development)

1. Install Python 3.10 or 3.11 from [python.org](https://www.python.org/)
2. Open terminal in this folder and install dependencies:
   ```cmd
   pip install faster-whisper pyserial customtkinter sounddevice numpy pyaudiowpatch Pillow
   ```
3. *(Optional)* For Nvidia GPU acceleration:
   ```cmd
   pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cuda-nvrtc-cu12
   ```
4. Run the app:
   - For the **HTML/React UI (PyWebView Dashboard)**:
     Double-click the **`run_webview.bat`** file in the project root directory. (Note: The dashboard window uses a fixed-aspect ratio and is non-resizable to prevent black margins).
   - For the **Tkinter Portrait UI**:
     Double-click the **`run_dev.bat`** file in the project root directory.
   - Alternatively, execute the scripts directly from your console:
     ```cmd
     "C:\Users\sushi\AppData\Local\Programs\Python\Python311\python.exe" captioncast_webview.py
     ```
     or
     ```cmd
     "C:\Users\sushi\AppData\Local\Programs\Python\Python311\python.exe" captioncast.py
     ```

> [!TIP]
> Launching either the python scripts (which will self-elevate) or the compiled `CaptorCore.exe` will trigger a standard Windows User Account Control (UAC) prompt to request Administrator privileges. This is required for the application to access ring 0 driver telemetry to read CPU temperatures.

---

## Re-building the Standalone Binary (.exe)

To build a standalone executable that packages all dependencies and CUDA libraries:
```cmd
pip install pyinstaller
pyinstaller --noconfirm captioncast.spec
```
The final packaged application will be built in `dist/CaptorCore/` (with the main executable at `dist/CaptorCore/CaptorCore.exe`).

---

## Creating the Windows Setup Installer (.exe)

Once compiled into the one-folder layout in `dist/CaptorCore/`, you can package the entire distribution into a single setup program:
1. Install Inno Setup version 6.x.
2. Open the **`captioncast.iss`** file in Inno Setup.
3. Click "Build -> Compile" (or press `Ctrl+F9`).
4. The single-file installer **`CaptorCoreSetup.exe`** (~990 MB) will be generated in the **`Output/`** folder.

---

## Captor X Firmware Setup

Folder: `captioncast_esp32/`

1. Open `captioncast_esp32.ino` in the Arduino IDE.
2. Install the following dependencies from the Library Manager:
   - **Adafruit SSD1306**
   - **Adafruit GFX Library**
3. Select your Captor X board (ESP32-C3) and flash. Connect it to your PC over USB; the same cable provides power and carries graphical bitmap data.

---

## Wiring (OLED to Captor X / ESP32-C3 SuperMini)

```
OLED VCC  →  3.3V
OLED GND  →  GND
OLED SDA  →  GPIO 5
OLED SCL  →  GPIO 6
```

*(Note: While standard ESP32/ESP32-S3 boards often use GPIO 8/9, the Captor X device (based on ESP32-C3 SuperMini) maps GPIO 8 to its onboard LED and GPIO 9 to the BOOT button. Connecting I2C lines to these strapping pins can cause startup/flashing failures. Therefore, the firmware is configured to use GPIO 5 and 6 for a safe and reliable connection.)*

---

## Configurations & Persistence

All staging values committed via the **APPLY** button are saved to your local user directory:
`%APPDATA%\CaptorCore\config.json`

If the application has difficulty finding the correct loopback speaker channel or custom COM port, edit the values directly inside the JSON file.

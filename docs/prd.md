# Product Requirements Document (PRD) — Captor Core

## 1. Executive Summary & Vision

**Captor Core** is an open-source, real-time speech-to-text (captioning) ecosystem. It captures system output audio (loopback playback), processes it locally using high-performance machine learning models, and streams pixel-perfect graphical captions over a USB serial connection to a physical Captor X driven SSD1306 OLED screen (128x64 pixels). 

The goal of the product is to provide a low-latency, highly accurate, and customizable subtitle display for desktop setups (speakers, video players, gaming consoles routed to PC, and video conferences) with zero cloud dependencies and a premium retro-brutalist GUI on the desktop controller.

---

## 2. Key Features & Functional Requirements

### 2.1 PC-Side Captioning Engine
- **Audio Loopback Capture**: Native WASAPI loopback interception (via `PyAudioWPatch`) to capture exactly what plays on the PC speakers/headphones, rather than a microphone feed.
- **Dynamic Resampling**: Robust on-the-fly resampling of captured audio (any host sample rate, e.g., 44.1kHz or 48kHz) to 16kHz for model compatibility, preserving remainder samples.
- **Whisper STT processing**: Local inference using `faster-whisper`.
- **English-Only Focus**:
  - Automatically filters out non-English languages in `Auto-Detect` mode.
  - If speech in a foreign language is detected with a probability > 40%, the transcription is discarded, and the screen continues showing the idle waveform.
- **Robust Sequence Alignment Merge**: Uses a fuzzy suffix-prefix matching algorithm (60% threshold) to merge overlapping sliding windows of transcription, allowing real-time edits (live correction of past words) and preventing duplications.
- **Silence Clearing**: Resets the screen to the idle state if no speech is transcribed for 3.0 seconds (disabled in Music Mode).
- **Music Mode & Visualizer Options**: Supports a Music Mode toggle to disable silence clearing timeout and Whisper VAD, alongside selectable sound-reactive visualizers (Sine Wave, Stereo Bars, Radial Ring) when idle.

### 2.2 OLED Rendering & Serial Protocol
- **Offline PIL Image Rendering**: The PC renders text on a 128x64 binary bitmap canvas using Pillow (`PIL`).
- **Defensive Character-Splitting Word-Wrap**:
  - Wraps text within a 116px boundary (preserving 6px horizontal margins).
  - Automatically splits words wider than 116px (such as `"Captor Core"`) character-by-character to prevent horizontal cutoff.
- **Text Alignment & Case Modification**: Supports standard left, center, and right alignments, along with Sentence case, UPPERCASE, and lowercase filters.
- **Speech Rate (WPM) Speed Tracker**: Calculates the current words-per-minute rate dynamically in a rolling 60-second window.
- **Pixel Offset Nudging (Position Tuning)**:
  - Custom X and Y offset controls to adjust the rendered text position by ±1px increments to correct custom font baseline alignments.
- **Serial Transmission**: Streams raw 1024-byte binary bitmaps prefixed by a 7-byte header (`0xAA, 0x55, 0xAA, 0x55, 0x01, length_hi, length_lo`) at **460,800 baud** (to support a stable 20 FPS refresh rate), along with hardware commands (`[BRIGHT:X]`, `[INVERT:B]`, `[PING]`/`[PONG]`).

### 2.3 Desktop GUI Controller
- **Layout**: Portrait vertical single-column layout (geometry `740x740`) with a solid black background.
- **OLED Screen Preview**: Center-aligned, 3x upscaled `384x192` simulation frame matching the OLED screen’s 2:1 aspect ratio, reflecting real-time fonts, casings, waveforms, and offsets.
- **Staged Settings**: GUI configuration changes are staged and only applied to the core engine when clicking the **APPLY** button.
- **Arrow Pad (D-pad) Nudging controls**: A grid-based 3x3 directional pad (Up, Down, Left, Right, and RST in the center) for intuitive alignment adjustments.
- **State Persistence**: Saves all parameters (model, language, font, display mode, alignment, case, brightness, inversion, alert word, welcome text, loopback device, COM port, and X/Y offsets) to `%APPDATA%\CaptorCore\config.json`.
- **Auto-Connect COM**: Automatically scans active serial ports on launch and connects to the saved COM port.
- **Administrator Elevation (UAC)**: The application enforces Administrator privileges automatically at startup (compiled with `uac_admin=True` manifest). This is required to access hardware CPU temperature registers via ring 0 drivers.

### 2.4 GIF Player Mode
- **Frame Extracting & Scaling**: Extracts frames from local GIF animations. Resizes frames using Pillow, maintaining aspect ratio (centered with black borders) or stretching to fill the full 128x64 display.
- **Dithering & Colors**: Converts frames to 1-bit monochrome using Floyd-Steinberg error diffusion or adjustable threshold levels. Supports color inversion.
- **Variable Frame Rate Caching**: Caches processed frames and frame delays in memory to preserve CPU during streaming, and matches the playback speed multiplier (from 0.25x to 3.0x) to the OLED physical refresh rate.

### 2.5 PC Stats Dashboard
- **Retro-Brutalist Layout**: Formats system metrics on the 128x64 buffer with a clean, grid-based aesthetic using multiple weights of the custom `Vin Mono Pro` font.
- **CPU Metrics Block**: Shows Ryzen CPU name (registry lookups), real-time clock frequency in MHz, CPU Temperature, and CPU utilization percentage.
  - **Native Temp Sensing**: Queries CPU temp natively via bundled `LibreHardwareMonitorLib.dll` loaded via `pythonnet` (requires Administrator elevation), falling back dynamically to named file mappings (`CoreTempSeg`), WMI classes, or ACPI classes.
  - **Stacked Layout**: CPU Temperature is stacked directly above CPU utilization on the right side of the CPU block without overlapping.
- **GPU & VRAM Metrics Block**: Displays Nvidia GPU Name, Core Clock speed, GPU Temp, GPU Utilization %, and active Video Memory (VRAM) usage formatted in Gigabytes (e.g. `Mem: 2.4GB`).
  - **GPU Fallback**: Automatically falls back to local time, RAM utilization, and Disk usage if no Nvidia GPU is present or GPU monitoring is disabled.

---

## 3. UI/UX Design System (Aesthetic System)

Captor Core uses a modern **premium dark gray backdrop** theme with rounded-corner **fillets**:
- **Main Window**: Background is solid black (`#000000`).
- **Panels & Cards**: OLED Preview Box and Settings Panel Frame are filled with deep gray (`#121212`), with no borders (`border_width=0`) and rounded corners (`corner_radius=8`).
- **Action Buttons**:
  - Rounded with custom fillets (`corner_radius=6` for control buttons, `corner_radius=4` for D-pad nudging controls, `corner_radius=8` for the main Start button).
  - Background is dark gray (`fg_color="#1E1E1E"`), highlighting on hover with a lighter gray (`hover_color="#2D2D2D"`), and white text (`text_color="#FFFFFF"`).
  - Text is uppercase with retro action arrows (`↗`).
- **Dropdowns & Inputs**:
  - Selection dropdowns (Whisper Model, Language, Font, Display Mode, Alignment, Text Case, Audio Source, and COM Port) and text entry boxes (Alert Hotword, Welcome Msg) are styled with a deep gray backdrop (`#121212`), a thin gray border boundary (`border_width=1`, `border_color="#444444"`), and rounded corners (`corner_radius=6` for dropdowns).
- **Typography & UI Fonts**:
  - The entire GUI is styled with the custom **Vin Mono Pro** font family (Regular, Bold, Thin weights) loaded dynamically at startup.
  - Normal labels, inputs, and dropdown items use `"Vin Mono Pro"`.
  - Section headers, buttons, D-pad controls, and offset status labels use `"Vin Mono Pro Bold"`.
  - Tooltips use `"Vin Mono Pro"` (size 9).
- **State-Based Color Toggles**:
  - **Apply Settings**: Flashes solid warning orange-red (`fg_color="#D84315"`, `hover_color="#BF360C"`) when settings are edited, returning to gray once saved.
  - **Start/Stop Button**: Turns solid red (`fg_color="#D32F2F"`, `hover_color="#B71C1C"`) when active, returning to gray when captioning is stopped.

---

## 4. Hardware & Firmware Requirements (Captor X)

- **Device**: Any Captor X device (Captor X-C3 microcontroller).
- **Screen**: SSD1306 monochrome OLED display (128x64 pixels) connected over I2C.
- **I2C Clock**: Fast mode configured at `400 kHz` to reduce screen update latencies to under 3ms.
- **Handshake Protocol**: Responds to `[PING]\n` with `[PONG]\n` over Serial to allow automatic COM port discovery.
- **Decoder**: Receives hex-encoded streams, decodes them back to 1024-byte binary arrays, and draws them directly to the buffer.
- **Commands**: Parsed on the fly to dim (`[BRIGHT:X]`) or invert (`[INVERT:B]`) the hardware display.

---

## 5. Technical Stack & Dependencies

- **Programming Language**: Python 3.10 / 3.11 (PC App), C++ (Captor X Firmware).
- **Core Dependencies**:
  - `faster-whisper`: Local transcription.
  - `PyAudioWPatch`: Native loopback capture on Windows.
  - `Pillow (PIL)`: Binary bitmap text rendering, waveform drawing, and GIF processing.
  - `customtkinter`: GUI engine.
  - `pyserial`: Serial communications.
  - `numpy`: Audio manipulations and linear interpolation.
  - `pythonnet`: Interfacing with compiled .NET assemblies (`LibreHardwareMonitorLib.dll`).
  - `wmi`: Redeundant fallback performance queries on Windows.
- **Acceleration**:
  - GPU execution supported via CUDA 12 (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, `nvidia-cuda-nvrtc-cu12`) with automatic fallback to CPU.
- **Packaging**: Compiled into a standalone, one-folder distribution directory (`dist/CaptorCore/`) using `PyInstaller` with an embedded UAC elevation manifest (`uac_admin=True`). Spec file bundles `LibreHardwareMonitorLib.dll` as a binary (placing it in the `_internal/` directory of the bundle), creating `CaptorCore.exe`.

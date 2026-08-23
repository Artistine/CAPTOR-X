# Project Status — Captor Core

## Overview
Captor Core is a real-time speech-to-text application designed to capture loopback audio from a PC, transcribe it using a local Whisper model, and stream high-performance binary graphics over a USB serial connection to a physical Captor X driven SSD1306 OLED display.

---

## Completed Implementations & Tasks

- [x] **Core Capture & STT Pipeline**
  - Intercepts PC speaker loopback using `PyAudioWPatch`.
  - Performs dynamic 16kHz resampling with numpy.
  - Switches to `"tiny.en"` for low-latency CPU/GPU English transcription.
  - Implemented a fuzzy suffix-prefix sequence alignment merging algorithm (`align_transcripts`) with a 60% threshold to resolve overlapping transcription blocks and handle real-time Whisper fluctuations/corrections.
  - Streams full graphical lines to ESP32 to support dynamic corrections.
  - Implemented 3.0s silence timeout to clear screen automatically.
  - Configured 400kHz fast I2C clock on the ESP32 for <3ms OLED refreshes.
  - Added dynamic font size auto-scaling in the image rendering pipeline to scale down font sizes (from 24pt down to 10pt) for long words so they fit perfectly on a single line instead of being divided character-by-character.
- [x] **GUI Transition to HTML/React (PyWebView)**
  - Migrated the user interface from a Python-rendered Tkinter GUI (CustomTkinter) to a modern, high-fidelity OS-native webview container served using the `pywebview` library (`captioncast_webview.py`).
  - **Premium Web Design**: Developed a React-based frontend using Tailwind CSS for styling, incorporating a clean, responsive layout.
  - **Perfect Rounded Corner Fillets**: Replicated the design language with a `#0c0c0c` container (`180x28px`, `14px` border radius) and a `#242524` button slider with a consistent `3px` spacing margin from the container walls on all sides.
  - **Dynamic Sliding Indicators**: Implemented Framer Motion spring-backed `layoutId` sliding active pills, removing any corner notches or blocky border glitches.
  - **Windows Viewport Scaling (75%)**: Configured the PyWebView window to `1096x804px` to account for Windows frame/title bar offsets, presenting a perfectly scaled `1080x765px` client area (exactly 75% of the original `1440x1020` canvas) that wraps the interface closely.
    - The Apply button turns warning orange-red (`#D84315`) when values are tweaked, and returns to gray once saved.
    - The Start/Stop button turns solid red (`#D32F2F`) while captioning is active.
  - **UI Font Migration to Vin Mono Pro**:
    - Migrated the entire GUI design to the custom **Vin Mono Pro** font family (Regular, Bold, Thin weights).
    - Added dynamic Win32 GDI font resource loading (`AddFontResourceW`) and OS broadcast updates at app startup to register the font family.
    - Styled all labels, dropdown menus, entries, checkboxes, status bar, and tooltips with the custom font for a complete premium terminal theme.
- [x] **Manual Position Tuning (Text Nudge)**
  - Implemented horizontal (`offset_x`) and vertical (`offset_y`) offsets in the PIL canvas text drawer.
  - Added a grid-based 3x3 D-pad layout (▲, ◄, RST, ►, ▼) to the Settings panel for fine-tuning text alignment.
  - Tied D-pad clicks to immediate staged updates in the upscaled preview window.
  - Saves offset coordinates persistently inside `%APPDATA%\CaptorCore\config.json`.
- [x] **Music Mode & Visualizers**
  - Added a toggle checkbox for Music Mode to disable the silence clearing timeout and Whisper VAD, allowing continuous lyric and singing transcription.
  - Added a dropdown selector for three sound-reactive visualizers (Sine Wave, Stereo Bars, Radial Ring) when captioning is idle.
- [x] **GIF Player Mode**
  - Added a `GIF PLAYER` tab option in the top segmented button selector.
  - Implemented a complete image processing pipeline in `captioncast.py` using Pillow to extract frames, resize, dithering (Threshold vs. Floyd-Steinberg), and optionally invert colors.
  - Caches processed frames and uses variable frame delays to play animated GIFs smoothly on the OLED display at selectable speeds (0.25x to 3.0x).
- [x] **PC Stats Dashboard Mode**
  - Added a `PC STATS` tab option in the segmented selector.
  - Formatted a dual-pane retro-brutalist layout (128x64 display buffer) using `Vin Mono Pro` fonts.
  - CPU block displays Ryzen CPU name, clock speed, CPU Temperature (queried natively at driver-level via bundled DLL, falling back to Core Temp Shared Memory or WMI classes), and CPU utilization stacked cleanly on the right.
  - GPU block displays Nvidia GPU Name, Core Clock, temp, utilization %, and active Video Memory (VRAM) usage in Gigabytes (e.g. `Mem: 2.4GB`).
  - Gracefully falls back to RAM, Disk usage, and local time if no Nvidia GPU is found.
- [x] **Packaging & Verification**
  - Packaged CUDA DLL search paths in `captioncast.spec` to bundle GPU runtime libraries.
  - Bundled `LibreHardwareMonitorLib.dll` into both root (`.`) and subfolder (`WinTmp`) directories inside the PyInstaller one-folder package layout.
  - Implemented robust multi-path lookup and detailed failure logging in `captioncast.py` for DLL loading.
  - Verified syntax compiling and successfully packaged the standalone application directory `dist/CaptorCore/` containing the main `CaptorCore.exe` and its `_internal/` dependency folders.
  - Compiled the Inno Setup script `captioncast.iss` using `ISCC.exe` on the host to generate a single-file Windows setup installer **`Output/CaptorCoreSetup.exe`** (~990 MB) for clean distribution.
  - Created a double-clickable Windows Batch launcher `run_dev.bat` in the project root to run the app directly using the correct Python 3.11 environment, eliminating any C-drive space leaks and ensuring sub-second startup during development.
  - Automatically launches the compiled executable in the user's desktop environment upon a successful compilation.
- [x] **Documentation & Requirements Audit**
  - Generated and finalized the Product Requirements Document (`prd.md`) detailing the product scope, design rules, and hardware details.
  - Created the developer and packaging workflow guide (`docs/workflow.md`).
  - Aligned and updated `README.md`, `docs/log.md`, and `docs/project status.md` to capture all final features, color systems, and UI controls.
- [x] **Post-Freeze UX Polish & Stability Improvements (June 12, 2026)**
  - Resolved PyAudio threading collisions by localizing audio streams and implementing generation checking.
  - Fixed aspect-ratio black borders by making the dashboard window non-resizable.
  - Scaled up the CC / GIF / STATS mode tab buttons to 240x38px across both React and Tkinter interfaces.
  - Fixed case-insensitive dropdown-to-backend text alignment mapping.
- [x] **Branding, UI Layout & Administrator Elevation (June 13, 2026)**
  - Rebranded the entire application to **Captor Core** across both python backend files, React frontend code, config systems, and PyInstaller spec files.
  - Converted custom 1080x1080 `Captor core icon.png` to a multi-resolution `.ico` (`captor_core_icon.ico`) and compiled it into the executable.
  - Resolved settings dropdown CSS layout wrap bug in `gui/captor-hub/src/index.css` by changing `.settings-panel` column style to `repeat(4, minmax(0, 1fr))`, forcing truncation and preserving D-pad alignment.
  - Configured PyInstaller to compile with UAC elevation manifest (`uac_admin=True`) to automatically run the app as Administrator, resolving Ryzen CPU temperature driver-level querying failures.
  - Updated configuration paths to use `%APPDATA%\CaptorCore\config.json`.
  - Removed the Devices Selection landing page and the top back button/icon from the React frontend, allowing the app to open directly to the core dashboard. Updated the Tkinter fallback (`captioncast.py`) to match this behavior.
  - Recompiled the standalone executable cleanly to `dist/CaptorCore/CaptorCore.exe`.
- [x] **JS Bridge React Fix, DLL Bundling & CPU Temp Verification (June 14, 2026)**
  - Fixed a race condition in the React frontend (`App.tsx`) where early calls to `get_settings` bypassed the native bridge check, causing it to default to mock mode.
  - Rebuilt the React frontend cleanly.
  - Modified PyInstaller spec file to bundle `LibreHardwareMonitorLib.dll` in `binaries` (ensuring it is placed in the internal directory `dist/CaptorCore/_internal/`).
  - Updated `get_cpu_temp()` to query `LibreHardwareMonitorLib.dll` via `pythonnet` (`clr`) with the Memory group disabled (`hw.IsMemoryEnabled = False`) to avoid type initialization crashes caused by missing RAM SPD dependencies.
  - Added self-elevation relaunch logic to `captioncast_webview.py` to prompt the user for Administrator privileges when running the script directly.
  - Recompiled the standalone executable cleanly to `dist/CaptorCore/CaptorCore.exe` with embedded UAC administrator requirements and verified successful runtime bridge execution and hardware monitoring.
  - Resolved audio interface microphone capture silence (where Input 2 / Right channel microphones were ignored) by changing the channel extraction logic in both `captioncast_webview.py` and `captioncast.py` to downmix by averaging all input channels instead of taking only channel 0.
  - Compiled the final standalone one-folder PyInstaller application directory (`dist/CaptorCore`) and packaged it using Inno Setup (`ISCC.exe`) into a single-file Windows setup installer (`Output/CaptorCoreSetup.exe`).
- [x] **OLED UI Font Polish & Box Alignment (June 20, 2026)**
  - Cleaned up the OLED font selection menu: deleted the `fewture` font and set `Vin Mono Pro (Thin)` as the default option.
  - Shortened all U8g2 font dropdown display names to clean initials/short forms (e.g., `Pixellari`, `VCR OSD`, `bipixel double`, `doomalpha04`).
  - Updated python backends (`captioncast.py` and `captioncast_webview.py`) to map simplified names to their native `.ttf` paths while keeping legacy `u8g2_font_*` fallback keys for settings compatibility.
  - Corrected the inverted spoken word highlight box. Switched from static line-height assumptions to dynamic character bounding box calculations (`draw.textbbox`), achieving exactly 1px of padding on all sides.
  - Refactored normal white text rendering to resolve thickness issues by removing duplicate bold outline drawing passes, yielding crisp and thin text.
  - Rebuilt the React frontend and recompiled Vite production assets.
- [x] **BOSE Jackpot Roller Boot Animation (June 20, 2026)**
  - Replaced the boot logs animation with a premium, vector-and-text based slot machine jackpot reel simulation written directly in the firmware.
  - Implemented 4 independent vertical reels centered at `34`, `54`, `74`, and `94` pixels, bringing them horizontally closer with a `4px` gap.
  - Extracted custom character bitmaps from `VinMonoPro-Regular.ttf` in three distinct sizes (Large 16x24, Medium 12x18, Small 8x12).
  - Dynamically projects character positions linearly (`y_proj = Y_CENTER + diff_y`) and scales character sizes based on their vertical distance from the center line to fake a 3D circular disk.
  - Added back-face culling (`abs(diff_y) <= 80.0`) to hide characters when they rotate to the back of the cylinder, creating a seamless, pop-free rotation.
  - Rendered a completely borderless, gridless, box-free reel layout.
  - Added physics-based ease-in acceleration and constant spinning when disconnected.
  - Created a staggered stopping sequence (300ms delay between columns) that decelerates each roller to stop exactly on the target letters: **`B`**, **`O`**, **`S`**, **`E`**.
  - Programmed a 800ms hold on the completed "BOSE" jackpot screen before seamlessly transitioning to host graphics upon software connection.
  - Created `vin_mono_reels.h` and deleted obsolete codebase components.
- [x] **Default BOOT.gif Integration (June 20, 2026)**
  - Configured `UI/OLED UI/BOOT.gif` as the default fallback GIF path when entering `GIF PLAYER` mode.
  - Automatically loads and plays the boot animation if no other custom GIF path is set.
- [x] **Hardware Mode Cycle Button Support (June 20, 2026)**
  - Configured a hardware mode cycle button on `SWITCH_CYCLE_PIN` (GPIO 20) with `INPUT_PULLUP` enabled on the ESP32-C3 SuperMini.
  - Implemented a simplified, highly reliable single-click mode cycling debouncer inside `loop()`. Reverted the double-click detection logic at the user's request. Press and release transitions are debounced using a 50ms delay, matching the pattern used by the power toggle button (`SWITCH_PIN`) to guarantee 100% stable clicks.
  - Refactored python backends (`captioncast_webview.py` and `captioncast.py`) to launch a background serial receiver thread with event-based ACKs (`self.ack_event = threading.Event()`) to maintain a 40 FPS frame rate.
  - Configured python to process incoming `"CYCLE"` commands to cycle mode, and `"DOUBLE"` commands to switch to `"CAPTIONS"` and toggle `"music_mode"` (turning it ON or OFF).
  - Integrated `window.cycleModeTo` and `window.toggleMusicModeAndCC` in React UI (`App.tsx`) to synchronize frontend state, update tab headers, toggle music mode, and clean up event listeners on page unmount.
- [x] **Asynchronous Serial Reconnection & ESP32 State Leak Fix (June 21, 2026)**
  - Moved the serial connection logic (`_connect_port()`) in both `captioncast_webview.py` and `captioncast.py` to a background thread to prevent blocking/freezing the main rendering loop or Tkinter GUI for 1.1 seconds.
  - Promoted the `static` `stop_complete_time` variable inside `loop()` in `main.cpp` to a global variable and updated `initRollers()` to reset it to `0` on connection timeout, resolving state leakage glitches during reconnects.
- [x] **Welcome Animation Text Changed to "CAPTOR X" with Dynamic Letter Culling (June 21, 2026)**
  - Expanded the welcome reels from 4 to 8 columns inside `main.cpp` to spell "CAPTOR X" (using a blank slot for the space).
  - Recalibrated column center spacing from 20px to 15px to center all 8 columns on the 128px screen, and reduced the stopping delay from 300ms to 150ms per column.
  - Implemented speed-based drawing window culling during the connection stop phase to smoothly wipe away adjacent characters, leaving only the clean, centered target text visible when stopped.
- [x] **GPIO 3 Sub-Layout Context Button & Standalone Packaging (June 21, 2026)**
  - Re-mapped GPIO 3 (`SWITCH_PIN`) from display sleep/wake to mode-dependent context actions (sends `"SUB\n"` over Serial on press).
  - Implemented backend layout cycling logic: toggles Music Mode in **CAPTIONS**, cycles layouts (`CPU` -> `GPU` -> `MEM & NET`) in **PC STATS**, and skips to the next GIF alphabetically in **GIF PLAYER**.
  - Integrated React bindings (`updateStatsLayout`, `updateGifPath`) to synchronize frontend settings instantly.
  - Fixed f-string backslash syntax errors to ensure full compatibility with the host's Python 3.11 environment.
  - Built the standalone distribution directory `dist/CaptorCore/` using PyInstaller, copying required resources (`gui/`, `fonts/`, `UI/`) side-by-side with the executable for immediate, zero-dependency deployment.
- [x] **CAPTOR X Mockup Cutout Seamless Rendering & 1.2x Scale (June 23, 2026)**
  - Realigned the OLED preview canvas coordinate composition for the new 3D device mockup (`UI/CAPTOR X MOCKUP.png`) in `captioncast.py` and scaled the entire dashboard card preview by 1.2x.
  - Re-mapped the scaled cutout coordinates to `[228, 135, 561, 299]` (for the `790x442` scaled mockup size), achieving a 2:1 aspect ratio that exactly matches the OLED screen geometry.
  - Pre-composited V1 (`336x188` size, `[97, 57, 239, 128]` cutout) and V2 (`790x442` size) mockup images in the constructor with black backgrounds behind the cutouts, ensuring the mockup screens look turned off (black) instead of showing grey holes.
  - Integrated the mockup overlay inside the React Webview frontend (`App.tsx` and `index.css`), scaling the container to `790x442` px and overlaying the transparent `CAPTOR_X_MOCKUP.png` image on top of the live visualization canvas using absolute coordinates (`left: 228px, top: 135px, width: 334px, height: 165px`).
  - Rebuilt the React frontend with Vite and recompiled the standalone PyInstaller executable package.

---

## Release Version Freeze (v1.0.0-stable)
The codebase has been frozen and polished as of **June 14, 2026**. All stability fixes, branding changes, native pywebview bridge fixes, and hardware configuration settings are verified.

---

## Hardware-Specific Releases
- **Captor X (ESP32-C3 SuperMini) Setup**: Firmware utilizes GPIO 8 (SDA) and GPIO 9 (SCL) for the 0.96" 128x64 OLED display. Pin 8 is shared with the onboard active-low LED, providing a natural data streaming indicator.
- **Momentary Buttons & CAPTOR X Slot Machine Reels Welcome Animation**: Firmware includes a debounced momentary push button toggle (on GPIO 3 and GND) that triggers mode-dependent sub-layout context actions (e.g. toggles Music Mode in Captions mode, cycles sub-layouts in PC Stats mode, or skips to the next GIF in GIF Player mode), a mode cycle switch (on GPIO 20 and GND) that cycles through active PC modes on press, alongside a local simulated slot machine reels animation using the custom `Vin Mono Pro` font in a completely borderless gridless layout. It projects character coordinates linearly (`y_proj = Y_CENTER + diff_y`) and filters out back-facing characters to fake a rotating circular disk, spinning forever while disconnected and stopping on a staggered "CAPTOR X" jackpot configuration when the software connects.
- **Serial Connection & Buffer Upgrades**: Configured a high-speed **460,800 baud rate** with a **4KB receive buffer** on the ESP32 to prevent serial queue buffer overflows. Added a robust **100ms parser watchdog** to automatically resynchronize the packet parser if any bytes are dropped during transmission.

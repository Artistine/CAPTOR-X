# Development Log — Captor Core

## 2026-06-07
- **Issue Discovered**: The application was failing because of a hardcoded `SAMPLE_RATE = 48000`. Selecting the default WASAPI device `Line (8- AI-04)` caused an immediate crash since this device only supports `44100 Hz` under WASAPI.
- **Requirement Added**: The user wants to record loopback audio from their playback device `Speakers (8- AI-04)` to capture what is playing on the PC, rather than using a microphone/input.
- **Requirement Added**: The user wants an OLED black-and-white high-contrast theme for the GUI with red and green controls.
- **Requirement Added**: Build a standalone executable `.exe` that runs without dependencies.
- **Action Taken**:
  - Installed `PyAudioWPatch` to support WASAPI loopback capture on Windows natively.
  - Verified loopback recording capability using a custom Python script.
  - Planned UI changes: pure black (`#000000`) background, high-contrast white text, clear borders, green start button, and red stop button.
  - Planned PyInstaller build updates using `collect_all` helper.
- **Feedback & Latency Optimization**:
  - User requested instant, word-to-word real-time captioning instead of waiting for a 3-second block to finish transcribing.
  - Transitioned from a discrete 3-second capture chunk mechanism to a thread-safe rolling audio buffer.
  - Set the transcription step rate to run every `0.5 seconds` on the last 3 seconds of rolling audio, keeping Whisper's high accuracy but reducing latency to ~0.8s.
  - Designed and implemented a prefix-suffix alignment match algorithm (`find_new_words`) to extract only newly transcribed words and feed them to the queue, avoiding duplicates.
  - Verified and compiled the final updated `.exe`.
- **Further Latency Optimization (Instantaneous Transcription)**:
  - User requested even faster, almost instant word updates.
  - Benchmarked CPU transcription latency: found the standard multilingual `tiny` model took ~338 ms on CPU.
  - Discovered that the English-only `"tiny.en"` model runs in just **~127 ms** on CPU (a 3x speedup) due to a smaller vocabulary projection layer.
  - Switched model to `"tiny.en"` and reduced the sliding window step rate from `0.5 seconds` to `0.25 seconds` (250 milliseconds).
  - Total latency is now under **~380 ms**, which is virtually instant for human speech.
  - Cleaned up locked background processes and successfully re-compiled the executable.
- **GPU (RTX 5070) Acceleration & Portability**:
  - User requested using their RTX 5070 GPU for processing.
  - Installed CUDA runtime libraries via pip: `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, and `nvidia-cuda-nvrtc-cu12`.
  - Added dynamic namespace path resolution in `captioncast.py` to append these DLL directories (`bin/` folders) to the environment PATH. This allows CTranslate2 to find `cublas64_12.dll` and other files at runtime both in dev and packaged environments.
  - Implemented automatic GPU-to-CPU fallback in `captioncast.py`: loads on `cuda` with `float16` if available, falling back to `cpu` with `int8` if CUDA is not supported.
  - Fixed PyInstaller collection bug: Corrected package names in `captioncast.spec` to use dot-notation modules (`nvidia.cublas`, `nvidia.cudnn`, `nvidia.cuda_nvrtc`) instead of hyphenated PyPI names, ensuring all CUDA DLLs are correctly bundled.
  - Successfully re-compiled and verified the 1.2 GB GPU-bundled executable.
- **ESP32 OLED Subtitle Upgrade**:
  - User requested improving the responsiveness, readability, and immediate look of the OLED output.
  - Upgraded `captioncast_esp32.ino` from flashing a single centered word at a time to a rolling subtitle system.
  - The firmware now maintains its own word history buffer, formats it into an auto-wrapping sentence using a readable text size (`2`), centers it vertically, and auto-scrolls when the text exceeds the screen height.
  - This is fully backward-compatible with the PC application's serial protocol (words sent one by one with `\n` suffix).

## 2026-06-07 (Sub-second Responsiveness & Accuracy Enhancements)
- **Problem Identified**: The exact suffix-prefix word matcher failed if Whisper updated punctuation, casing, or word endings (e.g. "brand" to "brands"). This caused the matcher to miss overlaps and print duplicate words, creating a laggy and cluttered transcript on both the PC log and the OLED display.
- **Action Taken — Robust Sequence Alignment (`align_transcripts`)**:
  - Replaced the exact word overlap matcher with a Sequence Alignment algorithm.
  - Aligns the end of the existing transcription history against the beginning of the new chunk.
  - Uses `difflib.SequenceMatcher` to find the best overlapping block based on word similarity (e.g., matching "brand" with "brands" using a prefix-matching/similarity ratio of >= 0.8).
  - Merges the streams by replacing the overlapping suffix of the session history with the updated transcription from Whisper. This allows live correction of previously spoken words in real time.
- **Action Taken — Line-based Serial Streaming Protocol**:
  - Shifted from single-word immutable streaming to complete line-based updates.
  - Every 0.25 seconds, the PC app sends the entire active subtitle frame (the last 15 words of the session history) as a single line ending in `\n`.
  - Upgraded `captioncast_esp32.ino` to split the received line by spaces, rebuild the rolling buffer, perform word wrapping, and center the text vertically.
  - This design gives the PC full control over dynamic corrections, scrolling, and formatting, making the OLED display extremely immediate and accurate.
- **Action Taken — Silence Timeout Clearing**:
  - Added a silence tracker on the PC app.
  - If no new speech is transcribed for 3.0 seconds, the PC sends an empty line (`"\n"`) to the serial port.
  - The ESP32 receives the empty line, clears the OLED screen, and the GUI resets the active word label to `"—"`.
- **Action Taken — 400kHz Fast I2C Clock**:
  - Configured the ESP32 I2C clock to `400000 Hz` (Fast Mode) in `captioncast_esp32.ino`. This reduces SSD1306 rendering latency from ~12ms to ~3ms, eliminating any lag between serial reception and visual updates.
- **Action Taken — Packaging**:
  - Successfully re-compiled the GPU-bundled executable using PyInstaller. Verified correct package initialization and startup behavior.

## 2026-06-07 (Layout, Tooltips, Staged Settings, and Transliteration Fixes)
- **Problem Identified — Aspect Ratio & Visualizer Preview**: The preview window was a standard flat label showing just the last transcribed word. It did not reflect font selection, size, alignments, casing, or the sound-reactive waveform and VU meter.
- **Action Taken — Upscaled 2:1 Bitmap Preview Screen**:
  - Resized the simulation window to exactly `384x192` (matching the 2:1 aspect ratio of the 128x64 OLED display).
  - Used nearest-neighbor interpolation (`Image.NEAREST`) to upscale the raw rendered monochrome PIL canvas 3x, preserving the retro pixelated look.
  - The preview window now renders the exact visual output of the OLED screen, including word-wrapping, fonts, alignments, casing, the blinking transmission heart, the animated waveform, and the real-time VU meter.
- **Problem Identified — Instant Setting Reloads**: Changing setting dropdowns triggered immediate model reloads and serial command spikes, creating a laggy experience while picking choices.
- **Action Taken — Staged Settings & Apply Button**:
- Implemented a staged settings model. GUI configurations are held in memory and only written to the active caption engine when the user clicks **Apply Settings**.
- Programmed variable tracing on all inputs. The moment a user alters a setting, the Apply button turns orange-red `⚠` with a warning label, reverting to green `✓` once saved.
- Automatically handles restarting of the transcription threads only if Whisper core configurations (model size, language, translation, VAD) are changed, avoiding unnecessary restarts for font/casing changes.
- **Problem Identified — Hinglish Transliteration Bugs**: Certain Hindi loan-consonants containing under-dots/nukta (like `ज़` in "zindagi", `फ़` in "film", or `ड़`) were not recognized as consonants, causing transliteration to fail on those words.
- **Action Taken — Comprehensive Consonant Parsing**:
  - Replaced range checks with a comprehensive consonant character set lookup covering all independent, dependent, and nukta-based Devanagari letters.
  - Transliteration is now completely robust and covers all loan words and conjuncts.
- **Action Taken — UI Polish & Tooltips**:
  - Created a `ToolTip` helper class. Added custom dark-themed tooltips to all options, dropdowns, check buttons, and sliders.
  - Enlarged the Start/Stop and serial helper buttons to make them more substantial and user-friendly.
  - Recompiled and packaged the final standalone executable.

- **Bug Fixed — Whisper Model Reload AttributeError**:
  - Discovered that the WhisperModel object does not possess a `model_path` attribute. Checking `self.model.model_path` during startup when reloading settings threw an `AttributeError`, causing the STT loading thread to crash and stop.
  - Added a state variable `self.loaded_model_size` to the App class to track the loaded Whisper model size.
- **Bug Fixed — Settings Reload Thread Race Condition**:
  - Stopping and immediately restarting the transcription threads when settings were applied caused a race condition where PyAudio tried to open the loopback interface before the old audio stream had finished releasing resources.
  - Added a `self.after(600, self._start)` delay when restarting captioning in `_apply_settings` to allow threads and audio/serial streams to shut down cleanly.
  - Recompiled and verified the final standalone executable.

## 2026-06-08 (Design Reversion, Gray Backdrop, D-pad Alignment, and Fillets)
- **Problem Identified — Landscape Layout Visual Noise**: Widescreen landscape dashboard layout with multiple side panels/tabs was too cluttered and visual heavy for the user.
- **Action Taken — Portrait Layout Reversion**:
  - Restored a single-column portrait layout (geometry `740x780`) putting all controls and preview stacked vertically.
- **Requirement Added — Border Removal & Gray Backdrop**:
  - User requested removing all white outlines and borders on frames and buttons, replacing them with a gray backdrop.
- **Action Taken — Borderless Gray Backdrop Styling**:
  - Removed all borders (`border_width=0`) from frames and buttons.
  - Set buttons to `#1E1E1E` (hover `#2D2D2D`, text `#FFFFFF`).
  - Set preview box and settings frame background to `#121212` (main window remains pure black `#000000`).
  - Implemented dynamic background color shifts: Apply button flashes solid warning orange-red (`#D84315`) when configurations are edited, and Start/Stop turns solid red (`#D32F2F`) while active.
- **Requirement Added — Text Position Tuning (Custom Fonts Centering)**:
  - Custom fonts often have baseline issues that prevent centering text on the OLED screen.
- **Action Taken — D-pad Grid Text Offset Controls**:
  - Added X and Y text offsets (stage variables, committed on Apply/Start).
  - Implemented ◄, ▲, ▼, ► directional arrow buttons and a **RST** button to Row 6 of the settings frame.
  - Arranged them in a standard 3x3 D-pad grid layout with the Reset button in the center and nudged labels aligned.
  - The live OLED preview is updated in real time as the arrow pad buttons are clicked.
- **Requirement Added — Rounded Edges (Fillets)**:
  - Edges were visually too sharp, requiring fillets.
- **Action Taken — Curved Corner radiuses**:
  - Configured `corner_radius=8` on the settings card, preview frame, and main Start button.
  - Configured `corner_radius=6` on auto-connect, re-scan, and apply settings buttons.
  - Configured `corner_radius=4` on D-pad arrow buttons to fillet the sharp corners.
- **Action Taken — Packaging**:
  - Compiled successfully and launched the updated standalone executable `dist/CaptionCast.exe` directly for the user.

## 2026-06-08 (Documentation Sync & PRD Audit)
- **Action Taken — Document Synchronization & PRD Generation**:
  - Generated and finalized `prd.md` in the project root containing the exhaustive Product Requirements Document (PRD) detailing executive vision, functional specifications, custom serial protocol, design system (dark gray backdrop, corner fillets, dynamic status colors), hardware/firmware, and technical dependencies.
  - Audited and updated `docs/project status.md` and `docs/log.md` to reflect the completed state of the UI redesign (D-pad text nudging, filleted corners, borderless design) and packaging.
  - Synchronized `README.md` to match the exact setup and features of the production build.
- **Action Taken — Dropdown & Input Gray Border Alignment**:
  - Replaced all `ctk.CTkOptionMenu` widgets with `ctk.CTkComboBox` in read-only mode (`state="readonly"`).
  - Configured all 8 dropdown selectors with a thin gray border (`border_width=1`, `border_color="#444444"`) and rounded corner fillets (`corner_radius=6`) to ensure a premium visual design.
  - Aligned all `ctk.CTkEntry` input boxes (welcome message and alert hotword) with the exact same thin border thickness (`border_width=1`, `border_color="#444444"`).
  - Re-compiled and packaged the app successfully into a standalone executable.

## 2026-06-08 (Version Freeze & Alignment Bugfix)
- **Problem Identified**: The transcription updates in "Line by Line" mode had a continuous glitchy/flickering behavior due to strict suffix-prefix alignment rules. If there was a single word difference/correction at the end of history, the overlap check failed and the entire buffer was appended, resulting in rapid phrase duplication on the screen.
- **Action Taken — Fuzzy Suffix-Prefix Alignment**:
  - Refactored `align_transcripts` in `captioncast.py` to use a 60% fuzzy overlap matching threshold.
  - Allows corrections/mismatches for medium overlaps (allows 1 mismatch in 3-4 word overlaps, and up to 2 mismatches in 5+ word overlaps).
  - Enforces 100% perfect match on short 2-word overlaps.
  - Rejects single-word overlaps if they are common stopwords to prevent false boundaries.
- **Problem Identified — Crash from Residual Animation Code**:
  - The `_poll` loop referenced undefined variables (`self.anim_var` and `self.typewriter_progress`) which caused immediate runtime crashes on subtitle updates.
- **Action Taken — Render Loop Cleanup**:
  - Removed all typewriter and animation reference hooks from both the GUI preview and serial rendering pipelines inside `_poll`.
  - Configured them to render `txt_gui` and `txt_serial` directly for maximum rendering stability.
- **Action Taken — Version Freeze v1.0.0-frozen**:
  - Updated all related documents (`prd.md`, `README.md`, `docs/project status.md`, and `docs/log.md`) with the corrected window geometry (`740x820`), the new fuzzy overlap alignment system, Music Mode, Visualizer Modes, and finalized version status.
  - Cleaned up build folders and compiled a final production standalone `CaptionCast.exe`.

## 2026-06-08 (ESP32-C3 SuperMini & OLED Hardware Optimization)
- **Requirement Met**: The user specified their hardware choice: **ESP32-C3 SuperMini** paired with a **0.96-inch 128x64 white OLED screen** (SSD1306 I2C).
- **Action Taken — Hardware-safe I2C Pin Assignment**:
  - Configured `captioncast_esp32.ino` to use **GPIO 5 (SDA)** and **GPIO 6 (SCL)**.
  - Using GPIO 8 and 9 (defaults in some libraries) was avoided since they are strapping pins. GPIO 8 is tied to the onboard LED, and GPIO 9 is the BOOT button. Pulling these pins low at boot time via I2C pull-ups can cause boot failures.
  - Initialized `Wire.begin(5, 6)` in `setup()` to safely initialize the OLED bus on non-strapping pins.
- **Action Taken — Onboard LED Error Signalling**:
  - Replaced `LED_BUILTIN` with `LED_PIN` mapped specifically to **GPIO 8** (the blue onboard LED on the ESP32-C3 SuperMini).
  - Adjusted the blink logic to properly handle active-low LED switching (setting `LOW` to turn ON, `HIGH` to turn OFF) to notify the user if the SSD1306 initialization fails.

## 2026-06-08 (Native Fonts Bundling & Pixel-Perfect Sizing)
- **Problem Identified**: The Minecraft and Pixel Operator fonts in the fonts folder did not render pixel-perfect on the OLED screen because the PC app rendered them at a stretched size of 24px, causing scaling distortion and blurry/uneven pixels.
- **Action Taken — Spec Bundling**:
  - Updated `captioncast.spec` to pack the `fonts/` directory natively inside the compiled executable.
  - Refactored `get_font` in `captioncast.py` to resolve paths relative to `sys._MEIPASS` when packaged.
- **Action Taken — Dynamic Pixel-Perfect Sizing**:
  - Implemented `get_font_size_for_name` in `_poll` to dynamically set the rendering font size based on the chosen font.
  - Pixel-perfect fonts (`Minecraft (Blocky)`, `Pixel Operator (Pixel)`, `MS Gothic (Monospace Pixel)`, and `Lucida Console (Retro)`) are rendered at their exact native **16px** size to eliminate scaling blur and ensure absolute pixel sharpness on the 128x64 display.

## 2026-06-08 (UI Font Migration to Vin Mono Pro & Branding Finalization)
- **Requirement Met — Branding Migration**:
  - Rebranded the PC application to **Captor Hub** and the physical device to **Captor X** across all UI labels, tooltip strings, log outputs, and Spec file targets.
  - Corrected layout coordinates to fit a compact vertical single-column portrait layout (`740x740` geometry), moving the Apply settings button and square start/stop buttons next to the D-pad nudging controls.
- **Requirement Met — Vin Mono Pro UI Font Migration**:
  - Registered the custom TrueType font family files (`VinMonoPro-Regular.ttf`, `VinMonoPro-Bold.ttf`, `VinMonoPro-Thin.ttf`) using Windows GDI API (`AddFontResourceW`) and broadcasted changes to tkinter using `SendMessageW`.
  - Replaced all occurrences of `Consolas` and the default sans-serif font across every label, entry field, checkbox, combobox list and dropdown, coordinates label, D-pad button, and action button with the `Vin Mono Pro` family weights.
  - Set tooltip fonts to use `Vin Mono Pro` at size 9.
- **Action Taken — Package Rebuild & Documentation Sync**:
  - Rebuilt the standalone single-directory binary target `dist/CaptorHub.exe` successfully with PyInstaller.
  - Updated all design systems specifications in `prd.md`, features list in `README.md`, status logs, and developer journals.

## 2026-06-09 (GIF Player, PC Stats, and DLL Bundling Fix)
- **Feature Added — GIF Player Mode**:
  - Added a `GIF PLAYER` operation mode selector to the top segmented tab in the GUI.
  - Implemented a complete frame processing pipeline in `captioncast.py` using Pillow (`PIL`). It extracts frames from user-provided GIFs, resizes them (with centering/padding or full stretching to 128x64), converts them to 1-bit monochrome (using Floyd-Steinberg error diffusion or thresholding with an adjustable threshold level), and supports color inversion.
  - Processed frames and delays are cached to memory to keep the real-time drawing loop extremely CPU-light.
  - Implemented real-time playback control that parses variable frame-rate delays to sync GIF speed (from 0.25x to 3.0x speed multipliers) perfectly with the physical OLED update rate.
- **Feature Added — PC Stats Dashboard**:
  - Added a `PC STATS` operation mode and a custom settings panel with update interval sliders and GPU toggle checkbox controls.
  - Implemented a retro-brutalist performance display layout that fits on the 128x64 screen (showing CPU block in the upper half and GPU/Memory block in the lower half).
  - Queries Ryzen CPU Name from Windows Registry and current clock frequency via `psutil`. CPU Temperature is queried natively at driver-level using the bundled `LibreHardwareMonitorLib.dll` via `pythonnet` (requires Administrator elevation), falling back dynamically to named file mapping `CoreTempSeg` (Core Temp Shared Memory), WMI namespaces (`root\LibreHardwareMonitor` / `root\OpenHardwareMonitor`), ACPI classes (`MSAcpi_ThermalZoneTemperature`), or CPU utilization.
  - Queries NVIDIA GPU statistics by calling `nvidia-smi` to parse GPU name, core clock frequency, utilization, temperature, and active Video Memory (VRAM) usage formatted in Gigabytes (e.g. `2.4GB` instead of memory clock in MHz).
  - Falls back to local time, RAM utilization, and Disk usage if no Nvidia GPU is detected or GPU monitoring is disabled.
- **Bug Fixed — LibreHardwareMonitor DLL Packaging & Resolution**:
  - Resolved DLL-loading crash where PyInstaller's packaging failed to include the DLL or the program checked the incorrect folder relative to the temporary extraction directory.
  - Updated `captioncast.spec` to manually copy `LibreHardwareMonitorLib.dll` to both the root folder (`.`) and the `WinTmp/` subdirectory of the bundle.
  - Rewrote the DLL path lookup in `captioncast.py` (`get_cpu_temp()`) to check all possible paths (under both one-file bundles and unbundled Python execution) and print all attempted paths to `lhm_error.log` upon failure.
  - Rebuilt the executable `dist/CaptorHub.exe` and verified it unpacks and reads CPU temperatures successfully when run as Administrator.
- **Packaging Shift — One-Folder Mode Layout**:
  - Converted the PyInstaller spec file from single-file (`--onefile`) execution to one-folder (`--onedir`) distribution directory format.
  - This completely prevents C drive space leaks caused by leftover `_MEIxxxxx` folders inside `AppData\Local\Temp` after app crashes/force closures.
  - Reduces application startup latency from ~15–20 seconds down to sub-second (virtually instant) launch speeds since decompression of the 1.4 GB CUDA and Whisper runtime binaries is no longer needed on every run.
  - Rebuilt the project successfully into `dist/CaptorHub/` (executable path is `dist/CaptorHub/CaptorHub.exe`).
- **Developer Workflow Optimization — Batch File Launcher & Admin Elevation**:
  - Created and optimized `run_dev.bat` in the project root directory. It runs the Python script directly using the absolute path to the Python 3.11 environment.
  - Implemented self-elevating code in the batch script to automatically check for and request Administrator privileges at startup (triggering the standard Windows UAC prompt). This ensures Python runs with the ring 0 driver-level permissions needed to query Ryzen CPU temperature registers.
  - Optimized the batch script to restore the script directory using `cd /d "%~dp0"` so it resolves script files correctly when elevated as Administrator.
- **Production Setup Installer Compilation & Workflow Sync**:
  - Installed Inno Setup version 6.7.3 using the Windows Package Manager (`winget`).
  - Compiled the Inno Setup script `captioncast.iss` using `ISCC.exe` on the host machine.
  - Successfully generated a single-file Windows setup installer **`Output/CaptorHubSetup.exe`** (~990 MB) which solid-compresses the entire 1.4 GB one-folder distribution.
  - Created a developer and packaging workflow guide **`docs/workflow.md`** to outline development runs, PyInstaller compiles, and setup installer builds.
  - When run on the user's end, this installer extracts files directly to `Program Files`, adds Start Menu/Desktop shortcuts, sets up uninstallation entries, and runs the app instantly as a standalone program.

## 2026-06-12 (Thread Race Crash Fix, Resizability Lock, Mode Selector Scaling & Centering)
- **Bug Fixed — PyAudio Thread Race & Access Violations**:
  - Resolved the crash that occurred when switching backend modes or toggling play/stop rapidly while audio capture is active.
  - Removed `pyaudio_instance` and `audio_stream` from the global namespace of `audio_thread_fn`, making them completely local to prevent concurrent threads from overwriting each other's references.
  - Added tracking variables (`self.audio_thread`, `self.stt_thread`, `self.load_thread`) in the constructors of `AppEngine` (Webview) and `App` (Tkinter).
  - Configured `_start()` to set a global stop event, join/await any active audio, STT, or load threads with a 1.0s timeout to allow clean shutdown before starting new threads.
  - Implemented thread generation checks (`threading.current_thread() == self.load_thread` and stop/running checks) inside the background `load` sub-routine to abort obsolete or stopped loader threads before spawning audio/STT threads.
- **Bug Fixed — Window Aspect Ratio Black Borders**:
  - Configured `resizable=False` inside the dashboard window creation in `captioncast_webview.py`. This disables maximizing the window and dragging borders, which prevents black aspect-ratio borders from appearing on the left and right sides.
- **Feature Enhanced — Mode Selector Scaling & Positioning**:
  - Scaled up the mode selector tab pill (CC / GIF / STATS) from 180x28px to 240x38px across both the React frontend and Tkinter backend.
  - In React, updated `.mode-selector-pill` (width 240px, height 38px, radius 19px), `.mode-btn` (height 32px, radius 16px, font-size 13px), and changed the active tab indicator's motion overlay border radius from `rounded-[11px]` to `rounded-[16px]` inside `App.tsx`. Rebuilt production assets via `npm run build`.
  - In Tkinter, updated `self.tab_container` to 240x38px (placing it at `y=333` to align with the control pill), scaled `self.tab_selector` to 234x32px (corner radius 16, font size 12), and set individual buttons to width 78 (corner radius 16).
- **Bug Fixed — Text Alignment Dropdown Mapping & Case-Insensitive Drawing**:
  - Updated the drawing function `wrap_text_to_image` to evaluate alignment case-insensitively using `.lower()`, ensuring dropdown choices like `"Center"`, `"Left"`, and `"Right"` align properly on the OLED preview/serial stream.
  - Configured explicit `anchor="center"` on Tkinter tab buttons and their internal `_text_label` grids.

## 2026-06-13 (Rebranding, Custom Icon, Grid Wrap Bugfix, and Admin UAC Elevation)
- **Action Taken — Rebranding to Captor Core**:
  - Renamed the application from "Captor Hub" / "CaptionCast" to **Captor Core** across all file titles, welcome text messages, settings folder paths, logs, and build specifications.
- **Action Taken — Custom App Icon Conversion**:
  - Converted the updated user-provided 1080x1080 `Captor core icon.png` into a multi-resolution `captor_core_icon.ico` supporting sizes from 16x16 to 256x256 to ensure clean display on both desktop scaling and taskbars.
  - Linked the converted icon in `captioncast.spec` to bind it natively to the compiled Windows binary.
- **Action Taken — AppData Configuration Renamed**:
  - Renamed the settings directory from `%APPDATA%\CaptionCast` to `%APPDATA%\CaptorCore` across the Python backend files (`captioncast.py` and `captioncast_webview.py`) to keep user-data names fully consistent with the new brand.
- **Action Taken — CSS Grid Column Wrap Bugfix**:
  - Resolved a UI glitch where settings panel dropdowns containing long sentences (e.g. loops or audio inputs) caused columns to stretch, pushing the D-pad alignment control off-screen.
  - Changed the grid columns from `repeat(4, 1fr)` to `repeat(4, minmax(0, 1fr))` in `gui/captor-hub/src/index.css` to restrict column size expansion and trigger standard CSS truncation with ellipses.
  - Re-ran `npm run build` inside `gui/captor-hub/` to compile the layout fixes into the web assets.
- **Action Taken — UAC Administrator Elevation**:
  - Configured `uac_admin=True` inside the PyInstaller `EXE` block in `captioncast.spec` to automatically trigger the Windows User Account Control (UAC) prompt on startup.
  - This ensures that the standalone executable runs with the ring 0 driver-level permissions required to successfully query CPU temperature sensors natively.
- **Action Taken — Packaging & Compilation target renamed**:
  - Cleaned up older build files and re-compiled PyInstaller output under the name `CaptorCore` (saving the standalone directory to `dist/CaptorCore/` and generating `CaptorCore.exe`).
- **Action Taken — Devices Page & Icon Removal**:
  - Removed the Devices selection screen markup and its `activeView` conditional rendering state from `App.tsx` in the React frontend. The application now bypasses the landing/devices page and opens directly to the core dashboard.
  - Deleted the "DEVICES" back button (`btn-back-to-devices`) and icon from the top of the dashboard.
  - Modified the Tkinter fallback file `captioncast.py` to place `view_dashboard` at `(0, 0)` initially and bypass placing `view_devices`, aligning its behavior with the direct-open webview flow.
- **Action Taken — Settings Loading, Saving & COM Auto-Connection**:
  - Fixed a bug where `"mode"` (operation mode, e.g. `PC STATS`) was skipped during `load_config()` startup parsing because it was missing from the default `active_settings` dictionary keys, defaulting it back to captions.
  - Added auto-connection to the saved COM port at application startup inside the `__init__` constructor of `captioncast_webview.py`.
  - Added loopback audio source auto-selection logic at startup. If the saved `audio_source` is empty or invalid, the backend scans for active WASAPI devices, selects the preferred loopback device (`Speakers (8- AI-04) [Loopback]`), and updates the configuration. This keeps the React dropdown and backend state fully synchronized.
  - Added detailed diagnostic error logging inside `get_cpu_temp()`, writing exceptions directly to `lhm_error.log` in the application directory.
  - Rebuilt the React frontend package and compiled the executable binaries cleanly to `dist/CaptorCore/CaptorCore.exe` using PyInstaller.

## 2026-06-14 (JS Bridge React Fix, Standalone Compilation, CPU Temp Monitoring & Elevation)
- **Problem Identified — React Native Bridge Race Condition**:
  - The React frontend tried to query settings via `window.pywebview.api.get_settings()` during initial loading. However, `window.pywebview.api` was created as an empty object before its native Python methods were fully injected. This caused the frontend to assume the native bridge was missing and fall back to mock mode.
- **Action Taken — Robust Bridge Wait**:
  - Refactored `App.tsx` initialization logic to wait until `window.pywebview.api.get_settings` is defined. This guarantees the native Python bridge is fully loaded before launching the settings query.
  - Rebuilt the React frontend with `npm run build`.
- **Problem Identified — CPU Temperature DLL Bundling & Registry Crash**:
  - CPU temperature query returned `0.0` or failed. Direct querying of `LibreHardwareMonitorLib.dll` via pythonnet was missing because the DLL was not copied inside the PyInstaller `_internal/` directory.
  - If we manually referenced the DLL, it crashed on `hw.Open()` because the Memory hardware group failed to initialize due to a missing companion DLL dependency (`RAMSPDToolkit-NDD.dll`).
- **Action Taken — DLL Bundling & Memory Group Disable**:
  - Updated `captioncast.spec` to place `LibreHardwareMonitorLib.dll` in the `binaries` list (bundling it directly into `dist/CaptorCore/_internal/`).
  - Updated `get_cpu_temp()` in `captioncast_webview.py` to query `LibreHardwareMonitorLib.dll` via `clr`, but explicitly disabled Memory group monitoring (`hw.IsMemoryEnabled = False`) to prevent initialization exceptions.
- **Action Taken — UAC Administrator Elevation**:
  - Set `uac_admin=True` in `captioncast.spec` to force UAC admin prompts when launching the compiled EXE.
  - Added auto-elevation relaunch code inside `captioncast_webview.py` to prompt the user for Administrator rights when executing the python script directly.
  - Verified that compiling to a standalone EXE works perfectly, starting with UAC prompt, loading the JS bridge natively, and running hardware sensors without crashing.
- **Problem Identified — Audio Interface Microphone Capture Silence**:
  - Microphones plugged into audio interfaces (which are typically on Channel 2 / Right channel) were silent. The application callback was hardcoded to only capture Channel 1 (`[:, 0]`), discarding speech on Channel 2 and feeding pure silence to the transcription engine.
- **Action Taken — Multi-channel Averaging Downmix**:
  - Updated the audio thread callback in both `captioncast_webview.py` and `captioncast.py` to downmix by averaging all input channels (`np.mean(..., axis=1)`) instead of slicing channel 0. This ensures speech signals are captured regardless of which interface port the microphone is connected to.
- **Action Taken — Safe Compilation Bypass & Distribution Release**:
  - Bypassed kernel-driver-level file locks on `dist/CaptorCore/CaptorCore.sys` (which was locked by the lingering running `R0CaptorCore` service in Windows from previous testing runs) by renaming the old distribution folder to `dist/CaptorCore_old`.
  - Re-ran PyInstaller with the spec file `captioncast.spec` to successfully build the standalone one-folder distribution package in `dist/CaptorCore/` without any permission or lock conflicts.
  - Compiled the Inno Setup project (`captioncast.iss`) successfully using the Inno Setup compiler (`ISCC.exe`) to generate the final setup installer `Output/CaptorCoreSetup.exe` (~990 MB).
  - Verified that all output binaries (`CaptorCore.exe` and `LibreHardwareMonitorLib.dll`) exist in their respective directories within the package.

## 2026-06-15 (Client-Only Casting, Loading Animation & Momentary Power Toggle)
- **Requirement Met — Client-Only Casting**:
  - Re-aligned the OLED screen behavior to act purely as a client casting the PC app's preview screen buffer.
- **Feature Added — Local Loading/Buffering Animation**:
  - Implemented a circular spinning loader animation in `captioncast_esp32.ino` and `main.cpp`.
  - If no serial frames are received for 2.0 seconds, the ESP32 automatically assumes it is disconnected/waiting for connection and draws the loading spinner locally.
  - Once serial frames are received, it immediately hides the spinner and casts the PC app screen.
- **Feature Added — Momentary Button Power Toggle**:
  - Added support for a physical mechanical keyboard switch (momentary tactile push button) on **GPIO 3** (connecting it to GND).
  - Implemented edge-detection button state toggle logic with software debouncing.
  - First press clears the screen and puts the SSD1306 display panel into deep sleep mode (`SSD1306_DISPLAYOFF`), conserving power and preventing OLED burn-in.
  - Second press wakes the display (`SSD1306_DISPLAYON`) and immediately restores active casting or the loader.
  - Configured background serial processing inside the button-release wait loop to ensure data packets are not dropped while the button is pressed.
- **Action Taken — Rebranding Sync**:
  - Updated the startup splash screen text in both `captioncast_esp32.ino` and `main.cpp` to say `"Captor Core"` instead of `"CaptionCast"`.
- **Action Taken — Documentation Update**:
  - Updated `firmware/README.md` and the brain `walkthrough.md` with the new wiring schematic, switch parameters, and firmware functionality.

## 2026-06-19 (Baud Rate Upgrade, Buffer Size Expansion, and Parser Watchdog)
- **Problem Identified — Serial Desynchronization & Overflows**:
  - High baud rate (230400/921600) streams overflowed the ESP32's default 256-byte RX queue during I2C OLED display draw cycles (which block the CPU for ~25ms). This caused packet corruption and permanent display freezes.
  - The previous watchdog timer check (`millis() - lastByteTime > 1000`) failed to trigger if data was continuously flowing, as `lastByteTime` was updated on every byte read, trapping the parser state machine in an out-of-sync state.
- **Action Taken — ESP32 RX Buffer Size Expansion**:
  - Added `Serial.setRxBufferSize(4096)` to both PlatformIO (`main.cpp`) and Arduino IDE (`captioncast_esp32.ino`) sources. This allocates a 4KB receive buffer, allowing the chip to store up to 4 complete frames while the CPU is busy updating the screen.
- **Action Taken — Robust Watchdog Timer**:
  - Replaced the byte-arrival watchdog with a strict packet timeout. Added a `packetStartTime` tracker, recorded when starting to parse a new packet. If the packet is not fully parsed within **100ms**, the state machine immediately resets to `STATE_MAGIC_1`, guaranteeing synchronization recovery.
- **Action Taken — Host Communication Tuning**:
  - Configured the system to run at **460,800 baud** in the firmware and `captioncast_webview.py`, providing a perfect balance of speed and stability.
  - Reduced the host ACK timeout in the Python serial thread from `0.2` seconds to `0.05` seconds (50ms). If a frame is dropped, the serial thread now only blocks for a single frame duration, keeping the visual playback perfectly smooth.
- **Action Taken — Documentation Sync**:
  - Updated the Product Requirements Document (`prd.md`), project status (`project status.md`), and firmware guide (`firmware/README.md`) to align with the library dependencies (`U8g2`), hardware configurations, and serial communications protocols.

## 2026-06-20 (OLED UI Font Polish, Spoken Word Box Alignment & Text Thickness Fixes)
- **Problem Identified — Dropdown Fonts Redundancy & Name Lengths**:
  - The OLED font options dropdown was cluttered with unused fonts and raw, complex U8g2 names (e.g., `u8g2_font_Pixellari_tf`), making it less user-friendly.
  - The `fewture` font was requested for deletion.
- **Action Taken — Font Selection Cleanup**:
  - Deleted the `fewture` font entirely.
  - Retained `Vin Mono Pro (Thin)` as the default font.
  - Kept the remaining 9 U8g2 fonts but shortened their display names to friendly initials/short names: `Pixellari`, `VCR OSD`, `blipfest 07`, `bipixel double`, `bpixel`, `bytesize`, `cubemel`, `doomalpha04`, `freedoomr10`.
  - Updated the React frontend `App.tsx` and recompiled production assets using Vite (`npm run build`).
  - Mapped both the new simplified names and legacy U8g2 names to their native `.ttf` paths in the backend `FONT_MAP` (`captioncast.py` and `captioncast_webview.py`) to preserve backward compatibility for users' existing settings.
- **Problem Identified — Inverted Spoken Word Highlight Box**:
  - The highlight box surrounding the active spoken word on the OLED screen was misaligned or had uneven borders due to static, generic line-height bounds.
- **Action Taken — Dynamic textbbox Inverted Highlights**:
  - Refactored the text rendering pipeline in both python backends. Switched to PIL's `draw.textbbox` on the actual rendered word to dynamically extract bounds.
  - Added exactly `1px` padding adjustments relative to the bounding box (`bx1 = word_bbox[2] + (2 if has_shadow else 1)`), producing a clean, tight box with exactly 1px padding on all sides across all selected fonts.
- **Problem Identified — Normal White Text Thickness**:
  - Normal white text appeared too thick or bold because the rendering pipeline drew duplicate outline/shadow strokes even for non-shadowed text.
- **Action Taken — Refactored Outline Rendering**:
  - Separated the text stroke drawing logic. Disabled double-drawing passes for normal white text so it renders with its native clean, thin font weights.
- **Problem Identified — PC Stats Page Font Loading Errors**:
  - Hardcoded internal keys for telemetry screens (`U8g2 Haxrcorp 4089` and `U8g2 ProFont`) were missing from the cleaned-up backend dictionary, causing formatting issues.
  - Restored these keys inside `FONT_MAP` to ensure telemetry layouts continue loading correctly.

- **Problem Identified — Reversion & Corruption of Firmware Files**:
  - The firmware developer reverted both `main.cpp` and `captioncast_esp32.ino` to the old Adafruit SSD1306, 115200 baud, and ASCII-hex parsing logic. Subsequently, `main.cpp` was corrupted by being completely overwritten with text.
- **Action Taken — Reconstruct and Restore Firmware**:
  - Re-parsed the session's logs, reconstructed the final, correct versions of both firmware files (incorporating the 460800 baud, 4KB RX buffer, 100ms watchdog, and U8g2 SSD1309 configurations), and successfully compiled the PlatformIO project.
  - Wrote a detailed guide `DEVELOPER_RULES.md` in the `firmware/` directory to prevent future developer regressions.

- **Feature Requested — Simulated Captor OS Console Boot Animation**:
  - The user requested changing the boot welcome console messages from "Linux" to "Captor OS", adding more diagnostic log lines, and disabling the console clear/loop so that it stays on the waiting screen with a blinking terminal cursor.
- **Action Taken — Implemented Captor OS Console Boot Log**:
  - Defined a pool of 35 kernel-like initialization log messages in PROGMEM (including checks for RISC-V core, flash size, I2C, SPIFFS, and all 10 U8g2 fonts).
  - Implemented a scrolling history buffer queue of up to 9 lines using U8g2's built-in 4x6 pixel micro-font (`u8g2_font_4x6_tr`) to display timestamps (e.g. `[  0.25] FS: Mount OK (1.2MB free)`) and log messages under 32 characters.
  - Randomized log printing timing using `random(40, 250)` milliseconds to simulate variable driver loading speeds.
  - Once the boot log completes, it halts line generation and appends a blinking terminal cursor (`_`) to the final log line (`System: Ready. Waiting host...`), blinking at 2Hz.
  - Deleted obsolete `BOOT_VER.h` files and associated code to keep the firmware clean and save RAM/Flash space.

- **Feature Requested — Default BOOT.gif Integration**:
  - The user added `BOOT.gif` to `UI/OLED UI/BOOT.gif` and requested it to be used as a default boot animation/welcome screen in the GIF player interface.
- **Action Taken — Configured Fallback to BOOT.gif**:
  - Modified both `captioncast.py` and `captioncast_webview.py` to default the `gif_path` to `"UI/OLED UI/BOOT.gif"` on startup if it exists.
  - Updated `_load_gif` in both files to automatically search for and fallback to `BOOT.gif` if no path is provided or if the selected path does not exist, enabling seamless default play.
  - Verified compilation of the updated Python scripts with no syntax errors.
## 2026-06-20 (BOSE Slot Machine Reels Welcome Animation & 2s Scroll Sync)
- **Problem Identified — 2.0s Scroll Speed Discrepancy**:
  - The previous simulated Captor OS boot console log used a randomized delay (`random(30, 85)` ms) per line. While the mathematical average of the delay was ~57ms (resulting in ~1.9s total scroll), the synchronous OLED drawing command (`u8g2.sendBuffer()`) added an extra 25ms of hardware latency per frame. This extended the real-world boot animation duration to ~2.8 seconds, exceeding the 2.0s constraint.
- **Action Taken — Time-Based Boot Animation Scheduler**:
  - Refactored the boot log animation in PlatformIO (`main.cpp`) to use a strict time-based scheduler: `target_lines = 1 + (elapsed * 34) / 2000` (where `elapsed = millis() - boot_start_time`). This guarantees the animation completes in exactly 2.0 seconds regardless of hardware rendering overhead by dropping frames/catching up automatically.
- **Feature Requested — BOSE Jackpot Slot Machine Reels Welcome Animation**:
  - The user requested replacing the welcome console boot logs with a jackpot slot machine reels animation showing "BOSE".
  - The reels must spin forever with an ease-in acceleration on boot, and upon software connection, all reels must come to a staggered stop to show "BOSE" before transitioning to the live stream display.
- **Action Taken — BOSE Slot Machine Reels Firmware**:
  - Replaced the console boot log messages and code in PlatformIO (`main.cpp`) with a vector slot machine reel simulator.
  - Extracted custom character bitmaps from `VinMonoPro-Regular.ttf` in three distinct sizes (Large 16x24, Medium 12x18, Small 8x12) to fake a 3D circular disk projection.
  - Configured 4 vertical reels using these custom XBMP font arrays centered at `34`, `54`, `74`, and `94` pixels with a `4px` horizontal column gap, and dynamically scaled character sizes based on their vertical distance from the center.
  - Removed all frames, borders, dividers, viewport boxes, and payline indicator triangles to form a completely borderless, gridless, box-free reel layout.
  - Implemented physics-based ease-in acceleration and constant reel rotation (40 FPS) when disconnected.
  - Programmed a staggered stopping sequence (300ms delay between columns) that decelerates each roller to stop exactly on the target letters: **`B`**, **`O`**, **`S`**, **`E`**.
  - Programmed a 800ms hold on the completed "BOSE" jackpot screen before transitioning control to the host graphics.
  - Restored `captioncast_esp32.ino` to its original pre-reels state as requested by the user.

- **Problem Identified — Linear Reels Sizing Lacks 3D depth**:
  - The previous BOSE reels welcome animation used linear Y coordinate scaling and simple linear thresholds to select font sizes. As a result, the vertical character spacing remained constant, and characters popped abruptly from Large to Small sizes with no visible Medium size transition or vertical bunching at the edges, failing to fake a rotating circular disk.
- **Action Taken — 3D Cylinder Perspective Projection**:
  - Refactored the character drawing loop `drawRollers()` in PlatformIO (`main.cpp`) to map the linear reel position (`diff_y`) to a 3D cylinder's vertical rotation angle: `alpha = diff_y * (PI / 160.0)`.
  - Projected the Y coordinates onto the screen using a sine curve: `y_proj = Y_CENTER + 32.0 * sin(alpha)`. This naturally compresses the vertical spacing (bunching the letters together) and slows down their vertical movement as they approach the top and bottom edges.
  - Selected the font size (Large, Medium, Small) dynamically based on the projected vertical distance from the center: `diff = abs(y_proj - 32.0)`. This allows a smooth progression through all three sizes (Large in the center, Medium in transition, Small at the edges).
  - Implemented back-face culling by only rendering characters on the front half of the cylinder (`abs(diff_y) <= 80.0` or `abs(alpha) <= PI / 2`), preventing characters from popping or turning around to rotate backwards on the screen.
  - Verified compilation compatibility using the PlatformIO command-line tool.

- **Action Taken — Reversion to Linear Projection**:
  - Restored the linear coordinate mapping `y_proj = Y_CENTER + diff_y` to keep constant vertical spacing and rotation speed.
  - Retained the back-face culling (`abs(diff_y) <= 80.0`) and the distance-based sizing logic (Large, Medium, Small) so that the characters still enter and exit Small at the screen boundaries.
  - Re-verified successful compilation via PlatformIO.

## 2026-06-20 (Hardware Mode Cycle Button Implementation)
- **Feature Requested — Hardware Mode Cycle Button**:
  - The user requested adding a physical button on GPIO 20 of the ESP32-C3 SuperMini to cycle through the PC application's modes (Captions -> GIF Player -> PC Stats -> Captions).
- **Action Taken — Event-Based Serial Receiver Thread**:
  - Refactored `captioncast_webview.py` and `captioncast.py` to run a background thread that constantly checks for incoming serial data from the ESP32 without blocking the sender loop.
  - Implemented an event-based ACK queue in python using `threading.Event()` to prevent serial sender thread blockages, preserving high visual frame rates (40 FPS) on the OLED.
- **Action Taken — Mode Switching Logic**:
  - Programmed the python backend to detect the `"CYCLE"` message from the serial receiver thread and call `cycle_operation_mode()`.
  - The python backend dynamically updates the active settings, gracefully terminates the running mode thread, and launches the new mode.
- **Action Taken — React Frontend Synchronization**:
  - Added a global binding `window.cycleModeTo` in React UI (`App.tsx`) to let the python backend command mode changes, automatically changing UI tab selection, applying configuration, and syncing active states.
  - Added event-listener cleanup on component unmount to prevent memory leaks.
  - Rebuilt production assets (`npm run build`).
- **Action Taken — Debounced Edge-Detection Firmware**:
  - Updated PlatformIO firmware (`main.cpp`) to declare `lastCycleButtonState` and detect presses on `SWITCH_CYCLE_PIN` (GPIO 20) in the main `loop()`.
  - Added a debounced edge-detection handler that writes `"CYCLE\n"` to the Serial output on press.
  - Implemented non-blocking button release waiting, running `handleSerial()` internally to keep the serial parse state machine responsive.
  - Compiled and verified the firmware successfully using PlatformIO.

- **Feature Requested — Button Double Press for Captions + Music Mode Toggle**:
  - The user requested that a double press on the cycle button should switch the mode to Captions (CC) and toggle Music Mode between ON and OFF, and corrected button timings to ensure single press works reliably.
- **Action Taken — Debounced Double-Press Detection & Timing Adjustments**:
  - Refactored `main.cpp` firmware to implement a non-blocking debounced edge confirmation algorithm.
  - When a falling edge is detected on `SWITCH_CYCLE_PIN` (GPIO 20), it flags a pending press and records `lastEdgeTime = millis()`.
  - After a `30ms` confirmation window, it checks if the pin reading is *still* `LOW`. If it is `HIGH`, it discards the edge as electrical noise (e.g., from OLED I2C operations) or release bounce. If it remains `LOW`, it confirms a genuine user click.
  - Confirmed clicks are debounced with a `150ms` lockout to completely ignore mechanical contact bounce on both press and release.
  - Tracks confirmed clicks in a `250ms` double press window. If a second click is confirmed within `250ms`, the loop transmits `"DOUBLE\n"` over Serial. If the window passes, it executes the standard `"CYCLE\n"` signal.
- **Action Taken — Python & React Mode Shifts**:
  - Refactored `captioncast_webview.py` and `captioncast.py` receiver loops to check for `"DOUBLE"` messages, switching the operation mode to `"CAPTIONS"` and toggling `"music_mode"` between `True` and `False`.
  - Added the `window.toggleMusicModeAndCC` API method inside React frontend `App.tsx` to handle updating tab state, toggling the `musicMode` checkbox, and resetting dirty forms.
  - Rebuilt production assets (`npm run build`) and verified Python compilation correctness.

- **Feature Requested — Simplify Button Logic to Single-Click Mode Cycling**:
  - The user requested that we remove the double-click detection feature and fall back to single-click mode cycling only because the switch was not registering reliably.
- **Action Taken — Reverted to Simple Single-Click Debounced Logic**:
  - Reverted state variables in `main.cpp` back to a clean `lastCycleButtonState`.
  - Replaced the multi-click state-integration logic with a simple, highly robust 50ms debouncing delay on press and release.
  - Implemented the exact same working pattern used for the power toggle switch (`SWITCH_PIN`).
  - Added `handleSerial()` parsing calls inside the release wait loops to ensure no serial packet drops or receiver overflows occur while the user holds down the cycle button.
  - Verified successful compilation of the simplified firmware.

- **Feature Requested — Fix Reconnection Glitches and Connecting Hangs**:
  - The user reported that when the device gets disconnected during live captioning, it hangs in the `"connecting"` state and becomes glitchy.
- **Action Taken — Asynchronous Serial Connection & ESP32 State Leak Fix**:
  - Refactored `_connect_port()` in both `captioncast_webview.py` and `captioncast.py` to run the serial port opening and initial handshakes in a separate background thread. This prevents blocking the main rendering loop (`_poll_loop`) and Tkinter GUI thread for 1.1 seconds (via `time.sleep()`), completely eliminating UI freezes during auto-reconnection checks.
  - Moved `serial.Serial()` instantiation outside of the `serial_lock` scope to avoid blocking other serial threads.
  - Promoted the `static` `stop_complete_time` variable inside `loop()` in `main.cpp` to a global scope and updated `initRollers()` to reset it to `0` on connection timeout. This prevents stale timers from skipping the 800ms BOSE jackpot hold screen.
  - Verified successful compilation of both the Python backends and the ESP32 firmware.

- **Feature Requested — Change Welcome Reels Jackpot Text from BOSE to CAPTOR X & Clean Up Adjacent Stopped Letters**:
  - The user requested changing the slot machine welcome animation's target word from "BOSE" to "CAPTOR X" and smoothly hiding all other adjacent letters on screen before the reels stop.
- **Action Taken — 8-Column Reels, Spacing Tuning & Dynamic Letter Culling**:
  - Increased `ROLLER_COUNT` from 4 to 8 in the firmware (`main.cpp`).
  - Updated `roller_chars` to stop on target characters spelling `"C"`, `"A"`, `"P"`, `"T"`, `"O"`, `"R"`, `" "` (space), and `"X"`.
  - Recalibrated column centers in `drawRollers()` to `11 + col * 15` pixels to center all 8 columns on the 128px screen width without truncation.
  - Adjusted the column stopping stagger delay from 300ms to 150ms per column to preserve the total 1.2-second transition time.
  - Implemented dynamic culling of adjacent characters: as each reel slows down during the connection phase, the drawing window is mathematically narrowed based on the speed (`12.0 + speed[col] * 4.5`). This smoothly hides the top and bottom character lines, leaving only the clean, centered "CAPTOR X" target text visible when fully stopped.
  - Verified successful compilation of the firmware.

- **Feature Requested — GPIO 3 Button Multi-Mode Context Actions & Standalone Executable Packaging (June 21, 2026)**:
  - The user requested re-mapping the physical button on GPIO 3 (`SWITCH_PIN`) to perform mode-dependent context actions (like cycling sub-layouts, skipping GIFs, or toggling Music Mode) and completely removing the old screen power toggle logic. They also requested building a standalone distribution folder for the application.
- **Action Taken — Re-Mapped Pins, Multi-Mode Layout Cycling, React Syncing, Python 3.11 Fix, and Standalone Folder Packaging**:
  - **Firmware**: Updated `main.cpp` to remove display sleep/wake toggle logic on GPIO 3. Configured GPIO 3 with a 50ms debouncer to output `"SUB\n"` over the serial port on press.
  - **Python Backends**: Added parsing support for the `"SUB"` command in both `captioncast_webview.py` and `captioncast.py`. Implemented `cycle_sub_layout()`:
    - **CAPTIONS Mode**: Toggles Music Mode ON/OFF.
    - **PC STATS Mode**: Cycles through stats views (`CPU` -> `GPU` -> `MEM & NET` -> `CPU` in webview, and toggles `stats_gpu` in Tkinter).
    - **GIF PLAYER Mode**: Scans directory of active GIF and cycles to the next `.gif` alphabetically.
  - **React Frontend**: Added `window.updateStatsLayout` and `window.updateGifPath` to `App.tsx` and handled cleanup on unmount. Recompiled with Vite (`npm run build`).
  - **Python 3.11 Syntax Fix**: Fixed a `SyntaxError` caused by backslashes within f-string expression braces by extracting path replacements to local variables prior to f-string construction.
  - **Standalone Packaging**: Ran PyInstaller to build a one-folder standalone package (`dist/CaptorCore/`) with `CaptorCore.exe` (run as Administrator to enable CPU temperature reading). Copied `gui/`, `fonts/`, and `UI/` directories side-by-side with the executable to ensure all relative resource paths resolve correctly out of the box with zero dependencies. Compiled the standalone directory into a single-file Windows setup installer **`Output/CaptorCoreSetup.exe`** (~990 MB) using Inno Setup (`ISCC.exe`) for easy distribution.
  - **GIF Playback Stuttering Fix**: Resolved a subtle GIF playback stuttering bug by removing the `serial_port.reset_input_buffer()` call inside `_serial_sender_loop()` in both Python files. This call was causing a race condition by clearing valid `[ACK]` lines and button presses from the buffer before the receiver thread could parse them. Also increased the `ack_event.wait()` timeout from 50ms to 100ms to provide a reliable buffer margin over the ~46ms roundtrip drawing time (preventing OS/USB scheduling jitter from causing frame drops). Recompiled and repackaged the standalone folder with this fix.

- **Feature Requested — Implement CAPTOR X Mockup Cutout Seamless Rendering & 1.2x Scale (June 23, 2026)**:
  - The user requested implementing the new 3D device mockup `UI/CAPTOR X MOCKUP.png` in the application interfaces, layering the live OLED preview screen seamlessly under the mockup's transparent window cutout, and scaling the mockup and OLED preview up to 1.2x scale (`790x442` size).
- **Action Taken — Adjusted Sizing and Coordinates for Cutout Alignment and 1.2x Scaling**:
  - **Mockup Coordinates Analysis**: Analyzed the transparent cutout bounding box inside `UI/CAPTOR X MOCKUP.png` using a Python script. At the 1.2x scaled display size of `790x442`, the screen cutout bounds scale exactly to `[228, 135, 561, 299]` (size `334x165`).
  - **Python Backend (`captioncast.py`)**:
    - Updated the V2 mockup resizing, compositing, and placement in the constructor to scale by 1.2x: resized `self.mockup_pil` to `(790, 442)`, pre-composited a black rectangle at `[228, 135, 561, 299]`, and placed the label `self.dev_image_label_v2` at `x=81, y=-17` inside the top card to keep it centered.
    - Updated the live preview drawing code in `_poll` to composite the frame at `790x442` size: resized the OLED canvas to `(334, 165)` using `NEAREST` resampling, drew a black rectangle at `[228, 135, 561, 299]`, and pasted the canvas at `(228, 135)` before overlaying the `790x442` mockup on top.
    - Verified that `captioncast.py` runs fluidly without any startup crashes or syntax errors.
  - **React Webview Frontend (`App.tsx` & `index.css`)**:
    - Copied the mockup PNG asset to `gui/captor-hub/assets/CAPTOR_X_MOCKUP.png` and imported it in `App.tsx`.
    - Integrated the 1.2x scaled layered layout: the container is sized to `790x442` px, with the visualization `<canvas>` positioned absolutely behind the transparent mockup overlay `<img>` at `left: 228px, top: 135px, width: 334px, height: 165px` (`z-index: 0`).
    - Modified `.device-preview-wrapper` in `index.css` to a width of `792px` to perfectly match the 1.2x mockup size.
    - Recompiled production assets via Vite (`npm run build`).
  - **Standalone Executable**: Recompiled the PyInstaller package using `captioncast.spec` to bundle the updated React assets in `dist/CaptorCore/`.

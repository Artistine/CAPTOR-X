# Google Stitch UI/UX Integration Blueprint: Captor Hub

This master document combines the visual design intent, frontend/backend architecture, HTML/CSS structure, asset mapping, and Python connection hooks. It is optimized to be read by **Google Stitch** to generate a pixel-perfect, production-ready desktop application frontend.

---

## 1. Visual Intent & Architectural Approach

### Visual Intent (Bose Design System)
The design uses a premium, high-contrast retro-brutalist theme. The user interface features:
* **Structured Cards**: Two primary content panels (Top and Bottom) with soft, rounded corner fillets (`border-radius: 24px`) set against a solid dark window background.
* **Functional Color Coding**: High-contrast, state-based accents (vibrant green `#11FF00` for online/active states, warning orange `#FF9100` for unsaved settings, and red `#FF0038` for critical stops/offline states).
* **Minimalist Borders**: Clean panels with zero outline borders, using subtle background shade variations (`#111111` for window vs. `#181818` for cards vs. `#252525` for buttons/controls) to define visual boundaries.

### Technical & Architectural Approach
Instead of a standard web app or a traditional Python Tkinter layout, this application is compiled as a **native Windows desktop application** using **`pywebview`** to render your HTML/CSS/JS frontend inside the OS-native Webview2 shell (Chromium).

```
 ┌────────────────────────────────────────────────────────┐
 │                      DESKTOP APP                       │
 │                                                        │
 │  ┌──────────────────────┐      JavaScript Bridges      │
 │  │      FRONTEND        │ ◄──────────────────────────┐ │
 │  │ (Affinity/Stitch UI) │    Calls Python functions  │ │
 │  └──────────┬───────────┘                            │ │
 │             │ Renders in                             ▼ │
 │             ▼                               ┌────────┴───────┐
 │  ┌──────────────────────┐                   │    BACKEND     │
 │  │   WEBVIEW2 WINDOW    │                   │ (Python Engine │
 │  │   (Native Webview)   │                   │    & Bridge)   │
 │  └───────────┬──────────┘                   └────────┬───────┘
 └──────────────┼───────────────────────────────────────┼─┘
                │                                       ▼ Serial
                │                                 ┌───────────┐
                └────────────────────────────────►│ CAPTOR X  │
                                                  └───────────┘
```

#### Why this is used:
1. **Design Fidelity**: Allows full CSS rendering (gradients, box-shadows, animations, and typography) that is impossible or sluggish in Python GUI toolkits.
2. **Offline execution**: Runs completely locally. The HTML/CSS/JS is bundled directly inside the final `.exe` using PyInstaller. No local web server or internet connection is required.
3. **Native bridge binding**: JavaScript can call Python methods asynchronously, and Python can push data to JavaScript dynamically using a native C/C++ API layer.

---

## 2. Global Visual & CSS Design Tokens

Configure your CSS stylesheet with these global custom variables:

```css
:root {
  /* Dimensions */
  --window-width: 1440px;
  --window-height: 1020px;
  
  /* Color Palette */
  --bg-window: #111111;           /* Deep charcoal main backdrop */
  --bg-card: #181818;             /* Dark grey card container panels */
  --bg-control: #252525;          /* Lighter grey for dropdowns, buttons, inputs */
  --bg-control-hover: #333333;    /* Highlight grey on hover */
  
  --color-green: #11FF00;         /* Active / Online / Success */
  --color-red: #FF0038;           /* Stop / Offline */
  --color-orange: #FF9100;        /* Connecting / Warning (Unapplied settings) */
  
  --text-primary: #FFFFFF;        /* Bright white text */
  --text-muted: #E4E4E4;          /* Soft grey labels & inputs */
  --border-color: #444444;        /* Inactive border boundaries */

  /* Fonts */
  --font-ui: "Vin Mono Pro", monospace;
}
```

---

## 3. DOM Structure & HTML Layout Hierarchy

The UI runs inside a single parent container. It contains a global setup header and two distinct views that toggle visibility.

```html
<div class="app-container">
  
  <!-- Global Configuration Header -->
  <header class="global-com-bar">
    <div class="port-select-wrapper">
      <select id="com-port-selector" class="dropdown"></select>
    </div>
    <!-- Icons are loaded as SVGs inside these buttons -->
    <button id="auto-connect-btn" class="icon-btn" title="Toggle Auto Connect"></button>
    <button id="rescan-btn" class="icon-btn" title="Rescan Ports"></button>
  </header>

  <!-- View 1: Devices Screen (Initial View) -->
  <main id="view-devices" class="view active">
    <div class="device-selection-card">
      <img src="Device Hand.png" class="device-render" />
      <div class="status-indicator-devices">
        <span class="status-dot green"></span>
        <span class="status-text">CAPTOR X [ONLINE]</span>
      </div>
    </div>
  </main>

  <!-- View 2: Main Application Dashboard -->
  <main id="view-dashboard" class="view">
    
    <!-- Top Card: Live Device Preview & Mode controls -->
    <div class="dashboard-top-card">
      <div class="status-indicator-dashboard">
        <span class="status-dot green"></span>
        <span class="status-text">CAPTOR X [ONLINE]</span>
      </div>
      
      <!-- Device render containing live display preview overlays -->
      <div class="device-preview-wrapper">
        <img src="Device Hand.png" class="device-preview-render" />
        
        <!-- Live screen visualizer and text overlays positioned relative to device display area -->
        <div class="device-screen-overlay">
          <canvas id="live-visualizer-canvas"></canvas>
          <div id="oled-preview-text-line">—</div>
        </div>
      </div>
      
      <!-- Mode Selector (CC, GIF, Stats) -->
      <div class="mode-selector-pill">
        <button id="mode-cc" class="mode-btn active">CC</button>
        <button id="mode-gif" class="mode-btn">GIF</button>
        <button id="mode-stats" class="mode-btn">📈</button>
      </div>

      <!-- Action Pill (Apply & Start/Stop) -->
      <div class="action-control-pill">
        <button id="action-apply" class="apply-btn idle" title="Apply Settings"></button>
        <button id="action-start-stop" class="start-btn stopped" title="Start Captioning"></button>
      </div>
    </div>

    <!-- Bottom Card: Sub-settings Panels & D-pad Nudger -->
    <div class="dashboard-bottom-card">
      
      <!-- Dynamic Form Container -->
      <div class="settings-form-container">
        
        <!-- Panel 1: Realtime AI Captions (CC) -->
        <div id="panel-cc" class="settings-panel active">
          <div class="form-row">
            <div class="form-group">
              <label>Model</label>
              <select id="dropdown-model" class="dropdown"></select>
            </div>
            <div class="form-group">
              <label>Text Case</label>
              <select id="dropdown-case" class="dropdown"></select>
            </div>
            <div class="form-group">
              <label>OLED Font</label>
              <select id="dropdown-font" class="dropdown"></select>
            </div>
            <div class="form-group">
              <label>Audio Source</label>
              <select id="dropdown-source" class="dropdown"></select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Language</label>
              <select id="dropdown-language" class="dropdown"></select>
            </div>
            <div class="form-group">
              <label>Text Alignment</label>
              <select id="dropdown-alignment" class="dropdown"></select>
            </div>
            <div class="form-group slider-group">
              <label>OLED Brightness</label>
              <input type="range" id="slider-brightness" class="slider" min="0" max="255" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group toggle-group">
              <label>Music Mode</label>
              <div class="toggle-switch" id="toggle-music-mode"></div>
            </div>
            <div class="form-group toggle-group">
              <label>Invert OLED</label>
              <div class="toggle-switch" id="toggle-invert-oled"></div>
            </div>
            <div class="form-group">
              <label>Display Mode</label>
              <select id="dropdown-display-mode" class="dropdown"></select>
            </div>
            <div class="form-group input-group">
              <label>Welcome Text</label>
              <input type="text" id="input-welcome-text" class="text-input" />
            </div>
          </div>
        </div>

        <!-- Panel 2: GIF Player Mode (GIF) -->
        <div id="panel-gif" class="settings-panel">
          <div class="form-row">
            <div class="form-group path-group">
              <label>Load GIF</label>
              <div class="path-input-wrapper">
                <input type="text" id="input-gif-path" class="text-input" readonly />
                <button id="btn-browse" class="btn">Browse</button>
              </div>
            </div>
            <div class="form-group slider-group">
              <label>Threshold</label>
              <input type="range" id="slider-threshold" class="slider" min="0" max="255" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>Speed</label>
              <select id="dropdown-speed" class="dropdown"></select>
            </div>
            <div class="form-group">
              <label>Dithering</label>
              <select id="dropdown-dithering" class="dropdown"></select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group toggle-group">
              <label>Invert OLED</label>
              <div class="toggle-switch" id="toggle-invert-gif"></div>
            </div>
            <div class="form-group">
              <label>Sizing Mode</label>
              <select id="dropdown-sizing" class="dropdown"></select>
            </div>
          </div>
        </div>

        <!-- Panel 3: PC Stats Dashboard (📈) -->
        <div id="panel-stats" class="settings-panel">
          <div class="form-row">
            <div class="form-group">
              <label>Update Interval</label>
              <select id="dropdown-interval" class="dropdown"></select>
            </div>
            <div class="form-group">
              <label>Dashboard Font</label>
              <select id="dropdown-stats-font" class="dropdown"></select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group toggle-group">
              <label>Monitor GPU</label>
              <div class="toggle-switch" id="toggle-monitor-gpu"></div>
            </div>
          </div>
        </div>

      </div>

      <!-- D-pad Nudger Section (Persistent) -->
      <div class="nudge-control-container">
        <span class="vertical-label">Nudge Text</span>
        <div class="dpad-controller">
          <!-- Load DPAD.svg inline -->
          <div class="dpad-bg-wrapper"></div>
          <!-- Absolute overlay glows -->
          <div class="dpad-glow top" id="glow-up"></div>
          <div class="dpad-glow left" id="glow-left"></div>
          <div class="dpad-glow bottom" id="glow-down"></div>
          <div class="dpad-glow right" id="glow-right"></div>
          <!-- Quadrant trigger buttons -->
          <button class="dpad-btn up" id="dpad-up"></button>
          <button class="dpad-btn left" id="dpad-left"></button>
          <button class="dpad-btn reset" id="dpad-reset">RST</button>
          <button class="dpad-btn right" id="dpad-right"></button>
          <button class="dpad-btn down" id="dpad-down"></button>
        </div>
      </div>

    </div>
  </main>

</div>
```

---

## 4. Asset Placement & Mapping Guide

Place these exported vector and image files exactly inside these HTML wrappers:

1. **`Device Hand.png`**:
   * Centered inside `.device-selection-card` (View 1) and `.dashboard-top-card` (View 2).
2. **`DPAD.svg`**:
   * Loaded as background-image inside `.dpad-bg-wrapper`.
3. **D-pad Glow Layers**:
   * Map `Dpad_glow_up.svg` to `#glow-up`.
   * Map `Dpad_glow_left.svg` to `#glow-left`.
   * Map `Dpad_glow_bottom.svg` to `#glow-down`.
   * Map `Dpad_glow_right.svg` to `#glow-right`.
   * Overlay them absolute with `opacity: 0` initially. Transition opacity to `1` when hovering over the corresponding button quadrant.
4. **`Auto Connect.svg`**:
   * SVG content embedded inside `#auto-connect-btn`.
5. **`Manual scan Icon.svg`**:
   * SVG content embedded inside `#rescan-btn`.
6. **`Chevron Down.svg` / `Chevron Up.svg`**:
   * Used as custom CSS `background-image` markers inside `.dropdown` select elements.

---

## 5. UI/UX Interaction & Logic Specification

### View Transitions
* Clicking anywhere on `.device-selection-card` in **View 1** transitions the app to **View 2**:
  ```javascript
  document.getElementById('view-devices').classList.remove('active');
  document.getElementById('view-dashboard').classList.add('active');
  ```

### Mode Switching (CC, GIF, Stats)
* Clicking a mode button highlights it, hides all other settings panels, and displays the matching panel layout:
  * **Caption Mode (`CC`)**: Shows input elements with IDs: `#dropdown-model`, `#dropdown-language`, `#dropdown-case`, `#dropdown-alignment`, `#dropdown-font`, `#dropdown-source`, `#dropdown-display-mode`, `#toggle-music-mode`, `#toggle-invert-oled`, `#input-welcome-text`, and `#slider-brightness`.
  * **GIF Mode (`GIF`)**: Shows input elements with IDs: `#input-gif-path`, `#btn-browse`, `#dropdown-speed`, `#dropdown-dithering`, `#dropdown-sizing`, `#toggle-invert-gif`, and `#slider-threshold`.
  * **Stats Mode (`📈`)**: Shows input elements with IDs: `#dropdown-interval`, `#dropdown-stats-font`, and `#toggle-monitor-gpu`.

### Action Button States (Apply & Start-Stop)
* **Dirty/Staged Settings Flag**:
  * Listen to change events on all form inputs. If any value changes from its initial/last applied value, add class `.dirty` to `#action-apply` (turning its icon/background color to `--color-orange`).
  * Once clicked, remove `.dirty`, write values, and transition briefly to `.success` (pulsing `--color-green`) before returning to `.idle` (grey).
* **Start/Stop Toggle**:
  * Clicking `#action-start-stop` alternates state between `.stopped` (white play triangle icon `▶`) and `.running` (red square icon `■` on background `--color-red`).

---

## 6. Visual Replication Guidelines (Match Mockups Exactly)

Follow these layout, sizing, and alignment specifications to create an exact replica of the mockup images:

### A. View 1: Devices Page
* **Card Placement**: Center `.device-selection-card` perfectly in the middle of the screen (both vertically and horizontally).
* **Card Dimensions**: `600px` x `560px` with a `24px` border radius (`border-radius: 24px;`).
* **Image Position**: Center the `Device Hand.png` graphic inside the card.
* **Status LED**: Center the status dot and text `● CAPTOR X [ONLINE]` underneath the image with a `20px` top margin. The green dot uses `#11FF00`.

### B. View 2: Dashboard Top Card
* **Card Dimensions**: `1360px` (width) x `560px` (height).
* **Card Alignment**: Position at `top: 100px; left: 40px;` (from top-left of the main window).
* **Connection Status LED**: Center the status label `● CAPTOR X [ONLINE]` horizontally at the top, exactly `30px` from the top edge.
* **Image Position**: The `Device Hand.png` graphic should be centered inside the card but offset slightly downwards to look natural.
* **Mode Selector Position**: Place the mode selection pill (`CC`, `GIF`, `📈`) at `bottom: 30px; left: 30px;` relative to the card container.
* **Action Pill Position**: Place the Apply/Start-Stop control capsule at `bottom: 30px; right: 30px;` relative to the card container.

### C. View 2: Dashboard Bottom Card (Settings & D-pad)
* **Card Dimensions**: `1360px` (width) x `280px` (height).
* **Card Alignment**: Position at `top: 700px; left: 40px;` (leaving a `40px` vertical gap below the top card).
* **Settings Grid Configuration**:
  * Set a left padding of `40px` and top padding of `30px`.
  * Arrange elements in parallel columns. Each column has a fixed width of `260px`.
  * Column Gap: `40px` (horizontal gap).
  * Row Gap: `24px` (vertical gap).
  * Label Styling: Labels (e.g., `Model`, `Text Case`, `OLED Font`) must use small text (`12px` or `13px`), muted color `#E4E4E4`, uppercase casing, and be positioned directly above the input fields with a `6px` bottom margin.
* **D-pad Alignment**:
  * Center the D-pad container vertically inside the bottom card on the right-hand side.
  * Position at `right: 60px;` from the card's right edge.
  * Vertical Label: Place `Nudge Text` as a vertical label on the left side of the D-pad (rotates -90 degrees, color `#444444`, font size `12px`, uppercase).

---

## 7. Python Backend Integration Hooks (PyWebView Bridges)

The frontend JavaScript must interface directly with our Python backend logic. Structure the scripts to bind to `window.pywebview.api`:

### JavaScript Connection Code (Add to Google Stitch JS Bundle)

```javascript
document.addEventListener("DOMContentLoaded", () => {
    // Wait for the python API to initialize
    window.addEventListener('pywebviewready', () => {
        initializeBackendConnection();
    });
});

// Initialize form settings and COM ports from Python on launch
function initializeBackendConnection() {
    // 1. Fetch available COM ports
    window.pywebview.api.get_serial_ports().then((ports) => {
        const selector = document.getElementById('com-port-selector');
        selector.innerHTML = '';
        ports.forEach(port => {
            const opt = document.createElement('option');
            opt.value = port;
            opt.innerText = port;
            selector.appendChild(opt);
        });
    });

    // 2. Bind start/stop button actions
    document.getElementById('action-start-stop').addEventListener('click', (e) => {
        const btn = e.currentTarget;
        if (btn.classList.contains('stopped')) {
            window.pywebview.api.start_captioning().then(() => {
                btn.classList.replace('stopped', 'running');
            });
        } else {
            window.pywebview.api.stop_captioning().then(() => {
                btn.classList.replace('running', 'stopped');
            });
        }
    });

    // 3. Bind Apply button settings write
    document.getElementById('action-apply').addEventListener('click', (e) => {
        const settings = gatherFormSettings(); // Read form values into a JSON object
        window.pywebview.api.apply_settings(settings).then((res) => {
            e.currentTarget.classList.remove('dirty');
            console.log(res);
        });
    });
}

// 4. Expose functions for Python to push live stats and visualizer updates
function updateWords(text) {
    // Called by Python to push real-time transcription line text
    document.getElementById('oled-preview-text-line').innerText = text;
}

function updateWaveform(waveformArray) {
    // Called by Python (30fps) to draw the sound visualizer wave on HTML5 Canvas
    drawSineWave(waveformArray);
}

function updateCpuTemp(tempValue) {
    // Called by Python to push live hardware telemetry
    document.getElementById('stats-cpu-temp').innerText = tempValue + "°C";
}
```

# Frontend Integration Plan: Affinity & Google Stitch UI Transition

This document outlines the architectural plan for integrating a high-fidelity vector UI designed in Affinity Designer and generated via Google Stitch (HTML/CSS/JS) into the existing python-based Captor Core backend.

---

## 1. Architectural Overview

We will transition the user interface from a Python-rendered Tkinter GUI (using CustomTkinter) to an OS-native HTML/CSS/JS wrapper rendered by the system's web engine (Microsoft Edge Webview2 on Windows) using the **`pywebview`** library.

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

### Key Benefits
* **Full Design Freedom**: Render advanced vector assets, gradients, shadows, and micro-animations designed in Affinity.
* **Single-Executable Distribution**: The UI code is compiled directly into the final executable with zero external web server/browser dependencies.
* **Developer Tools**: Access Chrome/Edge console tools (`Inspect Element`) directly inside the running app during development.
* **Fast Iteration**: Make instant HTML/CSS updates and reload the interface using `Ctrl + R` without having to compile.

---

## 2. Decoupling the Backend Engine

To prevent mixing UI layouts with hardware logic, the backend code in [captioncast.py](file:///d:/downloads/captioncast/captioncast/captioncast.py) will be decoupled. All audio capture, Whisper transcription, serial transmission, and performance monitoring will live in a standalone class:

```python
class CaptionCastEngine:
    def __init__(self):
        # Audio capture setup, serial connections, and stats monitoring
        pass
        
    def start(self):
        # Start transcription threads
        pass
        
    def stop(self):
        # Stop transcription threads
        pass
        
    def update_settings(self, settings):
        # Save config.json and reload port/model
        pass
```

---

## 3. Creating the PyWebView Bridge

We use `captioncast_webview.py` as the main entry point to load the HTML frontend and expose a Python API bridge to the JavaScript frontend.

### Python Side (`captioncast_webview.py`)
```python
import webview

class APIBridge:
    def __init__(self, engine):
        self.engine = engine
        
    def start_captioning(self):
        self.engine.start_stream()
        return "Started"

    def stop_captioning(self):
        self.engine.stop_stream()
        return "Stopped"

    def apply_settings(self, settings_dict):
        self.engine.update_settings(settings_dict)
        return "Applied Successfully"

    def get_serial_ports(self):
        # Scan and return active COM ports
        return serial.tools.list_ports.comports()

# Initialize engine & webview
engine = AppEngine()
bridge = APIBridge(engine)

# Outer dimensions scaled to 75% client width (1080x765) + Windows frame offsets
window = webview.create_window(
    title='Captor Core', 
    url='gui/index.html',  # Path to compiled React/Vite production build
    js_api=bridge,
    width=1096, 
    height=804,
    resizable=True
)

# Start GUI with Inspector console enabled for development
webview.start(debug=True)
```

### JavaScript/React Side (`gui/captor-hub/src/App.tsx`)
```javascript
// Exposes python methods inside the JS context under window.pywebview.api
document.addEventListener("DOMContentLoaded", () => {
    // Wait for the python API to initialize
    window.addEventListener('pywebviewready', () => {
        window.pywebview.api.get_serial_ports().then((ports) => {
            populatePorts(ports);
        });
    });
});
```

---

## 4. Real-time Streaming (Python ──► JS)

For high-frequency UI updates like waveforms, VU levels, and transcribed words, the Python engine pushes data to the JS layer using `window.evaluate_js()`:

```python
# Inside Python transcription thread:
window.evaluate_js(f"updateWords('{transcribed_words}')")

# Inside Python audio waveform thread (sent at 30fps):
window.evaluate_js(f"updateWaveform({waveform_data_array})")

# Inside Python PC stats monitoring loop:
window.evaluate_js(f"updateStats('{stats_json_string}')")
```

---

## 5. Development & Build Workflow

1. **Vite Development Server**: Run the local React development server for fast editing:
   ```cmd
   cd gui/captor-hub
   npm run dev
   ```
2. **Build and Deploy**: Compile React assets directly into the parent `gui/` directory using the custom output settings in `gui/captor-hub/vite.config.ts`:
   ```cmd
   npm run build
   ```
   *Vite is configured to write output files to `../` (the parent `gui` folder) with `emptyOutDir: false` to ensure built assets are automatically generated where `captioncast_webview.py` loads them.*
3. **Window Scaling Rules (75%)**:
   - The application has a standard container layout size of `1440x1020`.
   - In React, the window dynamically computes the scaling factor using `Math.min(dimensions.w / 1440, dimensions.h / 1020)` and applies CSS transform zoom.
   - On Windows, the outer OS border/title-bar takes up `16px` width and `39px` height.
   - To show a perfectly scaled `75%` client window (`1080x765px`), we create the PyWebView window at `1096x804px`.
4. **Sliding Indicator Animation (Framer Motion)**:
   - The active tab indicator uses Framer Motion's `<motion.div>` with a shared `layoutId="active-mode-indicator"` and spring transitions.
   - To prevent the background from being hidden behind parent elements due to browser stacking context rules, it uses `pointer-events-none` instead of a negative z-index.

---

## 6. Packaging & Compilation

Update your PyInstaller spec file [captioncast.spec](file:///d:/downloads/captioncast/captioncast/captioncast.spec) to bundle the web assets folder:

```python
# In captioncast.spec
datas=[
    ('gui', 'gui'),  # HTML/CSS/JS files and graphics
    ('fonts', 'fonts'),
    ('LibreHardwareMonitorLib.dll', '.')
]
```

Run PyInstaller to compile the standalone folder:
```cmd
C:\Users\sushi\AppData\Local\Programs\Python\Python311\python.exe -m PyInstaller --noconfirm captioncast.spec
```

# Captor X Software Connection Status Indicator: Implementation Guide

This document provides step-by-step instructions for implementing dynamic connection states for **Captor X** at the top of the desktop application dashboard. 

The three requested states are:
1. **Green Dot**: `CAPTOR X [CONNECTED]` (Active serial streaming / successful connection)
2. **Red Dot**: `CAPTOR X [DISCONNECTED]` (Serial port closed, offline, or write failure)
3. **Yellow Dot**: `CAPTOR X [CONNECTING]` (Handshake ping sent / awaiting port open)

---

## ── Architecture Overview ──

The application consists of a **Python (PyWebView) Backend** (`captioncast_webview.py`) and a **React/Vite Frontend** (`gui/captor-hub/src/App.tsx`).

1. **State Tracking**: Python tracks if the global `serial_port` is open and active.
2. **Event Callback**: When the connection state changes, Python evaluates a JavaScript function `window.updateConnectionStatus(status)` to push the new state.
3. **Startup Check**: On frontend initialization, React queries the initial state via an API bridge endpoint (`window.pywebview.api.get_connection_status()`).

---

## ── Step-by-Step Implementation ──

### Step 1: Add CSS Styles for the Yellow Dot
Open [gui/captor-hub/src/index.css](file:///d:/downloads/captioncast/captioncast/gui/captor-hub/src/index.css). Locate the `.status-dot` rules around line 242. 

Ensure the green, red, and yellow status classes are configured. Add the `.yellow` classes if they do not exist:

```css
/* gui/captor-hub/src/index.css */

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  box-shadow: 0 0 10px currentColor;
  transform: translateY(-1.5px);
  transition: background-color 0.3s ease, color 0.3s ease, box-shadow 0.3s ease;
}

.status-dot.green {
  background-color: var(--color-green, #22c55e);
  color: var(--color-green, #22c55e);
  animation: pulse-green 1.8s infinite alternate;
}

.status-dot.red {
  background-color: var(--color-red, #ef4444);
  color: var(--color-red, #ef4444);
}

.status-dot.yellow {
  background-color: var(--color-yellow, #eab308);
  color: var(--color-yellow, #eab308);
  animation: pulse-yellow 1.8s infinite alternate;
}

@keyframes pulse-green {
  0% { box-shadow: 0 0 4px rgba(34, 197, 94, 0.4); }
  100% { box-shadow: 0 0 12px rgba(34, 197, 94, 0.8); }
}

@keyframes pulse-yellow {
  0% { box-shadow: 0 0 4px rgba(234, 179, 8, 0.4); }
  100% { box-shadow: 0 0 12px rgba(234, 179, 8, 0.8); }
}
```

---

### Step 2: Update the React Frontend
Open [gui/captor-hub/src/App.tsx](file:///d:/downloads/captioncast/captioncast/gui/captor-hub/src/App.tsx).

#### A. Declare the Connection Status State
Near other `useState` hooks (around line 380), declare a state variable:

```typescript
const [connectionStatus, setConnectionStatus] = useState<"connected" | "disconnected" | "connecting">("disconnected");
```

#### B. Bind the Event Callback & Check Initial Status
Inside the main `useEffect` hook (around line 619), bind the status callback to `window` and fetch the startup status in the `initApp` loop:

```typescript
useEffect(() => {
  // 1. Bind frame updates (existing)
  (window as any).drawScreenFrame = (base64Img: string) => {
    // ... (existing canvas code)
  };

  // 2. Bind connection status updates from Python
  (window as any).updateConnectionStatus = (status: "connected" | "disconnected" | "connecting") => {
    setConnectionStatus(status);
  };

  let intervalId: any = null;
  let nativeListener: any = null;

  const initApp = async () => {
    const api = (window as any).pywebview.api;
    try {
      // Get Serial Ports (existing)
      if (api.get_serial_ports) {
        const ports = await api.get_serial_ports();
        setComPorts(ports);
      }

      // Query and set the initial connection status on startup
      if (api.get_connection_status) {
        const initialStatus = await api.get_connection_status();
        setConnectionStatus(initialStatus);
      } else {
        // Fallback guess based on active com port setting
        const settings = await api.get_settings();
        if (settings.com_port && settings.com_port !== "None") {
          setConnectionStatus("connected");
        } else {
          setConnectionStatus("disconnected");
        }
      }

      // ... rest of initApp settings loading
    } catch (err) {
      console.error("Error loading initial pywebview settings:", err);
    }
  };

  // ... rest of useEffect setup & cleanup

  return () => {
    delete (window as any).drawScreenFrame;
    delete (window as any).updateConnectionStatus; // Cleanup on unmount
    if (intervalId) clearInterval(intervalId);
    // ...
  };
}, [dimensions]);
```

#### C. Render the Dynamic Status Bar
Locate the top dashboard card container around line 1433:

```tsx
<div className="status-indicator-dashboard">
    <span className="status-dot green"></span>
    <span className="status-text text-white">CAPTOR X [ONLINE]</span>
</div>
```

Replace it with the dynamic status indicator layout:

```tsx
<div className="status-indicator-dashboard">
  <span className={`status-dot ${
    connectionStatus === "connected" ? "green" :
    connectionStatus === "connecting" ? "yellow" : "red"
  }`}></span>
  
  <span className="status-text text-white">
    {connectionStatus === "connected" && "CAPTOR X [CONNECTED]"}
    {connectionStatus === "connecting" && "CAPTOR X [CONNECTING]"}
    {connectionStatus === "disconnected" && "CAPTOR X [DISCONNECTED]"}
  </span>
</div>
```

> [!NOTE]
> If you prefer to display the exact spelling **`CAPTOR X [DISPONNECTED]`** matching local translation layouts, swap the final label string above.

---

### Step 3: Update the Python Backend
Open [captioncast_webview.py](file:///d:/downloads/captioncast/captioncast/captioncast_webview.py).

#### A. Initialize state on the `AppEngine`
Inside the `__init__` constructor of `AppEngine` (around line 891):

```python
class AppEngine:
    def __init__(self):
        self.model    = None
        self.model_on_gpu = False
        self.loaded_model_size = None
        self.running  = False
        
        # Add connection status tracking (default to disconnected or offline)
        self.connection_status = "disconnected"
```

#### B. Create the State Broadcasting Helper
Add this helper method inside `AppEngine` (e.g., near `_connect_port` around line 1270):

```python
    def set_connection_status(self, status):
        """Sets the connection status and pushes it to the React frontend."""
        self.connection_status = status
        if hasattr(self, "_window") and self._window:
            try:
                # Safely execute JS callback in the Webview
                self._window.evaluate_js(
                    f"if (window.updateConnectionStatus) window.updateConnectionStatus('{status}')"
                )
            except Exception as e:
                print(f"Error broadcasting connection status: {e}")
```

#### C. Expose Endpoint in `APIBridge`
Locate the `APIBridge` class around line 1618. Add the retrieval endpoint so React can read the state on load:

```python
class APIBridge:
    def __init__(self, app):
        self._app = app

    def get_connection_status(self):
        """Invoked by React on startup to sync state."""
        return getattr(self._app, "connection_status", "disconnected")
```

#### D. Integrate Status Updates into `_connect_port`
Modify `_connect_port` (around line 1277) to broadcast states:

```python
    def _connect_port(self, choice):
        global serial_port
        
        # 1. Handle disconnection if we disconnect or select "None"
        if serial_port and serial_port.is_open:
            serial_port.close()
            serial_port = None
        
        self.active_settings["com_port"] = choice
        self.save_config()

        if choice == "None":
            self.set_connection_status("disconnected")
            return
            
        # 2. Transitioning to Connecting status
        self.set_connection_status("connecting")
        
        try:
            # Attempt to open serial connection
            serial_port = serial.Serial(choice, BAUD_RATE, timeout=0.5)
            serial_port.write(b"\n")
            time.sleep(0.05)
            
            # Sync settings immediately
            time.sleep(0.15)
            self._handle_brightness(self.active_settings["brightness"])
            time.sleep(0.1)
            self._handle_inversion()
            
            # 3. Connection successful
            self.set_connection_status("connected")
            
        except Exception as e:
            print(f"Connection failed: {e}")
            # 4. Fallback to disconnected on failure
            self.set_connection_status("disconnected")
```

#### E. Handle Disconnection on Write Error (`send_line`)
Locate `send_line` around line 879. Update it so that if a `serial.SerialException` triggers (e.g. the USB cable is unplugged mid-stream), the global singleton `app_engine` sets the status to `"disconnected"`:

```python
def send_line(line_text):
    global serial_port
    if serial_port and serial_port.is_open:
        try:
            serial_port.write((line_text.strip() + "\n").encode("utf-8"))
        except serial.SerialException:
            serial_port = None
            
            # Broadcast disconnection immediately if AppEngine exists
            if 'app_engine' in globals():
                app_engine.set_connection_status("disconnected")
```

---

## ── Testing and Verification ──

To verify that the status indicator transitions correctly, the engineer can perform the following steps:

1. **Test `DISCONNECTED`**: 
   - Launch the application with the COM port selection set to `"None"`.
   - The status indicator should display a **Red Dot** next to `CAPTOR X [DISCONNECTED]`.
2. **Test `CONNECTING`**:
   - Select a valid COM port, or unplug the device and select the port it occupied.
   - For a brief duration (or permanently if the port is busy), a **Yellow Dot** and `CAPTOR X [CONNECTING]` should flash.
3. **Test `CONNECTED`**:
   - Plug in the device and select its active COM port.
   - The status indicator should turn into a pulsing **Green Dot** showing `CAPTOR X [CONNECTED]`.
4. **Test USB Unplug (Auto-Disconnect)**:
   - While streaming/casting is active (green dot), physically pull out the USB cable.
   - The indicator should instantly change to a **Red Dot** showing `CAPTOR X [DISCONNECTED]`.

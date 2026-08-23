import os

# 1. Edit captioncast_webview.py
webview_file = r"d:\downloads\captioncast\captioncast\captioncast_webview.py"
with open(webview_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Add js_log to APIBridge
old_bridge = """class APIBridge:
    def __init__(self, app):
        self._app = app

    def get_serial_ports(self):"""

new_bridge = """class APIBridge:
    def __init__(self, app):
        self._app = app

    def js_log(self, level, message):
        log.info("JS [%s] %s", str(level).upper(), message)

    def get_serial_ports(self):"""

content = content.replace(old_bridge, new_bridge)

# Add logging to get_serial_ports
old_ports = """    def get_serial_ports(self):
        return ["None"] + [p.device for p in serial.tools.list_ports.comports()]"""

new_ports = """    def get_serial_ports(self):
        log.info("API get_serial_ports called")
        res = ["None"] + [p.device for p in serial.tools.list_ports.comports()]
        log.info("API get_serial_ports returning %r", res)
        return res"""

content = content.replace(old_ports, new_ports)

# Update url to include ?native=true
content = content.replace("url='gui/index.html',", "url='gui/index.html?native=true',")

# Add check_js_state diagnostic right before webview.start
old_start = """    app_engine._window = window
    
    # Block and open the webview native frame window (debug=False disables devtools and right-click inspect)
    webview.start(debug=False)"""

new_start = """    app_engine._window = window
    
    def check_js_state():
        time.sleep(5)
        try:
            res = window.evaluate_js("typeof window.pywebview !== 'undefined' ? (typeof window.pywebview.api !== 'undefined' ? 'pywebview and api are OK' : 'pywebview OK but api undefined') : 'pywebview undefined'")
            log.info("DEBUG_JS_STATE: %s", res)
            
            loc = window.evaluate_js("window.location.href")
            log.info("DEBUG_JS_LOCATION: %s", loc)

            api_keys = window.evaluate_js("window.pywebview && window.pywebview.api ? Object.keys(window.pywebview.api) : []")
            log.info("DEBUG_JS_API_KEYS: %r", api_keys)

            early_logs = window.evaluate_js("window._consoleLogs")
            log.info("DEBUG_JS_EARLY_LOGS: %r", early_logs)
            
            root_html = window.evaluate_js("document.getElementById('root') ? document.getElementById('root').innerHTML : 'no root'")
            log.info("DEBUG_JS_ROOT_HTML: %s", root_html[:200])
        except Exception as e:
            log.error("DEBUG_JS_STATE failed: %s", e)

    window.events.loaded += lambda: threading.Thread(target=check_js_state, daemon=True).start()
    
    # Block and open the webview native frame window (debug=False disables devtools and right-click inspect)
    webview.start(debug=False)"""

content = content.replace(old_start, new_start)

# Add logging setup at the top of captioncast_webview.py if missing
if "logging.basicConfig" not in content:
    old_imports = """import os
import sys
import json
import threading
import queue
import time
import math
import io
import base64"""

    new_imports = """import os
import sys
import json
import threading
import queue
import time
import math
import io
import base64
import logging

# ── application logging ───────────────────────────────────────────────────────
_log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CaptorCore")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "captorcore.log")
logging.basicConfig(
    filename=_log_file,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("CaptorCore")
log.info("=" * 60)
log.info("CaptorCore starting — PID=%d", os.getpid())"""

    content = content.replace(old_imports, new_imports)

with open(webview_file, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated captioncast_webview.py with fixes")


# 2. Edit App.tsx
app_file = r"d:\downloads\captioncast\captioncast\gui\captor-hub\src\App.tsx"
with open(app_file, 'r', encoding='utf-8') as f:
    app_content = f.read()

# Add checkIsNative definition and update isMockRequired
old_mock_req = """    // Determine if we should run in mock mode
    const isViteDev = window.location.port === "5173" || window.location.port === "5174";
    const isMockRequired = isViteDev || window.location.protocol === "file:";"""

new_mock_req = """    // Determine if we should run in mock mode
    const isViteDev = window.location.port === "5173" || window.location.port === "5174";
    const isNativeUrl = window.location.search.includes("native=true");
    const isMockRequired = isViteDev || (window.location.protocol === "file:" && !isNativeUrl);"""

app_content = app_content.replace(old_mock_req, new_mock_req)

# Inject checkIsNative helper before App component
old_def = """interface StatsSettings {
  interval: string;
  statsFont: string;
  monitorGpu: boolean;
}

export default function App() {"""

new_def = """interface StatsSettings {
  interval: string;
  statsFont: string;
  monitorGpu: boolean;
}

const checkIsNative = (): boolean => {
  return typeof (window as any).pywebview !== "undefined" && 
         typeof (window as any).pywebview.api !== "undefined" && 
         !(window as any).pywebview.api.isMock;
};

export default function App() {"""

app_content = app_content.replace(old_def, new_def)

# Replace all inline pywebview checks with checkIsNative()
orig_expr = 'typeof (window as any).pywebview !== "undefined" && !(window as any).pywebview.api?.isMock'
app_content = app_content.replace(orig_expr, "checkIsNative()")

with open(app_file, 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Updated App.tsx with fixes")


# 3. Edit gui/captor-hub/index.html template
template_file = r"d:\downloads\captioncast\captioncast\gui\captor-hub\index.html"
with open(template_file, 'r', encoding='utf-8') as f:
    tmpl = f.read()

old_head = """    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>My Google AI Studio App</title>
  </head>"""

new_head = """    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>My Google AI Studio App</title>
    <script>
      (function() {
        window._consoleLogs = [];
        function capture(level) {
          const original = console[level];
          return function(...args) {
            if (original) {
              try {
                original.apply(console, args);
              } catch(e) {}
            }
            const msg = args.map(a => {
              try {
                return typeof a === 'object' ? JSON.stringify(a) : String(a);
              } catch(e) {
                return String(a);
              }
            }).join(' ');
            window._consoleLogs.push({ level: level, msg: msg });
            if (window.pywebview && window.pywebview.api && window.pywebview.api.js_log) {
              window.pywebview.api.js_log(level, msg);
            }
          };
        }
        console.log = capture('log');
        console.error = capture('error');
        console.warn = capture('warn');
        console.info = capture('info');

        window.addEventListener('pywebviewready', function() {
          if (window.pywebview && window.pywebview.api && window.pywebview.api.js_log) {
            window._consoleLogs.forEach(function(item) {
              window.pywebview.api.js_log(item.level, item.msg);
            });
            window._consoleLogs = [];
          }
        });
        
        window.addEventListener('error', function(e) {
          const msg = e.message + " at " + e.filename + ":" + e.lineno + ":" + e.colno;
          if (window.pywebview && window.pywebview.api && window.pywebview.api.js_log) {
            window.pywebview.api.js_log('error', msg);
          } else {
            window._consoleLogs.push({ level: 'error', msg: msg });
          }
        });
      })();
    </script>
  </head>"""

tmpl = tmpl.replace(old_head, new_head)
with open(template_file, 'w', encoding='utf-8') as f:
    f.write(tmpl)
print("Updated index.html template with logging")

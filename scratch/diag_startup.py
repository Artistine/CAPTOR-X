"""Diagnostic: Simulate app startup and check what state we get."""
import os, sys, json

sys.stdout.reconfigure(encoding='utf-8')

# 1. Check config files
appdata = os.environ.get("APPDATA", "")
config_path = os.path.join(appdata, "CaptorCore", "config.json")
print(f"=== Config path: {config_path} ===")
print(f"Exists: {os.path.exists(config_path)}")

if os.path.exists(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    print(f"Config keys: {list(cfg.keys())}")
    print(f"audio_source: {cfg.get('audio_source', '<MISSING>')}")
    print(f"com_port: {cfg.get('com_port', '<MISSING>')}")
    print(f"model: {cfg.get('model', '<MISSING>')}")
    print(f"mode: {cfg.get('mode', '<MISSING>')}")
    print(f"font: {cfg.get('font', '<MISSING>')}")
else:
    print("!!! CONFIG FILE NOT FOUND !!!")

# 2. Test PyAudio device enumeration
print("\n=== PyAudio Device Enumeration ===")
try:
    import pyaudiowpatch as pyaudio
    p = pyaudio.PyAudio()
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        wasapi_idx = wasapi_info['index']
        print(f"WASAPI host API index: {wasapi_idx}")
    except IOError:
        wasapi_idx = None
        print("WASAPI not found, using all APIs")
    
    devices = {}
    for i in range(p.get_device_count()):
        dev = p.get_device_info_by_index(i)
        if wasapi_idx is not None and dev['hostApi'] != wasapi_idx:
            continue
        if dev['maxInputChannels'] < 1:
            continue
        label = dev['name']
        devices[label] = i
    
    print(f"Found {len(devices)} input devices:")
    for label, idx in devices.items():
        print(f"  [{idx}] {label}")
    
    p.terminate()
    print("PyAudio terminated OK")
except Exception as e:
    print(f"!!! PyAudio error: {e}")

# 3. Check if a mutex from a previous instance is still held
print("\n=== Mutex Check ===")
import ctypes
kernel32 = ctypes.windll.kernel32
kernel32.SetLastError(0)
mutex = kernel32.CreateMutexW(None, True, "Global\\CaptorCore_SingleInstance_Mutex")
last_err = kernel32.GetLastError()
print(f"Mutex handle: {mutex}, Last error: {last_err}")
if last_err == 183:
    print("!!! ANOTHER INSTANCE IS ALREADY RUNNING !!!")
elif last_err == 5:
    print("!!! ACCESS DENIED - another instance may be running as different user !!!")
elif mutex and last_err == 0:
    print("Mutex acquired successfully - no other instance running")
else:
    print(f"Unknown state: handle={mutex}, err={last_err}")

# Release the mutex
if mutex:
    kernel32.ReleaseMutex(mutex)
    kernel32.CloseHandle(mutex)

print("\n=== Done ===")

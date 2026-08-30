import os
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
log.info("CaptorCore starting — PID=%d", os.getpid())

# Support GPU execution in PyInstaller packaged EXE by adding DLL directory paths
if hasattr(sys, "_MEIPASS"):
    base_path = sys._MEIPASS
    for folder in ["cublas/bin", "cuda_nvrtc/bin", "cudnn/bin"]:
        dll_path = os.path.join(base_path, "nvidia", *folder.split("/"))
        if os.path.exists(dll_path):
            os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")
else:
    for folder in ["cublas", "cuda_nvrtc", "cudnn"]:
        try:
            import importlib
            mod = importlib.import_module(f"nvidia.{folder}")
            mod_path = list(mod.__path__)[0]
            dll_path = os.path.join(mod_path, "bin")
            if os.path.exists(dll_path):
                os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")
        except (ImportError, AttributeError, IndexError):
            pass

import serial
import serial.tools.list_ports
import pyaudiowpatch as pyaudio
import numpy as np
import psutil
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance
import webview
import pystray


# ── font registration ─────────────────────────────────────────────────────────
def register_fonts():
    if sys.platform == "win32":
        try:
            import ctypes
            gdi32 = ctypes.windll.gdi32
            user32 = ctypes.windll.user32
            font_paths = [
                "fonts/vin-mono-pro-font-family/VinMonoPro-Regular.ttf",
                "fonts/vin-mono-pro-font-family/VinMonoPro-Bold.ttf",
                "fonts/vin-mono-pro-font-family/VinMonoPro-Thin.ttf",
                "fonts/vin-mono-pro-font-family/VinMonoPro-Medium.ttf",
                "fonts/vin-mono-pro-font-family/VinMonoPro-Light.ttf"
            ]
            for relative_path in font_paths:
                if hasattr(sys, "_MEIPASS"):
                    path = os.path.join(sys._MEIPASS, relative_path)
                else:
                    path = os.path.abspath(relative_path)
                if os.path.exists(path):
                    gdi32.AddFontResourceW(path)
            user32.SendNotifyMessageW(0xffff, 0x001d, 0, 0)
        except Exception as e:
            print(f"Error registering fonts: {e}")

register_fonts()

# ── settings ──────────────────────────────────────────────────────────────────
CHUNK_SECONDS = 3
BAUD_RATE     = 460800
STEP_SECONDS  = 0.25

FONT_MAP = {
    "Vin Mono Pro (Thin)": "fonts/vin-mono-pro-font-family/VinMonoPro-Thin.ttf",
    # Stats page internal fonts
    "U8g2 Haxrcorp 4089": "fonts/u8g2/haxrcorp4089.ttf",
    "U8g2 ProFont": "fonts/u8g2/ProFontForPowerline.ttf",
    # Clean names
    "Pixellari": "fonts/u8g2/Pixellari.ttf",
    "VCR OSD": "fonts/u8g2/8bitClassic.ttf",
    "blipfest 07": "fonts/u8g2/3x5.ttf",
    "bipixel double": "fonts/u8g2/8bitClassic.ttf",
    "bpixel": "fonts/u8g2/Terminal.ttf",
    "bytesize": "fonts/u8g2/Terminal.ttf",
    "cubemel": "fonts/u8g2/3x5.ttf",
    "doomalpha04": "fonts/u8g2/PressStart2P.ttf",
    "freedoomr10": "fonts/u8g2/Terminal.ttf",
    # Legacy u8g2 names (fallback)
    "u8g2_font_Pixellari_tf": "fonts/u8g2/Pixellari.ttf",
    "u8g2_font_VCR_OSD_mr": "fonts/u8g2/8bitClassic.ttf",
    "u8g2_font_blipfest_07_tr": "fonts/u8g2/3x5.ttf",
    "u8g2_font_bpixeldouble_tr": "fonts/u8g2/8bitClassic.ttf",
    "u8g2_font_bpixel_tr": "fonts/u8g2/Terminal.ttf",
    "u8g2_font_bytesize_te": "fonts/u8g2/Terminal.ttf",
    "u8g2_font_cube_mel_tr": "fonts/u8g2/3x5.ttf",
    "u8g2_font_doomalpha04_te": "fonts/u8g2/PressStart2P.ttf",
    "u8g2_font_freedoomr10_tu": "fonts/u8g2/Terminal.ttf"
}

# ── shared state ──────────────────────────────────────────────────────────────
audio_queue = queue.Queue()
transcription_queue = queue.Queue()
stop_event  = threading.Event()
serial_port = None
serial_lock = threading.RLock()
app_engine = None
pyaudio_instance = None
audio_stream = None

# Thread safety for the rolling audio buffer
buffer_lock = threading.Lock()
rolling_buffer = np.zeros(0, dtype=np.float32)
current_volume = 0.0

# ── helper: get config path ───────────────────────────────────────────────────
def get_config_path():
    appdata = os.environ.get("APPDATA")
    if appdata:
        config_dir = os.path.join(appdata, "CaptorCore")
    else:
        config_dir = os.path.join(os.path.expanduser("~"), ".captorcore")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "config.json")

# ── dynamic resample: any sample rate → 16000 ────────────────────────────────
def resample_audio(audio, orig_sr, target_sr=16000):
    if orig_sr == target_sr:
        return audio
    num_samples = int(len(audio) * target_sr / orig_sr)
    x_orig = np.linspace(0, 1, len(audio))
    x_target = np.linspace(0, 1, num_samples)
    return np.interp(x_target, x_orig, audio).astype(np.float32)

# ── word similarity comparator ────────────────────────────────────────────────
def words_similar(w1, w2):
    w1_clean = w1.lower().strip(".,!?;:\"'()[]-")
    w2_clean = w2.lower().strip(".,!?;:\"'()[]-")
    if w1_clean == w2_clean:
        return True
    if len(w1_clean) > 3 and len(w2_clean) > 3:
        import difflib
        ratio = difflib.SequenceMatcher(None, w1_clean, w2_clean).ratio()
        if ratio >= 0.8:
            return True
        if w1_clean.startswith(w2_clean) or w2_clean.startswith(w1_clean):
            if abs(len(w1_clean) - len(w2_clean)) <= 2:
                return True
    return False

# ── robust sequence alignment and merge ───────────────────────────────────────
def align_transcripts(old_words, new_words):
    if not new_words:
        return old_words
    if not old_words:
        return new_words

    A = old_words[-20:]
    B = new_words

    max_L = min(len(A), len(B))
    best_L = 0

    for L in range(max_L, 0, -1):
        suffix_A = A[-L:]
        prefix_B = B[:L]
        
        matches = 0
        for i in range(L):
            if words_similar(suffix_A[i], prefix_B[i]):
                matches += 1
        
        ratio = matches / L
        if ratio >= 0.6:
            if L == 1:
                word = suffix_A[0]
                word_clean = word.lower().strip(".,!?;:\"'()[]-")
                stopwords = {"the", "a", "an", "to", "in", "of", "and", "is", "it", "you", "that", "he", "was", "for", "on", "are", "as", "with", "his", "they", "i", "at", "be", "this", "have", "from", "or", "one", "had", "by", "word", "but", "not", "what", "all", "were", "we", "when", "your", "can", "said", "there", "use"}
                if len(word_clean) < 4 or word_clean in stopwords:
                    continue
            best_L = L
            break

    if best_L > 0:
        split_idx = len(old_words) - best_L
        return old_words[:split_idx] + B
    else:
        return old_words + B

# ── PIL Font & Image Rendering Pipeline ───────────────────────────────────────
loaded_fonts = {}

def get_font(font_name, font_size):
    key = (font_name, font_size)
    if key in loaded_fonts:
        return loaded_fonts[key]
    try:
        font_file = FONT_MAP.get(font_name, font_name)
        
        # Resolve relative paths relative to sys._MEIPASS if packaged, else the script directory or current directory
        if not os.path.isabs(font_file):
            if hasattr(sys, "_MEIPASS"):
                font_file_resolved = os.path.join(sys._MEIPASS, font_file)
                if os.path.exists(font_file_resolved):
                    font_file = font_file_resolved
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                font_file_resolved = os.path.join(script_dir, font_file)
                if os.path.exists(font_file_resolved):
                    font_file = font_file_resolved
                elif os.path.exists(font_file):
                    font_file = os.path.abspath(font_file)

        if os.path.isabs(font_file) and os.path.exists(font_file):
            font = ImageFont.truetype(font_file, font_size)
        else:
            font_path = os.path.join("C:\\Windows\\Fonts", font_file)
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
            else:
                font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    loaded_fonts[key] = font
    return font

def wrap_text_to_image(text, font_name, font_size, alignment="center", text_case="Sentence case", has_shadow=True, vu_volume=0.0, offset_x=0, offset_y=0):
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1" # Force pixel-perfect aliased rendering
    
    if not text.strip():
        return img
        
    if text_case == "UPPERCASE":
        text = text.upper()
    elif text_case == "lowercase":
        text = text.lower()
        
    font = get_font(font_name, font_size)
    words = text.split()
    
    PADDING_X = 6
    PADDING_Y = 6
    MAX_W = 128 - 2 * PADDING_X  # 116px horizontal wrapping boundary
    MAX_H = 64 - 2 * PADDING_Y   # 52px vertical wrapping boundary

    # ── Dynamic Font Size Auto-Scaling for Long Words ──
    current_font_size = font_size
    while current_font_size > 10:
        longest_word_w = 0
        for word in words:
            w_word = draw.textlength(word, font=font)
            if w_word > longest_word_w:
                longest_word_w = w_word
        
        if longest_word_w <= MAX_W:
            break
        
        current_font_size -= 2
        font = get_font(font_name, current_font_size)

    lines = []
    current_line = []
    
    for word in words:
        w_word = draw.textlength(word, font=font)
        if w_word > MAX_W:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = []
            chunks = []
            current_chunk = ""
            for char in word:
                test_chunk = current_chunk + char
                if draw.textlength(test_chunk, font=font) <= MAX_W:
                    current_chunk = test_chunk
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = char
                    else:
                        chunks.append(char)
                        current_chunk = ""
            if current_chunk:
                chunks.append(current_chunk)
            
            for chunk in chunks[:-1]:
                lines.append(chunk)
            if chunks:
                current_line = [chunks[-1]]
        else:
            test_line = " ".join(current_line + [word])
            w = draw.textlength(test_line, font=font)
            if w <= MAX_W:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
    if current_line:
        lines.append(" ".join(current_line))
        
    line_spacing = 2
    ref_bbox = draw.textbbox((0, 0), "Hg", font=font)
    ref_top = ref_bbox[1] if ref_bbox else 0
    ref_bot = ref_bbox[3] if ref_bbox else current_font_size
    line_h = ref_bot - ref_top
    
    total_h = len(lines) * line_h + (len(lines) - 1) * line_spacing
    
    while total_h > MAX_H and lines:
        lines.pop(0)
        total_h = len(lines) * line_h + (len(lines) - 1) * line_spacing
        
    align_lower = alignment.lower() if alignment else "center"
    y = (64 - total_h) // 2
    for idx, line in enumerate(lines):
        w = draw.textlength(line, font=font)
        if align_lower == "left":
            x = PADDING_X
        elif align_lower == "right":
            x = 128 - PADDING_X - w
        else:
            x = (128 - w) // 2
            
        x = max(PADDING_X, x)
        
        line_x = x + offset_x
        line_y = y + offset_y
        
        is_last_line = (idx == len(lines) - 1)
        
        if is_last_line:
            # Render the last word in an inverted box
            words_in_line = line.split()
            if len(words_in_line) > 1:
                preceding_text = " ".join(words_in_line[:-1])
                last_word = words_in_line[-1]
                w_preceding = draw.textlength(preceding_text + " ", font=font)
                
                # Draw preceding text normally
                draw.text((line_x, line_y), preceding_text, font=font, fill=1)
                
                # Draw last word in inverted box
                word_x = line_x + w_preceding
                word_bbox = draw.textbbox((word_x, line_y), last_word, font=font)
                bx0 = int(word_bbox[0] - 1)
                by0 = int(word_bbox[1] - 1)
                bx1 = int(word_bbox[2] + (2 if has_shadow else 1))
                by1 = int(word_bbox[3] + 1)
                draw.rectangle([bx0, by0, bx1, by1], fill=1)
                
                # Draw thickened/shadowed text inside inverted box
                if has_shadow:
                    draw.text((word_x + 1, line_y), last_word, font=font, fill=0)
                draw.text((word_x, line_y), last_word, font=font, fill=0)
            elif words_in_line:
                last_word = words_in_line[0]
                
                # Draw single word in inverted box
                word_bbox = draw.textbbox((line_x, line_y), last_word, font=font)
                bx0 = int(word_bbox[0] - 1)
                by0 = int(word_bbox[1] - 1)
                bx1 = int(word_bbox[2] + (2 if has_shadow else 1))
                by1 = int(word_bbox[3] + 1)
                draw.rectangle([bx0, by0, bx1, by1], fill=1)
                
                # Draw thickened/shadowed text inside inverted box
                if has_shadow:
                    draw.text((line_x + 1, line_y), last_word, font=font, fill=0)
                draw.text((line_x, line_y), last_word, font=font, fill=0)
        else:
            draw.text((line_x, line_y), line, font=font, fill=1)
            
        y += line_h + line_spacing
        
    return img

def parse_speed_multiplier(speed_str):
    try:
        val = speed_str.split()[0].replace("x", "")
        return float(val)
    except Exception:
        return 1.0

def apply_offset_to_image(img, offset_x, offset_y):
    if offset_x == 0 and offset_y == 0:
        return img
    offset_img = Image.new("1", (128, 64), 0)
    offset_img.paste(img, (offset_x, offset_y))
    return offset_img

# ── CPU Temperature Structures ───────────────────────────────────────────────
import ctypes

class CoreTempSharedDataEx(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("uiLoad", ctypes.c_uint * 256),
        ("uiTjMax", ctypes.c_uint * 128),
        ("uiCoreCnt", ctypes.c_uint),
        ("uiCPUCnt", ctypes.c_uint),
        ("fTemp", ctypes.c_float * 256),
        ("fVID", ctypes.c_float),
        ("fCPUSpeed", ctypes.c_float),
        ("fFSBSpeed", ctypes.c_float),
        ("fMultiplier", ctypes.c_float),
        ("sCPUName", ctypes.c_char * 100),
        ("ucFahrenheit", ctypes.c_ubyte),
        ("ucDeltaToTjMax", ctypes.c_ubyte),
        ("ucTdpSupported", ctypes.c_ubyte),
        ("ucPowerSupported", ctypes.c_ubyte),
        ("uiStructVersion", ctypes.c_uint),
        ("uiTdp", ctypes.c_uint * 128),
        ("fPower", ctypes.c_float * 128),
        ("fMultipliers", ctypes.c_float * 256),
    ]

def get_cpu_temp():
    # 0. Try native LibreHardwareMonitorLib via pythonnet (clr)
    try:
        import clr
        import os
        import sys
        
        # Resolve path to LibreHardwareMonitorLib.dll
        dll_path = None
        if hasattr(sys, "_MEIPASS"):
            paths_to_check = [
                os.path.join(sys._MEIPASS, "WinTmp", "LibreHardwareMonitorLib.dll"),
                os.path.join(sys._MEIPASS, "LibreHardwareMonitorLib.dll")
            ]
        else:
            paths_to_check = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "LibreHardwareMonitorLib.dll"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "WinTmp", "LibreHardwareMonitorLib.dll"),
                "LibreHardwareMonitorLib.dll"
            ]
            
        for path in paths_to_check:
            if os.path.exists(path):
                dll_path = os.path.abspath(path)
                break
                
        if dll_path:
            if not hasattr(get_cpu_temp, "dll_loaded"):
                clr.AddReference(dll_path)
                get_cpu_temp.dll_loaded = True
                
            from LibreHardwareMonitor import Hardware
            
            if not hasattr(get_cpu_temp, "hw"):
                hw = Hardware.Computer()
                hw.IsCpuEnabled = True
                hw.IsMemoryEnabled = False  # Bypasses RAMSPDToolkit-NDD.dll crash
                hw.IsGpuEnabled = False
                hw.IsMotherboardEnabled = False
                hw.IsStorageEnabled = False
                try:
                    hw.Open()
                    get_cpu_temp.hw = hw
                except Exception:
                    get_cpu_temp.hw = None
                    
            if get_cpu_temp.hw:
                for h in get_cpu_temp.hw.Hardware:
                    h.Update()
                    if h.HardwareType == Hardware.HardwareType.Cpu:
                        for sensor in h.Sensors:
                            if sensor.SensorType == Hardware.SensorType.Temperature:
                                val = sensor.Value
                                if val is not None and val > 1.0:
                                    return f"{int(val)}°C"
    except Exception:
        pass

    # 1. Try CoreTemp Shared Memory
    try:
        kernel32 = ctypes.windll.kernel32
        FILE_MAP_READ = 0x0004
        hMap = kernel32.OpenFileMappingA(FILE_MAP_READ, False, b"CoreTempSeg")
        if not hMap:
            hMap = kernel32.OpenFileMappingA(FILE_MAP_READ, False, b"Global\\CoreTempSeg")
        if hMap:
            try:
                pBuf = kernel32.MapViewOfFile(hMap, FILE_MAP_READ, 0, 0, 0)
                if pBuf:
                    try:
                        data = CoreTempSharedDataEx.from_address(pBuf)
                        core_cnt = data.uiCoreCnt
                        temps = [data.fTemp[i] for i in range(min(core_cnt, 256))]
                        if temps:
                            val = sum(temps) / len(temps)
                            if 0 < val < 150:
                                return f"{int(val)}°C"
                    finally:
                        kernel32.UnmapViewOfFile(pBuf)
            finally:
                kernel32.CloseHandle(hMap)
    except Exception:
        pass

    # 2. Try WMI queries for background monitoring tools or ACPI
    com_initialized = False
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        com_initialized = True
        
        # 2a. Try LibreHardwareMonitor WMI
        try:
            wmi_obj = win32com.client.GetObject("winmgmts:\\\\.\\root\\LibreHardwareMonitor")
            sensors = wmi_obj.ExecQuery("SELECT Value FROM Sensor WHERE SensorType = 'Temperature' AND (Name LIKE '%Package%' OR Name LIKE '%Core%')")
            for s in sensors:
                val = float(s.Value)
                if 0 < val < 150:
                    return f"{int(val)}°C"
        except Exception:
            pass

        # 2b. Try OpenHardwareMonitor WMI
        try:
            wmi_obj = win32com.client.GetObject("winmgmts:\\\\.\\root\\OpenHardwareMonitor")
            sensors = wmi_obj.ExecQuery("SELECT Value FROM Sensor WHERE SensorType = 'Temperature' AND (Name LIKE '%Package%' OR Name LIKE '%Core%')")
            for s in sensors:
                val = float(s.Value)
                if 0 < val < 150:
                    return f"{int(val)}°C"
        except Exception:
            pass

        # 2c. Try native ACPI ThermalZone WMI as a last resort
        try:
            wmi_obj = win32com.client.GetObject("winmgmts:\\\\.\\root\\wmi")
            sensors = wmi_obj.ExecQuery("SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature")
            for s in sensors:
                val = float(s.CurrentTemperature)
                temp_c = int(val / 10.0 - 273.15)
                if 0 < temp_c < 150:
                    return f"{temp_c}°C"
        except Exception:
            pass
    except Exception:
        pass
    finally:
        if com_initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    return None

# --- CPU Page Binary Assets ---
# 101x13 percent box
PARCENT_BOX_BITS = (
    bytes([0xff,0xff,0xfb,0xff,0xff,0xfe,0xff,0xff,0xfb,0xff,0xff,0xff,0x1f]) +
    bytes([0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x10]) * 11 +
    bytes([0xff,0xff,0xfb,0xff,0xff,0xfe,0xff,0xff,0xfb,0xff,0xff,0xff,0x1f])
)


# 4x8 progress bar head
PROGRESS_BAR_HEAD_BITS = bytes([0x03,0x03,0x0c,0x0c,0x03,0x03,0x0c,0x0c])

# 18x18 Smile
SMILE_BITS = bytes([
    0xc0,0x0f,0x00,0xf0,0x3f,0x00,0xf8,0x7f,0x00,0xfc,0xff,0x00,0xfe,0xff,0x01,0xfe,
    0xff,0x01,0xff,0xff,0x03,0xcf,0xcf,0x03,0x87,0x87,0x03,0x87,0x87,0x03,0xcf,0xcf,
    0x03,0xff,0xff,0x03,0xfe,0xff,0x01,0xbe,0xf7,0x01,0x7c,0xf8,0x00,0xf8,0x7f,0x00,
    0xf0,0x3f,0x00,0xc0,0x0f,0x00
])

# 18x21 Evil Smile
EVI_SMILE_BITS = bytes([
    0x0c,0xc0,0x00,0x06,0x80,0x01,0x07,0x80,0x03,0xcf,0xcf,0x03,0xff,0xff,0x03,0xff,
    0xff,0x03,0xfe,0xff,0x01,0xfe,0xff,0x01,0xfe,0xff,0x01,0xf7,0xbf,0x03,0xe7,0x9f,
    0x03,0xc7,0x8f,0x03,0x87,0x87,0x03,0x8f,0xc7,0x03,0xff,0xff,0x03,0xfe,0xff,0x01,
    0xde,0xef,0x01,0xbc,0xf4,0x00,0x78,0x78,0x00,0xf0,0x3f,0x00,0xc0,0x0f,0x00
])

# 11x1 dot line left/right
DOT_LINE_LEFT_BITS = bytes([0xdb,0x06])

# 14x6 RAM Icon
RAM_ICON_BITS = bytes([0xff,0x3f,0xfd,0x3f,0xfd,0x3f,0xfd,0x3f,0xfd,0x3f,0xff,0x3e])

# 11x8 Storage Icon
STORAGE_ICON_BITS = bytes([0xff,0x07,0xff,0x04,0xff,0x07,0xff,0x04,0xff,0x07,0xff,0x04,0xff,0x07,0x67,0x00])

# 19x10 TX Icon
TX_ICON_BITS = bytes([
    0xfe,0xff,0x03,0xff,0xff,0x07,0x1f,0xed,0x07,0xbf,0xed,0x07,0xbf,0xf3,0x07,0xbf,
    0xf3,0x07,0xbf,0xed,0x07,0xbf,0xed,0x07,0xff,0xff,0x07,0xfe,0xff,0x03
])

# 19x10 RX Icon
RX_ICON_BITS = bytes([
    0xfe,0xff,0x03,0xff,0xff,0x07,0x1f,0xdb,0x07,0xdf,0xda,0x07,0xdf,0xe6,0x07,0x1f,
    0xe7,0x07,0xdf,0xda,0x07,0xdf,0xda,0x07,0xff,0xff,0x07,0xfe,0xff,0x03
])

# Convert bits to PIL images
IMG_PARCENT_BOX = Image.frombytes("1", (101, 13), PARCENT_BOX_BITS, "raw", "1;R")
IMG_PROGRESS_BAR_HEAD = Image.frombytes("1", (4, 8), PROGRESS_BAR_HEAD_BITS, "raw", "1;R")
IMG_SMILE = Image.frombytes("1", (18, 18), SMILE_BITS, "raw", "1;R")
IMG_EVI_SMILE = Image.frombytes("1", (18, 21), EVI_SMILE_BITS, "raw", "1;R")
IMG_DOT_LINE_LEFT = Image.frombytes("1", (11, 1), DOT_LINE_LEFT_BITS, "raw", "1;R")
IMG_RAM_ICON = Image.frombytes("1", (14, 6), RAM_ICON_BITS, "raw", "1;R")
IMG_STORAGE_ICON = Image.frombytes("1", (11, 8), STORAGE_ICON_BITS, "raw", "1;R")
IMG_TX_ICON = Image.frombytes("1", (19, 10), TX_ICON_BITS, "raw", "1;R")
IMG_RX_ICON = Image.frombytes("1", (19, 10), RX_ICON_BITS, "raw", "1;R")

def get_stats_overshoot_value(t_elapsed, V_real, V_max):
    T_rise = 0.3
    T_fall = 0.7
    T_anim = T_rise + T_fall
    if t_elapsed >= T_anim:
        return V_real
    
    if t_elapsed < T_rise:
        # Rise phase: quadratic ease-in/out to V_max
        factor = 1.0 - (1.0 - t_elapsed / T_rise) ** 2
        return factor * V_max
    else:
        # Fall phase: V_max to V_real using cosine interpolation
        u = (t_elapsed - T_rise) / T_fall
        cos_val = (1.0 + math.cos(u * math.pi)) / 2.0
        return V_real + (V_max - V_real) * cos_val

def render_stats_cpu(stats):
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"

    cpu_util_str = stats.get("cpu_util", "0%")
    try:
        cpu_util = int(cpu_util_str.replace("%", ""))
    except Exception:
        cpu_util = 0

    cpu_temp_str = stats.get("cpu_temp", "--°C")
    cpu_temp_num = cpu_temp_str.replace("°C", "").replace("C", "")
    temp_display = f"{cpu_temp_num}C"

    # Fake CPU MHz based on cpu_util mapping from cpu_min_mhz to cpu_max_mhz
    cpu_min = int(stats.get("cpu_min_mhz", 3600))
    cpu_max = int(stats.get("cpu_max_mhz", 4200))
    cpu_mhz = cpu_min + int(cpu_util * (cpu_max - cpu_min) / 100)
    c_min = min(cpu_min, cpu_max)
    c_max = max(cpu_min, cpu_max)
    cpu_mhz = max(c_min, min(c_max, cpu_mhz))

    # 1. TEMP BOX (pushed left boundary to 102 to give more room)
    draw.rectangle([102, 2, 126, 14], fill=0, outline=1)

    # 2. PARCENT BOX
    img.paste(IMG_PARCENT_BOX, (1, 2))

    # 3. PROGRESS BAR (0-92 px, clamped to min 18 px so the white bar covers the text segment)
    bar_width = int(cpu_util * 92 / 100)
    bar_width = max(18, min(92, bar_width))
    if bar_width > 0:
        draw.rectangle([3, 4, 3 + bar_width - 1, 4 + 9 - 1], fill=1)

    # 4. PROGRESS BAR HEAD (pasted with transparent mask)
    head_x = 3 + bar_width
    img.paste(IMG_PROGRESS_BAR_HEAD, (head_x, 4), mask=IMG_PROGRESS_BAR_HEAD)

    # 5. MHZ BOX (rounded rect radius 2 at 54, 45, 19, 10)
    draw.rounded_rectangle([54, 45, 55 + 18 - 1, 45 + 10 - 1], radius=2, fill=1)

    # 6. DOT LINE LEFT/RIGHT (shifted left dot line to x=20 to prevent overlap)
    img.paste(IMG_DOT_LINE_LEFT, (20, 31))
    img.paste(IMG_DOT_LINE_LEFT, (96, 31))

    # 7. Face Sprite
    if cpu_mhz > 3900:
        img.paste(IMG_EVI_SMILE, (109, 21))
    else:
        img.paste(IMG_SMILE, (109, 23))

    font_hax = get_font("U8g2 Haxrcorp 4089", 15)  # size 15 (perfect pixel scaling, w=15, h=7)
    font_pro10 = get_font("U8g2 ProFont", 10)      # size 10
    font_pro29 = get_font("U8g2 ProFont", 30)      # size 30

    # Draw CPU text
    draw.text((2, 26), "CPU", font=font_pro10, fill=1)

    # Draw MHZ speed text (dynamically centered between the dot lines at x=20..30 and x=96..106)
    cpu_mhz_str = str(cpu_mhz)
    mhz_text_w = font_pro29.getlength(cpu_mhz_str)
    # Left dot line ends at 30, right starts at 96. Center is (30 + 96) // 2 = 63.
    cpu_x_pos = int(63 - mhz_text_w // 2)
    draw.text((cpu_x_pos, 18), cpu_mhz_str, font=font_pro29, fill=1)

    # Draw temperature dynamically inside 102..126 box
    # Extract only digits and sign from the temp string
    import re
    temp_digits = "".join(re.findall(r"[-+]?\d+", cpu_temp_num))
    if not temp_digits:
        temp_digits = "--"
    
    digits_w = font_hax.getlength(temp_digits)
    total_temp_w = digits_w + 8  # digits + degree (1) + gap (2) + C (5)
    temp_x = max(103, min(107, int(125 - total_temp_w)))
    
    # 1. digits
    draw.text((temp_x, 3), temp_digits, font=font_hax, fill=1)
    # 2. degree symbol (1x1 frame) - moved 2px down and 1px left
    deg_x = int(temp_x + digits_w)
    draw.rectangle([deg_x, 5, deg_x, 5], fill=1, outline=1)
    # 3. C symbol
    draw.text((temp_x + digits_w + 3, 3), "C", font=font_hax, fill=1)

    # XOR Layer
    xor_img = Image.new("1", (128, 64), 0)
    xor_draw = ImageDraw.Draw(xor_img)
    xor_draw.fontmode = "1"

    # Draw percentage text (XOR) - pushed up 1 pixel for vertical centering
    xor_draw.text((4, 3), f"{cpu_util}%", font=font_hax, fill=1)

    # Draw MHZ text (XOR) - shifted to x=56 to center inside the box
    xor_draw.text((56, 45), "MHZ", font=font_pro10, fill=1)

    # Apply XOR
    from PIL import ImageChops
    img = ImageChops.logical_xor(img, xor_img)

    return img

def render_stats_gpu(stats):
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"

    gpu_util_str = stats.get("gpu_util", "0%")
    try:
        gpu_util = int(gpu_util_str.replace("%", ""))
    except Exception:
        gpu_util = 0

    gpu_temp_str = stats.get("gpu_temp", "--°C")
    gpu_temp_num = gpu_temp_str.replace("°C", "").replace("C", "")
    temp_display = f"{gpu_temp_num}C"

    # Wattage: 30W to 180W depending on gpu_util
    # Wattage mapping from gpu_min_watt to gpu_max_watt depending on gpu_util
    gpu_min = int(stats.get("gpu_min_watt", 30))
    gpu_max = int(stats.get("gpu_max_watt", 180))
    watt = gpu_min + int(gpu_util * (gpu_max - gpu_min) / 100)
    w_min = min(gpu_min, gpu_max)
    w_max = max(gpu_min, gpu_max)
    watt = max(w_min, min(w_max, watt))

    # 1. TEMP BOX (pushed left boundary to 102 to give more room)
    draw.rectangle([102, 2, 126, 14], fill=0, outline=1)

    # 2. PARCENT BOX
    img.paste(IMG_PARCENT_BOX, (1, 2))

    # 3. PROGRESS BAR (0-92 px, clamped to min 18 px so the white bar covers the text segment)
    bar_width = int(gpu_util * 92 / 100)
    bar_width = max(18, min(92, bar_width))
    if bar_width > 0:
        draw.rectangle([3, 4, 3 + bar_width - 1, 4 + 9 - 1], fill=1)

    # 4. PROGRESS BAR HEAD (pasted with transparent mask)
    head_x = 3 + bar_width
    img.paste(IMG_PROGRESS_BAR_HEAD, (head_x, 4), mask=IMG_PROGRESS_BAR_HEAD)

    # 5. PWR BOX (rounded rect radius 2 at 54, 45, 19, 10)
    draw.rounded_rectangle([54, 45, 55 + 18 - 1, 45 + 10 - 1], radius=2, fill=1)

    # 6. DOT LINE LEFT/RIGHT (shifted left dot line to x=20 to prevent overlap)
    img.paste(IMG_DOT_LINE_LEFT, (20, 31))
    img.paste(IMG_DOT_LINE_LEFT, (96, 31))

    # 7. Face Sprite
    if watt > 70:
        img.paste(IMG_EVI_SMILE, (109, 21))
    else:
        img.paste(IMG_SMILE, (109, 23))

    font_hax = get_font("U8g2 Haxrcorp 4089", 15)  # size 15 (perfect pixel scaling)
    font_pro10 = get_font("U8g2 ProFont", 10)      # size 10
    font_pro29 = get_font("U8g2 ProFont", 30)      # size 30

    # Draw GPU text
    draw.text((2, 26), "GPU", font=font_pro10, fill=1)

    # Draw Wattage text (dynamically centered between the dot lines at x=20..30 and x=96..106)
    val_str = f"{watt}W"
    watt_text_w = font_pro29.getlength(val_str)
    # Left dot line ends at 30, right starts at 96. Center is (30 + 96) // 2 = 63.
    gpu_x_pos = int(63 - watt_text_w // 2)
    draw.text((gpu_x_pos, 18), val_str, font=font_pro29, fill=1)

    # Draw temperature dynamically inside 102..126 box
    # Extract only digits and sign from the temp string
    import re
    temp_digits = "".join(re.findall(r"[-+]?\d+", gpu_temp_num))
    if not temp_digits:
        temp_digits = "--"
    
    digits_w = font_hax.getlength(temp_digits)
    total_temp_w = digits_w + 8  # digits + degree (1) + gap (2) + C (5)
    temp_x = max(103, min(107, int(125 - total_temp_w)))
    
    # 1. digits
    draw.text((temp_x, 3), temp_digits, font=font_hax, fill=1)
    # 2. degree symbol (1x1 frame) - moved 2px down and 1px left
    deg_x = int(temp_x + digits_w)
    draw.rectangle([deg_x, 5, deg_x, 5], fill=1, outline=1)
    # 3. C symbol
    draw.text((temp_x + digits_w + 3, 3), "C", font=font_hax, fill=1)

    # XOR Layer
    xor_img = Image.new("1", (128, 64), 0)
    xor_draw = ImageDraw.Draw(xor_img)
    xor_draw.fontmode = "1"

    # Draw percentage text (XOR) - pushed up 1 pixel for vertical centering
    xor_draw.text((4, 3), f"{gpu_util}%", font=font_hax, fill=1)

    # Draw PWR text (XOR) - shifted to x=56 to center inside the box
    xor_draw.text((56, 45), "PWR", font=font_pro10, fill=1)

    # Apply XOR
    from PIL import ImageChops
    img = ImageChops.logical_xor(img, xor_img)

    return img

def render_stats_mem_net(stats):
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"

    ram_util_str = stats.get("ram_util", "0%")
    try:
        ram_util = int(ram_util_str.replace("%", ""))
    except Exception:
        ram_util = 0

    disk_util_str = stats.get("disk_util", "0%")
    try:
        disk_util = int(disk_util_str.replace("%", ""))
    except Exception:
        disk_util = 0

    net_tx_val = stats.get("net_tx", 0.0)
    net_rx_val = stats.get("net_rx", 0.0)

    def format_speed(speed_bytes):
        speed_kb = speed_bytes / 1024.0
        if speed_kb < 1024:
            return f"{int(speed_kb)}KB"
        else:
            val = speed_kb / 1024.0
            if val < 9.9:
                return f"{val:.1f}MB"
            else:
                return f"{int(val)}MB"

    tx_display = format_speed(net_tx_val)
    rx_display = format_speed(net_rx_val)

    # 1. RAM BOX & STORAGE BOX frames (pushed left boundary to 102 to give more room)
    draw.rectangle([102, 2, 126, 14], fill=0, outline=1)
    draw.rectangle([102, 17, 126, 29], fill=0, outline=1)

    # 2. PARCENT BOX (RAM) & PARCENT BOX (DISK)
    img.paste(IMG_PARCENT_BOX, (1, 2))
    img.paste(IMG_PARCENT_BOX, (1, 17))

    # 3. PROGRESS BAR RAM (0-92 px, clamped to min 18 px so the white bar covers the text segment)
    ram_bar_w = int(ram_util * 92 / 100)
    ram_bar_w = max(18, min(92, ram_bar_w))
    if ram_bar_w > 0:
        draw.rectangle([3, 4, 3 + ram_bar_w - 1, 4 + 9 - 1], fill=1)
    ram_head_x = 3 + ram_bar_w
    img.paste(IMG_PROGRESS_BAR_HEAD, (ram_head_x, 4), mask=IMG_PROGRESS_BAR_HEAD)

    # 4. PROGRESS BAR DISK (0-92 px, clamped to min 18 px so the white bar covers the text segment)
    disk_bar_w = int(disk_util * 92 / 100)
    disk_bar_w = max(18, min(92, disk_bar_w))
    if disk_bar_w > 0:
        draw.rectangle([3, 19, 3 + disk_bar_w - 1, 19 + 9 - 1], fill=1)
    disk_head_x = 3 + disk_bar_w
    img.paste(IMG_PROGRESS_BAR_HEAD, (disk_head_x, 19), mask=IMG_PROGRESS_BAR_HEAD)

    # 5. TX BOX & RX BOX frames
    draw.rectangle([1, 34, 1 + 63 - 1, 34 + 17 - 1], fill=0, outline=1)
    draw.rectangle([65, 34, 65 + 62 - 1, 34 + 17 - 1], fill=0, outline=1)

    # 6. STORAGE ICON & RAM ICON
    img.paste(IMG_RAM_ICON, (108, 5))
    img.paste(IMG_STORAGE_ICON, (109, 20))

    # 7. TX ICON & RX ICON (static)
    img.paste(IMG_TX_ICON, (1, 52))
    img.paste(IMG_RX_ICON, (65, 52))

    # 7b. ACTIVITY DOTS (2x2 blip next to icon, blinks during active transfer)
    t_now = time.time()
    blink = (t_now % 0.5 < 0.25)
    if net_tx_val > 1024 and blink:
        draw.rectangle([22, 56, 23, 57], fill=1)
    if net_rx_val > 1024 and blink:
        draw.rectangle([86, 56, 87, 57], fill=1)

    # 8. DEVIDER (Solid 126x2 block)
    draw.rectangle([1, 31, 126, 32], fill=1)

    # Load fonts
    font_hax = get_font("U8g2 Haxrcorp 4089", 15)  # size 15 (perfect pixel scaling)
    font_pro22 = get_font("U8g2 ProFont", 23)      # size 23 (height=14, offset=5)

    # Draw Tx / Rx speeds inside panels - pushed 1 pixel down for vertical centering
    draw.text((3, 32), tx_display, font=font_pro22, fill=1)
    draw.text((67, 32), rx_display, font=font_pro22, fill=1)

    # XOR Layer
    xor_img = Image.new("1", (128, 64), 0)
    xor_draw = ImageDraw.Draw(xor_img)
    xor_draw.fontmode = "1"

    # RAM utilization percentage (XOR) - pushed up 1 pixel for vertical centering
    xor_draw.text((4, 3), f"{ram_util}%", font=font_hax, fill=1)

    # DISK utilization percentage (XOR) - pushed up 1 pixel for vertical centering
    xor_draw.text((4, 18), f"{disk_util}%", font=font_hax, fill=1)

    # Apply XOR
    from PIL import ImageChops
    img = ImageChops.logical_xor(img, xor_img)

    return img

def render_pc_stats(stats, show_gpu, font_name="Proggy Tiny"):
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"

    STATS_FONT_SIZES = {
        "Proggy Tiny": {"small": 12, "large": 24},
        "Tiny5": {"small": 10, "large": 20},
        "Cozette": {"small": 13, "large": 26},
        "Tom Thumb": {"small": 15, "large": 30},
        "U8g2 Nokia Small": {"small": 8, "large": 16},
        "U8g2 Nokia Small Bold": {"small": 8, "large": 16},
        "U8g2 Nokia Large Bold": {"small": 10, "large": 20},
        "U8g2 Haxrcorp 4089": {"small": 8, "large": 16},
        "U8g2 3x5": {"small": 8, "large": 16},
        "U8g2 8bit Classic": {"small": 8, "large": 16},
        "U8g2 Commodore 64": {"small": 8, "large": 16},
        "U8g2 Press Start 2P": {"small": 8, "large": 16},
        "U8g2 Pixellari": {"small": 8, "large": 16},
        "U8g2 Terminal": {"small": 8, "large": 16}
    }

    sizes = STATS_FONT_SIZES.get(font_name)
    if not sizes:
        small_sz, large_sz = 9, 18
    else:
        small_sz = sizes["small"]
        large_sz = sizes["large"]

    cpu_name = stats.get("cpu_name", "Unknown CPU")
    cpu_mhz = stats.get("cpu_mhz", "0")
    cpu_temp = stats.get("cpu_temp", "--°C")
    cpu_util = stats.get("cpu_util", "0%")

    gpu_name = stats.get("gpu_name", "Unknown GPU")
    gpu_temp = stats.get("gpu_temp", "0°C")
    gpu_core = stats.get("gpu_core", "0")
    gpu_mem = stats.get("gpu_mem", "0")
    gpu_util = stats.get("gpu_util", "0%")

    disk_util = stats.get("disk_util", "0%")
    ram_util = stats.get("ram_util", "0%")
    local_time = stats.get("local_time", "00:00")

    current_large_sz = large_sz
    current_small_sz = small_sz
    
    while True:
        if font_name.startswith("Vin Mono Pro"):
            f_reg = get_font("Vin Mono Pro (Regular)", current_small_sz)
            f_bold = get_font("Vin Mono Pro (Bold)", current_small_sz)
            f_large = get_font("Vin Mono Pro (Bold)", current_large_sz)
            f_thin = get_font("Vin Mono Pro (Thin)", current_small_sz)
        else:
            f_reg = get_font(font_name, current_small_sz)
            f_bold = get_font(font_name, current_small_sz)
            f_large = get_font(font_name, current_large_sz)
            f_thin = get_font(font_name, current_small_sz)
            
        w_cpu = draw.textlength("CPU", font=f_large)
        w_mhz_val = draw.textlength(cpu_mhz, font=f_large)
        w_mhz_lbl = draw.textlength("MHz", font=f_thin)
        w_temp = draw.textlength(cpu_temp, font=f_bold)
        w_util = draw.textlength(cpu_util, font=f_bold)
        
        mhz_val_start = max(30, 2 + w_cpu + 2)
        mhz_lbl_start = mhz_val_start + w_mhz_val + 1
        left_block_end = mhz_lbl_start + w_mhz_lbl
        right_block_start = min(126 - w_temp, 126 - w_util)
        
        if left_block_end + 4 <= right_block_start:
            break
            
        if current_large_sz > current_small_sz:
            current_large_sz = current_small_sz
        elif current_small_sz > 5:
            current_small_sz -= 1
        else:
            break

    gpu_large_sz = large_sz
    gpu_small_sz = small_sz
    gpu_tag = "GPU" if show_gpu else "MEM"
    
    while True:
        if font_name.startswith("Vin Mono Pro"):
            f_reg_gpu = get_font("Vin Mono Pro (Regular)", gpu_small_sz)
            f_bold_gpu = get_font("Vin Mono Pro (Bold)", gpu_small_sz)
            f_large_gpu = get_font("Vin Mono Pro (Bold)", gpu_large_sz)
        else:
            f_reg_gpu = get_font(font_name, gpu_small_sz)
            f_bold_gpu = get_font(font_name, gpu_small_sz)
            f_large_gpu = get_font(font_name, gpu_large_sz)
            
        w_gpu_lbl = draw.textlength(gpu_tag, font=f_large_gpu)
        metrics_start = max(40, 2 + w_gpu_lbl + 2)
        
        if show_gpu:
            m1 = f"Core:{gpu_core}MHz"
            m2 = f"Mem :{gpu_mem}"
            m3 = f"Util:{gpu_util}"
        else:
            m1 = f"Disk:{disk_util}"
            m2 = f"Time:{local_time}"
            m3 = "Status:Active"
            
        w_m1 = draw.textlength(m1, font=f_reg_gpu)
        w_m2 = draw.textlength(m2, font=f_reg_gpu)
        w_m3 = draw.textlength(m3, font=f_reg_gpu)
        max_m_w = max(w_m1, w_m2, w_m3)
        
        if metrics_start + max_m_w <= 126:
            break
            
        if gpu_large_sz > gpu_small_sz:
            gpu_large_sz = gpu_small_sz
        elif gpu_small_sz > 5:
            gpu_small_sz -= 1
        else:
            break

    w_cpu_name = draw.textlength(cpu_name, font=f_bold)
    while 2 + w_cpu_name > 126 and len(cpu_name) > 3:
        cpu_name = cpu_name[:-1]
        w_cpu_name = draw.textlength(cpu_name + "...", font=f_bold)
    if 2 + w_cpu_name > 126:
        cpu_name = cpu_name + "..."

    w_gpu_name = draw.textlength(gpu_name, font=f_bold)
    while 2 + w_gpu_name > 126 and len(gpu_name) > 3:
        gpu_name = gpu_name[:-1]
        w_gpu_name = draw.textlength(gpu_name + "...", font=f_bold)
    if 2 + w_gpu_name > 126:
        gpu_name = gpu_name + "..."

    draw.text((2, 0), cpu_name, font=f_bold, fill=1)
    draw.text((2, 10), "CPU", font=f_large, fill=1)
    draw.text((mhz_val_start, 10), cpu_mhz, font=f_large, fill=1)
    y_offset = (current_large_sz - current_small_sz) if current_large_sz > current_small_sz else 0
    draw.text((mhz_lbl_start, 10 + y_offset), "MHz", font=f_thin, fill=1)
    w_temp = draw.textlength(cpu_temp, font=f_bold)
    draw.text((126 - w_temp, 10), cpu_temp, font=f_bold, fill=1)
    w_util = draw.textlength(cpu_util, font=f_bold)
    draw.text((126 - w_util, 19), cpu_util, font=f_bold, fill=1)

    if show_gpu:
        draw.text((2, 30), gpu_name, font=f_bold, fill=1)
        draw.text((2, 40), "GPU", font=f_large_gpu, fill=1)
        draw.text((2, 55), gpu_temp, font=f_reg_gpu, fill=1)
        draw.text((metrics_start, 40), m1, font=f_reg_gpu, fill=1)
        draw.text((metrics_start, 48), m2, font=f_reg_gpu, fill=1)
        draw.text((metrics_start, 56), m3, font=f_reg_gpu, fill=1)
    else:
        draw.text((2, 30), "Disk & Memory", font=f_bold, fill=1)
        draw.text((2, 40), "MEM", font=f_large_gpu, fill=1)
        draw.text((2, 55), ram_util, font=f_bold_gpu, fill=1)
        draw.text((metrics_start, 40), m1, font=f_reg_gpu, fill=1)
        draw.text((metrics_start, 48), m2, font=f_reg_gpu, fill=1)
        draw.text((metrics_start, 56), m3, font=f_reg_gpu, fill=1)

    return img

WHEEL_LEFT_BITS = bytes([
    0x00,0x00,0xc7,0x01,0x00,0x00,0x00,0xe0,0xc7,0x0f,0x00,0x00,0x00,0xf8,0xc7,0x3f,
    0x00,0x00,0x00,0xfe,0xc7,0xff,0x00,0x00,0x00,0xff,0x01,0xff,0x01,0x00,0x80,0x3f,
    0x00,0xf8,0x03,0x00,0xc0,0x0f,0x00,0xe0,0x07,0x00,0xe0,0x07,0x00,0xc0,0x0f,0x00,
    0xf0,0x01,0xfe,0x00,0x1f,0x00,0xf8,0x80,0xff,0x03,0x3e,0x00,0xf8,0xe0,0xff,0x0f,
    0x3e,0x00,0x7c,0xf0,0xff,0x1f,0x7c,0x00,0x3c,0xf8,0xff,0x3f,0x78,0x00,0x3e,0xfc,
    0xff,0x7f,0xf8,0x00,0x1e,0xfc,0xff,0x7f,0xf0,0x00,0x1e,0xfe,0x83,0xff,0xf0,0x00,
    0x1f,0xfe,0x01,0xff,0xf0,0x01,0x0f,0xff,0x00,0xfe,0xe1,0x01,0x0f,0x7f,0x00,0xfc,
    0xe1,0x01,0x00,0x7f,0x00,0xfc,0x01,0x00,0x00,0x7f,0x00,0xfc,0x01,0x00,0x00,0x7f,
    0x00,0xfc,0x01,0x00,0x0f,0x7f,0x00,0xfc,0xe1,0x01,0x0f,0xff,0x00,0xfe,0xe1,0x01,
    0x1f,0xfe,0x01,0xff,0xf0,0x01,0x1e,0xfe,0x83,0xff,0xf0,0x00,0x1e,0xfc,0xff,0x7f,
    0xf0,0x00,0x3e,0xfc,0xff,0x7f,0xf8,0x00,0x3c,0xf8,0xff,0x3f,0x78,0x00,0x7c,0xf0,
    0xff,0x1f,0x7c,0x00,0xf8,0xe0,0xff,0x0f,0x3e,0x00,0xf8,0x80,0xff,0x03,0x3e,0x00,
    0xf0,0x01,0xfe,0x00,0x1f,0x00,0xe0,0x07,0x00,0xc0,0x0f,0x00,0xc0,0x0f,0x00,0xe0,
    0x07,0x00,0x80,0x3f,0x00,0xf8,0x03,0x00,0x00,0xff,0x01,0xff,0x01,0x00,0x00,0xfe,
    0xc7,0xff,0x00,0x00,0x00,0xf8,0xc7,0x3f,0x00,0x00,0x00,0xe0,0xc7,0x0f,0x00,0x00,
    0x00,0x00,0xc7,0x01,0x00,0x00
])

STRING_STATIC_BITS = bytes([
    0x00,0x00,0x00,0xc0,0x0f,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0xc0,0x0f,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0xc0,0x0f,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0xc0,0x0f,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0xc0,0x0f,0x00,0x00,0x00,0x00,
    0x00,0x00,0x00,0x40,0x08,0x00,0x00,0x00,0x00,
    0x01,0x00,0x00,0x40,0x08,0x00,0x00,0x00,0x01,
    0x06,0x00,0x00,0x40,0x08,0x00,0x00,0xc0,0x00,
    0x18,0x00,0x07,0x30,0x30,0x80,0x03,0x30,0x00,
    0x60,0x80,0x0f,0x08,0x40,0xc0,0x07,0x0c,0x00,
    0x80,0xc0,0x1f,0x06,0x80,0xe1,0x0f,0x02,0x00,
    0x00,0xc3,0x9f,0x01,0x00,0xe6,0x8f,0x01,0x00,
    0x00,0xcc,0x5f,0x00,0x00,0xe8,0x6f,0x00,0x00,
    0x00,0xf0,0x3f,0x00,0x00,0xf0,0x1f,0x00,0x00,
    0x00,0xc0,0x0f,0x00,0x00,0xc0,0x07,0x00,0x00
])

IMG_WHEEL_LEFT = Image.frombytes("1", (41, 41), WHEEL_LEFT_BITS, "raw", "1;R")
IMG_STRING_STATIC = Image.frombytes("1", (65, 15), STRING_STATIC_BITS, "raw", "1;R")

# Day Night (OBSEDIAN) theme assets
IMAGE_ARROW_LEFT_BITS = bytes([0x01, 0x03, 0x07, 0x03, 0x01])
IMAGE_ARROW_RIGHT_BITS = bytes([0x04, 0x06, 0x07, 0x06, 0x04])
IMAGE_CLOCK_DIV_LINE_BITS = bytes([0xff, 0xff, 0xff, 0xff, 0x3c, 0xcf, 0xf3, 0xfc, 0xff, 0xff, 0xff, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0xff, 0xff, 0x3c, 0xcf, 0xf3, 0xfc, 0xff, 0xff, 0xff, 0x01])
IMAGE_DAY_BITS = bytes([0x20, 0x00, 0x22, 0x02, 0x74, 0x01, 0x88, 0x00, 0x04, 0x01, 0x07, 0x07, 0x04, 0x01, 0x88, 0x00, 0x74, 0x01, 0x22, 0x02, 0x20, 0x00])
IMAGE_MIDDAY_BITS = bytes([0x20, 0x00, 0x22, 0x02, 0x74, 0x01, 0xb8, 0x00, 0x3c, 0x01, 0x3f, 0x07, 0x3c, 0x01, 0xb8, 0x00, 0x74, 0x01, 0x22, 0x02, 0x20, 0x00])
IMAGE_NIGHT_BITS = bytes([0x38, 0x46, 0x22, 0x11, 0x11, 0x11, 0x22, 0x46, 0x38])
IMAGE_SUNSET_BITS = bytes([0x20, 0x00, 0x22, 0x02, 0x74, 0x01, 0x88, 0x00, 0x04, 0x01, 0x07, 0x07, 0x04, 0x01, 0xff, 0x07])

IMG_ARROW_LEFT = Image.frombytes("1", (3, 5), IMAGE_ARROW_LEFT_BITS, "raw", "1;R")
IMG_ARROW_RIGHT = Image.frombytes("1", (3, 5), IMAGE_ARROW_RIGHT_BITS, "raw", "1;R")
IMG_CLOCK_DIV_LINE = Image.frombytes("1", (89, 23), IMAGE_CLOCK_DIV_LINE_BITS, "raw", "1;R")
IMG_DAY = Image.frombytes("1", (11, 11), IMAGE_DAY_BITS, "raw", "1;R")
IMG_MIDDAY = Image.frombytes("1", (11, 11), IMAGE_MIDDAY_BITS, "raw", "1;R")
IMG_NIGHT = Image.frombytes("1", (7, 9), IMAGE_NIGHT_BITS, "raw", "1;R")
IMG_SUNSET = Image.frombytes("1", (11, 8), IMAGE_SUNSET_BITS, "raw", "1;R")

import random
RIGHT_WHEEL_OFFSET = random.uniform(30.0, 330.0)

def render_tape_graphics(tape_angle, vu_volume=0.0):
    img = Image.new("1", (128, 64), 0)
    img.paste(IMG_STRING_STATIC, (31, 43))
    left_rot = IMG_WHEEL_LEFT.rotate(-tape_angle, resample=Image.NEAREST)
    right_rot = IMG_WHEEL_LEFT.rotate(-(tape_angle + RIGHT_WHEEL_OFFSET), resample=Image.NEAREST)
    img.paste(left_rot, (14, 8))
    img.paste(right_rot, (72, 8))
    
    # Draw tiny cassette center window box aligned to bottom left corner
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 49, 15, 63], outline=1, fill=0)
    
    # Draw tiny oscilloscope wave inside the window
    if vu_volume > 0.01:
        points = []
        amp = vu_volume * 6.0
        for wx in range(1, 15):
            wy = 56 + amp * math.sin((wx - 1) * 0.6 + tape_angle * 0.2)
            points.append((wx, int(wy)))
        draw.line(points, fill=1, width=1)
    else:
        # Static line
        draw.line([(1, 56), (14, 56)], fill=1, width=1)
    return img



def render_stereo_bars(phase, vu_volume=0.0, peaks=None):
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    num_bars = 8
    bar_width = 10
    spacing = 4
    start_x = (128 - (num_bars * bar_width + (num_bars - 1) * spacing)) // 2
    for i in range(num_bars):
        wave_height = 4.0 + 3.0 * math.sin(phase + i * 0.8)
        vol_height = vu_volume * 45.0
        h = int(min(54, wave_height + vol_height))
        x0 = start_x + i * (bar_width + spacing)
        y0 = 64 - h
        x1 = x0 + bar_width - 1
        y1 = 64
        
        # Draw segmented equalizer bars
        for y in range(y0, y1, 4):
            draw.rectangle([x0, y, x1, min(y + 2, y1)], fill=1)
            
        # Draw peak-hold dots
        if peaks is not None:
            peak_h = peaks[i]
            if h > peak_h:
                peaks[i] = float(h)
            else:
                peaks[i] = max(0.0, peaks[i] - 1.2)  # Peak falls slowly
            
            y_peak = int(64 - peaks[i])
            if y_peak < 63:
                draw.rectangle([x0, y_peak, x1, min(y_peak + 1, 63)], fill=1)
                
    return img


def render_clock_mode(clock_format="12-Hour", clock_animation="Snappy Easing", clock_theme="OBSEDIAN", mock_time=None, mode_elapsed=None):
    import datetime
    import time
    import math
    from PIL import Image, ImageDraw

    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"

    # Get local system time
    if mock_time is not None:
        local_now = mock_time
        now_ts = mock_time.timestamp()
    else:
        now_ts = time.time()
        local_now = datetime.datetime.fromtimestamp(now_ts)
    sec = local_now.second
    # Easing animation logic for seconds slider
    t_frac = now_ts - math.floor(now_ts)
    
    if clock_animation == "Snappy Easing":
        anim_dur = 0.35 # smooth ease-in-out snap duration
        if t_frac < anim_dur:
            x = t_frac / anim_dur
            # Cubic ease-in-out curve
            ease = 3 * (x ** 2) - 2 * (x ** 3)
            S_smooth = (sec - 1 + ease) % 60
        else:
            S_smooth = sec
    else:
        # Smooth Sweep (Linear continuous sweep)
        S_smooth = (sec + t_frac) % 60

    clock_theme = "OBSEDIAN"

    if clock_theme == "OBSEDIAN":
        # Calculate transition progress t
        if mode_elapsed is not None and clock_animation != "None":
            t = min(1.0, max(0.0, mode_elapsed / 1.0))  # 1.0s duration
        else:
            t = 1.0

        def ease_out(val_t):
            if val_t >= 1.0:
                return 1.0
            return 1.0 - ((1.0 - val_t) ** 3)

        img_single_div = IMG_CLOCK_DIV_LINE.crop((0, 0, 89, 1))

        # 2. Get local time information
        hour = local_now.hour
        is_pm = hour >= 12
        if clock_format == "12-Hour":
            hour_12 = hour % 12
            if hour_12 == 0:
                hour_12 = 12
            hour_str = f"{hour_12:02d}"
        else:
            hour_str = f"{hour:02d}"
        min_str = f"{local_now.minute:02d}"
        sec_str = f"{sec:02d}"

        font_large = get_font("U8g2 ProFont", 31)
        font_haxr = get_font("U8g2 Haxrcorp 4089", 14)
        week_str = local_now.strftime("%a").upper()
        date_str = f"{local_now.month}/{local_now.day}"

        # Generate roll sequences for slot reel scroll
        hour_val = int(hour_str)
        modulo = 12 if clock_format == "12-Hour" else 24
        hour_roll_seq = []
        for i in range(5, -1, -1):
            val = (hour_val - i) % modulo
            if clock_format == "12-Hour" and val == 0:
                val = 12
            hour_roll_seq.append(f"{val:02d}")

        min_val = int(min_str)
        min_roll_seq = [f"{(min_val - i) % 60:02d}" for i in range(5, -1, -1)]

        sec_val = int(sec_str)
        sec_roll_seq = [f"{(sec_val - i) % 60:02d}" for i in range(5, -1, -1)]

        if t < 1.0:
            # --- ANIMATED RENDERING ---
            # 1. Clock div lines: expand from center
            w = int(round(ease_out(t) * 89))
            x_div = 19 + (89 - w) // 2
            img_single_div_anim = img_single_div.crop((0, 0, w, 1))
            img.paste(1, (x_div, 20), mask=img_single_div_anim)
            img.paste(1, (x_div, 41), mask=img_single_div_anim)

            # 2. Left and right arrows: slide in from second hour and first minute boundaries
            x_left = int(round(35 + ease_out(t) * 16))
            x_right = int(round(78 - ease_out(t) * 5))
            img.paste(1, (x_left, 29), mask=IMG_ARROW_LEFT)
            img.paste(1, (x_right, 29), mask=IMG_ARROW_RIGHT)

            # 3. Hour and Minutes: vertical reel scroll on temp canvases
            def render_scrolling_profont(draw_target, x_target, text_seq):
                p = ease_out(t) * (len(text_seq) - 1)
                idx = int(p)
                frac = p - idx
                offset = int(round(frac * 18))
                temp_w = 38
                temp_h = 20
                temp_img = Image.new("1", (temp_w, temp_h), 0)
                temp_draw = ImageDraw.Draw(temp_img)
                temp_draw.fontmode = "1"
                y1 = 19 - offset
                y2 = 19 + 18 - offset
                str1 = text_seq[idx]
                str2 = text_seq[min(idx + 1, len(text_seq) - 1)]
                # Draw bold (double-strike) with 2px left padding margin
                if offset > 0:
                    temp_draw.text((2, y2), str2, font=font_large, fill=1, anchor="ls")
                    temp_draw.text((3, y2), str2, font=font_large, fill=1, anchor="ls")
                if offset < 18:
                    temp_draw.text((2, y1), str1, font=font_large, fill=1, anchor="ls")
                    temp_draw.text((3, y1), str1, font=font_large, fill=1, anchor="ls")
                draw_target.paste(temp_img, (x_target - 2, 21), mask=temp_img)

            render_scrolling_profont(img, 19, hour_roll_seq)
            render_scrolling_profont(img, 78, min_roll_seq)

            # 4. Seconds box: slide up from bottom
            shift_icons = int(round((1.0 - ease_out(t)) * 20))
            draw.rounded_rectangle([56, 26 + shift_icons, 56 + 15 - 1, 26 + 10 - 1 + shift_icons], radius=2, fill=1)

            # 5. Daylight progression icons: slide up from bottom
            img.paste(1, (34, 45 + shift_icons), mask=IMG_DAY)
            img.paste(1, (50, 45 + shift_icons), mask=IMG_MIDDAY)
            img.paste(1, (66, 46 + shift_icons), mask=IMG_SUNSET)
            img.paste(1, (85, 46 + shift_icons), mask=IMG_NIGHT)

            # 6. Week name and Date/Year: scroll in-place (from bottom of header region)
            shift_y = int(round((1.0 - ease_out(t)) * 12))
            header_img = Image.new("1", (128, 20), 0)
            header_draw = ImageDraw.Draw(header_img)
            header_draw.fontmode = "1"
            header_draw.text((19, 18 + shift_y), week_str, font=font_haxr, fill=1, anchor="ls")
            header_draw.text((x_div + w, 18 + shift_y), date_str, font=font_haxr, fill=1, anchor="rs")
            img.paste(header_img, (0, 0), mask=header_img)

            # Create a temporary image for XOR rendering
            xor_img = Image.new("1", (128, 64), 0)
            xor_draw = ImageDraw.Draw(xor_img)
            xor_draw.fontmode = "1"

            # 7. Seconds: scroll inside temp canvas
            def render_scrolling_seconds(xor_img_target, text_seq):
                p = ease_out(t) * (len(text_seq) - 1)
                idx = int(p)
                frac = p - idx
                offset = int(round(frac * 10))
                temp_w = 15
                temp_h = 10
                temp_img = Image.new("1", (temp_w, temp_h), 0)
                temp_draw = ImageDraw.Draw(temp_img)
                temp_draw.fontmode = "1"
                y1 = 8 - offset
                y2 = 8 + 10 - offset
                str1 = text_seq[idx]
                str2 = text_seq[min(idx + 1, len(text_seq) - 1)]
                temp_draw.text((7, y1), str1, font=font_haxr, fill=1, anchor="ms")
                temp_draw.text((7, y2), str2, font=font_haxr, fill=1, anchor="ms")
                xor_img_target.paste(temp_img, (56, 26 + shift_icons))

            render_scrolling_seconds(xor_img, sec_roll_seq)

            # 8. Active slide border: RBox at (slide_x, 45 + shift_icons)
            positions = [33, 49, 65, 82]
            if 6 <= hour < 12:
                target_idx = 0
            elif 12 <= hour < 17:
                target_idx = 1
            elif 17 <= hour < 19:
                target_idx = 2
            else:
                target_idx = 3
            
            # Slide directly from the first icon (33) to the target icon
            slide_x = int(round(33 + ease_out(t) * (positions[target_idx] - 33)))
            
            xor_draw.rounded_rectangle([slide_x, 44 + shift_icons, slide_x + 13 - 1, 44 + 13 - 1 + shift_icons], radius=5, fill=1)

            # XOR the temporary image onto the main image
            from PIL import ImageChops
            img = ImageChops.difference(img, xor_img)
        else:
            # --- STATIC RENDERING (at rest / final frame) ---
            # 1. Clock div lines
            img.paste(1, (19, 20), mask=img_single_div)
            img.paste(1, (19, 41), mask=img_single_div)
            
            # 2. Left and right arrows at (51, 29) and (73, 29)
            img.paste(1, (51, 29), mask=IMG_ARROW_LEFT)
            img.paste(1, (73, 29), mask=IMG_ARROW_RIGHT)

            # 3. Bold hours and minutes
            draw.text((19, 40), hour_str, font=font_large, fill=1, anchor="ls")
            draw.text((20, 40), hour_str, font=font_large, fill=1, anchor="ls")
            draw.text((78, 40), min_str, font=font_large, fill=1, anchor="ls")
            draw.text((79, 40), min_str, font=font_large, fill=1, anchor="ls")

            # 4. Seconds box (56, 26)
            draw.rounded_rectangle([56, 26, 56 + 15 - 1, 26 + 10 - 1], radius=2, fill=1)

            # 5. Daylight progression icons
            img.paste(1, (34, 45), mask=IMG_DAY)
            img.paste(1, (50, 45), mask=IMG_MIDDAY)
            img.paste(1, (66, 46), mask=IMG_SUNSET)
            img.paste(1, (85, 46), mask=IMG_NIGHT)

            # 6. Week name and Date/Year
            draw.text((19, 18), week_str, font=font_haxr, fill=1, anchor="ls")
            draw.text((108, 18), date_str, font=font_haxr, fill=1, anchor="rs")

            # Create a temporary image for XOR rendering
            xor_img = Image.new("1", (128, 64), 0)
            xor_draw = ImageDraw.Draw(xor_img)
            xor_draw.fontmode = "1"

            # 7. Seconds
            xor_draw.text((64, 34), sec_str, font=font_haxr, fill=1, anchor="ms")

            # 8. Active slide border
            if 6 <= hour < 12:
                slide_x = 33
            elif 12 <= hour < 17:
                slide_x = 49
            elif 17 <= hour < 19:
                slide_x = 65
            else:
                slide_x = 82
            xor_draw.rounded_rectangle([slide_x, 44, slide_x + 13 - 1, 44 + 13 - 1], radius=5, fill=1)

            from PIL import ImageChops
            img = ImageChops.difference(img, xor_img)

    return img



# ── Auto-Port Scan Handshake ──────────────────────────────────────────────────
def auto_detect_captor_x_port():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    for port in ports:
        try:
            s = serial.Serial(port, BAUD_RATE, timeout=0.3)
            ping_packet = bytearray([0xAA, 0x55, 0xAA, 0x55, 0x02, 0x00, 0x04]) + b"PING"
            s.write(ping_packet)
            time.sleep(0.05)
            resp = s.readline().decode("utf-8").strip()
            if "[PONG]" in resp:
                s.close()
                return port
            s.close()
        except Exception:
            pass
    return None

# ── Audio Thread Fn ───────────────────────────────────────────────────────────
def audio_thread_fn(device_index, stop_event):
    global rolling_buffer, current_volume
    pyaudio_instance = pyaudio.PyAudio()
    audio_stream = None
    
    try:
        dev_info = pyaudio_instance.get_device_info_by_index(device_index)
        device_sr = int(dev_info['defaultSampleRate'])
        num_channels = dev_info['maxInputChannels']
        log.info("Opening audio stream on device %r (index=%r, sr=%r, channels=%r)", dev_info['name'], device_index, device_sr, num_channels)
    except Exception as e:
        transcription_queue.put([f"[ERROR: Querying device {device_index} failed: {e}]"])
        try:
            pyaudio_instance.terminate()
        except Exception:
            pass
        return

    def callback(in_data, frame_count, time_info, status_flags):
        global rolling_buffer, current_volume
        audio_data = np.frombuffer(in_data, dtype=np.float32)
        if num_channels > 1:
            mono = np.mean(audio_data.reshape(-1, num_channels), axis=1).astype(np.float32)
        else:
            mono = audio_data.copy()
            
        if len(mono) > 0:
            rms = np.sqrt(np.mean(mono**2))
            current_volume = min(1.0, float(rms) * 5.0)
        else:
            current_volume = 0.0

        resampled = resample_audio(mono, device_sr, 16000)
        
        with buffer_lock:
            rolling_buffer = np.concatenate([rolling_buffer, resampled])
            max_len = 16000 * CHUNK_SECONDS
            if len(rolling_buffer) > max_len:
                rolling_buffer = rolling_buffer[-max_len:]
                
        return (None, pyaudio.paContinue)

    try:
        audio_stream = pyaudio_instance.open(
            format=pyaudio.paFloat32,
            channels=num_channels,
            rate=device_sr,
            input=True,
            input_device_index=device_index,
            stream_callback=callback,
            frames_per_buffer=4096
        )
        audio_stream.start_stream()
        
        while not stop_event.is_set():
            time.sleep(0.05)
            
        try:
            audio_stream.stop_stream()
        except Exception:
            pass
        try:
            audio_stream.close()
        except Exception:
            pass
    except Exception as e:
        transcription_queue.put([f"[ERROR: {e}]"])
    finally:
        try:
            pyaudio_instance.terminate()
        except Exception:
            pass

def stt_thread_fn(model, language, vad_filter, task, model_size, stop_event, app_ref=None):
    global rolling_buffer
    time.sleep(1.0)
    
    while not stop_event.is_set():
        time.sleep(STEP_SECONDS)
        
        with buffer_lock:
            if len(rolling_buffer) < 16000:
                continue
            chunk = rolling_buffer.copy()
            
        try:
            segments, info = model.transcribe(
                chunk, 
                language=None if language is None or language == "auto" else language, 
                beam_size=1, 
                vad_filter=vad_filter,
                task=task
            )
            
            is_english = True
            if language is None and info and hasattr(info, "language") and info.language is not None:
                if not model_size.endswith(".en") and info.language != "en" and info.language_probability > 0.4:
                    is_english = False
            
            new_words = []
            if is_english:
                for seg in segments:
                    for word in seg.text.strip().split():
                        clean = word.strip(".,!?;:\"'()-[]")
                        if clean:
                            new_words.append(clean)
            
            transcription_queue.put(new_words)
                
        except Exception as e:
            print(f"STT Thread Error: {e}")
            err_msg = str(e).lower()
            if "cuda" in err_msg or "out of memory" in err_msg or "cu" in err_msg or "alloc" in err_msg:
                if app_ref and getattr(app_ref, "model_on_gpu", False):
                    print("CUDA/GPU error detected during transcription. Triggering self-healing fallback to CPU...")
                    app_ref.trigger_cpu_fallback()
            time.sleep(1.0)

# ── Serial Send ────────────────────────────────────────────────────────────────
def send_line(line_text):
    global serial_port, app_engine
    cmd_clean = line_text.strip()
    if cmd_clean.startswith("[") and cmd_clean.endswith("]"):
        cmd_clean = cmd_clean[1:-1]
    cmd_bytes = cmd_clean.encode("utf-8")
    length = len(cmd_bytes)
    packet = bytearray([0xAA, 0x55, 0xAA, 0x55, 0x02, (length >> 8) & 0xFF, length & 0xFF]) + cmd_bytes
    with serial_lock:
        if serial_port and serial_port.is_open:
            try:
                serial_port.write(packet)
            except serial.SerialException:
                try:
                    serial_port.close()
                except Exception:
                    pass
                serial_port = None
                if app_engine:
                    app_engine.set_connection_status("disconnected")

def send_binary_frame(frame_bytes):
    global serial_port, app_engine
    length = len(frame_bytes)
    packet = bytearray([0xAA, 0x55, 0xAA, 0x55, 0x01, (length >> 8) & 0xFF, length & 0xFF]) + frame_bytes
    with serial_lock:
        if serial_port and serial_port.is_open:
            try:
                serial_port.write(packet)
            except serial.SerialException:
                try:
                    serial_port.close()
                except Exception:
                    pass
                serial_port = None
                if app_engine:
                    app_engine.set_connection_status("disconnected")

# ══════════════════════════════════════════════════════════════════════════════
#  APPLICATION STATE (UI-Free Engine Core)
# ══════════════════════════════════════════════════════════════════════════════
class AppEngine:
    def __init__(self):
        self.model    = None
        self.model_on_gpu = False
        self.loaded_model_size = None
        self.force_cpu_mode = False
        self.running  = False
        self.connection_status = "disconnected"
        self.history  = []
        self.dev_map  = {}   
        self._window   = None # Ref to Webview window
        
        # Thread handles for safe starting and stopping
        self.audio_thread = None
        self.stt_thread = None
        self.load_thread = None
        
        self.last_speech_time = time.time()
        self.oled_cleared = True
        self.wave_phase = 0.0
        self.tape_angle = 0.0
        self.tape_velocity = 0.0
        self.vis_peaks = [0.0] * 8
        self.last_reconnect_attempt = 0.0
        self.active_caption = ""
        self.word_timestamps = []
        
        self.gif_frames = []
        self.gif_delays = []
        self.gif_total_duration = 0.0
        self.gif_start_time = 0.0
        
        self.lang_map = {
            "Auto-Detect": None,
            "English": "en"
        }

        import shutil
        self.has_nvidia = shutil.which("nvidia-smi") is not None

        self.active_settings = {
            "model": "tiny.en",
            "language": "English",
            "font": "Vin Mono Pro (Thin)",
            "size": 24,
            "display_mode": "Line by Line",
            "alignment": "center",
            "case": "Sentence case",
            "brightness": 255,
            "invert": False,
            "alert": "",
            "welcome": "Captor Core Active",
            "com_port": "None",
            "audio_source": "",
            "custom_fonts": {},
            "offset_x": 0,
            "offset_y": 0,
            "visualizer": "Tape Graphics",
            "font_offsets": {},
            "music_mode": False,
            "mode": "CAPTIONS",
            "gif_path": os.path.abspath(os.path.join("UI", "OLED UI", "BOOT.gif")) if os.path.exists(os.path.join("UI", "OLED UI", "BOOT.gif")) else "",
            "gif_speed": "1.0x (Normal)",
            "gif_dither": "Threshold",
            "gif_scale": "Aspect Ratio",
            "gif_invert": False,
            "gif_threshold": 128,
            "stats_font": "Proggy Tiny",
            "stats_interval": "1.0s (Normal)",
            "stats_gpu": self.has_nvidia,
            "stats_layout": "CPU",
            "clock_format": "12-Hour",
            "clock_animation": "Snappy Easing",
            "clock_theme": "OBSEDIAN",
            "auto_start": False
        }
        self.last_valid_font = self.active_settings["font"]

        self.load_config()
        self._apply_startup_setting(self.active_settings.get("auto_start", False))
        self.active_settings["mode"] = self.active_settings.get("mode", "CAPTIONS").upper()

        if self.active_settings.get("gif_path"):
            self._load_gif(self.active_settings["gif_path"])

        for font_name, font_path in self.active_settings["custom_fonts"].items():
            FONT_MAP[font_name] = font_path

        self.system_stats = {
            "cpu_name": "Unknown CPU",
            "cpu_mhz": "0",
            "cpu_util": "0%",
            "cpu_temp": "--°C",
            "gpu_name": "Unknown GPU",
            "gpu_temp": "0°C",
            "gpu_core": "0",
            "gpu_mem": "0",
            "gpu_util": "0%",
            "ram_util": "0%",
            "disk_util": "0%",
            "local_time": "00:00",
            "net_tx": 0.0,
            "net_rx": 0.0
        }
        self._last_net_io = None
        
        # Initialize CPU hardware sensors on main thread
        try:
            get_cpu_temp()
        except:
            pass

        self.stats_thread_running = False
        self._start_stats_thread()
        self._populate_devices()

        # Select default/preferred audio source if none saved or saved is invalid
        saved_audio = self.active_settings.get("audio_source")
        if saved_audio:
            if saved_audio in self.dev_map:
                pass
            else:
                matched_label = None
                for label in self.dev_map.keys():
                    c1 = "".join(c for c in saved_audio.lower() if c.isalnum())
                    c2 = "".join(c for c in label.lower() if c.isalnum())
                    if c1 in c2 or c2 in c1:
                        matched_label = label
                        break
                if matched_label:
                    self.active_settings["audio_source"] = matched_label
                else:
                    saved_audio = None

        if not saved_audio or self.active_settings["audio_source"] not in self.dev_map:
            preferred = None
            for label in self.dev_map.keys():
                if "ai-04" in label.lower() or "8-" in label.lower():
                    if "loopback" in label.lower():
                        preferred = label
                        break
                    elif not preferred or "loopback" not in preferred.lower():
                        preferred = label
            if preferred:
                self.active_settings["audio_source"] = preferred
            elif self.dev_map:
                self.active_settings["audio_source"] = list(self.dev_map.keys())[0]

        # Auto-connect to last COM port on startup
        port = self.active_settings.get("com_port", "None")
        if port and port != "None":
            self._connect_port(port)

        # Initialize serial queue and sender thread to decouple serial write from preview/render loop
        self.ack_event = threading.Event()
        self.serial_queue = queue.Queue(maxsize=1)
        self.serial_thread = threading.Thread(target=self._serial_sender_loop, daemon=True)
        self.serial_thread.start()

        # Initialize background serial receiver thread to listen for hardware button triggers
        self.serial_receiver_thread = threading.Thread(target=self._serial_receiver_loop, daemon=True)
        self.serial_receiver_thread.start()

        # Start background polling loop
        self.poll_thread_running = True
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def load_config(self):
        config_path = get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    for k, v in saved.items():
                        if k in self.active_settings:
                            self.active_settings[k] = v
                    if "animation" in self.active_settings:
                        self.active_settings["animation"] = "None"
                    self.last_valid_font = self.active_settings["font"]
            except Exception as e:
                print(f"Error loading config: {e}")

    def save_config(self):
        config_path = get_config_path()
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.active_settings, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def _apply_startup_setting(self, enabled):
        import sys
        import os
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key_name = "CaptorCore"
        
        # Resolve target executable path
        if getattr(sys, 'frozen', False):
            # Running as compiled .exe
            exe_path = sys.executable
        else:
            # Fallback for dev environment running raw Python
            script_path = os.path.abspath(sys.argv[0])
            exe_path = f'"{sys.executable}" "{script_path}"'
            
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enabled:
                winreg.SetValueEx(key, key_name, 0, winreg.REG_SZ, exe_path)
                print(f"[Startup] Enabled. Executable registered at: {exe_path}")
            else:
                try:
                    winreg.DeleteValue(key, key_name)
                    print("[Startup] Disabled. Registry entry removed.")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[Startup] Failed to configure startup registry: {e}")

    def _load_gif(self, path):
        if not path or not os.path.exists(path):
            default_path = os.path.abspath(os.path.join("UI", "OLED UI", "BOOT.gif"))
            if os.path.exists(default_path):
                path = default_path
            else:
                self.gif_frames = []
                self.gif_delays = []
                self.gif_total_duration = 0.0
                return
            
        gif = None
        try:
            gif = Image.open(path)
            scale_mode = self.active_settings.get("gif_scale", "Aspect Ratio")
            dither_mode = self.active_settings.get("gif_dither", "Threshold")
            invert_colors = self.active_settings.get("gif_invert", False)
            
            frames = []
            delays = []
            
            canvas = None
            for frame_idx in range(getattr(gif, "n_frames", 1)):
                gif.seek(frame_idx)
                delay = gif.info.get("duration", 100)
                if not delay or delay <= 0:
                    delay = 100
                delays.append(delay)
                
                frame_rgba = gif.convert("RGBA")
                
                if canvas is None:
                    canvas = Image.new("RGBA", gif.size, (0, 0, 0, 0))
                
                # Backup canvas for disposal == 3
                canvas_before = canvas.copy()
                
                # Get the update bounding box (left, top, right, bottom)
                left, top, right, bottom = 0, 0, gif.size[0], gif.size[1]
                if gif.tile:
                    left, top, right, bottom = gif.tile[0][1]
                
                disposal = gif.info.get("disposal", getattr(gif, "disposal_method", 0))
                
                # Composite the current frame onto the accumulator canvas
                canvas.paste(frame_rgba, (0, 0), frame_rgba)
                
                if scale_mode == "Stretch":
                    frame_resized = canvas.resize((128, 64), Image.Resampling.LANCZOS)
                else:
                    fit_canvas = Image.new("RGBA", (128, 64), (0, 0, 0, 255))
                    orig_w, orig_h = canvas.size
                    ratio_w = 128.0 / orig_w
                    ratio_h = 64.0 / orig_h
                    ratio = min(ratio_w, ratio_h)
                    
                    new_w = int(orig_w * ratio)
                    new_h = int(orig_h * ratio)
                    new_w = max(1, new_w)
                    new_h = max(1, new_h)
                    
                    resized_img = canvas.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    x = (128 - new_w) // 2
                    y = (64 - new_h) // 2
                    fit_canvas.paste(resized_img, (x, y), resized_img)
                    frame_resized = fit_canvas
                
                if dither_mode == "Floyd-Steinberg Dither":
                    gray = frame_resized.convert("L")
                    mono = gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
                else:
                    gray = frame_resized.convert("L")
                    threshold_val = self.active_settings.get("gif_threshold", 128)
                    mono = gray.point(lambda p: 255 if p >= threshold_val else 0).convert("1")
                
                if invert_colors:
                    mono = ImageOps.invert(mono)
                    
                frames.append(mono)
                
                # Apply disposal method to prepare canvas for the next frame
                if disposal == 2:
                    # Clear only the updated region of the current frame to transparent
                    draw = ImageDraw.Draw(canvas)
                    draw.rectangle([left, top, right - 1, bottom - 1], fill=(0, 0, 0, 0))
                elif disposal == 3:
                    # Restore to state before this frame
                    canvas = canvas_before
                
            # Update animation state variables atomically to prevent out-of-bounds in serial thread
            self.gif_frames = frames
            self.gif_delays = delays
            self.gif_total_duration = sum(delays) / 1000.0
            self.gif_start_time = time.time()  # Reset start time to sync animation to frame 0
            print(f"Loaded GIF '{path}': {len(frames)} frames")
        except Exception as e:
            print(f"Error loading GIF '{path}': {e}")
        finally:
            if gif is not None:
                gif.close()

    def _serial_sender_loop(self):
        global serial_port
        while True:
            try:
                # Wait for a frame to send
                raw_bytes = self.serial_queue.get()
                
                # Send frame
                self.ack_event.clear()
                send_binary_frame(raw_bytes)
                
                # Wait for ACK event instead of reading directly from serial
                self.ack_event.wait(timeout=0.1)
            except Exception:
                time.sleep(0.01)

    def _serial_receiver_loop(self):
        global serial_port
        while True:
            try:
                if serial_port and serial_port.is_open:
                    if serial_port.in_waiting > 0:
                        with serial_lock:
                            if serial_port and serial_port.is_open:
                                line = serial_port.readline().decode("utf-8", errors="ignore").strip()
                                if line == "CYCLE":
                                    self.cycle_operation_mode()
                                elif line == "DOUBLE":
                                    self.toggle_music_mode_and_cc()
                                elif line == "SUB":
                                    self.cycle_sub_layout()
                                elif "[ACK]" in line:
                                    self.ack_event.set()
                time.sleep(0.01)
            except Exception:
                time.sleep(0.1)

    def cycle_operation_mode(self):
        modes = ["CAPTIONS", "GIF PLAYER", "PC STATS", "CLK"]
        current_mode = self.active_settings.get("mode", "CAPTIONS").upper()
        next_idx = (modes.index(current_mode) + 1) % len(modes)
        next_mode = modes[next_idx]
        
        print(f"[HW Button] Cycling operation mode to: {next_mode}")
        
        was_running = self.running
        if was_running:
            self._stop()
            time.sleep(0.6)
            
        self.active_settings["mode"] = next_mode
        self.save_config()
        
        if next_mode == "GIF PLAYER":
            self._load_gif(self.active_settings.get("gif_path", ""))
            
        self._start()
        
        if self._window:
            try:
                self._window.evaluate_js(f"if (window.cycleModeTo) window.cycleModeTo('{next_mode}')")
            except Exception as e:
                print(f"Error notifying frontend of mode cycle: {e}")

    def toggle_music_mode_and_cc(self):
        current_music_mode = self.active_settings.get("music_mode", False)
        next_music_mode = not current_music_mode
        print(f"[HW Button] Switching to CAPTIONS mode and setting Music Mode to {next_music_mode}")
        
        was_running = self.running
        if was_running:
            self._stop()
            time.sleep(0.6)
            
        self.active_settings["mode"] = "CAPTIONS"
        self.active_settings["music_mode"] = next_music_mode
        self.save_config()
        
        self._start()
        
        if self._window:
            try:
                self._window.evaluate_js(f"if (window.toggleMusicModeAndCC) window.toggleMusicModeAndCC({str(next_music_mode).lower()})")
            except Exception as e:
                print(f"Error notifying frontend of double press toggle: {e}")

    def cycle_sub_layout(self):
        active_mode = self.active_settings.get("mode", "CAPTIONS").upper()
        if active_mode == "CAPTIONS":
            self.toggle_music_mode_and_cc()
        elif active_mode == "PC STATS":
            layouts = ["CPU", "GPU", "MEM & NET"]
            current_layout = self.active_settings.get("stats_layout", "CPU")
            try:
                current_idx = layouts.index(current_layout)
            except ValueError:
                current_idx = 0
            next_idx = (current_idx + 1) % len(layouts)
            next_layout = layouts[next_idx]
            
            print(f"[HW Button] Cycling stats layout to: {next_layout}")
            self.active_settings["stats_layout"] = next_layout
            self.save_config()
            self._transition_start_time = time.time()
            
            if hasattr(self, "_window") and self._window:
                try:
                    self._window.evaluate_js(f"if (window.updateStatsLayout) window.updateStatsLayout('{next_layout}')")
                except Exception as e:
                    print(f"Error updating frontend stats layout: {e}")
        elif active_mode == "GIF PLAYER":
            current_gif = self.active_settings.get("gif_path", "")
            if not current_gif or not os.path.exists(current_gif):
                default_path = os.path.abspath(os.path.join("UI", "OLED UI", "BOOT.gif"))
                if os.path.exists(default_path):
                    current_gif = default_path
                else:
                    current_gif = ""
            
            if current_gif:
                directory = os.path.dirname(current_gif)
                if os.path.exists(directory):
                    files = [os.path.abspath(os.path.join(directory, f)) for f in os.listdir(directory) if f.lower().endswith(".gif")]
                    files.sort()
                    
                    if files:
                        try:
                            current_idx = files.index(os.path.abspath(current_gif))
                        except ValueError:
                            current_idx = -1
                        next_idx = (current_idx + 1) % len(files)
                        next_gif = files[next_idx]
                        
                        print(f"[HW Button] Cycling GIF to: {next_gif}")
                        
                        was_running = self.running
                        if was_running:
                            self._stop()
                            time.sleep(0.6)
                            
                        self.active_settings["gif_path"] = next_gif
                        self.save_config()
                        self._load_gif(next_gif)
                        self._start()
                        
                        if hasattr(self, "_window") and self._window:
                            try:
                                gif_normalized = next_gif.replace('\\', '/')
                                self._window.evaluate_js(f"if (window.updateGifPath) window.updateGifPath('{gif_normalized}')")
                            except Exception as e:
                                print(f"Error updating frontend GIF path: {e}")

    def _start_stats_thread(self):
        self.stats_thread_running = True
        t = threading.Thread(target=self._stats_loop, daemon=True)
        t.start()

    def _stats_loop(self):
        import subprocess
        cpu_name = "Unknown CPU"
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
            for words_to_remove in [" 6-Core Processor", " 8-Core Processor", " 12-Core Processor", " 16-Core Processor", " Processor", " 4-Core Processor"]:
                cpu_name = cpu_name.replace(words_to_remove, "")
            cpu_name = cpu_name.replace("AMD ", "").replace("Intel ", "")
            if len(cpu_name) > 16:
                cpu_name = cpu_name[:16]
        except Exception:
            pass
        self.system_stats["cpu_name"] = cpu_name

        gpu_name = "Unknown GPU"
        if self.has_nvidia:
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                gpu_name = out.decode("utf-8").strip()
                gpu_name = gpu_name.replace("NVIDIA ", "").replace("GeForce ", "")
                if len(gpu_name) > 16:
                    gpu_name = gpu_name[:16]
            except Exception:
                pass
        self.system_stats["gpu_name"] = gpu_name

        while self.stats_thread_running:
            active_mode = self.active_settings.get("mode", "CAPTIONS").upper()
            
            # Heavy hardware telemetry querying
            try:
                cpu_util_val = int(psutil.cpu_percent())
                self.system_stats["cpu_util"] = f"{cpu_util_val}%"
                
                cpu_mhz_val = 0
                freq = psutil.cpu_freq()
                if freq:
                    cpu_mhz_val = int(freq.current)
                self.system_stats["cpu_mhz"] = str(cpu_mhz_val)
                
                cpu_temp_val = get_cpu_temp()
                if cpu_temp_val:
                    self.system_stats["cpu_temp"] = cpu_temp_val
                else:
                    self.system_stats["cpu_temp"] = "--°C"
                
                mem = psutil.virtual_memory()
                self.system_stats["ram_util"] = f"{int(mem.percent)}%"
                
                disk = psutil.disk_usage('/')
                self.system_stats["disk_util"] = f"{int(disk.percent)}%"
                self.system_stats["local_time"] = time.strftime("%H:%M")

                # Network speed calculation
                try:
                    net_io = psutil.net_io_counters()
                    current_time = time.time()
                    if hasattr(self, "_last_net_io") and self._last_net_io:
                        last_net_io, last_time = self._last_net_io
                        dt = current_time - last_time
                        if dt > 0:
                            tx_speed = (net_io.bytes_sent - last_net_io.bytes_sent) / dt
                            rx_speed = (net_io.bytes_recv - last_net_io.bytes_recv) / dt
                            self.system_stats["net_tx"] = tx_speed
                            self.system_stats["net_rx"] = rx_speed
                    self._last_net_io = (net_io, current_time)
                except Exception:
                    pass

                active_layout = self.active_settings.get("stats_layout", "CPU")
                show_gpu = (self.active_settings.get("stats_gpu", True) or active_layout == "GPU") and self.has_nvidia
                if show_gpu:
                    try:
                        out = subprocess.check_output(
                            ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,clocks.gr,memory.used,memory.total", "--format=csv,noheader,nounits"],
                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                        )
                        parts = out.decode("utf-8").strip().split(",")
                        if len(parts) >= 5:
                            self.system_stats["gpu_util"] = f"{parts[0].strip()}%"
                            self.system_stats["gpu_temp"] = f"{parts[1].strip()}°C"
                            self.system_stats["gpu_core"] = parts[2].strip()
                            try:
                                used_mb = float(parts[3].strip())
                                self.system_stats["gpu_mem"] = f"{used_mb / 1024.0:.1f}GB"
                            except Exception:
                                self.system_stats["gpu_mem"] = f"{parts[3].strip()}MB"
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error in stats thread: {e}")

            interval_str = self.active_settings.get("stats_interval", "1.0s (Normal)")
            try:
                sleep_time = float(interval_str.split()[0].replace("s", ""))
            except Exception:
                sleep_time = 1.0
            
            for _ in range(int(sleep_time * 10)):
                if not self.stats_thread_running:
                    break
                time.sleep(0.1)

    def _populate_devices(self):
        self.dev_map = {}
        
        try:
            p = pyaudio.PyAudio()
        except Exception as e:
            print(f"Error initializing PyAudio: {e}")
            saved_audio = self.active_settings.get("audio_source")
            if saved_audio:
                self.dev_map[saved_audio] = -1
            return

        try:
            try:
                wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                wasapi_idx = wasapi_info['index']
            except IOError:
                wasapi_idx = None
            
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                if wasapi_idx is not None and dev['hostApi'] != wasapi_idx:
                    continue
                if dev['maxInputChannels'] < 1:
                    continue
                label = dev['name']
                self.dev_map[label] = i
                
            # If saved audio is not in the list, preserve it
            saved_audio = self.active_settings.get("audio_source")
            if saved_audio and saved_audio not in self.dev_map:
                matched_label = None
                for label in self.dev_map.keys():
                    c1 = "".join(c for c in saved_audio.lower() if c.isalnum())
                    c2 = "".join(c for c in label.lower() if c.isalnum())
                    if c1 in c2 or c2 in c1:
                        matched_label = label
                        break
                if matched_label:
                    self.active_settings["audio_source"] = matched_label
                else:
                    self.dev_map[saved_audio] = -1
        finally:
            try:
                p.terminate()
            except Exception:
                pass

    def _handle_brightness(self, val):
        send_line(f"[BRIGHT:{int(val)}]")

    def _handle_inversion(self):
        val = 1 if self.active_settings["invert"] else 0
        send_line(f"[INVERT:{val}]")

    def set_connection_status(self, status):
        """Sets the connection status and pushes it to the React frontend."""
        self.connection_status = status
        if hasattr(self, "_window") and self._window:
            try:
                self._window.evaluate_js(
                    f"if (window.updateConnectionStatus) window.updateConnectionStatus('{status}')"
                )
            except Exception as e:
                print(f"Error broadcasting connection status: {e}")

    def _connect_port(self, choice):
        if getattr(self, "_connecting_in_progress", False):
            return
        
        self.active_settings["com_port"] = choice
        self.save_config()

        if choice == "None":
            global serial_port
            with serial_lock:
                if serial_port and serial_port.is_open:
                    try:
                        serial_port.close()
                    except Exception:
                        pass
                    serial_port = None
            self.set_connection_status("disconnected")
            return

        def target():
            self._connecting_in_progress = True
            global serial_port
            self.set_connection_status("connecting")
            try:
                with serial_lock:
                    if serial_port and serial_port.is_open:
                        try:
                            serial_port.close()
                        except Exception:
                            pass
                        serial_port = None

                new_port = serial.Serial(choice, BAUD_RATE, timeout=0.5)
                new_port.dtr = True
                new_port.rts = True
                
                with serial_lock:
                    serial_port = new_port
                
                time.sleep(1.0)
                self._handle_brightness(self.active_settings["brightness"])
                time.sleep(0.1)
                self._handle_inversion()
                self.set_connection_status("connected")
            except Exception as e:
                print(f"Connection failed: {e}")
                with serial_lock:
                    if serial_port:
                        try:
                            serial_port.close()
                        except Exception:
                            pass
                        serial_port = None
                self.set_connection_status("disconnected")
            finally:
                self._connecting_in_progress = False

        threading.Thread(target=target, daemon=True).start()

    def _start(self):
        # Signal stop to any existing running threads
        if hasattr(self, "session_stop_event") and self.session_stop_event:
            self.session_stop_event.set()
        else:
            self.session_stop_event = None
        stop_event.set()

        # Wait for old threads to terminate cleanly (so they don't lock PortAudio device or cause collision)
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=1.0)
        if self.stt_thread and self.stt_thread.is_alive():
            self.stt_thread.join(timeout=1.0)
        if self.load_thread and self.load_thread.is_alive():
            self.load_thread.join(timeout=1.0)

        self.running = True
        self.session_stop_event = threading.Event()
        local_stop_event = self.session_stop_event
        stop_event.clear()

        active_mode = self.active_settings.get("mode", "CAPTIONS").upper()
        if active_mode in ["GIF PLAYER", "PC STATS", "CLK"]:
            if active_mode == "GIF PLAYER":
                self.gif_start_time = time.time()
                if not self.gif_frames:
                    self._load_gif(self.active_settings.get("gif_path", ""))
            self._unload_model()
            return
        
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break
        while not transcription_queue.empty():
            try:
                transcription_queue.get_nowait()
            except queue.Empty:
                break
                
        global rolling_buffer
        with buffer_lock:
            rolling_buffer = np.zeros(0, dtype=np.float32)

        self.last_speech_time = time.time()
        self.oled_cleared = False
        self.active_caption = ""
        self.word_timestamps = []

        def load():
            try:
                dev = self.dev_map.get(self.active_settings["audio_source"])
                if dev is None:
                    # Fallback to first available if saved source doesn't exist
                    dev = list(self.dev_map.values())[0] if self.dev_map else 0
                
                if self.active_settings.get("music_mode", False):
                    # Check if this thread has been replaced or stop signaled
                    if threading.current_thread() != self.load_thread or local_stop_event.is_set() or not self.running:
                        print("Startup aborted: load thread is obsolete or stopped.")
                        return
                    self.audio_thread = threading.Thread(target=audio_thread_fn, args=(dev, local_stop_event), daemon=True)
                    self.audio_thread.start()
                else:
                    target_model_size = self.active_settings["model"]
                    target_device = "CPU" if self.force_cpu_mode else "GPU"
                    current_device_mode = "GPU" if self.model_on_gpu else "CPU"
                    
                    if self.model is None or self.loaded_model_size != target_model_size or current_device_mode != target_device:
                        if target_device == "GPU":
                            try:
                                self.model = WhisperModel(target_model_size, device="cuda", compute_type="float16")
                                self.model_on_gpu = True
                                self.loaded_model_size = target_model_size
                            except Exception as gpu_err:
                                print(f"GPU load failed: {gpu_err}. Fallback to CPU...")
                                self.model = WhisperModel(target_model_size, device="cpu", compute_type="int8")
                                self.model_on_gpu = False
                                self.loaded_model_size = target_model_size
                        else:
                            self.model = WhisperModel(target_model_size, device="cpu", compute_type="int8")
                            self.model_on_gpu = False
                            self.loaded_model_size = target_model_size

                    # Check again after loading (since model loading is slow)
                    if threading.current_thread() != self.load_thread or local_stop_event.is_set() or not self.running:
                        print("Startup aborted: load thread is obsolete or stopped after model loading.")
                        return

                    lang_code = self.lang_map[self.active_settings["language"]]
                    vad_active = True
                    task_str = "transcribe"
                    
                    self.audio_thread = threading.Thread(target=audio_thread_fn, args=(dev, local_stop_event), daemon=True)
                    self.audio_thread.start()
                    self.stt_thread = threading.Thread(target=stt_thread_fn, args=(self.model, lang_code, vad_active, task_str, target_model_size, local_stop_event, self), daemon=True)
                    self.stt_thread.start()
            except Exception as e:
                print(f"STT loading thread error: {e}")
                self._stop()

        self.load_thread = threading.Thread(target=load, daemon=True)
        self.load_thread.start()

    def _stop(self):
        self.running = False
        if hasattr(self, "session_stop_event") and self.session_stop_event:
            self.session_stop_event.set()
        stop_event.set()
        self.active_caption = ""
        self.force_cpu_mode = False
        self._unload_model()

    def _unload_model(self):
        if self.model is not None:
            print("Unloading Whisper model to free memory...")
            self.model = None
            self.loaded_model_size = None
            self.model_on_gpu = False
            import gc
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def trigger_cpu_fallback(self):
        if not getattr(self, "force_cpu_mode", False):
            print("Triggering CPU fallback due to GPU/CUDA failure...")
            # Schedule execution safely outside the thread
            # We can use a simple helper or daemon thread/timer since we don't have tkinter .after in app engine
            import threading
            def reload_job():
                self._stop()
                self._unload_model()
                self.force_cpu_mode = True
                import time
                time.sleep(1.0)
                self._start()
            threading.Thread(target=reload_job, daemon=True).start()

    def _poll_loop(self):
        global current_volume
        
        def get_font_size_for_name(font_name):
            pixel_fonts = [
                "Minecraft (Blocky)", "Pixel Operator (Pixel)", "MS Gothic (Monospace Pixel)", 
                "SimSun (Monospace Pixel)", "Lucida Console (Retro)", "Vin Mono Pro (Regular)", 
                "Vin Mono Pro (Bold)", "Vin Mono Pro (Thin)", "Proggy Tiny", "Tiny5", 
                "Cozette", "Tom Thumb"
            ]
            if font_name in pixel_fonts or font_name.startswith("U8g2") or font_name.startswith("u8g2_font") or font_name in FONT_MAP or font_name == "Browse custom font...":
                if font_name == "Proggy Tiny":
                    return 12
                elif font_name == "Tiny5":
                    return 10
                elif font_name == "Cozette":
                    return 13
                elif font_name == "Tom Thumb":
                    return 15
                elif font_name == "U8g2 Nokia Large Bold":
                    return 10
                elif font_name in ["u8g2_font_Pixellari_tf", "Pixellari"]:
                    return 16
                elif font_name in ["u8g2_font_VCR_OSD_mr", "VCR OSD"]:
                    return 20
                elif font_name in ["u8g2_font_blipfest_07_tr", "blipfest 07"]:
                    return 20
                elif font_name in ["u8g2_font_bpixeldouble_tr", "bipixel double"]:
                    return 20
                elif font_name in ["u8g2_font_bpixel_tr", "bpixel"]:
                    return 20
                elif font_name in ["u8g2_font_bytesize_te", "bytesize"]:
                    return 20
                elif font_name in ["u8g2_font_cube_mel_tr", "cubemel"]:
                    return 20
                elif font_name in ["u8g2_font_doomalpha04_te", "doomalpha04"]:
                    return 16
                elif font_name in ["u8g2_font_freedoomr10_tu", "freedoomr10"]:
                    return 20
                elif font_name.startswith("U8g2") or font_name.startswith("u8g2_font"):
                    return 16
                return 16
            elif font_name == "Courier New (Typewriter)":
                return 20
            else:
                return 24

        while self.poll_thread_running:
            loop_start = time.time()
            has_new = False
            try:
                while True:
                    new_chunk_words = transcription_queue.get_nowait()
                    if new_chunk_words:
                            old_history = list(self.history)
                            self.history = align_transcripts(self.history, new_chunk_words)
                            if self.history != old_history:
                                has_new = True
                                self.last_speech_time = time.time()
                                self.oled_cleared = False
                                
                                num_added = len(self.history) - len(old_history)
                                if num_added > 0:
                                    now = time.time()
                                    for _ in range(num_added):
                                        self.word_timestamps.append(now)
                                
                                if self.history:
                                    last_word = self.history[-1]
                                    alert_word = self.active_settings["alert"].strip().lower()
                                    if alert_word and last_word.lower().strip(".,!?;:\"'()[]-") == alert_word:
                                        send_line("[INVERT:1]")
                                        time.sleep(0.4)
                                        send_line(f"[INVERT:{1 if self.active_settings['invert'] else 0}]")
            except queue.Empty:
                pass

            if has_new:
                if len(self.history) > 400:
                    self.history = self.history[-400:]
                self.active_caption = "join"
                self.active_caption = " ".join(self.history[-15:])

            # Calculate WPM
            now = time.time()
            self.word_timestamps = [t for t in self.word_timestamps if now - t <= 60]

            # Silence clear timeout
            if self.running and not self.active_settings.get("music_mode", False) and not self.oled_cleared and (now - self.last_speech_time > 3.0):
                self.active_caption = ""
                self.history = []
                self.oled_cleared = True

            # Automatic reconnection check
            if serial_port is None and self.active_settings.get("com_port", "None") != "None":
                if now - self.last_reconnect_attempt > 2.0:
                    self.last_reconnect_attempt = now
                    com_choice = self.active_settings.get("com_port", "None")
                    available_ports = [p.device for p in serial.tools.list_ports.comports()]
                    if com_choice in available_ports:
                        try:
                            self._connect_port(com_choice)
                        except Exception:
                            pass

            self.wave_phase = (self.wave_phase + 0.15) % (2 * math.pi)
            target_speed = (1.5 + current_volume * 18.0) if current_volume > 0.01 else 0.0
            self.tape_velocity += (target_speed - self.tape_velocity) * 0.1
            self.tape_angle = (self.tape_angle + self.tape_velocity) % 360.0

            # Get rendering settings from active settings
            active_font = self.active_settings["font"]
            active_mode = self.active_settings["display_mode"]
            active_align = self.active_settings["alignment"]
            active_case = self.active_settings["case"]
            active_welcome = self.active_settings["welcome"]
            active_offset_x = self.active_settings.get("offset_x", 0)
            active_offset_y = self.active_settings.get("offset_y", 0)
            active_invert = self.active_settings["invert"]
            active_bright = self.active_settings["brightness"]

            # --- RENDER IMAGE BUFFER ---
            active_mode_type = self.active_settings.get("mode", "CAPTIONS").upper()
            active_layout = self.active_settings.get("stats_layout", "CPU")
            current_mode_layout = (active_mode_type, active_layout)
            if not hasattr(self, "_last_mode_layout"):
                self._last_mode_layout = current_mode_layout
                self._transition_start_time = 0.0
            elif self._last_mode_layout != current_mode_layout:
                self._last_mode_layout = current_mode_layout
                self._transition_start_time = time.time()

            if active_mode_type == "GIF PLAYER":
                if self.gif_frames:
                    if self.running:
                        active_speed_mult = parse_speed_multiplier(self.active_settings.get("gif_speed", "1.0x (Normal)"))
                        if self.gif_total_duration > 0:
                            elapsed_serial = ((time.time() - self.gif_start_time) * active_speed_mult) % self.gif_total_duration
                        else:
                            elapsed_serial = 0.0
                        elapsed_serial_ms = elapsed_serial * 1000.0
                        cum = 0.0
                        frame_idx_serial = 0
                        for i, d in enumerate(self.gif_delays):
                            cum += d
                            if cum > elapsed_serial_ms:
                                frame_idx_serial = i
                                break
                        img_serial_base = self.gif_frames[frame_idx_serial]
                    else:
                        img_serial_base = self.gif_frames[0]
                    img_serial = apply_offset_to_image(img_serial_base, active_offset_x, active_offset_y)
                else:
                    img_serial = wrap_text_to_image(
                        "No GIF Loaded",
                        active_font,
                        get_font_size_for_name(active_font),
                        active_align,
                        active_case,
                        has_shadow=True,
                        vu_volume=0.0,
                        offset_x=active_offset_x,
                        offset_y=active_offset_y
                    )
            elif active_mode_type == "PC STATS":
                active_layout = self.active_settings.get("stats_layout", "CPU")
                
                # Copy self.system_stats to a local dict for rendering
                render_stats = self.system_stats.copy()
                render_stats["cpu_min_mhz"] = self.active_settings.get("cpu_min_mhz", 3600)
                render_stats["cpu_max_mhz"] = self.active_settings.get("cpu_max_mhz", 4200)
                render_stats["gpu_min_watt"] = self.active_settings.get("gpu_min_watt", 30)
                render_stats["gpu_max_watt"] = self.active_settings.get("gpu_max_watt", 180)
                
                # Apply overshoot animation if within transition duration
                t_elapsed = time.time() - getattr(self, "_transition_start_time", 0.0)
                T_anim = 1.0
                if t_elapsed < T_anim:
                    # 1. CPU utilization
                    try:
                        cpu_util_real = int(self.system_stats.get("cpu_util", "0%").replace("%", ""))
                    except Exception:
                        cpu_util_real = 0
                    cpu_util_anim = get_stats_overshoot_value(t_elapsed, cpu_util_real, 100)
                    render_stats["cpu_util"] = f"{int(cpu_util_anim)}%"
                    
                    # 2. GPU utilization
                    try:
                        gpu_util_real = int(self.system_stats.get("gpu_util", "0%").replace("%", ""))
                    except Exception:
                        gpu_util_real = 0
                    gpu_util_anim = get_stats_overshoot_value(t_elapsed, gpu_util_real, 100)
                    render_stats["gpu_util"] = f"{int(gpu_util_anim)}%"
                    
                    # 3. RAM utilization
                    try:
                        ram_util_real = int(self.system_stats.get("ram_util", "0%").replace("%", ""))
                    except Exception:
                        ram_util_real = 0
                    ram_util_anim = get_stats_overshoot_value(t_elapsed, ram_util_real, 100)
                    render_stats["ram_util"] = f"{int(ram_util_anim)}%"
                    
                    # 4. DISK utilization
                    try:
                        disk_util_real = int(self.system_stats.get("disk_util", "0%").replace("%", ""))
                    except Exception:
                        disk_util_real = 0
                    disk_util_anim = get_stats_overshoot_value(t_elapsed, disk_util_real, 100)
                    render_stats["disk_util"] = f"{int(disk_util_anim)}%"
                    
                    # 5. CPU Temperature
                    cpu_temp_str = self.system_stats.get("cpu_temp", "--°C")
                    cpu_temp_num = cpu_temp_str.replace("°C", "").replace("C", "")
                    import re
                    temp_digits = "".join(re.findall(r"[-+]?\d+", cpu_temp_num))
                    try:
                        cpu_temp_real = int(temp_digits)
                    except Exception:
                        cpu_temp_real = 45
                    cpu_temp_anim = get_stats_overshoot_value(t_elapsed, cpu_temp_real, 99)
                    render_stats["cpu_temp"] = f"{int(cpu_temp_anim)}°C"
                    
                    # 6. GPU Temperature
                    gpu_temp_str = self.system_stats.get("gpu_temp", "--°C")
                    gpu_temp_num = gpu_temp_str.replace("°C", "").replace("C", "")
                    temp_digits = "".join(re.findall(r"[-+]?\d+", gpu_temp_num))
                    try:
                        gpu_temp_real = int(temp_digits)
                    except Exception:
                        gpu_temp_real = 45
                    gpu_temp_anim = get_stats_overshoot_value(t_elapsed, gpu_temp_real, 99)
                    render_stats["gpu_temp"] = f"{int(gpu_temp_anim)}°C"

                if active_layout == "CPU":
                    img_serial_base = render_stats_cpu(render_stats)
                elif active_layout == "GPU":
                    img_serial_base = render_stats_gpu(render_stats)
                elif active_layout == "MEM & NET":
                    img_serial_base = render_stats_mem_net(render_stats)
                else:
                    active_show_gpu = self.active_settings.get("stats_gpu", self.has_nvidia)
                    img_serial_base = render_pc_stats(render_stats, active_show_gpu, self.active_settings.get("stats_font", "Proggy Tiny"))
                img_serial = apply_offset_to_image(img_serial_base, active_offset_x, active_offset_y)
            elif active_mode_type == "CLK":
                active_elapsed = time.time() - getattr(self, "_transition_start_time", 0.0)
                img_serial_base = render_clock_mode(
                    clock_format=self.active_settings.get("clock_format", "12-Hour"),
                    clock_animation=self.active_settings.get("clock_animation", "Snappy Easing"),
                    clock_theme=self.active_settings.get("clock_theme", "OBSEDIAN"),
                    mode_elapsed=active_elapsed
                )
                img_serial = apply_offset_to_image(img_serial_base, active_offset_x, active_offset_y)
            else:
                if self.running:
                    if self.active_settings.get("music_mode", False) or self.active_caption.strip() == "":
                        vis_mode = self.active_settings.get("visualizer", "Tape Graphics")
                        if vis_mode == "Stereo Bars":
                            img_serial = render_stereo_bars(self.wave_phase, current_volume, self.vis_peaks)
                        else:
                            img_serial = render_tape_graphics(self.tape_angle, current_volume)
                    else:
                        if active_mode == "Word by Word":
                            txt_serial = self.history[-1] if self.history else ""
                        else:
                            txt_serial = self.active_caption
                            
                        if txt_serial.strip() == "":
                            vis_mode = self.active_settings.get("visualizer", "Tape Graphics")
                            if vis_mode == "Stereo Bars":
                                img_serial = render_stereo_bars(self.wave_phase, current_volume, self.vis_peaks)
                            else:
                                img_serial = render_tape_graphics(self.tape_angle, current_volume)
                        else:
                            img_serial = wrap_text_to_image(
                                txt_serial,
                                active_font,
                                get_font_size_for_name(active_font),
                                active_align,
                                active_case,
                                has_shadow=True,
                                vu_volume=current_volume,
                                offset_x=active_offset_x,
                                offset_y=active_offset_y
                            )
                else:
                    txt_serial = active_welcome
                    img_serial = wrap_text_to_image(
                        txt_serial,
                        active_font,
                        get_font_size_for_name(active_font),
                        active_align,
                        active_case,
                        has_shadow=True,
                        vu_volume=0.0,
                        offset_x=active_offset_x,
                        offset_y=active_offset_y
                    )

            # --- PUSH IMAGE FRAME TO WEBVIEW ---
            if self._window:
                try:
                    # Style preview image before pushing
                    img_preview = img_serial.convert("RGB")
                    if active_invert:
                        img_preview = ImageOps.invert(img_preview)
                    
                    # Apply brightness dimming
                    brightness_factor = active_bright / 255.0
                    brightness_factor = max(0.05, brightness_factor)
                    enhancer = ImageEnhance.Brightness(img_preview)
                    img_preview = enhancer.enhance(brightness_factor)
                    
                    # Convert to base64 PNG
                    buffered = io.BytesIO()
                    img_preview.save(buffered, format="PNG")
                    img_str = base64.b64encode(buffered.getvalue()).decode()
                    
                    # Evaluate drawing JS
                    self._window.evaluate_js(f"window.drawScreenFrame('{img_str}')")
                except Exception as e:
                    pass

            # --- QUEUE BYTES FOR BACKGROUND SERIAL SENDER THREAD ---
            raw_bytes = img_serial.tobytes()
            try:
                while True:
                    try:
                        self.serial_queue.put_nowait(raw_bytes)
                        break
                    except queue.Full:
                        try:
                            self.serial_queue.get_nowait()
                        except queue.Empty:
                            pass
            except Exception:
                pass

            # Delay to cap loop to 20fps (50ms)
            elapsed = time.time() - loop_start
            sleep_time = max(0.001, 0.050 - elapsed)
            time.sleep(sleep_time)

# ══════════════════════════════════════════════════════════════════════════════
#  JS-TO-PYTHON API BRIDGE
# ══════════════════════════════════════════════════════════════════════════════
class APIBridge:
    def __init__(self, app):
        self._app = app

    def js_log(self, level, message):
        log.info("JS [%s] %s", str(level).upper(), message)

    def get_serial_ports(self):
        log.info("API get_serial_ports called")
        res = ["None"] + [p.device for p in serial.tools.list_ports.comports()]
        log.info("API get_serial_ports returning %r", res)
        return res

    def get_connection_status(self):
        """Invoked by React on startup to sync state."""
        return getattr(self._app, "connection_status", "disconnected")

    def get_audio_sources(self):
        self._app._populate_devices()
        return list(self._app.dev_map.keys())

    def get_settings(self):
        s = self._app.active_settings
        return {
            "com_port": s.get("com_port", "None"),
            "model": s.get("model", "tiny.en"),
            "text_case": s.get("case", "Sentence case"),
            "oled_font": s.get("font", "Vin Mono Pro (Thin)"),
            "audio_source": s.get("audio_source", ""),
            "language": s.get("language", "English"),
            "alignment": s.get("alignment", "center"),
            "brightness": s.get("brightness", 255),
            "music_mode": s.get("music_mode", False),
            "invert_oled": s.get("invert", False),
            "display_mode": s.get("display_mode", "Line by Line"),
            "welcome_text": s.get("welcome", "ACTIVE"),
            "gif_path": s.get("gif_path", ""),
            "gif_speed": s.get("gif_speed", "1.0x (Normal)"),
            "gif_dithering": s.get("gif_dither", "Threshold"),
            "gif_sizing": s.get("gif_scale", "Aspect Ratio"),
            "invert_gif": s.get("gif_invert", False),
            "gif_threshold": s.get("gif_threshold", 128),
            "stats_interval": s.get("stats_interval", "1.0s (Normal)"),
            "stats_font": s.get("stats_font", "Proggy Tiny"),
            "monitor_gpu": s.get("stats_gpu", True),
            "stats_layout": s.get("stats_layout", "CPU"),
            "current_mode": s.get("mode", "CAPTIONS"),
            "cpu_min_mhz": s.get("cpu_min_mhz", 3600),
            "cpu_max_mhz": s.get("cpu_max_mhz", 4200),
            "gpu_min_watt": s.get("gpu_min_watt", 30),
            "gpu_max_watt": s.get("gpu_max_watt", 180),
            "visualizer": s.get("visualizer", "Tape Graphics"),
            "auto_start": s.get("auto_start", False)
        }

    def change_mode(self, mode_name):
        self._app.active_settings["mode"] = mode_name.upper()
        self._app.save_config()
        if mode_name.upper() == "GIF PLAYER":
            self._app._load_gif(self._app.active_settings["gif_path"])

    def apply_settings(self, d):
        old_com_port = self._app.active_settings.get("com_port", "None")
        model_changed = (
            ("model" in d and d["model"] != self._app.active_settings.get("model")) or
            ("language" in d and d["language"] != self._app.active_settings.get("language")) or
            ("music_mode" in d and d["music_mode"] != self._app.active_settings.get("music_mode")) or
            ("audio_source" in d and d["audio_source"] != self._app.active_settings.get("audio_source"))
        )
                         
        mode_changed = ("current_mode" in d and d["current_mode"] != self._app.active_settings.get("mode"))
        
        gif_changed = (
            ("gif_path" in d and d["gif_path"] != self._app.active_settings.get("gif_path")) or
            ("gif_dithering" in d and d["gif_dithering"] != self._app.active_settings.get("gif_dither")) or
            ("gif_sizing" in d and d["gif_sizing"] != self._app.active_settings.get("gif_scale")) or
            ("invert_gif" in d and d["invert_gif"] != self._app.active_settings.get("gif_invert")) or
            ("gif_threshold" in d and int(d["gif_threshold"]) != self._app.active_settings.get("gif_threshold"))
        )

        self._app.active_settings["com_port"] = d.get("com_port", self._app.active_settings.get("com_port", "None"))
        self._app.active_settings["model"] = d.get("model", self._app.active_settings.get("model", "tiny.en"))
        self._app.active_settings["case"] = d.get("text_case", self._app.active_settings.get("case", "Sentence case"))
        self._app.active_settings["font"] = d.get("oled_font", self._app.active_settings.get("font", "Vin Mono Pro (Thin)"))
        self._app.active_settings["audio_source"] = d.get("audio_source", self._app.active_settings.get("audio_source", ""))
        self._app.active_settings["language"] = d.get("language", self._app.active_settings.get("language", "English"))
        self._app.active_settings["alignment"] = d.get("alignment", self._app.active_settings.get("alignment", "center"))
        self._app.active_settings["brightness"] = int(d.get("brightness", self._app.active_settings.get("brightness", 255)))
        self._app.active_settings["music_mode"] = d.get("music_mode", self._app.active_settings.get("music_mode", False))
        self._app.active_settings["invert"] = d.get("invert_oled", self._app.active_settings.get("invert", False))
        self._app.active_settings["display_mode"] = d.get("display_mode", self._app.active_settings.get("display_mode", "Line by Line"))
        self._app.active_settings["welcome"] = d.get("welcome_text", self._app.active_settings.get("welcome", "ACTIVE"))
        self._app.active_settings["gif_path"] = d.get("gif_path", self._app.active_settings.get("gif_path", ""))
        self._app.active_settings["gif_speed"] = d.get("gif_speed", self._app.active_settings.get("gif_speed", "1.0x (Normal)"))
        self._app.active_settings["gif_dither"] = d.get("gif_dithering", self._app.active_settings.get("gif_dither", "Threshold"))
        self._app.active_settings["gif_scale"] = d.get("gif_sizing", self._app.active_settings.get("gif_scale", "Aspect Ratio"))
        self._app.active_settings["gif_invert"] = d.get("invert_gif", self._app.active_settings.get("gif_invert", False))
        self._app.active_settings["gif_threshold"] = int(d.get("gif_threshold", self._app.active_settings.get("gif_threshold", 128)))
        self._app.active_settings["stats_interval"] = d.get("stats_interval", self._app.active_settings.get("stats_interval", "1.0s (Normal)"))
        self._app.active_settings["stats_font"] = d.get("stats_font", self._app.active_settings.get("stats_font", "Proggy Tiny"))
        self._app.active_settings["stats_gpu"] = d.get("monitor_gpu", self._app.active_settings.get("stats_gpu", True))
        self._app.active_settings["stats_layout"] = d.get("stats_layout", self._app.active_settings.get("stats_layout", "CPU"))
        self._app.active_settings["mode"] = d.get("current_mode", self._app.active_settings.get("mode", "CAPTIONS"))
        self._app.active_settings["cpu_min_mhz"] = int(d.get("cpu_min_mhz", self._app.active_settings.get("cpu_min_mhz", 3600)))
        self._app.active_settings["cpu_max_mhz"] = int(d.get("cpu_max_mhz", self._app.active_settings.get("cpu_max_mhz", 4200)))
        self._app.active_settings["gpu_min_watt"] = int(d.get("gpu_min_watt", self._app.active_settings.get("gpu_min_watt", 30)))
        self._app.active_settings["gpu_max_watt"] = int(d.get("gpu_max_watt", self._app.active_settings.get("gpu_max_watt", 180)))
        self._app.active_settings["visualizer"] = d.get("visualizer", self._app.active_settings.get("visualizer", "Tape Graphics"))
        self._app.active_settings["clock_format"] = d.get("clock_format", self._app.active_settings.get("clock_format", "12-Hour"))
        self._app.active_settings["clock_animation"] = d.get("clock_animation", self._app.active_settings.get("clock_animation", "Snappy Easing"))
        self._app.active_settings["clock_theme"] = d.get("clock_theme", self._app.active_settings.get("clock_theme", "OBSEDIAN"))
        self._app.active_settings["auto_start"] = d.get("auto_start", self._app.active_settings.get("auto_start", False))
        self._app._apply_startup_setting(self._app.active_settings["auto_start"])


        # Handle font specific offsets
        font_name = self._app.active_settings["font"]
        font_offsets = self._app.active_settings.setdefault("font_offsets", {})
        if font_name in font_offsets:
            self._app.active_settings["offset_x"] = font_offsets[font_name].get("x", 0)
            self._app.active_settings["offset_y"] = font_offsets[font_name].get("y", 0)

        self._app.save_config()

        # Connect port if port selection changed
        if "com_port" in d and d.get("com_port") != old_com_port:
            self._app._connect_port(d.get("com_port"))

        if gif_changed or (mode_changed and self._app.active_settings["mode"] == "GIF PLAYER"):
            self._app._load_gif(self._app.active_settings["gif_path"])

        self._app._handle_brightness(self._app.active_settings["brightness"])
        self._app._handle_inversion()

        if self._app.running and (model_changed or mode_changed):
            self._app._stop()
            time.sleep(0.6)
            self._app._start()

        return "Applied"

    def update_brightness(self, val):
        val_int = int(val)
        self._app.active_settings["brightness"] = val_int
        self._app._handle_brightness(val_int)
        return "Updated"

    def start_captioning(self):
        self._app._start()
        return "Started"

    def stop_captioning(self):
        self._app._stop()
        return "Stopped"

    def browse_gif(self):
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        f_path = filedialog.askopenfilename(filetypes=[("GIF Files", "*.gif")])
        root.destroy()
        return f_path.replace("\\", "/") if f_path else ""

    def nudge_text(self, direction):
        font_name = self._app.active_settings["font"]
        font_offsets = self._app.active_settings.setdefault("font_offsets", {})
        offsets = font_offsets.setdefault(font_name, {"x": 0, "y": 0})

        if direction == "up":
            offsets["y"] -= 1
        elif direction == "down":
            offsets["y"] += 1
        elif direction == "left":
            offsets["x"] -= 1
        elif direction == "right":
            offsets["x"] += 1
        elif direction == "reset":
            offsets["x"] = 0
            offsets["y"] = 0

        self._app.active_settings["offset_x"] = offsets["x"]
        self._app.active_settings["offset_y"] = offsets["y"]
        self._app.save_config()
        return {"x": offsets["x"], "y": offsets["y"]}

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN LAUNCH LOOP
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import ctypes
    import sys
    import os

    # Ensure working directory is set to the script's directory
    script_path = os.path.abspath(sys.argv[0])
    script_dir = os.path.dirname(script_path)
    os.chdir(script_dir)

    # Auto-elevate to Administrator on Windows if required
    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False

    if not is_admin() and "--no-elevate" not in sys.argv:
        # Relaunch the script with admin privileges
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]] + ["--no-elevate"])
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script_path}" {params}', script_dir, 1)
            sys.exit(0)
        except Exception:
            # Continue running as normal user if elevation failed or was denied
            pass

    kernel32 = ctypes.windll.kernel32
    kernel32.SetLastError(0)
    _mutex_holder = kernel32.CreateMutexW(None, True, "Global\\CaptorCore_SingleInstance_Mutex")
    last_err = kernel32.GetLastError()
    
    ERROR_ALREADY_EXISTS = 183
    ERROR_ACCESS_DENIED = 5
    
    is_collision = False
    if not _mutex_holder:
        if last_err == ERROR_ACCESS_DENIED:
            is_collision = True
    else:
        if last_err == ERROR_ALREADY_EXISTS:
            is_collision = True
            
    if is_collision:
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning("Captor Core", "Another instance of Captor Core is already running.")
            root.destroy()
        except Exception:
            pass
        sys.exit(0)

    app_engine = AppEngine()
    bridge = APIBridge(app_engine)

    start_minimized = "--minimized" in sys.argv

    window = webview.create_window(
        title='Captor Core', 
        url='gui/index.html?native=true',
        js_api=bridge,
        width=1096,
        height=804,
        resizable=False,
        hidden=start_minimized
    )
    
    app_engine._window = window
    
    # ── system tray setup ────────────────────────────────────────────────────────
    tray_icon = None

    def setup_tray():
        global tray_icon
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captor_core_icon.ico")
            if hasattr(sys, "_MEIPASS"):
                icon_path = os.path.join(sys._MEIPASS, "captor_core_icon.ico")
            
            image = Image.open(icon_path)
        except Exception as e:
            log.error("Failed to load tray icon image: %s", e)
            image = Image.new('RGB', (64, 64), color='blue')
            
        def on_show(icon, item):
            window.show()

        def on_exit(icon, item):
            icon.stop()
            try:
                window.events.closing -= on_closing
            except Exception:
                pass
            window.destroy()

        from pystray import MenuItem as item
        menu = pystray.Menu(
            item('Show Control Panel', on_show, default=True),
            item('Exit', on_exit)
        )
        
        tray_icon = pystray.Icon("CaptorCore", image, "Captor Core", menu)
        threading.Thread(target=tray_icon.run, daemon=True).start()

    def on_closing():
        window.hide()
        try:
            if tray_icon:
                tray_icon.notify("Captor Core is running in the background.", "System Tray")
        except Exception:
            pass
        return False

    window.events.closing += on_closing
    setup_tray()

    
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
    webview.start(debug=False)
    
    # Cleanup background threads on window close
    app_engine._stop()
    
    # Save final config on exit
    try:
        app_engine.save_config()
    except Exception:
        pass

    # Wait for threads to exit to ensure clean PortAudio/WASAPI termination
    if app_engine.audio_thread and app_engine.audio_thread.is_alive():
        app_engine.audio_thread.join(timeout=1.0)
    if app_engine.stt_thread and app_engine.stt_thread.is_alive():
        app_engine.stt_thread.join(timeout=1.0)
    if app_engine.load_thread and app_engine.load_thread.is_alive():
        app_engine.load_thread.join(timeout=1.0)

    app_engine.stats_thread_running = False
    app_engine.poll_thread_running = False
    with serial_lock:
        if serial_port and serial_port.is_open:
            try:
                serial_port.close()
            except Exception:
                pass

    # Force immediate process termination to release all native resources cleanly
    os._exit(0)

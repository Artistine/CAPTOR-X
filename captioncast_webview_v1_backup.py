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
            user32.SendMessageW(0xffff, 0x001d, 0, 0)
        except Exception as e:
            print(f"Error registering fonts: {e}")

register_fonts()

# ── settings ──────────────────────────────────────────────────────────────────
CHUNK_SECONDS = 3
BAUD_RATE     = 115200
STEP_SECONDS  = 0.25

FONT_MAP = {
    "Vin Mono Pro (Regular)": "fonts/vin-mono-pro-font-family/VinMonoPro-Regular.ttf",
    "Vin Mono Pro (Bold)": "fonts/vin-mono-pro-font-family/VinMonoPro-Bold.ttf",
    "Vin Mono Pro (Thin)": "fonts/vin-mono-pro-font-family/VinMonoPro-Thin.ttf",
    "Proggy Tiny": "fonts/proggy_tiny/ProggyTiny.ttf",
    "Tiny5": "fonts/tiny5/Tiny5-Regular.ttf",
    "Cozette": "fonts/cozette/CozetteVector.ttf",
    "Tom Thumb": "fonts/tom_thumb/TomThumb.ttf",
    "U8g2 Nokia Small": "fonts/u8g2/NokiaSmallPlain.ttf",
    "U8g2 Nokia Small Bold": "fonts/u8g2/NokiaSmallBold.ttf",
    "U8g2 Nokia Large Bold": "fonts/u8g2/NokiaLargeBold.ttf",
    "U8g2 Haxrcorp 4089": "fonts/u8g2/haxrcorp4089.ttf",
    "U8g2 3x5": "fonts/u8g2/3x5.ttf",
    "U8g2 8bit Classic": "fonts/u8g2/8bitClassic.ttf",
    "U8g2 Commodore 64": "fonts/u8g2/Commodore64.ttf",
    "U8g2 Press Start 2P": "fonts/u8g2/PressStart2P.ttf",
    "U8g2 Pixellari": "fonts/u8g2/Pixellari.ttf",
    "U8g2 Terminal": "fonts/u8g2/Terminal.ttf",
    "Consolas (Monospace)": "consola.ttf",
    "Lucida Console (Retro)": "lucon.ttf",
    "Courier New (Typewriter)": "cour.ttf",
    "Tahoma (Clean)": "tahoma.ttf",
    "Verdana (Readable)": "verdana.ttf",
    "Arial (Standard)": "arial.ttf",
    "Segoe UI (Modern)": "segoeui.ttf",
    "MS Gothic (Monospace Pixel)": "msgothic.ttc",
    "SimSun (Monospace Pixel)": "simsun.ttc"
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
        
        # Resolve relative paths relative to sys._MEIPASS if packaged, else the current directory
        if not os.path.isabs(font_file):
            if hasattr(sys, "_MEIPASS"):
                font_file_resolved = os.path.join(sys._MEIPASS, font_file)
                if os.path.exists(font_file_resolved):
                    font_file = font_file_resolved
            else:
                if os.path.exists(font_file):
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
    bbox = font.getbbox("Ay")
    line_h = bbox[3] - bbox[1] if bbox else current_font_size
    
    total_h = len(lines) * line_h + (len(lines) - 1) * line_spacing
    
    while total_h > MAX_H and lines:
        lines.pop(0)
        total_h = len(lines) * line_h + (len(lines) - 1) * line_spacing
        
    align_lower = alignment.lower() if alignment else "center"
    y = (64 - total_h) // 2
    for line in lines:
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
        
        if has_shadow:
            draw.text((line_x + 1, line_y + 1), line, font=font, fill=1)
            draw.text((line_x - 1, line_y), line, font=font, fill=1)
            draw.text((line_x + 1, line_y), line, font=font, fill=1)
            draw.text((line_x, line_y - 1), line, font=font, fill=1)
            draw.text((line_x, line_y + 1), line, font=font, fill=1)
            
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

def render_silence_wave(phase, vu_volume=0.0):
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    points = []
    amplitude = 6.0 + vu_volume * 14.0
    for x in range(128):
        y = 32 + amplitude * math.sin(x * 0.15 + phase)
        points.append((x, int(y)))
    draw.line(points, fill=1, width=1)
    if int(phase * 2) % 2 == 0:
        draw.rectangle([122, 2, 125, 5], fill=1)
    return img

def render_stereo_bars(phase, vu_volume=0.0):
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
        for y in range(y0, y1, 4):
            draw.rectangle([x0, y, x1, min(y + 2, y1)], fill=1)
    if int(phase * 2) % 2 == 0:
        draw.rectangle([122, 2, 125, 5], fill=1)
    return img

def render_radial_ring(phase, vu_volume=0.0):
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    cx, cy = 64, 32
    base_r = 10.0 + 4.0 * math.sin(phase)
    vol_r = vu_volume * 18.0
    r = int(min(28, base_r + vol_r))
    num_spokes = 16
    for i in range(num_spokes):
        angle = i * (2 * math.pi / num_spokes) + phase * 0.2
        spoke_len = r + 4.0 * math.sin(phase * 2 + i)
        x_end = cx + spoke_len * math.cos(angle)
        y_end = cy + spoke_len * math.sin(angle)
        draw.line([(cx, cy), (int(x_end), int(y_end))], fill=1, width=1)
    inner_r = max(4, r // 2)
    draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], fill=0)
    if int(phase * 2) % 2 == 0:
        draw.rectangle([122, 2, 125, 5], fill=1)
    return img

# ── Auto-Port Scan Handshake ──────────────────────────────────────────────────
def auto_detect_captor_x_port():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    for port in ports:
        try:
            s = serial.Serial(port, BAUD_RATE, timeout=0.3)
            s.write(b"\n")
            time.sleep(0.05)
            s.write(b"[PING]\n")
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

# ── STT Thread Fn ─────────────────────────────────────────────────────────────
def stt_thread_fn(model, language, vad_filter, task, model_size, stop_event):
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
            transcription_queue.put([f"[STT ERR: {e}]"])

# ── Serial Send ────────────────────────────────────────────────────────────────
def send_line(line_text):
    global serial_port, app_engine
    with serial_lock:
        if serial_port and serial_port.is_open:
            try:
                serial_port.write((line_text.strip() + "\n").encode("utf-8"))
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
            "font": "Vin Mono Pro (Regular)",
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
            "visualizer": "Sine Wave",
            "font_offsets": {},
            "music_mode": False,
            "mode": "CAPTIONS",
            "gif_path": "",
            "gif_speed": "1.0x (Normal)",
            "gif_dither": "Threshold",
            "gif_scale": "Aspect Ratio",
            "gif_invert": False,
            "gif_threshold": 128,
            "stats_font": "Proggy Tiny",
            "stats_interval": "1.0s (Normal)",
            "stats_gpu": self.has_nvidia
        }
        self.last_valid_font = self.active_settings["font"]

        self.load_config()
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
            "local_time": "00:00"
        }
        
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

    def _load_gif(self, path):
        self.gif_frames = []
        self.gif_delays = []
        self.gif_total_duration = 0.0
        
        if not path or not os.path.exists(path):
            return
            
        gif = None
        try:
            gif = Image.open(path)
            scale_mode = self.active_settings.get("gif_scale", "Aspect Ratio")
            dither_mode = self.active_settings.get("gif_dither", "Threshold")
            invert_colors = self.active_settings.get("gif_invert", False)
            
            frames = []
            delays = []
            
            for frame_idx in range(getattr(gif, "n_frames", 1)):
                gif.seek(frame_idx)
                delay = gif.info.get("duration", 100)
                if not delay or delay <= 0:
                    delay = 100
                delays.append(delay)
                
                frame_rgba = gif.convert("RGBA")
                
                if scale_mode == "Stretch":
                    frame_resized = frame_rgba.resize((128, 64), Image.Resampling.LANCZOS)
                else:
                    canvas = Image.new("RGBA", (128, 64), (0, 0, 0, 255))
                    orig_w, orig_h = frame_rgba.size
                    ratio_w = 128.0 / orig_w
                    ratio_h = 64.0 / orig_h
                    ratio = min(ratio_w, ratio_h)
                    
                    new_w = int(orig_w * ratio)
                    new_h = int(orig_h * ratio)
                    new_w = max(1, new_w)
                    new_h = max(1, new_h)
                    
                    resized_img = frame_rgba.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    x = (128 - new_w) // 2
                    y = (64 - new_h) // 2
                    canvas.paste(resized_img, (x, y), resized_img)
                    frame_resized = canvas
                
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
                
            self.gif_frames = frames
            self.gif_delays = delays
            self.gif_total_duration = sum(delays) / 1000.0
            print(f"Loaded GIF '{path}': {len(frames)} frames")
        except Exception as e:
            print(f"Error loading GIF '{path}': {e}")
        finally:
            if gif is not None:
                gif.close()

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

                show_gpu = self.active_settings.get("stats_gpu", True) and self.has_nvidia
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
        global serial_port
        with serial_lock:
            if serial_port and serial_port.is_open:
                try:
                    serial_port.close()
                except Exception:
                    pass
                serial_port = None
            
            self.active_settings["com_port"] = choice
            self.save_config()

            if choice == "None":
                self.set_connection_status("disconnected")
                return
                
            self.set_connection_status("connecting")
            try:
                serial_port = serial.Serial(choice, BAUD_RATE, timeout=0.5)
                serial_port.write(b"\n")
                time.sleep(0.05)
                # Sync settings immediately
                time.sleep(0.15)
                self._handle_brightness(self.active_settings["brightness"])
                time.sleep(0.1)
                self._handle_inversion()
                self.set_connection_status("connected")
            except Exception as e:
                print(f"Connection failed: {e}")
                self.set_connection_status("disconnected")

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

        if self.active_settings.get("mode", "CAPTIONS").upper() == "GIF PLAYER":
            self.gif_start_time = time.time()
            if not self.gif_frames:
                self._load_gif(self.active_settings.get("gif_path", ""))
            return

        if self.active_settings.get("mode", "CAPTIONS").upper() == "PC STATS":
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
                    if self.model is None or self.loaded_model_size != target_model_size:
                        try:
                            self.model = WhisperModel(target_model_size, device="cuda", compute_type="float16")
                            self.model_on_gpu = True
                            self.loaded_model_size = target_model_size
                        except Exception as gpu_err:
                            print(f"GPU load failed: {gpu_err}. Fallback to CPU...")
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
                    self.stt_thread = threading.Thread(target=stt_thread_fn, args=(self.model, lang_code, vad_active, task_str, target_model_size, local_stop_event), daemon=True)
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

    def _poll_loop(self):
        global current_volume
        
        def get_font_size_for_name(font_name):
            pixel_fonts = [
                "Minecraft (Blocky)", "Pixel Operator (Pixel)", "MS Gothic (Monospace Pixel)", 
                "SimSun (Monospace Pixel)", "Lucida Console (Retro)", "Vin Mono Pro (Regular)", 
                "Vin Mono Pro (Bold)", "Vin Mono Pro (Thin)", "Proggy Tiny", "Tiny5", 
                "Cozette", "Tom Thumb"
            ]
            if font_name in pixel_fonts or font_name.startswith("U8g2") or font_name == "Browse custom font...":
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
                elif font_name.startswith("U8g2"):
                    return 8
                return 16
            elif font_name == "Courier New (Typewriter)":
                return 20
            else:
                return 24

        while self.poll_thread_running:
            has_new = False
            try:
                while True:
                    new_chunk_words = transcription_queue.get_nowait()
                    if new_chunk_words:
                        if len(new_chunk_words) == 1 and new_chunk_words[0].startswith("[STT ERR:"):
                            self.history.append(new_chunk_words[0])
                            has_new = True
                        else:
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

            self.wave_phase = (self.wave_phase + 0.15) % (2 * math.pi)

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
                active_show_gpu = self.active_settings.get("stats_gpu", self.has_nvidia)
                img_serial_base = render_pc_stats(self.system_stats, active_show_gpu, self.active_settings.get("stats_font", "Proggy Tiny"))
                img_serial = apply_offset_to_image(img_serial_base, active_offset_x, active_offset_y)
            else:
                if self.running:
                    if self.active_settings.get("music_mode", False) or self.active_caption.strip() == "":
                        vis_mode = self.active_settings.get("visualizer", "Sine Wave")
                        if vis_mode == "Stereo Bars":
                            img_serial = render_stereo_bars(self.wave_phase, current_volume)
                        elif vis_mode == "Radial Ring":
                            img_serial = render_radial_ring(self.wave_phase, current_volume)
                        else:
                            img_serial = render_silence_wave(self.wave_phase, current_volume)
                    else:
                        if active_mode == "Word by Word":
                            txt_serial = self.history[-1] if self.history else ""
                        else:
                            txt_serial = self.active_caption
                            
                        if txt_serial.strip() == "":
                            vis_mode = self.active_settings.get("visualizer", "Sine Wave")
                            if vis_mode == "Stereo Bars":
                                img_serial = render_stereo_bars(self.wave_phase, current_volume)
                            elif vis_mode == "Radial Ring":
                                img_serial = render_radial_ring(self.wave_phase, current_volume)
                            else:
                                img_serial = render_silence_wave(self.wave_phase, current_volume)
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

            # --- STREAM BYTES TO SERIAL COM PORT ---
            raw_bytes = img_serial.tobytes()
            hex_data = raw_bytes.hex()
            send_line(hex_data)

            # Delay to throttle loop to ~12fps
            time.sleep(0.08)

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
            "oled_font": s.get("font", "Vin Mono Pro (Regular)"),
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
            "current_mode": s.get("mode", "CAPTIONS")
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
        self._app.active_settings["font"] = d.get("oled_font", self._app.active_settings.get("font", "Vin Mono Pro (Regular)"))
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
        self._app.active_settings["mode"] = d.get("current_mode", self._app.active_settings.get("mode", "CAPTIONS"))

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

    # Auto-elevate to Administrator on Windows if required
    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False

    if not is_admin() and "--no-elevate" not in sys.argv:
        # Relaunch the script with admin privileges
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]] + ["--no-elevate"])
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
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

    window = webview.create_window(
        title='Captor Core', 
        url='gui/index.html?native=true',
        js_api=bridge,
        width=1096,
        height=804,
        resizable=False
    )
    
    app_engine._window = window
    
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

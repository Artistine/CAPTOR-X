import os
import sys
import json

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

import threading
import queue
import time
import math
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
import serial
import serial.tools.list_ports
import pyaudiowpatch as pyaudio
import numpy as np
import psutil
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance

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
BAUD_RATE     = 230400
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

# ── custom tooltip helper ─────────────────────────────────────────────────────
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify="left",
                         background="#1e1e1e", foreground="#ffffff",
                         relief="solid", borderwidth=1,
                         font=("Vin Mono Pro", "9", "normal"), padx=6, pady=3)
        label.pack()

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

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
    # If any word exceeds the MAX_W (116px) boundary, scale down the font size iteratively
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
            # Word exceeds MAX_W, push current line first
            if current_line:
                lines.append(" ".join(current_line))
                current_line = []
            # Split the long word into chunks that fit
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
    draw.fontmode = "1" # Force pixel-perfect aliased rendering

    # Font sizing mapping for stats layout to maintain perfect alignment
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
        # Fallback for legacy Vin Mono Pro or other custom fonts
        small_sz, large_sz = 9, 18
    else:
        small_sz = sizes["small"]
        large_sz = sizes["large"]

    # --- CPU Metrics ---
    cpu_name = stats.get("cpu_name", "Unknown CPU")
    cpu_temp = stats.get("cpu_temp", "--°C")
    cpu_util = stats.get("cpu_util", "0%")
    try:
        cpu_util_val = int(cpu_util.replace("%", ""))
    except Exception:
        cpu_util_val = 0
    # Fake CPU MHz based on cpu_util mapping from cpu_min_mhz to cpu_max_mhz
    cpu_min = int(stats.get("cpu_min_mhz", 3600))
    cpu_max = int(stats.get("cpu_max_mhz", 4200))
    cpu_mhz_val = cpu_min + int(cpu_util_val * (cpu_max - cpu_min) / 100)
    c_min = min(cpu_min, cpu_max)
    c_max = max(cpu_min, cpu_max)
    cpu_mhz = str(max(c_min, min(c_max, cpu_mhz_val)))

    # --- GPU / Fallback Section metrics ---
    gpu_name = stats.get("gpu_name", "Unknown GPU")
    gpu_temp = stats.get("gpu_temp", "0°C")
    gpu_core = stats.get("gpu_core", "0")
    gpu_mem = stats.get("gpu_mem", "0")
    gpu_util = stats.get("gpu_util", "0%")

    disk_util = stats.get("disk_util", "0%")
    ram_util = stats.get("ram_util", "0%")
    local_time = stats.get("local_time", "00:00")

    # --- CPU Row layout solver (auto-scale and prevent clashes) ---
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
        
        # Calculate dynamic positions with safety padding
        mhz_val_start = max(30, 2 + w_cpu + 2)
        mhz_lbl_start = mhz_val_start + w_mhz_val + 1
        left_block_end = mhz_lbl_start + w_mhz_lbl
        
        right_block_start = min(126 - w_temp, 126 - w_util)
        
        # Check clash
        if left_block_end + 4 <= right_block_start:
            break
            
        # For pixel fonts, instead of smooth shrinking, immediately drop to 1x native scale
        if current_large_sz > current_small_sz:
            current_large_sz = current_small_sz
        elif current_small_sz > 5:
            # Fallback legacy shrink if already at 1x
            current_small_sz -= 1
        else:
            break

    # --- GPU Row layout solver ---
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

    # --- Auto-truncate Name Strings to prevent horizontal overflow ---
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

    # --- Draw CPU Section ---
    draw.text((2, 0), cpu_name, font=f_bold, fill=1)
    
    draw.text((2, 10), "CPU", font=f_large, fill=1)
    draw.text((mhz_val_start, 10), cpu_mhz, font=f_large, fill=1)
    # Align baseline of MHz label
    y_offset = (current_large_sz - current_small_sz) if current_large_sz > current_small_sz else 0
    draw.text((mhz_lbl_start, 10 + y_offset), "MHz", font=f_thin, fill=1)
    
    w_temp = draw.textlength(cpu_temp, font=f_bold)
    draw.text((126 - w_temp, 10), cpu_temp, font=f_bold, fill=1)

    w_util = draw.textlength(cpu_util, font=f_bold)
    draw.text((126 - w_util, 19), cpu_util, font=f_bold, fill=1)

    # --- Draw GPU / Fallback Section ---
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
                if offset > 0:
                    temp_draw.text((8, y2), str2, font=font_haxr, fill=1, anchor="ms")
                if offset < 10:
                    temp_draw.text((8, y1), str1, font=font_haxr, fill=1, anchor="ms")
                xor_img_target.paste(temp_img, (56, 26 + shift_icons), mask=temp_img)

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

# ══════════════════════════════════════════════════════════════════════════════
#  AUDIO CAPTURE
# ══════════════════════════════════════════════════════════════════════════════
def audio_thread_fn(device_index, stop_event):
    global rolling_buffer, current_volume
    pyaudio_instance = pyaudio.PyAudio()
    audio_stream = None
    
    try:
        dev_info = pyaudio_instance.get_device_info_by_index(device_index)
        device_sr = int(dev_info['defaultSampleRate'])
        num_channels = dev_info['maxInputChannels']
        print(f"Opening audio stream on device: {dev_info['name']} (index={device_index}, sr={device_sr}, channels={num_channels})")
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

# ══════════════════════════════════════════════════════════════════════════════
#  STT THREAD (English Filtered)
# ══════════════════════════════════════════════════════════════════════════════
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
            
            # English Focus Language Filter:
            # If language auto-detect detects non-English speech with >40% confidence, ignore it.
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

# ══════════════════════════════════════════════════════════════════════════════
#  SERIAL SEND
# ══════════════════════════════════════════════════════════════════════════════
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
                    app_engine.connection_status = "disconnected"

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
                    app_engine.connection_status = "disconnected"

# ══════════════════════════════════════════════════════════════════════════════
#  GUI APPLICATION (Portrait Layout with Saved State)
# ══════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.configure(fg_color="#111111")
        self.title("Captor Core")
        self.geometry("1008x672")
        self.resizable(False, False)

        self.model    = None
        self.model_on_gpu = False
        self.loaded_model_size = None
        self.force_cpu_mode = False
        self.running  = False
        self.history  = []
        self.dev_map  = {}   
        
        # Thread handles for safe starting and stopping
        self.audio_thread = None
        self.stt_thread = None
        self.load_thread = None
        
        # Style state
        self.last_speech_time = time.time()
        self.oled_cleared = True
        self.wave_phase = 0.0
        self.tape_angle = 0.0
        self.tape_velocity = 0.0
        self.vis_peaks = [0.0] * 8
        self.last_reconnect_attempt = 0.0
        self.active_caption = ""
        self.word_timestamps = []
        
        # GIF Player state
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

        # Active Settings (Committed via Apply Settings button / Loaded from JSON)
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
            "clock_format": "12-Hour",
            "clock_animation": "Snappy Easing",
            "clock_theme": "OBSEDIAN",
            "auto_start": False
        }
        self.last_valid_font = self.active_settings["font"]

        # Load configuration from AppData JSON
        self.load_config()
        self._apply_startup_setting(self.active_settings.get("auto_start", False))
        if "mode" in self.active_settings:
            self.active_settings["mode"] = self.active_settings["mode"].upper()
        else:
            self.active_settings["mode"] = "CAPTIONS"

        # Load GIF if path is saved
        if self.active_settings.get("gif_path"):
            self._load_gif(self.active_settings["gif_path"])

        # Update FONT_MAP with custom loaded fonts
        for font_name, font_path in self.active_settings["custom_fonts"].items():
            FONT_MAP[font_name] = font_path

        # Initialize PC Stats
        import psutil
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

        self._build_ui()
        self._populate_devices()
        self._refresh_ports()
        self._check_pending_changes() # Initialize button state

        # Restore saved Audio Source if available (with fuzzy matching fallback)
        saved_audio = self.active_settings["audio_source"]
        if saved_audio:
            if saved_audio in self.dev_map:
                self.audio_var.set(saved_audio)
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
                    self.audio_var.set(matched_label)

        # Auto-connect to saved COM Port
        saved_com = self.active_settings["com_port"]
        if saved_com != "None":
            # Schedule auto-connect shortly after startup
            self.after(500, lambda: self._connect_to_port(saved_com))

        # Initialize serial queue and sender thread to decouple serial write from main UI thread
        self.ack_event = threading.Event()
        self.serial_queue = queue.Queue(maxsize=1)
        self.serial_thread = threading.Thread(target=self._serial_sender_loop, daemon=True)
        self.serial_thread.start()

        # Initialize transition tracking variables
        self.clk_mode_start_time = 0.0
        self.last_mode_type = None
        self.clk_staged_start_time = 0.0
        self.last_staged_mode = None

        self._poll()

    def load_config(self):
        config_path = get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    for k, v in saved.items():
                        if k in self.active_settings:
                            self.active_settings[k] = v
                    # Clean/overwrite old animation values to guarantee static updates
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
            
            # Extract scaling and dither settings
            scale_mode = self.active_settings.get("gif_scale", "Aspect Ratio")
            dither_mode = self.active_settings.get("gif_dither", "Threshold")
            invert_colors = self.active_settings.get("gif_invert", False)
            
            frames = []
            delays = []
            
            canvas = None
            for frame_idx in range(getattr(gif, "n_frames", 1)):
                gif.seek(frame_idx)
                
                # Get frame delay (duration in milliseconds)
                delay = gif.info.get("duration", 100)
                if not delay or delay <= 0:
                    delay = 100
                delays.append(delay)
                
                # Convert frame to RGBA first to handle transparency properly
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
                
                # Sizing/scaling
                if scale_mode == "Stretch":
                    frame_resized = canvas.resize((128, 64), Image.Resampling.LANCZOS)
                else:
                    # Aspect Ratio: create a black canvas
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
                
                # Conversion to 1-bit monochrome
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
            self.gif_total_duration = sum(delays) / 1000.0  # seconds
            self.gif_start_time = time.time()  # Reset start time to sync animation to frame 0
            print(f"Loaded GIF '{path}': {len(frames)} frames, total duration: {self.gif_total_duration}s")
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
                                    self.after(0, self.cycle_operation_mode)
                                elif line == "DOUBLE":
                                    self.after(0, self.toggle_music_mode_and_cc)
                                elif line == "SUB":
                                    self.after(0, self.cycle_sub_layout)
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
        
        try:
            self.set_staged_mode(next_mode)
        except Exception as e:
            print(f"Error updating Tkinter mode tab: {e}")

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
        
        try:
            self.set_staged_mode("CAPTIONS")
            self.music_var.set(next_music_mode)
        except Exception as e:
            print(f"Error updating Tkinter mode tab: {e}")

    def cycle_sub_layout(self):
        active_mode = self.active_settings.get("mode", "CAPTIONS").upper()
        if active_mode == "CAPTIONS":
            self.toggle_music_mode_and_cc()
        elif active_mode == "PC STATS":
            current_stats_gpu = self.active_settings.get("stats_gpu", self.has_nvidia)
            next_stats_gpu = not current_stats_gpu
            print(f"[HW Button] Cycling stats layout: GPU display to {next_stats_gpu}")
            self.active_settings["stats_gpu"] = next_stats_gpu
            self.save_config()
            try:
                self.stats_gpu_var.set(next_stats_gpu)
            except Exception as e:
                print(f"Error updating Tkinter stats GPU checkbox: {e}")
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
                        
                        try:
                            self.gif_path_var.set(next_gif)
                        except Exception as e:
                            print(f"Error updating Tkinter GIF path: {e}")

    def _build_ui(self):
        # UI Font Definitions
        font_reg = ctk.CTkFont(family="Vin Mono Pro", size=9)
        font_bold = ctk.CTkFont(family="Vin Mono Pro Bold", size=9)
        font_thin = ctk.CTkFont(family="Vin Mono Pro Thin", size=9)

        # ── Two Views Setup ────────────────────────────────────────────────────────
        self.view_devices = ctk.CTkFrame(self, width=1008, height=672, fg_color="transparent")

        self.view_dashboard = ctk.CTkFrame(self, width=1008, height=672, fg_color="transparent")
        self.view_dashboard.place(x=0, y=0)

        # ── View 1: Devices Page Layout ──
        self.dev_card = ctk.CTkFrame(self.view_devices, width=420, height=392, fg_color="#181818", corner_radius=17)
        self.dev_card.place(x=294, y=140)

        # ── View 2: Dashboard Layout ───────────────────────────────────────────────
        self.top_card = ctk.CTkFrame(self.view_dashboard, width=952, height=392, fg_color="#181818", corner_radius=17)
        self.top_card.place(x=28, y=28)

        
        self.bottom_card = ctk.CTkFrame(self.view_dashboard, width=952, height=196, fg_color="#181818", corner_radius=17)
        self.bottom_card.place(x=28, y=448)

        # ── Load Device Mockup Image ───────────────────────────────────────────────
        mockup_path = "UI/CAPTOR X MOCKUP.png"
        if hasattr(sys, "_MEIPASS"):
            mockup_path = os.path.join(sys._MEIPASS, mockup_path)

        if os.path.exists(mockup_path):
            img_raw = Image.open(mockup_path).convert("RGBA")
            self.mockup_pil = img_raw.resize((790, 442), Image.Resampling.LANCZOS)
            
            # Create a clean initial V2 mockup (with a black screen turned off)
            base_v2 = Image.new("RGBA", (790, 442), (24, 24, 24, 255))
            draw_v2 = ImageDraw.Draw(base_v2)
            draw_v2.rectangle([228, 135, 561, 299], fill=(0, 0, 0, 255))
            base_v2.paste(self.mockup_pil, (0, 0), self.mockup_pil)
            self.ctk_img_v2 = ctk.CTkImage(light_image=base_v2, dark_image=base_v2, size=(790, 442))

            # Create clean welcome V1 mockup (with a black screen turned off)
            img_v1_res = img_raw.resize((336, 188), Image.Resampling.LANCZOS)
            base_v1 = Image.new("RGBA", (336, 188), (24, 24, 24, 255))
            draw_v1 = ImageDraw.Draw(base_v1)
            draw_v1.rectangle([97, 57, 239, 128], fill=(0, 0, 0, 255))
            base_v1.paste(img_v1_res, (0, 0), img_v1_res)
            self.ctk_img_v1 = ctk.CTkImage(light_image=base_v1, dark_image=base_v1, size=(336, 188))
        else:
            self.mockup_pil = None
            self.ctk_img_v1 = None
            self.ctk_img_v2 = None

        self.dev_image_label_v1 = ctk.CTkLabel(self.dev_card, image=self.ctk_img_v1, text="")
        self.dev_image_label_v1.place(x=42, y=70)

        self.esp_lbl_v1 = ctk.CTkLabel(self.dev_card, text="● CAPTOR X [OFFLINE]", text_color="#FF0038",
                                       font=ctk.CTkFont(family="Vin Mono Pro Bold", size=8))
        self.esp_lbl_v1.place(relx=0.5, y=280, anchor="center")

        # Bind View 1 elements to transition
        self.dev_card.bind("<Button-1>", lambda e: self.slide_transition())
        self.dev_image_label_v1.bind("<Button-1>", lambda e: self.slide_transition())
        self.esp_lbl_v1.bind("<Button-1>", lambda e: self.slide_transition())

        self.dev_image_label_v2 = ctk.CTkLabel(self.top_card, image=self.ctk_img_v2, text="")
        self.dev_image_label_v2.place(x=81, y=-17)

        self.esp_lbl = ctk.CTkLabel(self.top_card, text="● CAPTOR X [OFFLINE]", text_color="#FF0038",
                                    font=ctk.CTkFont(family="Vin Mono Pro Bold", size=8))
        self.esp_lbl.place(relx=0.5, y=42, anchor="center")

        # Centered OLED Preview Box on top of the mockup screen
        self.preview_label = ctk.CTkLabel(self.top_card, text="", bg_color="#000000", width=156, height=78)
        # Hidden when using the composited transparent bezel cutout overlay
        # self.preview_label.place(x=284, y=118)

        # Mode Selector
        self.app_mode_var = ctk.StringVar()
        self.set_staged_mode(self.active_settings.get("mode", "CAPTIONS"))
        # Outer rounded container (scaled up)
        self.tab_container = ctk.CTkFrame(self.top_card, width=240, height=38, corner_radius=19, fg_color="#0c0c0c")
        self.tab_container.place(x=21, y=333)

        self.tab_selector = ctk.CTkSegmentedButton(self.tab_container, values=["CC", "GIF", "STATS", "CLK"],
                                                    variable=self.app_mode_var,
                                                    command=self._handle_tab_change,
                                                    font=ctk.CTkFont(family="Vin Mono Pro Bold", size=12),
                                                    width=234, height=32,
                                                    border_width=0,
                                                    corner_radius=16,
                                                    fg_color="#0c0c0c",
                                                    selected_color="#242524",
                                                    selected_hover_color="#2c2d2c",
                                                    unselected_color="#0c0c0c",
                                                    unselected_hover_color="#121212",
                                                    text_color="#e4e4e4",
                                                    background_corner_colors=("#0c0c0c", "#0c0c0c", "#0c0c0c", "#0c0c0c"))
        self.tab_selector.place(x=3, y=3)
        buttons = list(self.tab_selector._buttons_dict.values())
        if len(buttons) >= 4:
            for btn in buttons:
                btn.configure(width=58, corner_radius=16, anchor="center", background_corner_colors=("#0c0c0c", "#0c0c0c", "#0c0c0c", "#0c0c0c"))
                btn._text_label.grid(column=0, columnspan=5, sticky="nsew")
                try:
                    btn._text_label.configure(anchor="center")
                except Exception:
                    pass

        # Control Pill
        self.control_pill = ctk.CTkFrame(self.top_card, width=77, height=38, fg_color="#252525", corner_radius=19)
        self.control_pill.place(x=854, y=333)

        self.apply_btn = ctk.CTkButton(self.control_pill, text="✓", font=ctk.CTkFont(family="Vin Mono Pro Bold", size=8),
                                       height=26, width=26, fg_color="#444444", hover_color="#555555", text_color="#FFFFFF",
                                       border_width=0, corner_radius=13,
                                       command=self._apply_settings)
        self.apply_btn.place(x=8, y=6)
        ToolTip(self.apply_btn, "Commit and save all configuration edits to the preview and display")

        self.btn = ctk.CTkButton(self.control_pill, text="▶", font=ctk.CTkFont(family="Vin Mono Pro Bold", size=8),
                                 width=26, height=26, corner_radius=13,
                                 fg_color="#252525", hover_color="#333333", text_color="#FFFFFF",
                                 border_width=0, command=self._toggle)
        self.btn.place(x=43, y=6)
        ToolTip(self.btn, "Start/Stop speech captioning capture")

# COM selection, auto connect and rescan elements (placed top-right of Top Card)
        com_bar = ctk.CTkFrame(self.top_card, width=320, height=30, fg_color="transparent")
        com_bar.place(x=952 - 28, y=28, anchor="ne")

        self.port_var = ctk.StringVar(value="None")
        self.port_menu = ctk.CTkComboBox(com_bar, variable=self.port_var, values=["None"], width=140, height=29,
                                           command=self._connect_port,
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=15,
                                           fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                           font=font_reg, dropdown_font=font_reg)
        self.port_menu.pack(side="left", padx=5)
        ToolTip(self.port_menu, "Select serial USB port of your Captor X device")

        self.auto_btn = ctk.CTkButton(com_bar, text="AUTO CONNECT ↗", width=98, height=29, command=self._auto_connect_async,
                                      fg_color="#252525", hover_color="#333333", text_color="#FFFFFF",
                                      border_width=0, corner_radius=15,
                                      font=ctk.CTkFont(family="Vin Mono Pro Bold", size=11))
        self.auto_btn.pack(side="left", padx=5)
        ToolTip(self.auto_btn, "Scan COM ports and handshake with Captor X device automatically")

        self.refresh_btn = ctk.CTkButton(com_bar, text="RE-SCAN ↗", width=70, height=29, command=self._refresh_ports,
                                          fg_color="#252525", hover_color="#333333", text_color="#FFFFFF",
                                          border_width=0, corner_radius=15,
                                          font=ctk.CTkFont(family="Vin Mono Pro Bold", size=11))
        self.refresh_btn.pack(side="left", padx=5)
        ToolTip(self.refresh_btn, "Re-scan serial COM ports")


        # ── Settings Sub-frames (Bottom Card Settings container) ───────────────────
        self.tab_container = ctk.CTkFrame(self.bottom_card, width=700, height=154, fg_color="transparent")
        self.tab_container.place(x=28, y=21)

        self.captions_tab_frame = ctk.CTkFrame(self.tab_container, fg_color="transparent")
        self.captions_tab_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, minsize=154)

        self.gif_tab_frame = ctk.CTkFrame(self.tab_container, fg_color="transparent")
        self.gif_tab_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, minsize=154)

        self.stats_tab_frame = ctk.CTkFrame(self.tab_container, fg_color="transparent")
        self.stats_tab_frame.grid_columnconfigure((0, 1, 2, 3), weight=1, minsize=154)

        self.clk_tab_frame = ctk.CTkFrame(self.tab_container, fg_color="transparent")
        self.clk_tab_frame.grid_columnconfigure((0, 1, 2), weight=1, minsize=154)

        current_mode = self.get_staged_mode()
        if current_mode == "CAPTIONS":
            self.captions_tab_frame.pack(fill="both", expand=True)
        elif current_mode == "GIF PLAYER":
            self.gif_tab_frame.pack(fill="both", expand=True)
        elif current_mode == "PC STATS":
            self.stats_tab_frame.pack(fill="both", expand=True)
        elif current_mode == "CLK":
            self.clk_tab_frame.pack(fill="both", expand=True)

        # ── CAPTIONS Mode Form Grid ────────────────────────────────────────────────
        ctk.CTkLabel(self.captions_tab_frame, text="MODEL", text_color="#E4E4E4", font=font_bold).grid(row=0, column=0, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.captions_tab_frame, text="TEXT CASE", text_color="#E4E4E4", font=font_bold).grid(row=0, column=1, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.captions_tab_frame, text="OLED FONT", text_color="#E4E4E4", font=font_bold).grid(row=0, column=2, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.captions_tab_frame, text="AUDIO SOURCE", text_color="#E4E4E4", font=font_bold).grid(row=0, column=3, sticky="w")

        self.model_var = ctk.StringVar(value=self.active_settings["model"])
        self.model_menu = ctk.CTkComboBox(self.captions_tab_frame, variable=self.model_var, values=["tiny.en", "tiny", "base", "small"],
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                           fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                           font=font_reg, dropdown_font=font_reg)
        self.model_menu.grid(row=1, column=0, sticky="ew", padx=(0, 28), pady=(0, 4))
        ToolTip(self.model_menu, "Choose Whisper size (tiny.en is fastest, small is most accurate)")

        self.case_var = ctk.StringVar(value=self.active_settings["case"])
        self.case_menu = ctk.CTkComboBox(self.captions_tab_frame, variable=self.case_var, values=["Sentence case", "UPPERCASE", "lowercase"],
                                          state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                          fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                          font=font_reg, dropdown_font=font_reg)
        self.case_menu.grid(row=1, column=1, sticky="ew", padx=(0, 28), pady=(0, 4))
        ToolTip(self.case_menu, "Re-format text casing style")

        self.font_var = ctk.StringVar(value=self.active_settings["font"])
        self.font_menu = ctk.CTkComboBox(self.captions_tab_frame, variable=self.font_var, values=list(FONT_MAP.keys()) + ["Browse custom font..."],
                                           command=self._handle_font_selection,
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                           fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                           font=font_reg, dropdown_font=font_reg)
        self.font_menu.grid(row=1, column=2, sticky="ew", padx=(0, 28), pady=(0, 4))
        ToolTip(self.font_menu, "Select pixel-perfect screen font or load a custom .ttf/.otf file")

        self.audio_var  = ctk.StringVar(value="Scanning...")
        self.audio_menu = ctk.CTkComboBox(self.captions_tab_frame, variable=self.audio_var, values=["Scanning..."],
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                           fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                           font=font_reg, dropdown_font=font_reg)
        self.audio_menu.grid(row=1, column=3, sticky="ew", pady=(0, 4))
        ToolTip(self.audio_menu, "Select playback loopback interface to record PC sound")

        ctk.CTkLabel(self.captions_tab_frame, text="LANGUAGE", text_color="#E4E4E4", font=font_bold).grid(row=2, column=0, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.captions_tab_frame, text="TEXT ALIGNMENT", text_color="#E4E4E4", font=font_bold).grid(row=2, column=1, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.captions_tab_frame, text="OLED BRIGHTNESS", text_color="#E4E4E4", font=font_bold).grid(row=2, column=2, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.captions_tab_frame, text="ALERT HOTWORD", text_color="#E4E4E4", font=font_bold).grid(row=2, column=3, sticky="w")

        self.lang_var = ctk.StringVar(value=self.active_settings["language"])
        self.lang_menu = ctk.CTkComboBox(self.captions_tab_frame, variable=self.lang_var, values=["English", "Auto-Detect"],
                                          state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                          fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                          font=font_reg, dropdown_font=font_reg)
        self.lang_menu.grid(row=3, column=0, sticky="ew", padx=(0, 28), pady=(0, 4))
        ToolTip(self.lang_menu, "Select English or enable Auto-Detect to filter out non-English speech")

        self.align_var = ctk.StringVar(value=self.active_settings["alignment"])
        self.align_menu = ctk.CTkComboBox(self.captions_tab_frame, variable=self.align_var, values=["center", "left", "right"],
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                           fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                           font=font_reg, dropdown_font=font_reg)
        self.align_menu.grid(row=3, column=1, sticky="ew", padx=(0, 28), pady=(0, 4))
        ToolTip(self.align_menu, "Align text lines on screen")

        self.bright_slider = ctk.CTkSlider(self.captions_tab_frame, from_=0, to=255, height=11, fg_color="#252525", progress_color="#11FF00",
                                            button_color="#FFFFFF", button_hover_color="#FFFFFF",
                                            command=self._handle_slider_change)
        self.bright_slider.set(self.active_settings["brightness"])
        self.bright_slider.grid(row=3, column=2, sticky="ew", padx=(0, 28), pady=(0, 4))
        ToolTip(self.bright_slider, "Dim or brighten the physical OLED screen")

        self.alert_var = ctk.StringVar(value=self.active_settings["alert"])
        self.alert_entry = ctk.CTkEntry(self.captions_tab_frame, textvariable=self.alert_var, fg_color="#252525", border_color="#444444", border_width=1, corner_radius=14, text_color="#FFFFFF", font=font_reg)
        self.alert_entry.grid(row=3, column=3, sticky="ew", pady=(0, 4))
        ToolTip(self.alert_entry, "Flash screen/invert colors momentarily if this exact word is spoken")

        ctk.CTkLabel(self.captions_tab_frame, text="MUSIC MODE", text_color="#E4E4E4", font=font_bold).grid(row=4, column=0, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.captions_tab_frame, text="INVERT OLED", text_color="#E4E4E4", font=font_bold).grid(row=4, column=1, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.captions_tab_frame, text="DISPLAY MODE", text_color="#E4E4E4", font=font_bold).grid(row=4, column=2, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.captions_tab_frame, text="WELCOME TEXT", text_color="#E4E4E4", font=font_bold).grid(row=4, column=3, sticky="w")

        self.music_var = ctk.BooleanVar(value=self.active_settings.get("music_mode", False))
        self.music_cb = ctk.CTkSwitch(self.captions_tab_frame, text="", variable=self.music_var, font=font_reg,
                                      progress_color="#11FF00", fg_color="#252525", button_color="#FFFFFF", button_hover_color="#FFFFFF")
        self.music_cb.grid(row=5, column=0, sticky="w", padx=(0, 28))
        ToolTip(self.music_cb, "Disable silence clear timeout and Whisper VAD to transcribe lyrics/singing better")

        self.invert_var = ctk.BooleanVar(value=self.active_settings["invert"])
        self.invert_cb = ctk.CTkSwitch(self.captions_tab_frame, text="", variable=self.invert_var, font=font_reg,
                                       progress_color="#11FF00", fg_color="#252525", button_color="#FFFFFF", button_hover_color="#FFFFFF")
        self.invert_cb.grid(row=5, column=1, sticky="w", padx=(0, 28))
        ToolTip(self.invert_cb, "Swap display background to white with black text")

        self.mode_var = ctk.StringVar(value=self.active_settings["display_mode"])
        self.mode_menu = ctk.CTkComboBox(self.captions_tab_frame, variable=self.mode_var, values=["Line by Line", "Word by Word"],
                                          state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                          fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                          font=font_reg, dropdown_font=font_reg)
        self.mode_menu.grid(row=5, column=2, sticky="ew", padx=(0, 28))
        ToolTip(self.mode_menu, "Set captions layout to show line by line or word by word")

        self.welcome_var = ctk.StringVar(value=self.active_settings["welcome"])
        self.welcome_entry = ctk.CTkEntry(self.captions_tab_frame, textvariable=self.welcome_var, fg_color="#252525", border_color="#444444", border_width=1, corner_radius=14, text_color="#FFFFFF", font=font_reg)
        self.welcome_entry.grid(row=5, column=3, sticky="ew")
        ToolTip(self.welcome_entry, "Text rendered on OLED when captioning is idle")

        ctk.CTkLabel(self.captions_tab_frame, text="AUDIO RESPONSE", text_color="#E4E4E4", font=font_bold).grid(row=6, column=0, sticky="w", padx=(0, 28))
        self.vis_var = ctk.StringVar(value=self.active_settings.get("visualizer", "Tape Graphics"))
        self.vis_menu = ctk.CTkComboBox(self.captions_tab_frame, variable=self.vis_var, values=["Tape Graphics", "Stereo Bars"],
                                         state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                         fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                         font=font_reg, dropdown_font=font_reg)
        self.vis_menu.grid(row=7, column=0, sticky="ew", padx=(0, 28))
        ToolTip(self.vis_menu, "Choose idle screen audio visualizer mode")

        ctk.CTkLabel(self.captions_tab_frame, text="AUTO START", text_color="#E4E4E4", font=font_bold).grid(row=6, column=1, sticky="w", padx=(0, 28))
        self.auto_start_var = ctk.BooleanVar(value=self.active_settings.get("auto_start", False))
        self.auto_start_cb = ctk.CTkSwitch(self.captions_tab_frame, text="", variable=self.auto_start_var, font=font_reg,
                                            progress_color="#11FF00", fg_color="#252525")
        self.auto_start_cb.grid(row=7, column=1, sticky="w", padx=(0, 28))
        ToolTip(self.auto_start_cb, "Automatically start Captor Core when Windows boots")

        # ── GIF Mode Form Grid ─────────────────────────────────────────────────────
        ctk.CTkLabel(self.gif_tab_frame, text="LOAD GIF", text_color="#E4E4E4", font=font_bold).grid(row=0, column=0, columnspan=2, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.gif_tab_frame, text="THRESHOLD", text_color="#E4E4E4", font=font_bold).grid(row=0, column=2, sticky="w", padx=(0, 28))

        gif_path_frame = ctk.CTkFrame(self.gif_tab_frame, fg_color="transparent")
        gif_path_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 28), pady=(0, 4))

        self.gif_path_var = ctk.StringVar(value=self.active_settings.get("gif_path", ""))
        self.gif_entry = ctk.CTkEntry(gif_path_frame, textvariable=self.gif_path_var, state="readonly",
                                       fg_color="#252525", border_color="#444444", border_width=1, corner_radius=14, text_color="#FFFFFF", font=font_reg)
        self.gif_entry.pack(side="left", fill="x", expand=True)

        self.gif_browse_btn = ctk.CTkButton(gif_path_frame, text="BROWSE ↗", width=70, height=29, command=self._browse_gif,
                                            fg_color="#252525", hover_color="#333333", text_color="#FFFFFF",
                                            border_width=0, corner_radius=15,
                                            font=ctk.CTkFont(family="Vin Mono Pro Bold", size=11))
        self.gif_browse_btn.pack(side="right", padx=(7, 0))
        ToolTip(self.gif_browse_btn, "Select an animated .gif file to play")

        gif_thresh_frame = ctk.CTkFrame(self.gif_tab_frame, fg_color="transparent")
        gif_thresh_frame.grid(row=1, column=2, sticky="ew", padx=(0, 28), pady=(0, 4))

        self.gif_threshold_var = tk.IntVar(value=self.active_settings.get("gif_threshold", 128))
        
        def _on_threshold_slider(val):
            self.gif_threshold_var.set(int(float(val)))
            self.gif_thresh_val_lbl.configure(text=str(self.gif_threshold_var.get()))
            self._check_pending_changes()

        self.gif_thresh_slider = ctk.CTkSlider(gif_thresh_frame, from_=0, to=255, height=11, fg_color="#252525", progress_color="#11FF00",
                                               button_color="#FFFFFF", button_hover_color="#FFFFFF",
                                               command=_on_threshold_slider)
        self.gif_thresh_slider.set(self.active_settings.get("gif_threshold", 128))
        self.gif_thresh_slider.pack(side="left", fill="x", expand=True)
        ToolTip(self.gif_thresh_slider, "Set pixel threshold level for binary B&W conversion")

        self.gif_thresh_val_lbl = ctk.CTkLabel(gif_thresh_frame, text=str(self.gif_threshold_var.get()), text_color="#FFFFFF", font=font_reg, width=21)
        self.gif_thresh_val_lbl.pack(side="right", padx=(7, 0))

        ctk.CTkLabel(self.gif_tab_frame, text="SPEED", text_color="#E4E4E4", font=font_bold).grid(row=2, column=0, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.gif_tab_frame, text="DITHERING", text_color="#E4E4E4", font=font_bold).grid(row=2, column=1, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.gif_tab_frame, text="SIZING MODE", text_color="#E4E4E4", font=font_bold).grid(row=2, column=2, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.gif_tab_frame, text="INVERT COLORS", text_color="#E4E4E4", font=font_bold).grid(row=2, column=3, sticky="w")

        self.gif_speed_var = ctk.StringVar(value=self.active_settings.get("gif_speed", "1.0x (Normal)"))
        self.gif_speed_menu = ctk.CTkComboBox(self.gif_tab_frame, variable=self.gif_speed_var,
                                              values=["0.25x", "0.5x", "1.0x (Normal)", "1.5x", "2.0x", "3.0x"],
                                              state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                              fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                              font=font_reg, dropdown_font=font_reg)
        self.gif_speed_menu.grid(row=3, column=0, sticky="ew", padx=(0, 28))
        ToolTip(self.gif_speed_menu, "Scale the animation frame rate / playback speed")

        self.gif_dither_var = ctk.StringVar(value=self.active_settings.get("gif_dither", "Threshold"))
        self.gif_dither_menu = ctk.CTkComboBox(self.gif_tab_frame, variable=self.gif_dither_var,
                                               values=["Threshold", "Floyd-Steinberg Dither"],
                                               state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                               fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                               font=font_reg, dropdown_font=font_reg)
        self.gif_dither_menu.grid(row=3, column=1, sticky="ew", padx=(0, 28))
        ToolTip(self.gif_dither_menu, "Choose 1-bit monochrome dithering algorithm")

        self.gif_scale_var = ctk.StringVar(value=self.active_settings.get("gif_scale", "Aspect Ratio"))
        self.gif_scale_menu = ctk.CTkComboBox(self.gif_tab_frame, variable=self.gif_scale_var,
                                               values=["Aspect Ratio", "Stretch"],
                                               state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                               fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                               font=font_reg, dropdown_font=font_reg)
        self.gif_scale_menu.grid(row=3, column=2, sticky="ew", padx=(0, 28))
        ToolTip(self.gif_scale_menu, "Select resize scaling mode for the display aspect ratio")

        self.gif_invert_var = ctk.BooleanVar(value=self.active_settings.get("gif_invert", False))
        self.gif_invert_cb = ctk.CTkSwitch(self.gif_tab_frame, text="", variable=self.gif_invert_var, font=font_reg,
                                           progress_color="#11FF00", fg_color="#252525", button_color="#FFFFFF", button_hover_color="#FFFFFF")
        self.gif_invert_cb.grid(row=3, column=3, sticky="w")
        ToolTip(self.gif_invert_cb, "Invert black and white pixels in the output animation")

        self.gif_thresh_lbl = ctk.CTkLabel(self.gif_tab_frame, text="THRESHOLD", text_color="#E4E4E4", font=font_bold)

        # ── PC STATS Mode Form Grid ────────────────────────────────────────────────
        ctk.CTkLabel(self.stats_tab_frame, text="UPDATE INTERVAL", text_color="#E4E4E4", font=font_bold).grid(row=0, column=0, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.stats_tab_frame, text="DASHBOARD FONT", text_color="#E4E4E4", font=font_bold).grid(row=0, column=1, sticky="w", padx=(0, 28))
        ctk.CTkLabel(self.stats_tab_frame, text="MONITOR GPU", text_color="#E4E4E4", font=font_bold).grid(row=0, column=2, sticky="w", padx=(0, 28))

        self.stats_interval_var = ctk.StringVar(value=self.active_settings.get("stats_interval", "1.0s (Normal)"))
        self.stats_interval_menu = ctk.CTkComboBox(self.stats_tab_frame, variable=self.stats_interval_var,
                                                   values=["0.5s", "1.0s (Normal)", "2.0s", "5.0s"],
                                                   state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                                   fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                                   font=font_reg, dropdown_font=font_reg)
        self.stats_interval_menu.grid(row=1, column=0, sticky="ew", padx=(0, 28))
        ToolTip(self.stats_interval_menu, "How often to poll and update system resource metrics")

        self.stats_font_var = ctk.StringVar(value=self.active_settings.get("stats_font", "Proggy Tiny"))
        self.stats_font_menu = ctk.CTkComboBox(self.stats_tab_frame, variable=self.stats_font_var,
                                               values=[
                                                   "Proggy Tiny", "Tiny5", "Cozette", "Tom Thumb",
                                                   "U8g2 Nokia Small", "U8g2 Nokia Small Bold", "U8g2 Nokia Large Bold",
                                                   "U8g2 Haxrcorp 4089", "U8g2 3x5", "U8g2 8bit Classic",
                                                   "U8g2 Commodore 64", "U8g2 Press Start 2P", "U8g2 Pixellari",
                                                   "U8g2 Terminal"
                                               ],
                                               state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                               fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                               font=font_reg, dropdown_font=font_reg)
        self.stats_font_menu.grid(row=1, column=1, sticky="ew", padx=(0, 28))
        ToolTip(self.stats_font_menu, "Font family optimized for SSD1306 128x64 display layouts")

        self.stats_gpu_var = ctk.BooleanVar(value=self.active_settings.get("stats_gpu", self.has_nvidia))
        self.stats_gpu_cb = ctk.CTkSwitch(self.stats_tab_frame, text="", variable=self.stats_gpu_var, font=font_reg,
                                          progress_color="#11FF00", fg_color="#252525", button_color="#FFFFFF", button_hover_color="#FFFFFF")
        self.stats_gpu_cb.grid(row=1, column=2, sticky="w")
        ToolTip(self.stats_gpu_cb, "Toggle NVIDIA GPU utilization/clock speed/temperature tracking (Requires nvidia-smi)")
        if not self.has_nvidia:
            self.stats_gpu_cb.configure(state="disabled")
            self.stats_gpu_var.set(False)

        # ── CLOCK Mode Form Grid ───────────────────────────────────────────────────
        self.clk_lbl_format = ctk.CTkLabel(self.clk_tab_frame, text="TIME FORMAT", text_color="#E4E4E4", font=font_bold)
        self.clk_lbl_format.grid(row=0, column=0, sticky="w", pady=(8, 2), padx=(0, 28))
        self.clk_lbl_theme = ctk.CTkLabel(self.clk_tab_frame, text="CLOCK THEME", text_color="#E4E4E4", font=font_bold)
        self.clk_lbl_theme.grid(row=0, column=1, sticky="w", pady=(8, 2), padx=(0, 28))

        self.clk_format_var = ctk.StringVar(value=self.active_settings.get("clock_format", "12-Hour"))
        self.clk_format_menu = ctk.CTkComboBox(self.clk_tab_frame, variable=self.clk_format_var,
                                               values=["12-Hour", "24-Hour"],
                                               state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                               fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                               font=font_reg, dropdown_font=font_reg)
        self.clk_format_menu.grid(row=1, column=0, sticky="ew", padx=(0, 28))
        ToolTip(self.clk_format_menu, "Toggle between 12-Hour and 24-Hour display format")

        self.clk_theme_var = ctk.StringVar(value=self.active_settings.get("clock_theme", "OBSEDIAN"))
        self.clk_theme_menu = ctk.CTkComboBox(self.clk_tab_frame, variable=self.clk_theme_var,
                                               values=["OBSEDIAN"],
                                               state="readonly", border_width=1, border_color="#444444", corner_radius=14,
                                               fg_color="#252525", button_color="#252525", button_hover_color="#333333", text_color="#FFFFFF",
                                               font=font_reg, dropdown_font=font_reg)
        self.clk_theme_menu.grid(row=1, column=1, sticky="ew", padx=(0, 28))
        ToolTip(self.clk_theme_menu, "Select the visual theme for the clock display")

        # ── Offsets initialization (D-pad removed but offsets variables kept for text rendering alignment) ──
        self.offset_x_var = tk.IntVar(value=self.active_settings.get("offset_x", 0))
        self.offset_y_var = tk.IntVar(value=self.active_settings.get("offset_y", 0))

        # ── Trace Settings Modifications ──────────────────────────────────────────
        self.model_var.trace_add("write", self._handle_model_change)
        self.lang_var.trace_add("write", self._handle_language_change)
        self.font_var.trace_add("write", self._handle_font_change)
        self.mode_var.trace_add("write", self._check_pending_changes)
        self.align_var.trace_add("write", self._check_pending_changes)
        self.case_var.trace_add("write", self._check_pending_changes)
        self.invert_var.trace_add("write", self._check_pending_changes)
        self.alert_var.trace_add("write", self._check_pending_changes)
        self.welcome_var.trace_add("write", self._check_pending_changes)
        self.vis_var.trace_add("write", self._check_pending_changes)
        self.music_var.trace_add("write", self._check_pending_changes)
        self.gif_speed_var.trace_add("write", self._check_pending_changes)
        self.gif_dither_var.trace_add("write", self._check_pending_changes)
        self.gif_scale_var.trace_add("write", self._check_pending_changes)
        self.gif_invert_var.trace_add("write", self._check_pending_changes)
        self.gif_path_var.trace_add("write", self._check_pending_changes)
        self.gif_dither_var.trace_add("write", self._update_thresh_state)
        self._update_thresh_state()
        self.stats_interval_var.trace_add("write", self._check_pending_changes)
        self.stats_gpu_var.trace_add("write", self._check_pending_changes)
        self.stats_font_var.trace_add("write", self._check_pending_changes)
        self.clk_format_var.trace_add("write", self._check_pending_changes)
        self.clk_anim_var.trace_add("write", self._check_pending_changes)
        self.clk_theme_var.trace_add("write", self._check_pending_changes)
        self.auto_start_var.trace_add("write", self._check_pending_changes)


        # ── Bottom Margin Status Labels ────────────────────────────────────────────
        self.wpm_lbl = ctk.CTkLabel(self, text="Speed: 0 WPM", text_color="#FF9100", font=ctk.CTkFont(family="Vin Mono Pro", size=11))
        self.wpm_lbl.place(x=28, y=650)

        self.mdl_lbl = ctk.CTkLabel(self, text="Stopped", text_color="#888888", font=ctk.CTkFont(family="Vin Mono Pro", size=11))
        self.mdl_lbl.place(x=980, y=650, anchor="ne")

    def slide_transition(self):
        if hasattr(self, "_transitioning") and self._transitioning:
            return
        self._transitioning = True
        
        self.view_dashboard.place(x=1008, y=0)
        
        steps = 15
        delay = 10
        
        def animate(step):
            if step > steps:
                self.view_devices.place_forget()
                self.view_dashboard.place(x=0, y=0)
                self._transitioning = False
                return
            
            t = step / steps
            ease_out = 1 - (1 - t) ** 3
            
            x_offset = int(1008 * (1 - ease_out))
            
            self.view_devices.place(x=x_offset - 1008, y=0)
            self.view_dashboard.place(x=x_offset, y=0)
            
            self.after(delay, lambda: animate(step + 1))
            
        animate(1)

    def _update_connection_status(self, text, color):
        if color == "#D32F2F" or color == "#FF0038":
            bose_color = "#FF0038"
        elif color == "#FF9800" or color == "#FF9100":
            bose_color = "#FF9100"
        elif color == "#4CAF50" or color == "#11FF00":
            bose_color = "#11FF00"
        else:
            bose_color = color

        if "scanning" in text.lower():
            display_text = "● CAPTOR X [CONNECTING...]"
        elif "not connected" in text.lower() or "failed" in text.lower():
            display_text = "● CAPTOR X [OFFLINE]"
        elif "connected" in text.lower():
            parts = text.split()
            port_info = f" ({parts[-1]})" if len(parts) > 3 else ""
            display_text = f"● CAPTOR X [ONLINE]{port_info}"
        else:
            display_text = text

        if hasattr(self, 'esp_lbl_v1') and self.esp_lbl_v1:
            self.esp_lbl_v1.configure(text=display_text, text_color=bose_color)
        if hasattr(self, 'esp_lbl') and self.esp_lbl:
            self.esp_lbl.configure(text=display_text, text_color=bose_color)


    def _handle_language_change(self, *args):
        if self.lang_var.get() not in ["Auto-Detect", "English"]:
            if self.model_var.get() == "tiny.en":
                self.model_var.set("tiny")
        self._check_pending_changes()

    def _handle_model_change(self, *args):
        if self.model_var.get() == "tiny.en":
            if self.lang_var.get() not in ["Auto-Detect", "English"]:
                self.lang_var.set("English")
        self._check_pending_changes()
    def _handle_tab_change(self, choice):
        self.captions_tab_frame.pack_forget()
        self.gif_tab_frame.pack_forget()
        self.stats_tab_frame.pack_forget()
        self.clk_tab_frame.pack_forget()
        
        backend_choice = self.get_staged_mode()
        if backend_choice == "CAPTIONS":
            self.captions_tab_frame.pack(fill="both", expand=True)
        elif backend_choice == "GIF PLAYER":
            self.gif_tab_frame.pack(fill="both", expand=True)
        elif backend_choice == "PC STATS":
            self.stats_tab_frame.pack(fill="both", expand=True)
        elif backend_choice == "CLK":
            self.clk_tab_frame.pack(fill="both", expand=True)
        self._check_pending_changes()
        self._update_status_and_button_states()

    def _update_status_and_button_states(self):
        selected_mode = self.get_staged_mode()
        active_mode = self.active_settings.get("mode", "CAPTIONS").upper()
        
        # 1. Update self.btn (Play/Stop icon and color)
        if self.running and selected_mode == active_mode:
            self.btn.configure(text="■", fg_color="#FF0038", hover_color="#D30030", text_color="#FFFFFF")
        else:
            self.btn.configure(text="▶", fg_color="#252525", hover_color="#333333", text_color="#FFFFFF")
            
        # 2. Update self.mdl_lbl status text
        if self.running:
            if selected_mode == active_mode:
                if active_mode == "GIF PLAYER":
                    self.mdl_lbl.configure(text="GIF Player Active ✓", text_color="#4CAF50")
                elif active_mode == "PC STATS":
                    self.mdl_lbl.configure(text="PC Stats Active ✓", text_color="#4CAF50")
                else:  # CAPTIONS
                    if self.active_settings.get("music_mode", False):
                        self.mdl_lbl.configure(text="Music Mode Active ✓", text_color="#4CAF50")
                    elif self.model:
                        device_str = "GPU" if self.model_on_gpu else "CPU"
                        self.mdl_lbl.configure(text=f"{self.loaded_model_size} ({device_str}) ready ✓", text_color="#4CAF50")
                    else:
                        self.mdl_lbl.configure(text="Loading model...", text_color="#FF9800")
            else:
                self.mdl_lbl.configure(text=f"Active ({active_mode}) ✓", text_color="#FF9800")
        else:
            self.mdl_lbl.configure(text="Stopped", text_color="#888888")
    def _update_thresh_state(self, *args):
        mode = self.gif_dither_var.get()
        if mode == "Threshold":
            self.gif_thresh_slider.configure(state="normal")
            self.gif_thresh_lbl.configure(text_color="#E4E4E4")
            self.gif_thresh_val_lbl.configure(text_color="#E4E4E4")
        else:
            self.gif_thresh_slider.configure(state="disabled")
            self.gif_thresh_lbl.configure(text_color="#444444")
            self.gif_thresh_val_lbl.configure(text_color="#444444")

    def get_staged_mode(self):
        val = self.app_mode_var.get().upper()
        if val == "CC":
            return "CAPTIONS"
        if val == "GIF":
            return "GIF PLAYER"
        if val == "STATS":
            return "PC STATS"
        return val

    def set_staged_mode(self, mode):
        mode_upper = mode.upper()
        if mode_upper == "CAPTIONS":
            self.app_mode_var.set("CC")
        elif mode_upper == "GIF PLAYER":
            self.app_mode_var.set("GIF")
        elif mode_upper == "PC STATS":
            self.app_mode_var.set("STATS")
        else:
            self.app_mode_var.set(mode)

    def _start_stats_thread(self):
        self.stats_thread_running = True
        t = threading.Thread(target=self._stats_loop, daemon=True)
        t.start()

    def _stats_loop(self):
        import subprocess
        
        # Resolve CPU Name once at startup
        cpu_name = "Unknown CPU"
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
            # Clean up CPU name
            for words_to_remove in [" 6-Core Processor", " 8-Core Processor", " 12-Core Processor", " 16-Core Processor", " Processor", " 4-Core Processor"]:
                cpu_name = cpu_name.replace(words_to_remove, "")
            cpu_name = cpu_name.replace("AMD ", "").replace("Intel ", "")
            if len(cpu_name) > 16:
                cpu_name = cpu_name[:16]
        except Exception:
            pass
        self.system_stats["cpu_name"] = cpu_name

        # Resolve GPU Name once if possible
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

        # Main stats update loop
        while self.stats_thread_running:
            if not hasattr(self, "app_mode_var"):
                time.sleep(0.1)
                continue
            try:
                selected_mode = self.get_staged_mode()
                active_mode = self.active_settings.get("mode", "CAPTIONS").upper()
            except Exception:
                time.sleep(0.1)
                continue
            
            if selected_mode != "PC STATS" and not (self.running and active_mode == "PC STATS"):
                # Suspend heavy background querying to save memory and CPU resources
                time.sleep(1.0)
                continue

            try:
                # 1. CPU utilization and frequency
                cpu_util_val = int(psutil.cpu_percent())
                self.system_stats["cpu_util"] = f"{cpu_util_val}%"
                
                cpu_mhz_val = 0
                freq = psutil.cpu_freq()
                if freq:
                    cpu_mhz_val = int(freq.current)
                self.system_stats["cpu_mhz"] = str(cpu_mhz_val)
                
                # Fetch CPU Temperature
                cpu_temp_val = get_cpu_temp()
                if cpu_temp_val:
                    self.system_stats["cpu_temp"] = cpu_temp_val
                else:
                    self.system_stats["cpu_temp"] = "--°C"
                
                # 2. RAM and Disk
                mem = psutil.virtual_memory()
                self.system_stats["ram_util"] = f"{int(mem.percent)}%"
                
                disk = psutil.disk_usage('/')
                self.system_stats["disk_util"] = f"{int(disk.percent)}%"
                
                # 3. Local Time
                self.system_stats["local_time"] = time.strftime("%H:%M")

                # 4. GPU stats if enabled and nvidia-smi is available
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

            # Sleep dynamic interval
            interval_str = self.active_settings.get("stats_interval", "1.0s (Normal)")
            try:
                sleep_time = float(interval_str.split()[0].replace("s", ""))
            except Exception:
                sleep_time = 1.0
            
            for _ in range(int(sleep_time * 10)):
                if not self.stats_thread_running:
                    break
                time.sleep(0.1)

    def _browse_gif(self):
        f_path = filedialog.askopenfilename(filetypes=[("GIF Files", "*.gif")])
        if f_path:
            f_path = f_path.replace("\\", "/")
            self.gif_path_var.set(f_path)
            self._check_pending_changes()

    def _check_pending_changes(self, *args):
        has_changes = (
            self.model_var.get() != self.active_settings["model"] or
            self.lang_var.get() != self.active_settings["language"] or
            self.font_var.get() != self.active_settings["font"] or
            self.mode_var.get() != self.active_settings["display_mode"] or
            self.align_var.get() != self.active_settings["alignment"] or
            self.case_var.get() != self.active_settings["case"] or
            int(self.bright_slider.get()) != self.active_settings["brightness"] or
            self.invert_var.get() != self.active_settings["invert"] or
            self.alert_var.get() != self.active_settings["alert"] or
            self.welcome_var.get() != self.active_settings["welcome"] or
            self.offset_x_var.get() != self.active_settings.get("offset_x", 0) or
            self.offset_y_var.get() != self.active_settings.get("offset_y", 0) or
            self.vis_var.get() != self.active_settings.get("visualizer", "Tape Graphics") or
            self.music_var.get() != self.active_settings.get("music_mode", False) or
            self.get_staged_mode() != self.active_settings.get("mode", "CAPTIONS").upper() or
            self.gif_speed_var.get() != self.active_settings.get("gif_speed", "1.0x (Normal)") or
            self.gif_dither_var.get() != self.active_settings.get("gif_dither", "Threshold") or
            self.gif_scale_var.get() != self.active_settings.get("gif_scale", "Aspect Ratio") or
            self.gif_invert_var.get() != self.active_settings.get("gif_invert", False) or
            self.gif_path_var.get() != self.active_settings.get("gif_path", "") or
            int(self.gif_thresh_slider.get()) != self.active_settings.get("gif_threshold", 128) or
            self.stats_interval_var.get() != self.active_settings.get("stats_interval", "1.0s (Normal)") or
            self.stats_gpu_var.get() != self.active_settings.get("stats_gpu", self.has_nvidia) or
            self.stats_font_var.get() != self.active_settings.get("stats_font", "Proggy Tiny") or
            self.clk_format_var.get() != self.active_settings.get("clock_format", "12-Hour") or
            self.clk_anim_var.get() != self.active_settings.get("clock_animation", "Snappy Easing") or
            self.clk_theme_var.get() != self.active_settings.get("clock_theme", "OBSEDIAN") or
            self.auto_start_var.get() != self.active_settings.get("auto_start", False)
        )
        if has_changes:
            self.apply_btn.configure(
                text="✓",
                fg_color="#FF9100",
                hover_color="#E08000",
                text_color="#FFFFFF"
            )
        else:
            self.apply_btn.configure(
                text="✓",
                fg_color="#444444",
                hover_color="#555555",
                text_color="#FFFFFF"
            )

    def _apply_settings(self):
        model_changed = (self.model_var.get() != self.active_settings["model"] or
                         self.lang_var.get() != self.active_settings["language"] or
                         self.music_var.get() != self.active_settings.get("music_mode", False) or
                         self.audio_var.get() != self.active_settings.get("audio_source", ""))
        
        mode_changed = (self.get_staged_mode() != self.active_settings.get("mode", "CAPTIONS").upper())
        gif_changed = (
            self.gif_path_var.get() != self.active_settings.get("gif_path", "") or
            self.gif_dither_var.get() != self.active_settings.get("gif_dither", "Threshold") or
            self.gif_scale_var.get() != self.active_settings.get("gif_scale", "Aspect Ratio") or
            self.gif_invert_var.get() != self.active_settings.get("gif_invert", False) or
            int(self.gif_thresh_slider.get()) != self.active_settings.get("gif_threshold", 128)
        )

        # Commit GUI values to active_settings
        self.active_settings["model"] = self.model_var.get()
        self.active_settings["language"] = self.lang_var.get()
        self.active_settings["font"] = self.font_var.get()
        self.active_settings["display_mode"] = self.mode_var.get()
        self.active_settings["alignment"] = self.align_var.get()
        self.active_settings["case"] = self.case_var.get()
        self.active_settings["brightness"] = int(self.bright_slider.get())
        self.active_settings["invert"] = self.invert_var.get()
        self.active_settings["alert"] = self.alert_var.get()
        self.active_settings["welcome"] = self.welcome_var.get()
        self.active_settings["audio_source"] = self.audio_var.get()
        self.active_settings["offset_x"] = self.offset_x_var.get()
        self.active_settings["offset_y"] = self.offset_y_var.get()
        self.active_settings["visualizer"] = self.vis_var.get()
        self.active_settings["music_mode"] = self.music_var.get()
        
        self.active_settings["mode"] = self.get_staged_mode()
        self.active_settings["gif_path"] = self.gif_path_var.get()
        self.active_settings["gif_speed"] = self.gif_speed_var.get()
        self.active_settings["gif_dither"] = self.gif_dither_var.get()
        self.active_settings["gif_scale"] = self.gif_scale_var.get()
        self.active_settings["gif_invert"] = self.gif_invert_var.get()
        self.active_settings["gif_threshold"] = int(self.gif_thresh_slider.get())
        self.active_settings["stats_interval"] = self.stats_interval_var.get()
        self.active_settings["stats_gpu"] = self.stats_gpu_var.get()
        self.active_settings["stats_font"] = self.stats_font_var.get()
        self.active_settings["clock_format"] = self.clk_format_var.get()
        self.active_settings["clock_animation"] = self.clk_anim_var.get()
        self.active_settings["clock_theme"] = self.clk_theme_var.get()
        self.active_settings["auto_start"] = self.auto_start_var.get()
        self._apply_startup_setting(self.active_settings["auto_start"])


        # Save per-font offset
        font_name = self.font_var.get()
        if font_name != "Browse custom font...":
            font_offsets = self.active_settings.setdefault("font_offsets", {})
            font_offsets[font_name] = {"x": self.offset_x_var.get(), "y": self.offset_y_var.get()}

        # Save configuration
        self.save_config()

        # Reload GIF if settings changed or switched to GIF player mode
        if gif_changed or (mode_changed and self.active_settings["mode"] == "GIF PLAYER"):
            self._load_gif(self.active_settings["gif_path"])

        # Update physical display hardware configuration immediately
        self._handle_brightness(self.active_settings["brightness"])
        self._handle_inversion()

        # Reload transcription pipeline if Whisper configurations or mode changed while running
        if self.running and (model_changed or mode_changed):
            self._stop()
            self.after(600, self._start)

        self._check_pending_changes()
        self._update_status_and_button_states()

    def _handle_font_selection(self, choice):
        if choice == "Browse custom font...":
            f_path = filedialog.askopenfilename(filetypes=[("Font Files", "*.ttf;*.otf")])
            if f_path:
                f_path = f_path.replace("\\", "/")
                vals = list(self.font_menu.cget("values"))
                font_name = os.path.basename(f_path)
                FONT_MAP[font_name] = f_path
                self.active_settings["custom_fonts"][font_name] = f_path
                if font_name not in vals:
                    vals.insert(-1, font_name)
                    self.font_menu.configure(values=vals)
                self.font_var.set(font_name)
                self.last_valid_font = font_name
                self.save_config()
            else:
                self.font_var.set(self.last_valid_font)
        else:
            self.last_valid_font = choice
        self._check_pending_changes()

    def _handle_font_change(self, *args):
        font_name = self.font_var.get()
        if font_name == "Browse custom font...":
            return
        font_offsets = self.active_settings.setdefault("font_offsets", {})
        offsets = font_offsets.get(font_name, {"x": 0, "y": 0})
        self.offset_x_var.set(offsets.get("x", 0))
        self.offset_y_var.set(offsets.get("y", 0))
        self._check_pending_changes()

    def _handle_slider_change(self, val):
        self._check_pending_changes()
        val_int = int(float(val))
        if not hasattr(self, "_last_sent_brightness") or self._last_sent_brightness != val_int:
            self._last_sent_brightness = val_int
            self._handle_brightness(val_int)

    def _handle_brightness(self, val):
        send_line(f"[BRIGHT:{int(val)}]")

    def _handle_inversion(self):
        val = 1 if self.active_settings["invert"] else 0
        send_line(f"[INVERT:{val}]")

    def _populate_devices(self):
        self.dev_map = {}
        names = []
        
        try:
            p = pyaudio.PyAudio()
        except Exception as e:
            print(f"Error initializing PyAudio: {e}")
            saved_audio = self.active_settings.get("audio_source")
            if saved_audio:
                names.append(saved_audio)
                self.dev_map[saved_audio] = -1
            return

        try:
            try:
                wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                wasapi_idx = wasapi_info['index']
            except IOError:
                wasapi_idx = None
            
            preferred = None
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                if wasapi_idx is not None and dev['hostApi'] != wasapi_idx:
                    continue
                if dev['maxInputChannels'] < 1:
                    continue
                
                label = dev['name']
                names.append(label)
                self.dev_map[label] = i
                
                if "ai-04" in label.lower() or "8-" in label.lower():
                    if "loopback" in label.lower():
                        preferred = label  
                    elif not preferred or "loopback" not in preferred.lower():
                        preferred = label  
        finally:
            try:
                p.terminate()
            except Exception:
                pass

        if not names:
            try:
                p = pyaudio.PyAudio()
                for i in range(p.get_device_count()):
                    dev = p.get_device_info_by_index(i)
                    if dev['maxInputChannels'] > 0:
                        label = f"{dev['name']} [{i}]"
                        names.append(label)
                        self.dev_map[label] = i
            except Exception as e:
                print(f"Error in PyAudio fallback: {e}")
            finally:
                try:
                    p.terminate()
                except Exception:
                    pass

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
                names.insert(0, saved_audio)
                self.dev_map[saved_audio] = -1

        if names:
            self.audio_menu.configure(values=names)
            saved_audio = self.active_settings["audio_source"]
            if saved_audio in self.dev_map:
                self.audio_var.set(saved_audio)
            elif preferred and preferred in self.dev_map:
                self.audio_var.set(preferred)
            else:
                self.audio_var.set(names[0])

    def _refresh_ports(self):
        ports = ["None"] + [p.device for p in serial.tools.list_ports.comports()]
        self.port_menu.configure(values=ports)
        if self.port_var.get() not in ports:
            self.port_var.set("None")

    def _auto_connect_async(self):
        def scan():
            self._update_connection_status("● Scanning COM ports...", "#FF9800")
            port = auto_detect_captor_x_port()
            if port:
                self.after(0, lambda: self._connect_to_port(port))
            else:
                self.after(0, lambda: self._update_connection_status("● Captor X not found (Auto)", "#D32F2F"))
        threading.Thread(target=scan, daemon=True).start()
        
    def _connect_to_port(self, port):
        self.port_var.set(port)
        self._connect_port(port)

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
            self._update_connection_status("● Captor X not connected", "#D32F2F")
            return

        def target():
            self._connecting_in_progress = True
            global serial_port
            self._update_connection_status("● Connecting...", "#FF9800")
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
                
                self._update_connection_status(f"● Captor X Connected {choice}", "#4CAF50")
                time.sleep(1.0)
                self._handle_brightness(self.active_settings["brightness"])
                time.sleep(0.1)
                self._handle_inversion()
            except Exception as e:
                self._update_connection_status(f"● Connection failed: {e}", "#D32F2F")
                with serial_lock:
                    if serial_port:
                        try:
                            serial_port.close()
                        except Exception:
                            pass
                        serial_port = None
            finally:
                self._connecting_in_progress = False

        threading.Thread(target=target, daemon=True).start()

    def _toggle(self):
        selected_mode = self.get_staged_mode()
        active_mode = self.active_settings.get("mode", "CAPTIONS").upper()
        
        if self.running:
            if selected_mode == active_mode:
                self._stop()
            else:
                self._stop()
                self.after(100, self._start)
        else:
            self._start()

    def _start(self):
        # Apply staged GUI values to settings
        self._apply_settings()

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
            self._update_status_and_button_states()
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

        self._update_status_and_button_states()
        self.update()

        self.last_speech_time = time.time()
        self.oled_cleared = False
        self.active_caption = ""
        self.word_timestamps = []

        def load():
            try:
                dev = self.dev_map.get(self.audio_var.get())
                if self.active_settings.get("music_mode", False):
                    # Check if this thread has been replaced or stop signaled
                    if threading.current_thread() != self.load_thread or local_stop_event.is_set() or not self.running:
                        print("Startup aborted: load thread is obsolete or stopped.")
                        return
                    self.after(0, self._update_status_and_button_states)
                    self.audio_thread = threading.Thread(target=audio_thread_fn, args=(dev, local_stop_event), daemon=True)
                    self.audio_thread.start()
                else:
                    target_model_size = self.active_settings["model"]
                    target_device = "CPU" if self.force_cpu_mode else "GPU"
                    current_device_mode = "GPU" if self.model_on_gpu else "CPU"
                    
                    if self.model is None or self.loaded_model_size != target_model_size or current_device_mode != target_device:
                        if target_device == "GPU":
                            try:
                                self.mdl_lbl.configure(text=f"Loading {target_model_size} (GPU)...", text_color="#FF9800")
                                self.update()
                                self.model = WhisperModel(target_model_size, device="cuda", compute_type="float16")
                                self.model_on_gpu = True
                                self.loaded_model_size = target_model_size
                                self.after(0, self._update_status_and_button_states)
                            except Exception as gpu_err:
                                print(f"GPU load failed: {gpu_err}. Fallback to CPU...")
                                self.mdl_lbl.configure(text=f"Loading {target_model_size} (CPU)...", text_color="#FF9800")
                                self.update()
                                self.model = WhisperModel(target_model_size, device="cpu", compute_type="int8")
                                self.model_on_gpu = False
                                self.loaded_model_size = target_model_size
                                self.after(0, self._update_status_and_button_states)
                        else:
                            self.mdl_lbl.configure(text=f"Loading {target_model_size} (CPU)...", text_color="#FF9800")
                            self.update()
                            self.model = WhisperModel(target_model_size, device="cpu", compute_type="int8")
                            self.model_on_gpu = False
                            self.loaded_model_size = target_model_size
                            self.after(0, self._update_status_and_button_states)
                    else:
                        self.after(0, self._update_status_and_button_states)

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
                self.after(0, lambda: self.mdl_lbl.configure(text=f"Error: {e}", text_color="#D32F2F"))
                self.after(0, self._stop)

        self.load_thread = threading.Thread(target=load, daemon=True)
        self.load_thread.start()

    def _stop(self):
        self.running = False
        if hasattr(self, "session_stop_event") and self.session_stop_event:
            self.session_stop_event.set()
        stop_event.set()
        self._update_status_and_button_states()
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
            self.after(0, lambda: self.mdl_lbl.configure(text="Stopped", text_color="#888888"))

    def trigger_cpu_fallback(self):
        if not getattr(self, "force_cpu_mode", False):
            print("Triggering CPU fallback due to GPU/CUDA failure...")
            self.after(0, self._handle_gpu_fallback)

    def _handle_gpu_fallback(self):
        self._stop()
        self._unload_model()
        self.force_cpu_mode = True
        self.after(1000, self._start)

    def _poll(self):
        global current_volume
        has_new = False
        
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
                                self.after(400, lambda: send_line(f"[INVERT:{1 if self.active_settings['invert'] else 0}]"))
                            pass
        except queue.Empty:
            pass

        if has_new:
            if len(self.history) > 400:
                self.history = self.history[-400:]
            self.active_caption = " ".join(self.history[-15:])

        # Calculate Words Per Minute
        now = time.time()
        self.word_timestamps = [t for t in self.word_timestamps if now - t <= 60]
        self.wpm_lbl.configure(text=f"Speed: {len(self.word_timestamps)} WPM")

        # Silence clear timeout - skipped if Music Mode is enabled
        if self.running and not self.active_settings.get("music_mode", False) and not self.oled_cleared and (now - self.last_speech_time > 3.0):
            self.active_caption = ""
            self.history = []  # Clear history on silence to start a fresh alignment with new speech
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

        # Render current frame
        self.wave_phase = (self.wave_phase + 0.15) % (2 * math.pi)
        target_speed = (1.5 + current_volume * 18.0) if current_volume > 0.01 else 0.0
        self.tape_velocity += (target_speed - self.tape_velocity) * 0.1
        self.tape_angle = (self.tape_angle + self.tape_velocity) % 360.0

        # Get preview styling (staged, from GUI widgets directly for live feedback)
        try:
            preview_font = self.font_var.get()
            preview_mode = self.mode_var.get()
            preview_align = self.align_var.get()
            preview_case = self.case_var.get()
            preview_invert = self.invert_var.get()
            preview_bright = int(self.bright_slider.get())
            preview_welcome = self.welcome_var.get()
            preview_offset_x = self.offset_x_var.get()
            preview_offset_y = self.offset_y_var.get()
        except Exception:
            # Fallback to active settings if GUI widgets are not ready yet
            preview_font = self.active_settings["font"]
            preview_mode = self.active_settings["display_mode"]
            preview_align = self.active_settings["alignment"]
            preview_case = self.active_settings["case"]
            preview_invert = self.active_settings["invert"]
            preview_bright = self.active_settings["brightness"]
            preview_welcome = self.active_settings["welcome"]
            preview_offset_x = self.active_settings.get("offset_x", 0)
            preview_offset_y = self.active_settings.get("offset_y", 0)

        # Active settings for serial port transmission
        active_font = self.active_settings["font"]
        active_mode = self.active_settings["display_mode"]
        active_align = self.active_settings["alignment"]
        active_case = self.active_settings["case"]
        active_welcome = self.active_settings["welcome"]
        active_offset_x = self.active_settings.get("offset_x", 0)
        active_offset_y = self.active_settings.get("offset_y", 0)

        # --- 1. RENDER GUI PREVIEW IMAGE (Using Staged Settings) ---
        staged_mode = self.get_staged_mode()
        active_mode_type = self.active_settings.get("mode", "CAPTIONS").upper()
        
        # Track staged mode transitions
        if staged_mode == "CLK":
            if self.last_staged_mode != "CLK":
                self.clk_staged_start_time = time.time()
            staged_elapsed = time.time() - self.clk_staged_start_time
        else:
            staged_elapsed = None
        self.last_staged_mode = staged_mode

        if staged_mode == "GIF PLAYER":
            if self.gif_frames:
                is_active_gif = (self.running and active_mode_type == "GIF PLAYER")
                if is_active_gif:
                    preview_speed_mult = parse_speed_multiplier(self.gif_speed_var.get())
                    if self.gif_total_duration > 0:
                        elapsed_gui = ((time.time() - self.gif_start_time) * preview_speed_mult) % self.gif_total_duration
                    else:
                        elapsed_gui = 0.0
                    elapsed_gui_ms = elapsed_gui * 1000.0
                    cum = 0.0
                    frame_idx_gui = 0
                    for i, d in enumerate(self.gif_delays):
                        cum += d
                        if cum > elapsed_gui_ms:
                            frame_idx_gui = i
                            break
                    img_gui_base = self.gif_frames[frame_idx_gui]
                else:
                    img_gui_base = self.gif_frames[0]
                img_gui = apply_offset_to_image(img_gui_base, preview_offset_x, preview_offset_y)
            else:
                img_gui = wrap_text_to_image(
                    "No GIF Loaded",
                    preview_font,
                    get_font_size_for_name(preview_font),
                    preview_align,
                    preview_case,
                    has_shadow=True,
                    vu_volume=0.0,
                    offset_x=preview_offset_x,
                    offset_y=preview_offset_y
                )
        elif staged_mode == "PC STATS":
            staged_show_gpu = self.stats_gpu_var.get()
            self.system_stats["cpu_min_mhz"] = self.active_settings.get("cpu_min_mhz", 3600)
            self.system_stats["cpu_max_mhz"] = self.active_settings.get("cpu_max_mhz", 4200)
            img_gui_base = render_pc_stats(self.system_stats, staged_show_gpu, self.stats_font_var.get())
            img_gui = apply_offset_to_image(img_gui_base, preview_offset_x, preview_offset_y)
        elif staged_mode == "CLK":
            img_gui_base = render_clock_mode(
                clock_format=self.clk_format_var.get(),
                clock_animation=self.clk_anim_var.get(),
                clock_theme=self.clk_theme_var.get(),
                mode_elapsed=staged_elapsed
            )
            img_gui = apply_offset_to_image(img_gui_base, preview_offset_x, preview_offset_y)
        else:
            is_active_captions = (self.running and active_mode_type == "CAPTIONS")
            if is_active_captions:
                # Force visualizer rendering if music mode is enabled or active caption has been cleared by timeout
                if self.music_var.get() or self.active_caption.strip() == "":
                    vis_mode = self.vis_var.get()
                    if vis_mode == "Stereo Bars":
                        img_gui = render_stereo_bars(self.wave_phase, current_volume)
                    else:
                        img_gui = render_tape_graphics(self.tape_angle)
                else:
                    if preview_mode == "Word by Word":
                        txt_gui = self.history[-1] if self.history else ""
                    else:
                        txt_gui = self.active_caption
                        
                    if txt_gui.strip() == "":
                        vis_mode = self.vis_var.get()
                        if vis_mode == "Stereo Bars":
                            img_gui = render_stereo_bars(self.wave_phase, current_volume)
                        else:
                            img_gui = render_tape_graphics(self.tape_angle)
                    else:
                        img_gui = wrap_text_to_image(
                            txt_gui,
                            preview_font,
                            get_font_size_for_name(preview_font),
                            preview_align,
                            preview_case,
                            has_shadow=True,
                            vu_volume=current_volume,
                            offset_x=preview_offset_x,
                            offset_y=preview_offset_y
                        )
            else:
                txt_gui = preview_welcome
                img_gui = wrap_text_to_image(
                    txt_gui,
                    preview_font,
                    get_font_size_for_name(preview_font),
                    preview_align,
                    preview_case,
                    has_shadow=True,
                    vu_volume=0.0,
                    offset_x=preview_offset_x,
                    offset_y=preview_offset_y
                )

        # --- 2. RENDER SERIAL STREAM IMAGE (Using Active Settings) ---
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
            self.system_stats["cpu_min_mhz"] = self.active_settings.get("cpu_min_mhz", 3600)
            self.system_stats["cpu_max_mhz"] = self.active_settings.get("cpu_max_mhz", 4200)
            img_serial_base = render_pc_stats(self.system_stats, active_show_gpu, self.active_settings.get("stats_font", "Proggy Tiny"))
            img_serial = apply_offset_to_image(img_serial_base, active_offset_x, active_offset_y)
        elif active_mode_type == "CLK":
            if self.last_mode_type != "CLK":
                self.clk_mode_start_time = time.time()
            active_elapsed = time.time() - self.clk_mode_start_time

            img_serial_base = render_clock_mode(
                clock_format=self.active_settings.get("clock_format", "12-Hour"),
                clock_animation=self.active_settings.get("clock_animation", "Snappy Easing"),
                clock_theme=self.active_settings.get("clock_theme", "OBSEDIAN"),
                mode_elapsed=active_elapsed
            )
            img_serial = apply_offset_to_image(img_serial_base, active_offset_x, active_offset_y)
        else:
            if self.running:
                # Force visualizer rendering if music mode is enabled or active caption has been cleared by timeout
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

        self.last_mode_type = active_mode_type

        # Convert and style the preview image to match physical parameters
        img_preview = img_gui.convert("RGB")
        
        # Apply Inversion
        if preview_invert:
            img_preview = ImageOps.invert(img_preview)
            
        # Apply Brightness / Contrast dimming
        brightness_factor = preview_bright / 255.0
        brightness_factor = max(0.05, brightness_factor)  # Outline remains visible
        enhancer = ImageEnhance.Brightness(img_preview)
        img_preview = enhancer.enhance(brightness_factor)

        if hasattr(self, "mockup_pil") and self.mockup_pil:
            base_img = Image.new("RGBA", (790, 442), (24, 24, 24, 255))
            draw = ImageDraw.Draw(base_img)
            draw.rectangle([228, 135, 561, 299], fill=(0, 0, 0, 255))
            
            oled_scaled = img_preview.resize((334, 165), Image.Resampling.NEAREST)
            base_img.paste(oled_scaled, (228, 135))
            base_img.paste(self.mockup_pil, (0, 0), self.mockup_pil)
            
            self.ctk_img_v2 = ctk.CTkImage(light_image=base_img, dark_image=base_img, size=(790, 442))
            self.dev_image_label_v2.configure(image=self.ctk_img_v2)
        else:
            img_preview_resized = img_preview.resize((156, 78), Image.Resampling.NEAREST)
            self.ctk_img = ctk.CTkImage(light_image=img_preview_resized, dark_image=img_preview_resized, size=(156, 78))
            self.preview_label.configure(image=self.ctk_img, text="")

        # Queue bytes for the background serial sender thread
        raw_bytes = img_serial.tobytes()
        try:
            while True:
                try:
                    self.serial_queue.put_nowait(raw_bytes)
                    break
                except queue.Full:
                    try:
                        self.serial_queue.get_nowait()
                        # Wait, we want to discard the old item and try again
                    except queue.Empty:
                        pass
        except Exception:
            pass

        self.after(50, self._poll)


if __name__ == "__main__":
    import ctypes
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

    app = App()
    app.mainloop()
    
    # Clean background thread cleanup
    stop_event.set()
    app.running = False
    app.stats_thread_running = False
    
    # Save final config on exit
    try:
        app.save_config()
    except Exception:
        pass

    # Wait for threads to exit to ensure clean PortAudio/WASAPI termination
    if app.audio_thread and app.audio_thread.is_alive():
        app.audio_thread.join(timeout=1.0)
    if app.stt_thread and app.stt_thread.is_alive():
        app.stt_thread.join(timeout=1.0)
    if app.load_thread and app.load_thread.is_alive():
        app.load_thread.join(timeout=1.0)

    with serial_lock:
        if serial_port and serial_port.is_open:
            try:
                serial_port.close()
            except Exception:
                pass

    # Force immediate process termination to release all native resources cleanly
    import os
    os._exit(0)

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
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance

# ── settings ──────────────────────────────────────────────────────────────────
CHUNK_SECONDS = 3
BAUD_RATE     = 115200
STEP_SECONDS  = 0.25

FONT_MAP = {
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
        config_dir = os.path.join(appdata, "CaptionCast")
    else:
        config_dir = os.path.join(os.path.expanduser("~"), ".captioncast")
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
                         font=("Arial", "9", "normal"), padx=6, pady=3)
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

    best_L = 0
    best_score = -999999.0
    
    max_L = min(len(A), len(B))
    for L in range(1, max_L + 1):
        suffix_A = A[-L:]
        prefix_B = B[:L]
        
        match_count = 0
        for i in range(L):
            if words_similar(suffix_A[i], prefix_B[i]):
                match_count += 1
                
        mismatch_count = L - match_count
        score = match_count - 1.5 * mismatch_count
        
        if score > best_score or (score == best_score and L > best_L):
            best_score = score
            best_L = L

    accept = False
    if best_score > 0:
        if best_L > 1:
            accept = True
        else:
            word = A[-1]
            word_clean = word.lower().strip(".,!?;:\"'()[]-")
            stopwords = {"the", "a", "an", "to", "in", "of", "and", "is", "it", "you", "that", "he", "was", "for", "on", "are", "as", "with", "his", "they", "i", "at", "be", "this", "have", "from", "or", "one", "had", "by", "word", "but", "not", "what", "all", "were", "we", "when", "your", "can", "said", "there", "use"}
            if len(word_clean) >= 4 and word_clean not in stopwords:
                accept = True

    if accept:
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
        if os.path.isabs(font_name) and os.path.exists(font_name):
            font = ImageFont.truetype(font_name, font_size)
        else:
            font_file = FONT_MAP.get(font_name, font_name)
            if os.path.isabs(font_file) and os.path.exists(font_file):
                font = ImageFont.truetype(font_file, font_size)
            elif os.path.exists(font_file):
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
    bbox = font.getbbox("Ay")
    line_h = bbox[3] - bbox[1] if bbox else current_font_size
    
    total_h = len(lines) * line_h + (len(lines) - 1) * line_spacing
    
    while total_h > MAX_H and lines:
        lines.pop(0)
        total_h = len(lines) * line_h + (len(lines) - 1) * line_spacing
        
    y = (64 - total_h) // 2
    for line in lines:
        w = draw.textlength(line, font=font)
        if alignment == "left":
            x = PADDING_X
        elif alignment == "right":
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

# ── Auto-Port Scan Handshake ──────────────────────────────────────────────────
def auto_detect_esp32_port():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    for port in ports:
        try:
            s = serial.Serial(port, BAUD_RATE, timeout=0.3)
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

# ══════════════════════════════════════════════════════════════════════════════
#  AUDIO CAPTURE
# ══════════════════════════════════════════════════════════════════════════════
def audio_thread_fn(device_index):
    global pyaudio_instance, audio_stream, rolling_buffer, current_volume
    pyaudio_instance = pyaudio.PyAudio()
    
    try:
        dev_info = pyaudio_instance.get_device_info_by_index(device_index)
        device_sr = int(dev_info['defaultSampleRate'])
        num_channels = dev_info['maxInputChannels']
    except Exception as e:
        transcription_queue.put([f"[ERROR: Querying device {device_index} failed: {e}]"])
        pyaudio_instance.terminate()
        pyaudio_instance = None
        return

    def callback(in_data, frame_count, time_info, status_flags):
        global rolling_buffer, current_volume
        audio_data = np.frombuffer(in_data, dtype=np.float32)
        if num_channels > 1:
            mono = audio_data.reshape(-1, num_channels)[:, 0].copy()
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
            
        audio_stream.stop_stream()
        audio_stream.close()
    except Exception as e:
        transcription_queue.put([f"[ERROR: {e}]"])
    finally:
        audio_stream = None
        pyaudio_instance.terminate()
        pyaudio_instance = None

# ══════════════════════════════════════════════════════════════════════════════
#  STT THREAD (English Filtered)
# ══════════════════════════════════════════════════════════════════════════════
def stt_thread_fn(model, language, vad_filter, task):
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
                if not model.model_path.endswith(".en") and info.language != "en" and info.language_probability > 0.4:
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

# ══════════════════════════════════════════════════════════════════════════════
#  SERIAL SEND
# ══════════════════════════════════════════════════════════════════════════════
def send_line(line_text):
    global serial_port
    if serial_port and serial_port.is_open:
        try:
            serial_port.write((line_text.strip() + "\n").encode("utf-8"))
        except serial.SerialException:
            serial_port = None

# ══════════════════════════════════════════════════════════════════════════════
#  GUI APPLICATION (Portrait Layout with Saved State)
# ══════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.configure(fg_color="#000000")
        self.title("CaptionCast Pro")
        self.geometry("740x780")
        self.resizable(False, False)

        self.model    = None
        self.model_on_gpu = False
        self.loaded_model_size = None
        self.running  = False
        self.history  = []
        self.dev_map  = {}   
        
        # Style state
        self.last_speech_time = time.time()
        self.oled_cleared = True
        self.wave_phase = 0.0
        self.active_caption = ""
        self.word_timestamps = []
        
        self.lang_map = {
            "Auto-Detect": None,
            "English": "en"
        }

        # Active Settings (Committed via Apply Settings button / Loaded from JSON)
        self.active_settings = {
            "model": "tiny.en",
            "language": "English",
            "font": "Lucida Console (Retro)",
            "size": 24,
            "display_mode": "Line by Line",
            "alignment": "center",
            "case": "Sentence case",
            "brightness": 255,
            "invert": False,
            "alert": "",
            "welcome": "CaptionCast Active",
            "com_port": "None",
            "audio_source": "",
            "custom_fonts": {},
            "offset_x": 0,
            "offset_y": 0
        }
        self.last_valid_font = self.active_settings["font"]

        # Load configuration from AppData JSON
        self.load_config()

        # Update FONT_MAP with custom loaded fonts
        for font_name, font_path in self.active_settings["custom_fonts"].items():
            FONT_MAP[font_name] = font_path

        self._build_ui()
        self._populate_devices()
        self._refresh_ports()
        self._check_pending_changes() # Initialize button state

        # Restore saved Audio Source if available
        saved_audio = self.active_settings["audio_source"]
        if saved_audio in self.dev_map:
            self.audio_var.set(saved_audio)

        # Auto-connect to saved COM Port
        saved_com = self.active_settings["com_port"]
        if saved_com != "None":
            # Schedule auto-connect shortly after startup
            self.after(500, lambda: self._connect_to_port(saved_com))

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

    def _build_ui(self):
        # Header
        ctk.CTkLabel(self, text="CaptionCast Pro",
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color="#FFFFFF").pack(pady=(12,2))
        ctk.CTkLabel(self, text="Realtime Speech → OLED Graphics Output",
                     font=ctk.CTkFont(size=12), text_color="#888888").pack(pady=(0,8))

        # Centered OLED Preview Box (Exactly 2:1 Aspect Ratio)
        wf = ctk.CTkFrame(self, width=388, height=196, corner_radius=8,
                          fg_color="#121212", border_width=0)
        wf.pack(pady=(10,10))
        wf.pack_propagate(False)
        self.preview_label = ctk.CTkLabel(wf, text="OLED Screen Preview", text_color="#333333")
        self.preview_label.pack(padx=2, pady=2, expand=True, fill="both")

        # Settings panel frame
        sf = ctk.CTkFrame(self, fg_color="#121212", border_width=0, corner_radius=8)
        sf.pack(fill="both", expand=True, padx=20, pady=(0,10))
        sf.grid_columnconfigure((0,1,2,3), weight=1, pad=10)

        # Settings Row 0: Model & Language
        ctk.CTkLabel(sf, text="Whisper Model:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.model_var = ctk.StringVar(value=self.active_settings["model"])
        self.model_menu = ctk.CTkComboBox(sf, variable=self.model_var, values=["tiny.en", "tiny", "base", "small"],
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=6,
                                           fg_color="#121212", button_color="#1F1F1F", button_hover_color="#333333", text_color="#FFFFFF")
        self.model_menu.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ToolTip(self.model_menu, "Choose Whisper size (tiny.en is fastest, small is most accurate)")

        ctk.CTkLabel(sf, text="Language:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=0, column=2, padx=10, pady=5, sticky="w")
        self.lang_var = ctk.StringVar(value=self.active_settings["language"])
        self.lang_menu = ctk.CTkComboBox(sf, variable=self.lang_var, values=["English", "Auto-Detect"],
                                          state="readonly", border_width=1, border_color="#444444", corner_radius=6,
                                          fg_color="#121212", button_color="#1F1F1F", button_hover_color="#333333", text_color="#FFFFFF")
        self.lang_menu.grid(row=0, column=3, padx=10, pady=5, sticky="ew")
        ToolTip(self.lang_menu, "Select English or enable Auto-Detect to filter out non-English speech")

        # Settings Row 1: Font & Display Mode
        ctk.CTkLabel(sf, text="OLED Font:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.font_var = ctk.StringVar(value=self.active_settings["font"])
        self.font_menu = ctk.CTkComboBox(sf, variable=self.font_var, values=list(FONT_MAP.keys()) + ["Browse custom font..."],
                                           command=self._handle_font_selection,
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=6,
                                           fg_color="#121212", button_color="#1F1F1F", button_hover_color="#333333", text_color="#FFFFFF")
        self.font_menu.grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        ToolTip(self.font_menu, "Select pixel-perfect screen font or load a custom .ttf/.otf file")

        ctk.CTkLabel(sf, text="Display Mode:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=1, column=2, padx=10, pady=5, sticky="w")
        self.mode_var = ctk.StringVar(value=self.active_settings["display_mode"])
        self.mode_menu = ctk.CTkComboBox(sf, variable=self.mode_var, values=["Line by Line", "Word by Word"],
                                          state="readonly", border_width=1, border_color="#444444", corner_radius=6,
                                          fg_color="#121212", button_color="#1F1F1F", button_hover_color="#333333", text_color="#FFFFFF")
        self.mode_menu.grid(row=1, column=3, padx=10, pady=5, sticky="ew")
        ToolTip(self.mode_menu, "Set captions layout to show line by line or word by word")

        # Settings Row 2: Alignment & Text Case
        ctk.CTkLabel(sf, text="Text Alignment:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.align_var = ctk.StringVar(value=self.active_settings["alignment"])
        self.align_menu = ctk.CTkComboBox(sf, variable=self.align_var, values=["center", "left", "right"],
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=6,
                                           fg_color="#121212", button_color="#1F1F1F", button_hover_color="#333333", text_color="#FFFFFF")
        self.align_menu.grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        ToolTip(self.align_menu, "Align text lines on screen")

        ctk.CTkLabel(sf, text="Text Case:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=2, column=2, padx=10, pady=5, sticky="w")
        self.case_var = ctk.StringVar(value=self.active_settings["case"])
        self.case_menu = ctk.CTkComboBox(sf, variable=self.case_var, values=["Sentence case", "UPPERCASE", "lowercase"],
                                          state="readonly", border_width=1, border_color="#444444", corner_radius=6,
                                          fg_color="#121212", button_color="#1F1F1F", button_hover_color="#333333", text_color="#FFFFFF")
        self.case_menu.grid(row=2, column=3, padx=10, pady=5, sticky="ew")
        ToolTip(self.case_menu, "Re-format text casing style")

        # Settings Row 3: Brightness Slider & OLED Inversion Checkbox
        ctk.CTkLabel(sf, text="OLED Brightness:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.bright_slider = ctk.CTkSlider(sf, from_=0, to=255, height=16, fg_color="#333333", progress_color="#4CAF50",
                                            button_color="#4CAF50", button_hover_color="#388E3C",
                                            command=self._handle_slider_change)
        self.bright_slider.set(self.active_settings["brightness"])
        self.bright_slider.grid(row=3, column=1, padx=10, pady=5, sticky="ew")
        ToolTip(self.bright_slider, "Dim or brighten the physical OLED screen")

        self.invert_var = ctk.BooleanVar(value=self.active_settings["invert"])
        self.invert_cb = ctk.CTkCheckBox(sf, text="Invert OLED Screen", variable=self.invert_var,
                                         fg_color="#4CAF50", hover_color="#388E3C", text_color="#FFFFFF", font=ctk.CTkFont(size=12))
        self.invert_cb.grid(row=3, column=2, columnspan=2, padx=10, pady=5, sticky="w")
        ToolTip(self.invert_cb, "Swap display background to white with black text")

        # Settings Row 4: Audio Source & Alert Hotword
        ctk.CTkLabel(sf, text="Audio Source:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.audio_var  = ctk.StringVar(value="Scanning...")
        self.audio_menu = ctk.CTkComboBox(sf, variable=self.audio_var, values=["Scanning..."],
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=6,
                                           fg_color="#121212", button_color="#1F1F1F", button_hover_color="#333333", text_color="#FFFFFF")
        self.audio_menu.grid(row=4, column=1, padx=10, pady=5, sticky="ew")
        ToolTip(self.audio_menu, "Select playback loopback interface to record PC sound")

        ctk.CTkLabel(sf, text="Alert Hotword:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=4, column=2, padx=10, pady=5, sticky="w")
        self.alert_var = ctk.StringVar(value=self.active_settings["alert"])
        self.alert_entry = ctk.CTkEntry(sf, textvariable=self.alert_var, fg_color="#121212", border_color="#444444", border_width=1, text_color="#FFFFFF", font=ctk.CTkFont(size=12))
        self.alert_entry.grid(row=4, column=3, padx=10, pady=5, sticky="ew")
        ToolTip(self.alert_entry, "Flash screen/invert colors momentarily if this exact word is spoken")

        # Settings Row 5: Serial Config & Welcome message
        serial_frame = ctk.CTkFrame(sf, fg_color="transparent")
        serial_frame.grid(row=5, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        
        ctk.CTkLabel(serial_frame, text="COM:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0,4))
        self.port_var  = ctk.StringVar(value="None")
        self.port_menu = ctk.CTkComboBox(serial_frame, variable=self.port_var, values=["None"], width=100,
                                           command=self._connect_port,
                                           state="readonly", border_width=1, border_color="#444444", corner_radius=6,
                                           fg_color="#121212", button_color="#1F1F1F", button_hover_color="#333333", text_color="#FFFFFF")
        self.port_menu.pack(side="left", padx=4)
        ToolTip(self.port_menu, "Select serial USB port of your ESP32 board")
        
        self.auto_btn = ctk.CTkButton(serial_frame, text="AUTO CONNECT ↗", width=120, command=self._auto_connect_async,
                                      fg_color="#1E1E1E", hover_color="#2D2D2D", text_color="#FFFFFF",
                                      border_width=0, corner_radius=6,
                                      font=ctk.CTkFont(family="Consolas", size=11, weight="bold"))
        self.auto_btn.pack(side="left", padx=3)
        ToolTip(self.auto_btn, "Scan COM ports and handshake with ESP32 board automatically")
        
        self.refresh_btn = ctk.CTkButton(serial_frame, text="RE-SCAN ↗", width=80, command=self._refresh_ports,
                                          fg_color="#1E1E1E", hover_color="#2D2D2D", text_color="#FFFFFF",
                                          border_width=0, corner_radius=6,
                                          font=ctk.CTkFont(family="Consolas", size=11, weight="bold"))
        self.refresh_btn.pack(side="left", padx=3)
        ToolTip(self.refresh_btn, "Re-scan serial COM ports")

        ctk.CTkLabel(sf, text="Welcome Msg:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=5, column=2, padx=10, pady=5, sticky="w")
        self.welcome_var = ctk.StringVar(value=self.active_settings["welcome"])
        self.welcome_entry = ctk.CTkEntry(sf, textvariable=self.welcome_var, fg_color="#121212", border_color="#444444", border_width=1, text_color="#FFFFFF", font=ctk.CTkFont(size=12))
        self.welcome_entry.grid(row=5, column=3, padx=10, pady=5, sticky="ew")
        ToolTip(self.welcome_entry, "Text rendered on OLED when captioning is idle")

        # Settings Row 6: Text Offset Position Tuning
        ctk.CTkLabel(sf, text="Nudge Text:", text_color="#FFFFFF", font=ctk.CTkFont(size=12)).grid(row=6, column=0, padx=10, pady=(15,5), sticky="nw")
        
        offset_frame = ctk.CTkFrame(sf, fg_color="transparent")
        offset_frame.grid(row=6, column=1, columnspan=2, padx=10, pady=5, sticky="w")
        
        self.offset_x_var = tk.IntVar(value=self.active_settings.get("offset_x", 0))
        self.offset_y_var = tk.IntVar(value=self.active_settings.get("offset_y", 0))
        
        def adjust_offset(dx, dy):
            self.offset_x_var.set(self.offset_x_var.get() + dx)
            self.offset_y_var.set(self.offset_y_var.get() + dy)
            self.offset_val_lbl.configure(text=f"X: {self.offset_x_var.get()} | Y: {self.offset_y_var.get()}")
            self._check_pending_changes()
            
        def reset_offset():
            self.offset_x_var.set(0)
            self.offset_y_var.set(0)
            self.offset_val_lbl.configure(text="X: 0 | Y: 0")
            self._check_pending_changes()

        # Arrow buttons using our retro-brutalist outline style
        btn_style = {
            "fg_color": "#1E1E1E",
            "hover_color": "#2D2D2D",
            "text_color": "#FFFFFF",
            "border_width": 0,
            "corner_radius": 4,
            "width": 32,
            "height": 26,
            "font": ctk.CTkFont(family="Consolas", size=12, weight="bold")
        }
        
        # Grid-based D-pad layout for alignment
        up_btn = ctk.CTkButton(offset_frame, text="▲", command=lambda: adjust_offset(0, -1), **btn_style)
        up_btn.grid(row=0, column=1, padx=2, pady=2)
        ToolTip(up_btn, "Nudge text up (decrease Y offset)")

        left_btn = ctk.CTkButton(offset_frame, text="◄", command=lambda: adjust_offset(-1, 0), **btn_style)
        left_btn.grid(row=1, column=0, padx=2, pady=2)
        ToolTip(left_btn, "Nudge text left (decrease X offset)")
        
        reset_btn = ctk.CTkButton(offset_frame, text="RST", command=reset_offset,
                                   fg_color="#1E1E1E", hover_color="#2D2D2D", text_color="#FFFFFF",
                                   border_width=0, corner_radius=4,
                                   width=32, height=26, font=ctk.CTkFont(family="Consolas", size=9, weight="bold"))
        reset_btn.grid(row=1, column=1, padx=2, pady=2)
        ToolTip(reset_btn, "Reset offsets to X: 0, Y: 0")

        right_btn = ctk.CTkButton(offset_frame, text="►", command=lambda: adjust_offset(1, 0), **btn_style)
        right_btn.grid(row=1, column=2, padx=2, pady=2)
        ToolTip(right_btn, "Nudge text right (increase X offset)")

        down_btn = ctk.CTkButton(offset_frame, text="▼", command=lambda: adjust_offset(0, 1), **btn_style)
        down_btn.grid(row=2, column=1, padx=2, pady=2)
        ToolTip(down_btn, "Nudge text down (increase Y offset)")

        self.offset_val_lbl = ctk.CTkLabel(sf, text=f"X: {self.offset_x_var.get()} | Y: {self.offset_y_var.get()}",
                                            text_color="#FFFFFF", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"))
        self.offset_val_lbl.grid(row=6, column=3, padx=10, pady=(15,5), sticky="ne")

        # Settings Row 7: Apply Settings Button
        self.apply_btn = ctk.CTkButton(sf, text="SETTINGS APPLIED ✓", font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                                       height=38, fg_color="#1E1E1E", hover_color="#2D2D2D", text_color="#FFFFFF",
                                       border_width=0, corner_radius=6,
                                       command=self._apply_settings)
        self.apply_btn.grid(row=7, column=0, columnspan=4, padx=10, pady=(10,5), sticky="ew")
        ToolTip(self.apply_btn, "Commit and save all configuration edits to the preview and display")

        # Trace modifications to show unsaved settings warning
        self.model_var.trace_add("write", self._handle_model_change)
        self.lang_var.trace_add("write", self._handle_language_change)
        self.font_var.trace_add("write", self._check_pending_changes)
        self.mode_var.trace_add("write", self._check_pending_changes)
        self.align_var.trace_add("write", self._check_pending_changes)
        self.case_var.trace_add("write", self._check_pending_changes)
        self.invert_var.trace_add("write", self._check_pending_changes)
        self.alert_var.trace_add("write", self._check_pending_changes)
        self.welcome_var.trace_add("write", self._check_pending_changes)

        # Bottom row: Status Bar
        sb = ctk.CTkFrame(self, fg_color="transparent")
        sb.pack(fill="x", padx=20, pady=(4,0))
        self.esp_lbl = ctk.CTkLabel(sb, text="● ESP not connected", text_color="#D32F2F", font=ctk.CTkFont(size=11))
        self.esp_lbl.pack(side="left")
        
        self.wpm_lbl = ctk.CTkLabel(sb, text="Speed: 0 WPM", text_color="#FF9800", font=ctk.CTkFont(size=11))
        self.wpm_lbl.pack(side="left", padx=(25,0))

        self.mdl_lbl = ctk.CTkLabel(sb, text="Model: not loaded", text_color="#888888", font=ctk.CTkFont(size=11))
        self.mdl_lbl.pack(side="right")

        # Start button (Taller & Larger Font)
        self.btn = ctk.CTkButton(self, text="START CAPTIONING ↗",
                                  font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
                                  height=50, corner_radius=8,
                                  fg_color="#1E1E1E", hover_color="#2D2D2D",
                                  text_color="#FFFFFF", border_width=0,
                                  command=self._toggle)
        self.btn.pack(pady=(12,8), padx=20, fill="x")

        ctk.CTkLabel(self, text="Model loading matches GPU or falls back to CPU automatically",
                     font=ctk.CTkFont(size=10), text_color="#555555").pack()

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
            self.offset_y_var.get() != self.active_settings.get("offset_y", 0)
        )
        if has_changes:
            self.apply_btn.configure(
                text="APPLY PENDING CHANGES ⚠",
                fg_color="#D84315",
                hover_color="#BF360C",
                text_color="#FFFFFF"
            )
        else:
            self.apply_btn.configure(
                text="SETTINGS APPLIED ✓",
                fg_color="#1E1E1E",
                hover_color="#2D2D2D",
                text_color="#FFFFFF"
            )

    def _apply_settings(self):
        model_changed = (self.model_var.get() != self.active_settings["model"] or
                         self.lang_var.get() != self.active_settings["language"])

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

        # Save configuration
        self.save_config()

        # Update physical display hardware configuration immediately
        self._handle_brightness(self.active_settings["brightness"])
        self._handle_inversion()

        # Reload transcription pipeline if Whisper configurations changed
        if self.running and model_changed:
            self._stop()
            self.after(600, self._start)

        self._check_pending_changes()

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

    def _handle_slider_change(self, val):
        self._check_pending_changes()

    def _handle_brightness(self, val):
        send_line(f"[BRIGHT:{int(val)}]")

    def _handle_inversion(self):
        val = 1 if self.active_settings["invert"] else 0
        send_line(f"[INVERT:{val}]")

    def _populate_devices(self):
        self.dev_map = {}
        names = []
        p = pyaudio.PyAudio()
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
            p.terminate()

        if not names:
            p = pyaudio.PyAudio()
            try:
                for i in range(p.get_device_count()):
                    dev = p.get_device_info_by_index(i)
                    if dev['maxInputChannels'] > 0:
                        label = f"{dev['name']} [{i}]"
                        names.append(label)
                        self.dev_map[label] = i
            finally:
                p.terminate()

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
            self.esp_lbl.configure(text="● Scanning COM ports...", text_color="#FF9800")
            port = auto_detect_esp32_port()
            if port:
                self.after(0, lambda: self._connect_to_port(port))
            else:
                self.after(0, lambda: self.esp_lbl.configure(
                    text="● ESP not found (Auto)", text_color="#D32F2F"))
        threading.Thread(target=scan, daemon=True).start()
        
    def _connect_to_port(self, port):
        self.port_var.set(port)
        self._connect_port(port)

    def _connect_port(self, choice):
        global serial_port
        if serial_port and serial_port.is_open:
            serial_port.close()
            serial_port = None
        
        self.active_settings["com_port"] = choice
        self.save_config()

        if choice == "None":
            self.esp_lbl.configure(text="● ESP not connected", text_color="#D32F2F")
            return
        try:
            serial_port = serial.Serial(choice, BAUD_RATE, timeout=0.5)
            self.esp_lbl.configure(text=f"● Connected {choice}", text_color="#4CAF50")
            # Sync settings immediately
            self.after(200, lambda: self._handle_brightness(self.active_settings["brightness"]))
            self.after(300, self._handle_inversion)
        except Exception as e:
            self.esp_lbl.configure(text=f"● Connection failed: {e}", text_color="#D32F2F")

    def _toggle(self):
        if not self.running: self._start()
        else:                self._stop()

    def _start(self):
        # Auto-apply all current settings on start
        self._apply_settings()

        self.running = True
        stop_event.clear()
        
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

        self.btn.configure(text="STOP CAPTIONING ↗", fg_color="#D32F2F", hover_color="#B71C1C", text_color="#FFFFFF")
        self.mdl_lbl.configure(text="Loading model...", text_color="#FF9800")
        self.update()

        self.last_speech_time = time.time()
        self.oled_cleared = False
        self.active_caption = ""
        self.word_timestamps = []

        def load():
            try:
                target_model_size = self.active_settings["model"]
                if self.model is None or self.loaded_model_size != target_model_size:
                    try:
                        self.mdl_lbl.configure(text=f"Loading {target_model_size} (GPU)...", text_color="#FF9800")
                        self.update()
                        self.model = WhisperModel(target_model_size, device="cuda", compute_type="float16")
                        self.model_on_gpu = True
                        self.loaded_model_size = target_model_size
                        self.after(0, lambda: self.mdl_lbl.configure(
                            text=f"{target_model_size} (GPU) ready ✓", text_color="#4CAF50"))
                    except Exception as gpu_err:
                        print(f"GPU load failed: {gpu_err}. Fallback to CPU...")
                        self.mdl_lbl.configure(text=f"Loading {target_model_size} (CPU)...", text_color="#FF9800")
                        self.update()
                        self.model = WhisperModel(target_model_size, device="cpu", compute_type="int8")
                        self.model_on_gpu = False
                        self.loaded_model_size = target_model_size
                        self.after(0, lambda: self.mdl_lbl.configure(
                            text=f"{target_model_size} (CPU) ready ✓", text_color="#4CAF50"))
                else:
                    device_str = "GPU" if self.model_on_gpu else "CPU"
                    self.after(0, lambda: self.mdl_lbl.configure(
                        text=f"{target_model_size} ({device_str}) ready ✓", text_color="#4CAF50"))

                dev = self.dev_map.get(self.audio_var.get())
                
                lang_code = self.lang_map[self.active_settings["language"]]
                vad_active = True
                task_str = "transcribe"
                
                threading.Thread(target=audio_thread_fn, args=(dev,), daemon=True).start()
                threading.Thread(target=stt_thread_fn, args=(self.model, lang_code, vad_active, task_str), daemon=True).start()
            except Exception as e:
                self.after(0, lambda: self.mdl_lbl.configure(text=f"Error: {e}", text_color="#D32F2F"))
                self.after(0, self._stop)

        threading.Thread(target=load, daemon=True).start()

    def _stop(self):
        self.running = False
        stop_event.set()
        self.btn.configure(text="START CAPTIONING ↗", fg_color="#1E1E1E", hover_color="#2D2D2D", text_color="#FFFFFF")
        self.mdl_lbl.configure(text="Stopped", text_color="#888888")
        self.active_caption = ""

    def _poll(self):
        global current_volume
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

        if self.running and not self.oled_cleared and (now - self.last_speech_time > 3.0):
            self.active_caption = ""
            self.oled_cleared = True

        # Render current frame
        self.wave_phase = (self.wave_phase + 0.15) % (2 * math.pi)

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
        if self.running:
            if preview_mode == "Word by Word":
                txt_gui = self.history[-1] if self.history else ""
            else:
                txt_gui = self.active_caption
                
            if txt_gui.strip() == "":
                img_gui = render_silence_wave(self.wave_phase, current_volume)
            else:
                img_gui = wrap_text_to_image(
                    txt_gui,
                    preview_font,
                    24,  # Always use 24pt for ultra-readable layout
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
                24,  # Always use 24pt
                preview_align,
                preview_case,
                has_shadow=True,
                vu_volume=0.0,
                offset_x=preview_offset_x,
                offset_y=preview_offset_y
            )

        # --- 2. RENDER SERIAL STREAM IMAGE (Using Active Settings) ---
        if self.running:
            if active_mode == "Word by Word":
                txt_serial = self.history[-1] if self.history else ""
            else:
                txt_serial = self.active_caption
                
            if txt_serial.strip() == "":
                img_serial = render_silence_wave(self.wave_phase, current_volume)
            else:
                img_serial = wrap_text_to_image(
                    txt_serial,
                    active_font,
                    24,  # Always use 24pt
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
                24,  # Always use 24pt
                active_align,
                active_case,
                has_shadow=True,
                vu_volume=0.0,
                offset_x=active_offset_x,
                offset_y=active_offset_y
            )

        # Convert and style the preview image to match physical parameters
        img_preview = img_gui.resize((384, 192), Image.NEAREST).convert("RGB")
        
        # Apply Inversion
        if preview_invert:
            img_preview = ImageOps.invert(img_preview)
            
        # Apply Brightness / Contrast dimming
        brightness_factor = preview_bright / 255.0
        brightness_factor = max(0.05, brightness_factor)  # Outline remains visible
        enhancer = ImageEnhance.Brightness(img_preview)
        img_preview = enhancer.enhance(brightness_factor)

        self.ctk_img = ctk.CTkImage(light_image=img_preview, dark_image=img_preview, size=(384, 192))
        self.preview_label.configure(image=self.ctk_img, text="")

        # Stream raw bytes of the active running layout to ESP32 serial port
        raw_bytes = img_serial.tobytes()
        hex_data = raw_bytes.hex()
        send_line(hex_data)

        self.after(80, self._poll)


if __name__ == "__main__":
    app = App()
    app.mainloop()
    stop_event.set()

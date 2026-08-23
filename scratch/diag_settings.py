"""Quick test: simulate AppEngine init + get_settings to verify first-launch behavior."""
import os, sys, json
sys.stdout.reconfigure(encoding='utf-8')

# Add project to path
sys.path.insert(0, os.getcwd())

# Simulate the config path
appdata = os.environ.get("APPDATA", "")
config_path = os.path.join(appdata, "CaptorCore", "config.json")

print("=== Step 1: Read saved config ===")
with open(config_path, "r", encoding="utf-8") as f:
    saved = json.load(f)
print(json.dumps(saved, indent=2))

print("\n=== Step 2: Simulate active_settings defaults ===")
active_settings = {
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
    "stats_gpu": True
}

print("\n=== Step 3: Merge saved config into defaults ===")
for k, v in saved.items():
    if k in active_settings:
        active_settings[k] = v

print(f"audio_source after merge: '{active_settings['audio_source']}'")
print(f"font after merge: '{active_settings['font']}'")
print(f"mode after merge: '{active_settings['mode']}'")
print(f"com_port after merge: '{active_settings['com_port']}'")

print("\n=== Step 4: Simulate get_settings() response ===")
s = active_settings
response = {
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
print(json.dumps(response, indent=2))

print("\n=== Step 5: Check what React would do with these values ===")
# Simulate React's initApp logic
s2 = response
alignment = s2.get("alignment", "center")
if alignment:
    alignment = alignment[0].upper() + alignment[1:]
print(f"React alignment: '{alignment}'")
print(f"React audioSource: '{s2.get('audio_source', '')}'")
print(f"React oledFont: '{s2.get('oled_font', 'Vin Mono Pro (Regular)')}'")
print(f"React displayMode: '{s2.get('display_mode', 'Word by Word')}'")

print("\n=== ALL OK ===")

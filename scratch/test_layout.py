import os
import sys
from PIL import Image, ImageDraw, ImageFont

# ── font registration ─────────────────────────────────────────────────────────
FONT_MAP = {
    "Vin Mono Pro (Regular)": "fonts/vin-mono-pro-font-family/VinMonoPro-Regular.ttf",
    "Vin Mono Pro (Bold)": "fonts/vin-mono-pro-font-family/VinMonoPro-Bold.ttf",
    "Vin Mono Pro (Thin)": "fonts/vin-mono-pro-font-family/VinMonoPro-Thin.ttf"
}

def get_font(font_name, font_size):
    try:
        font_file = FONT_MAP.get(font_name, font_name)
        if os.path.exists(font_file):
            return ImageFont.truetype(font_file, font_size)
    except Exception:
        pass
    return ImageFont.load_default()

def render_layout():
    # Create black 128x64 image
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)

    # Sample stats
    cpu_name = "Ryzen 5 3600"
    cpu_mhz = "3600"
    cpu_util = "45%"
    
    gpu_name = "RTX 5070"
    gpu_temp = "51°C"
    gpu_core = "2707"
    gpu_mem = "14001"
    gpu_util = "9%"

    # Load fonts
    font_reg_9 = get_font("Vin Mono Pro (Regular)", 9)
    font_bold_9 = get_font("Vin Mono Pro (Bold)", 9)
    font_bold_10 = get_font("Vin Mono Pro (Bold)", 10)
    font_bold_18 = get_font("Vin Mono Pro (Bold)", 18)
    font_thin_9 = get_font("Vin Mono Pro (Thin)", 9)

    # --- Draw CPU Section ---
    # Row 0: CPU Name (Top Left)
    draw.text((2, 0), cpu_name, font=font_bold_9, fill=1)

    # Row 1: CPU block
    draw.text((2, 10), "CPU", font=font_bold_18, fill=1)
    draw.text((38, 10), cpu_mhz, font=font_bold_18, fill=1)
    draw.text((82, 10), "MHz", font=font_thin_9, fill=1)
    draw.text((102, 18), cpu_util, font=font_bold_9, fill=1)

    # --- Draw GPU Section ---
    # Row 2: GPU Name
    draw.text((2, 30), gpu_name, font=font_bold_9, fill=1)

    # Row 3: GPU Details
    draw.text((2, 40), "GPU", font=font_bold_18, fill=1)
    draw.text((2, 55), gpu_temp, font=font_reg_9, fill=1)

    draw.text((45, 40), f"Core:{gpu_core}MHz", font=font_reg_9, fill=1)
    draw.text((45, 48), f"Mem :{gpu_mem}MHz", font=font_reg_9, fill=1)
    draw.text((45, 56), f"Util:{gpu_util}", font=font_reg_9, fill=1)

    # Save output
    img_preview = img.resize((384, 192), Image.NEAREST).convert("RGB")
    img_preview.save("refs/test_resource_ui_rendered_2.png")
    print("Rendered successfully to refs/test_resource_ui_rendered_2.png")

if __name__ == "__main__":
    render_layout()

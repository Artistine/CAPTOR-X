import os
import numpy as np
from PIL import Image, ImageDraw

def overlay_rectangles():
    crop_path = 'C:/Users/sushi/.gemini/antigravity/brain/d7ce2f0a-ec88-44c3-a3da-20c29559f129/active_screen_crop_test.png'
    output_path = 'C:/Users/sushi/.gemini/antigravity/brain/d7ce2f0a-ec88-44c3-a3da-20c29559f129/rectangles_overlay.png'
    
    if not os.path.exists(crop_path):
        print("Crop image not found")
        return
        
    img = Image.open(crop_path).convert('RGB')
    draw = ImageDraw.Draw(img)
    
    # We want to find the inner display rectangle where the OLED screen is active.
    # Looking at the image, the outer glass bezel is 769x516 (which is 384x258 at @1x).
    # The inner OLED display should have size 256x128 in @2x (which is 128x64 at @1x).
    # Wait, let's verify if the aspect ratio is exactly 2:1 (128x64).
    # If the active display is 256x128 at @2x (which is 128x64 at @1x):
    # Wait! The active screen display on the Captor X is 128x64.
    # So in @2x, the active screen should be 256x128?
    # Or is it larger?
    # Let's check: the width of the crop is 769px. The height is 516px.
    # In the mockup, the display is scaled! The image is scaled by 0.6830.
    # The original image is 2752x1536.
    # If the active OLED screen on the device is 128x64 pixels physically,
    # then in the image, it has some pixel size.
    # Let's draw some candidate rectangles.
    # Since the active display is a 2:1 aspect ratio, let's draw rectangles with 2:1 aspect ratio.
    # Candidate 1: centered in the left part of the crop.
    # The left bezel is at x=0. The right bezel ends before the fingers (say, around x=600).
    # So the glass screen center is around x=300, y=258.
    # Let's draw several rectangles centered at (300, 258) with different widths:
    # Widths: 300, 350, 400, 450, 500, 550
    # Heights: 150, 175, 200, 225, 250, 275
    
    colors = ["red", "green", "blue", "yellow", "cyan", "magenta", "orange"]
    widths = [350, 400, 450, 500, 550]
    
    # Let's draw them
    for i, w in enumerate(widths):
        h = w // 2 # 2:1 aspect ratio
        x0 = 300 - w // 2
        y0 = 258 - h // 2
        x1 = 300 + w // 2
        y1 = 258 + h // 2
        draw.rectangle([x0, y0, x1, y1], outline=colors[i % len(colors)], width=2)
        draw.text((x0 + 5, y0 + 5), f"W:{w} H:{h}", fill=colors[i % len(colors)])
        
    img.save(output_path)
    print(f"Overlay image saved to: {output_path}")

if __name__ == '__main__':
    overlay_rectangles()

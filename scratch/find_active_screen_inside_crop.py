import os
import numpy as np
from PIL import Image

def find_active_screen():
    crop_path = 'C:/Users/sushi/.gemini/antigravity/brain/d7ce2f0a-ec88-44c3-a3da-20c29559f129/screen_crop_test.png'
    if not os.path.exists(crop_path):
        print("Crop image not found")
        return
        
    img = Image.open(crop_path).convert('RGB')
    width, height = img.size
    print(f"Crop size: {width}x{height}")
    
    # The active screen is the dark inner region.
    # Let's inspect a horizontal line at y = height // 2 to find the transitions
    # from the bezel (which is lighter) to the screen (which is darker).
    y = height // 2
    row = [img.getpixel((x, y)) for x in range(width)]
    # Print some pixel values to see
    print("Row pixel colors (R,G,B) at y =", y)
    # Let's find where the active black screen is.
    # The active screen is completely black #000000 or very close (e.g. RGB < 10, 10, 10)
    black_pixels = []
    for cy in range(height):
        for cx in range(width):
            r, g, b = img.getpixel((cx, cy))
            if r <= 15 and g <= 15 and b <= 15:
                # The finger or device body might also be dark, but they are on the right/bezel.
                # The screen is on the left side of the crop.
                # Let's restrict search to cx < width * 0.7 (left 70% of the crop)
                # and cy between 10% and 90% of height.
                if cx < width * 0.75 and cy > height * 0.05 and cy < height * 0.95:
                    black_pixels.append((cx, cy))
                    
    if not black_pixels:
        print("No dark pixels found in active area")
        return
        
    xs = [p[0] for p in black_pixels]
    ys = [p[1] for p in black_pixels]
    
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    print(f"Active screen relative to crop (@2x):")
    print(f"X: {min_x} to {max_x} (width: {max_x - min_x})")
    print(f"Y: {min_y} to {max_y} (height: {max_y - min_y})")
    print(f"In @1x coordinates (relative to crop):")
    print(f"X: {min_x/2} to {max_x/2} (width: {(max_x - min_x)/2})")
    print(f"Y: {min_y/2} to {max_y/2} (height: {(max_y - min_y)/2})")

if __name__ == '__main__':
    find_active_screen()

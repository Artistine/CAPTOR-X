import os
from PIL import Image

def find_green_bounds():
    img_path = 'UI/MOCKUP/AI REALTIME CAPTIONS PAGE.png'
    if not os.path.exists(img_path):
        print("Mockup not found")
        return
    
    img = Image.open(img_path)
    width, height = img.size
    print(f"Mockup size: {width}x{height}")
    
    # Let's search for green pixels
    # Active Highlight Green: #11FF00 (approx R=17, G=255, B=0)
    # Let's look for pixels with high green value and low red/blue
    green_pixels = []
    
    for y in range(height):
        for x in range(width):
            r, g, b, *a = img.getpixel((x, y))
            # Check if it looks like the active green color
            if g > 200 and r < 100 and b < 100:
                green_pixels.append((x, y))
                
    if not green_pixels:
        print("No green pixels found")
        return
        
    xs = [p[0] for p in green_pixels]
    ys = [p[1] for p in green_pixels]
    
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    print(f"Green pixels bounds: X: {min_x} to {max_x}, Y: {min_y} to {max_y}")
    print(f"Width: {max_x - min_x}, Height: {max_y - min_y}")
    
    # Also let's print the bounding box of the top card (which should be #181818 or R=24, G=24, B=24)
    # The top card starts from x=80 (40px in @2x) and y=200 (100px in @2x)
    # Let's verify the colors at some positions.

if __name__ == '__main__':
    find_green_bounds()

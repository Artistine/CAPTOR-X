import os
from PIL import Image

def find_black_screen():
    img_path = 'UI/MOCKUP/AI REALTIME CAPTIONS PAGE.png'
    if not os.path.exists(img_path):
        print("Mockup not found")
        return
    
    img = Image.open(img_path)
    width, height = img.size
    
    # We want to search for the OLED display area in the top card.
    # The top card is roughly at y: 200 to 1320 (in @2x coordinates).
    # The device mockup is centered.
    # Let's count the frequency of colors or find the block of black pixels.
    # The OLED display has background #000000.
    # Let's find all pixels in the top card that are exactly (0, 0, 0).
    black_pixels = []
    for y in range(200, 1100):
        for x in range(400, 2400):
            p = img.getpixel((x, y))
            r, g, b = p[:3]
            # Since the screen is black, look for exact (0, 0, 0)
            if r == 0 and g == 0 and b == 0:
                black_pixels.append((x, y))
                
    if not black_pixels:
        print("No black pixels found")
        return
        
    # Let's find clusters or the main rectangle.
    # The OLED screen is a single contiguous rectangle.
    # Let's filter out outliers and find the min/max coordinates of the main rectangle.
    # Let's sort the pixels and find the most dense range.
    xs = sorted([p[0] for p in black_pixels])
    ys = sorted([p[1] for p in black_pixels])
    
    # Let's find the bounding box of the middle 98% to ignore single pixel outliers
    def get_percentile_range(lst, low=0.01, high=0.99):
        n = len(lst)
        return lst[int(n * low)], lst[int(n * high)]
        
    min_x, max_x = get_percentile_range(xs)
    min_y, max_y = get_percentile_range(ys)
    
    print(f"Detected OLED screen bounds in mockup (@2x):")
    print(f"X: {min_x} to {max_x} (width: {max_x - min_x})")
    print(f"Y: {min_y} to {max_y} (height: {max_y - min_y})")
    print(f"In @1x coordinates (divide by 2):")
    print(f"X: {min_x/2} to {max_x/2} (width: {(max_x - min_x)/2})")
    print(f"Y: {min_y/2} to {max_y/2} (height: {(max_y - min_y)/2})")

if __name__ == '__main__':
    find_black_screen()

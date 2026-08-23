import os
import numpy as np
from PIL import Image

def find_scale_and_pos():
    mockup_path = 'UI/MOCKUP/AI REALTIME CAPTIONS PAGE.png'
    device_path = 'gui/assets/Device Hand.png'
    
    if not os.path.exists(mockup_path) or not os.path.exists(device_path):
        print("Files not found")
        return
        
    mockup = Image.open(mockup_path).convert('RGB')
    device = Image.open(device_path) # Has alpha channel
    
    # We want to match the device (transparency) placed on #181818 background
    # against the mockup top card region.
    # The top card starts at y=200, ends at y=1320 (height 1120), x=80 to x=2800 (width 2720) in @2x.
    # Let's crop the top card region from the mockup.
    top_card = mockup.crop((80, 200, 2800, 1320))
    tc_w, tc_h = top_card.size
    
    # Let's analyze Device Hand.png
    dev_w, dev_h = device.size
    print(f"Device Hand size: {dev_w}x{dev_h}")
    
    # In the HTML/CSS, the device image height is 420px (840px in @2x).
    # Let's see if the mockup has the device at a specific height.
    # Let's try different heights for the device, resize it, composite it on #181818 background,
    # and find which height and position minimizes the difference with the mockup.
    
    # Let's do a fast search.
    # We can downsample both to speed up search.
    # But wait, is there an alpha channel?
    # Let's extract the RGB of the device on #181818 background:
    bg_color = (24, 24, 24)
    
    # Let's find the bounding box of the non-transparent pixels in Device Hand.png
    alpha = np.array(device.split()[-1])
    opaque_mask = alpha > 0
    ys, xs = np.where(opaque_mask)
    dev_min_x, dev_max_x = xs.min(), xs.max()
    dev_min_y, dev_max_y = ys.min(), ys.max()
    print(f"Opaque bounds in Device Hand.png: X: {dev_min_x} to {dev_max_x}, Y: {dev_min_y} to {dev_max_y}")
    
    # Let's find the bounding box of non-#181818 pixels in the top card region of the mockup.
    tc_arr = np.array(top_card)
    diff = np.abs(tc_arr - np.array(bg_color, dtype=np.uint8))
    # If any channel diff > 5, it's part of the device/status
    non_bg = np.any(diff > 5, axis=2)
    
    # Ignore the top status line (y < 100 in top card coordinates) and bottom/left pills
    # Let's crop to y: 100 to 1020, x: 200 to 2500
    non_bg_cropped = non_bg[100:1020, 200:2500]
    ys_tc, xs_tc = np.where(non_bg_cropped)
    if len(ys_tc) > 0:
        tc_min_x, tc_max_x = xs_tc.min() + 200, xs_tc.max() + 200
        tc_min_y, tc_max_y = ys_tc.min() + 100, ys_tc.max() + 100
        print(f"Opaque bounds in Mockup Top Card: X: {tc_min_x} to {tc_max_x}, Y: {tc_min_y} to {tc_max_y}")
        
        # Calculate scale:
        scale_x = (tc_max_x - tc_min_x) / (dev_max_x - dev_min_x)
        scale_y = (tc_max_y - tc_min_y) / (dev_max_y - dev_min_y)
        print(f"Calculated scale from bounds: X: {scale_x:.4f}, Y: {scale_y:.4f}")
        
        # Let's find the exact width and height of the image in @2x:
        mockup_img_w = dev_w * scale_x
        mockup_img_h = dev_h * scale_y
        print(f"Mockup image size in @2x: {mockup_img_w:.1f} x {mockup_img_h:.1f}")
        print(f"Mockup image size in @1x: {mockup_img_w/2:.1f} x {mockup_img_h/2:.1f}")
        
        # Position in top card:
        # The top-left of the image relative to the top card:
        # tc_min_x matches dev_min_x * scale_x + image_left
        img_left = tc_min_x - dev_min_x * scale_x
        img_top = tc_min_y - dev_min_y * scale_y
        print(f"Mockup image top-left in Top Card (@2x): left: {img_left:.1f}, top: {img_top:.1f}")
        print(f"Mockup image top-left in Top Card (@1x): left: {img_left/2:.1f}, top: {img_top/2:.1f}")

if __name__ == '__main__':
    find_scale_and_pos()

import os
import numpy as np
from PIL import Image

def match_precision():
    mockup_path = 'UI/MOCKUP/AI REALTIME CAPTIONS PAGE.png'
    device_path = 'gui/assets/Device Hand.png'
    
    if not os.path.exists(mockup_path) or not os.path.exists(device_path):
        print("Files not found")
        return
        
    mockup = Image.open(mockup_path).convert('RGB')
    device = Image.open(device_path) # RGBA
    
    # Crop top card (width 2720, height 1120 in @2x)
    # y = 200 to 1320, x = 80 to 2800
    top_card = mockup.crop((80, 200, 2800, 1320))
    tc_w, tc_h = top_card.size
    
    # Downsample for speed
    down_factor = 4
    tc_small = top_card.resize((tc_w // down_factor, tc_h // down_factor), Image.Resampling.BILINEAR)
    tc_small_arr = np.array(tc_small, dtype=np.float32)
    
    # Device image
    dev_w, dev_h = device.size
    
    # Let's search for the best scale factor s (aspect ratio preserved)
    # and offset (x, y) relative to top card
    best_mse = float('inf')
    best_s = 0
    best_ox = 0
    best_oy = 0
    
    # We will search scale from 0.3 to 1.2
    # In @2x, the top card height is 1120. The device image height is 1536.
    # If it is scaled to cover or fit, the scale factor s would be around 1120/1536 = 0.73
    # or if it's scaled such that the height is 420px at @1x (840px at @2x), s = 840/1536 = 0.547
    # Let's search s from 0.4 to 0.9 with step 0.01
    
    bg_color = np.array([24, 24, 24], dtype=np.float32)
    
    for s in np.arange(0.4, 0.9, 0.01):
        w_s = int(dev_w * s)
        h_s = int(dev_h * s)
        if w_s <= 0 or h_s <= 0:
            continue
            
        dev_resized = device.resize((w_s, h_s), Image.Resampling.BILINEAR)
        dev_arr = np.array(dev_resized, dtype=np.float32)
        dev_rgb = dev_arr[:, :, :3]
        dev_alpha = dev_arr[:, :, 3:4] / 255.0
        
        # Composite device on #181818 background
        # We want to match this composite inside the top card
        # The small versions:
        w_s_small = w_s // down_factor
        h_s_small = h_s // down_factor
        if w_s_small <= 0 or h_s_small <= 0:
            continue
            
        dev_small_resized = dev_resized.resize((w_s_small, h_s_small), Image.Resampling.BILINEAR)
        dev_small_arr = np.array(dev_small_resized, dtype=np.float32)
        dev_small_rgb = dev_small_arr[:, :, :3]
        dev_small_alpha = dev_small_arr[:, :, 3:4] / 255.0
        
        # We slide the resized device small over the top card small
        # Since the device can extend outside the top card, the offset (ox, oy) can be negative!
        # Search offset x from -w_s_small to tc_small.width
        # Search offset y from -h_s_small to tc_small.height
        # Let's restrict the search to reasonable offsets:
        # e.g., the device is centered in the card, so:
        # centered offset x = (tc_w_small - w_s_small) / 2
        # centered offset y = (tc_h_small - h_s_small) / 2
        # Let's search around that!
        cx = (tc_w // down_factor - w_s_small) // 2
        cy = (tc_h // down_factor - h_s_small) // 2
        
        for oy_s in range(cy - 50, cy + 50, 2):
            for ox_s in range(cx - 50, cx + 50, 2):
                # Composite the device onto a background card of tc_small size
                comp = np.ones_like(tc_small_arr) * bg_color
                
                # Bounding box of device in top card space
                y0_d = max(0, -oy_s)
                y1_d = min(h_s_small, tc_small.height - oy_s)
                x0_d = max(0, -ox_s)
                x1_d = min(w_s_small, tc_small.width - ox_s)
                
                if y0_d >= y1_d or x0_d >= x1_d:
                    continue
                    
                y0_c = oy_s + y0_d
                y1_c = oy_s + y1_d
                x0_c = ox_s + x0_d
                x1_c = ox_s + x1_d
                
                # Blend
                alpha_crop = dev_small_alpha[y0_d:y1_d, x0_d:x1_d]
                rgb_crop = dev_small_rgb[y0_d:y1_d, x0_d:x1_d]
                
                comp[y0_c:y1_c, x0_c:x1_c] = rgb_crop * alpha_crop + comp[y0_c:y1_c, x0_c:x1_c] * (1.0 - alpha_crop)
                
                # Compute MSE (ignore regions where buttons are, e.g. bottom 15% and sides)
                # Let's just crop to the middle region where the device hand is
                crop_y0 = int(tc_small.height * 0.1)
                crop_y1 = int(tc_small.height * 0.8)
                crop_x0 = int(tc_small.width * 0.1)
                crop_x1 = int(tc_small.width * 0.9)
                
                mse = np.mean((comp[crop_y0:crop_y1, crop_x0:crop_x1] - tc_small_arr[crop_y0:crop_y1, crop_x0:crop_x1]) ** 2)
                if mse < best_mse:
                    best_mse = mse
                    best_s = s
                    best_ox = ox_s * down_factor
                    best_oy = oy_s * down_factor
                    
    print(f"Best Match:")
    print(f"Scale factor s: {best_s:.3f}")
    print(f"Offset X (@2x): {best_ox} (offset X @1x: {best_ox/2})")
    print(f"Offset Y (@2x): {best_oy} (offset Y @1x: {best_oy/2})")
    print(f"Device width in @2x: {dev_w * best_s:.1f} (width @1x: {dev_w * best_s / 2:.1f})")
    print(f"Device height in @2x: {dev_h * best_s:.1f} (height @1x: {dev_h * best_s / 2:.1f})")
    print(f"MSE: {best_mse:.2f}")

if __name__ == '__main__':
    match_precision()

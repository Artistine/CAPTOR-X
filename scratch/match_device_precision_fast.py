import os
import numpy as np
from PIL import Image

def match_precision_fast():
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
    
    dev_w, dev_h = device.size
    
    bg_color = np.array([24, 24, 24], dtype=np.float32)
    
    # We will do coarse-to-fine search
    # Coarse search: down_factor = 8, scale step = 0.04, offset step = 4
    # Medium search: down_factor = 4, scale step = 0.01, offset step = 2
    # Fine search: down_factor = 2, scale step = 0.002, offset step = 1
    
    stages = [
        {"down": 8, "scale_range": np.arange(0.4, 0.9, 0.04), "offset_step": 4, "offset_radius": 40},
        {"down": 4, "scale_range": None, "offset_step": 2, "offset_radius": 12},
        {"down": 2, "scale_range": None, "offset_step": 1, "offset_radius": 4}
    ]
    
    best_s = 0.65  # initial guess
    best_ox = (tc_w - dev_w * best_s) // 2  # centered guess
    best_oy = (tc_h - dev_h * best_s) // 2
    
    for i, stage in enumerate(stages):
        down = stage["down"]
        offset_step = stage["offset_step"]
        offset_radius = stage["offset_radius"]
        
        tc_small = top_card.resize((tc_w // down, tc_h // down), Image.Resampling.BILINEAR)
        tc_small_arr = np.array(tc_small, dtype=np.float32)
        
        # Determine scale range for this stage
        if stage["scale_range"] is not None:
            scale_range = stage["scale_range"]
        else:
            # Search around the best scale from previous stage
            scale_range = np.arange(best_s - 0.03, best_s + 0.03, 0.005 if i == 1 else 0.002)
            
        best_stage_mse = float('inf')
        stage_best_s = best_s
        stage_best_ox = best_ox
        stage_best_oy = best_oy
        
        for s in scale_range:
            w_s = int(dev_w * s)
            h_s = int(dev_h * s)
            w_s_small = w_s // down
            h_s_small = h_s // down
            
            if w_s_small <= 0 or h_s_small <= 0:
                continue
                
            dev_resized = device.resize((w_s_small, h_s_small), Image.Resampling.BILINEAR)
            dev_arr = np.array(dev_resized, dtype=np.float32)
            dev_rgb = dev_arr[:, :, :3]
            dev_alpha = dev_arr[:, :, 3:4] / 255.0
            
            # Search offsets in range around best_ox, best_oy
            ox_center_small = int(best_ox // down)
            oy_center_small = int(best_oy // down)
            rad_small = int(offset_radius // down)
            
            x_search = range(ox_center_small - rad_small, ox_center_small + rad_small + 1, max(1, offset_step // down))
            y_search = range(oy_center_small - rad_small, oy_center_small + rad_small + 1, max(1, offset_step // down))
            
            for oy_s in y_search:
                for ox_s in x_search:
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
                    comp = np.ones_like(tc_small_arr) * bg_color
                    alpha_crop = dev_alpha[y0_d:y1_d, x0_d:x1_d]
                    rgb_crop = dev_rgb[y0_d:y1_d, x0_d:x1_d]
                    comp[y0_c:y1_c, x0_c:x1_c] = rgb_crop * alpha_crop + comp[y0_c:y1_c, x0_c:x1_c] * (1.0 - alpha_crop)
                    
                    # Compute MSE on crop
                    crop_y0 = int(tc_small.height * 0.1)
                    crop_y1 = int(tc_small.height * 0.8)
                    crop_x0 = int(tc_small.width * 0.1)
                    crop_x1 = int(tc_small.width * 0.9)
                    
                    mse = np.mean((comp[crop_y0:crop_y1, crop_x0:crop_x1] - tc_small_arr[crop_y0:crop_y1, crop_x0:crop_x1]) ** 2)
                    if mse < best_stage_mse:
                        best_stage_mse = mse
                        stage_best_s = s
                        stage_best_ox = ox_s * down
                        stage_best_oy = oy_s * down
                        
        best_s = stage_best_s
        best_ox = stage_best_ox
        best_oy = stage_best_oy
        print(f"Stage {i+1} (down={down}) complete. Best scale: {best_s:.4f}, offset: ({best_ox}, {best_oy}) with MSE: {best_stage_mse:.2f}")

    print("\n=== FINAL RESULT ===")
    print(f"Scale factor s: {best_s:.4f}")
    print(f"Offset X (@2x): {best_ox} (offset X @1x: {best_ox/2:.1f}px)")
    print(f"Offset Y (@2x): {best_oy} (offset Y @1x: {best_oy/2:.1f}px)")
    print(f"Device width in @2x: {dev_w * best_s:.1f} (width @1x: {dev_w * best_s / 2:.1f}px)")
    print(f"Device height in @2x: {dev_h * best_s:.1f} (height @1x: {dev_h * best_s / 2:.1f}px)")

if __name__ == '__main__':
    match_precision_fast()

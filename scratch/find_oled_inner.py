import os
import numpy as np
from PIL import Image

def find_inner_oled():
    crop_path = 'C:/Users/sushi/.gemini/antigravity/brain/d7ce2f0a-ec88-44c3-a3da-20c29559f129/active_screen_crop_test.png'
    if not os.path.exists(crop_path):
        print("Active crop image not found")
        return
        
    img = Image.open(crop_path).convert('L') # Convert to grayscale
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape
    print(f"Active crop size: {w}x{h}")
    
    # Sum horizontally to find vertical edges (y coordinates)
    # Sum vertically to find horizontal edges (x coordinates)
    # The active OLED screen is the darkest part in the middle.
    # So the profile will drop in the active screen region.
    # Let's print the average pixel values for each row and column.
    
    row_means = np.mean(arr, axis=1)
    col_means = np.mean(arr, axis=0)
    
    # Find active region by thresholding the means.
    # Bezel is lighter, screen is darker.
    # Let's find the threshold: the minimum pixel value in the center is very low.
    # Let's print the row values from top to bottom
    print("Row averages:")
    for y in range(0, h, 10):
        print(f"y={y}: {row_means[y]:.1f}")
        
    print("\nCol averages:")
    for x in range(0, w, 20):
        print(f"x={x}: {col_means[x]:.1f}")
        
    # Let's automatically find the range where row/col mean is less than a threshold.
    # We can use the center average as the baseline for the dark area
    center_val = np.mean(arr[h//3:2*h//3, w//3:2*w//3])
    print(f"\nCenter average (OLED active screen): {center_val:.2f}")
    
    # Find where it is within some tolerance of center_val
    tol = 5.0
    ys = np.where(row_means < center_val + tol)[0]
    xs = np.where(col_means < center_val + tol)[0]
    
    # We only care about the contiguous block in the middle
    active_y0, active_y1 = ys.min(), ys.max()
    active_x0, active_x1 = xs.min(), xs.max()
    
    print(f"\nDetected Active OLED bounds relative to active crop (@2x):")
    print(f"X: {active_x0} to {active_x1} (width: {active_x1 - active_x0})")
    print(f"Y: {active_y0} to {active_y1} (height: {active_y1 - active_y0})")
    print(f"In @1x:")
    print(f"X: {active_x0/2} to {active_x1/2} (width: {(active_x1 - active_x0)/2})")
    print(f"Y: {active_y0/2} to {active_y1/2} (height: {(active_y1 - active_y0)/2})")

if __name__ == '__main__':
    find_inner_oled()

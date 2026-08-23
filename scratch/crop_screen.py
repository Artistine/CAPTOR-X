import os
from PIL import Image

def crop_screen():
    mockup_path = 'UI/MOCKUP/AI REALTIME CAPTIONS PAGE.png'
    output_path = 'C:/Users/sushi/.gemini/antigravity/brain/d7ce2f0a-ec88-44c3-a3da-20c29559f129/screen_crop_test.png'
    
    if not os.path.exists(mockup_path):
        print("Mockup not found")
        return
        
    img = Image.open(mockup_path)
    # Crop the detected screen bounds
    crop_img = img.crop((917, 352, 1943, 926))
    crop_img.save(output_path)
    print(f"Cropped screen saved to: {output_path}")

if __name__ == '__main__':
    crop_screen()

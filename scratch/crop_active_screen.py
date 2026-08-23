import os
from PIL import Image

def crop_active():
    crop_path = 'C:/Users/sushi/.gemini/antigravity/brain/d7ce2f0a-ec88-44c3-a3da-20c29559f129/screen_crop_test.png'
    output_path = 'C:/Users/sushi/.gemini/antigravity/brain/d7ce2f0a-ec88-44c3-a3da-20c29559f129/active_screen_crop_test.png'
    
    if not os.path.exists(crop_path):
        print("Crop image not found")
        return
        
    img = Image.open(crop_path)
    # Crop the detected active bounds
    crop_img = img.crop((0, 29, 769, 545))
    crop_img.save(output_path)
    print(f"Active screen crop saved to: {output_path}")

if __name__ == '__main__':
    crop_active()

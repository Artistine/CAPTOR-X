I was using a .9 inch I2c oled display with ssd1306 driver...but I shifted to a waveshare 2.4 inch white oled.
you can find the related detail here:
 https://www.waveshare.com/wiki/2.42inch_OLED_Module 
 how ever as it is a different driver SSD1309 it wasn't working due to different address.
 if you see the code now there I defined the address 0x3D just to get it working...but some features are not working as brightness slider.
I just made the display to work only to check that new display is working or not...

as the 2.4 inch display is bit big...we can't take the text and overall UI and UX for granted...because in big display things gonna get more noticable...

so I want shift to U8G2 library...as it has pretty much what I need...and I want each animation smooth as possible....target frame is 60fps

it is hard to make you understand visually to put which things where, so I used lokaka to create Ui elements and converted it in U8g2 code...

this is the plan to overhaul the OLED UI & UX
first starting with 
1. music mode: In the UI/OLED UI folder you will see MUSIC MODE.cpp, the actual UI in code u8g2 format. there are few components, I will tell you only the thing needs to animated...
   
   aniamtion: wheel left and wheel right, circular rotation from individual center....
   
   action: previouly there was a sinewave, and we are replacing with this tape graphics...where whenever the audio gets played the wheel will start rotating...
   no audio no rotation....



1. Stats page: A rather complex implimentation logic...
   previouly we are just drawing things on the display with fewer option, and in big display it is not looking good. so I manually designed the Ui in lopaka and exported the code in U8G2 code...
   
   inside this chat page...we need to add a drop down that user can select which detail they want to see starting with:
   
CPU: the only things you need to map:
   - the numbers with the real values...
   - as I think you have to code the progress bar so there is also a progress bar head you need to attact it to the progress bar...
   - you will find 2 Ui mockups UI/OLED UI....cpu page max.cpp and cpu page min.cpp...the only thing is changed there is evilsmile1 and smile...we need to map these to mhz values...
     eg: 3200 mhz to 3900mhz = smile
     3900 mhz to 4200 mhz = evil smile 1

GPU : same concept as CPU:
   - you will find 2 Ui mockups UI/OLED UI....GPU page max.cpp and GPU page min.cpp...the only thing is changed there is evilsmile1 and smile...we need to map these to watt num values...
     eg: 35 to 70 watt = smile
     70 to 180 = evilsmile1
   - here I wanted to map the gpu watt with the Watt num element...it will show that how much power gpu is consuming....if it is tricky to fetch the raw hardware data we could fake it...by mapping the watt value with the GPU usage...1% usage 35 watt, 100% 180w it will go up down according to the gpu usage....

MEM and NETWORK : 
   - Again you just need to attach the number with the backend data...and the progress bar to the backend data....
   - there you will find a tx and rx icon...I want it to flash when incoming or outgoing data packet is transfering...

chunked implimentation cycle:
1. step 1: implimenting music mode....fix...repeat..until the desired result acieved..
2. step 2: implimenting music CPU page and making the dropdown....fix...repeat..until the desired result acieved..
3. step 3: implimenting music GPU page and adding it to the dropdown....fix...repeat..until the desired result acieved..
4. step 4: implimenting music MEM and NETWORK page and adding it to the dropdown....fix...repeat..until the desired result acieved..
   
   key things need to do first:
1. In our destop .py app there is a mockup captor x graphics where the preview display is attached...remove it and make the display big resambeling the 2.4 inch display...as this is temporary...when I will design the enclosure we will replace it with my designed captor x...
2. keep a backup of the original .py and rename with a version name that if I want to role back I can, on a perticular version...
3. the OLED ui's are designed with font haxcorp4089.bdf, profont29.bdf, profont22.bdf, profont10.bdf



as we are shifting in u8g2...
I want to replace the drop the selectable fonts in main CC page with these exact fonts...as these are optimized for the display....

### Final Selectable Fonts List (with Clean Dropdown Names)

The font dropdown list has been simplified to display only the user-friendly initials/short names, with `Vin Mono Pro (Thin)` acting as the default selection:

1. **Vin Mono Pro (Thin)** (Default Font) - Custom premium TrueType monospace font.
2. **Pixellari** (mapped from `u8g2_font_Pixellari_tf`)
3. **VCR OSD** (mapped from `u8g2_font_VCR_OSD_mr`)
4. **blipfest 07** (mapped from `u8g2_font_blipfest_07_tr`)
5. **bipixel double** (mapped from `u8g2_font_bpixeldouble_tr`)
6. **bpixel** (mapped from `u8g2_font_bpixel_tr`)
7. **bytesize** (mapped from `u8g2_font_bytesize_te`)
8. **cubemel** (mapped from `u8g2_font_cube_mel_tr`)
9. **doomalpha04** (mapped from `u8g2_font_doomalpha04_te`)
10. **freedoomr10** (mapped from `u8g2_font_freedoomr10_tu`)

> [!NOTE]
> The `fewture` font (`u8g2_font_fewture_tr`) has been completely removed from the selection options per design feedback.



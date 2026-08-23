#include <Arduino.h>
#include <Wire.h>
#include <U8g2lib.h>
#include "vin_mono_reels.h"

// ── display config ────────────────────────────────────────────────────────────
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
#define OLED_ADDRESS  0x7A  // 0x3D in 7-bit translates to 0x7A in 8-bit for U8g2

// Default I2C pins for ESP32-C3 SuperMini
#define I2C_SDA 8
#define I2C_SCL 9

// Momentary keyboard switch pin (Power Toggle)
#define SWITCH_PIN 3

// Momentary keyboard switch pin (Mode Cycle)
#define SWITCH_CYCLE_PIN 20

U8G2_SSD1309_128X64_NONAME0_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);

#define BAUD 460800

// ── global variables ─────────────────────────────────────────────────────────
uint8_t imgBuffer[1024];

// State variables
bool lastButtonState = HIGH;
bool lastCycleButtonState = HIGH;
bool screenPowerState = true; // Start turned ON
bool connected = false;
unsigned long lastDataTime = 0;
int animFrame = 0;
unsigned long lastAnimTime = 0;
unsigned long packetStartTime = 0;
unsigned long stop_complete_time = 0;

// Magic sync parsing state machine variables
enum ParseState {
  STATE_MAGIC_1, // Looking for 0xAA
  STATE_MAGIC_2, // Looking for 0x55
  STATE_MAGIC_3, // Looking for 0xAA
  STATE_MAGIC_4, // Looking for 0x55
  STATE_TYPE,    // Read Type
  STATE_LEN_HI,  // Read Length High
  STATE_LEN_LO,  // Read Length Low
  STATE_PAYLOAD  // Read Payload
};

ParseState pState = STATE_MAGIC_1;
uint8_t packetType = 0;
uint16_t packetLen = 0;
uint16_t payloadIdx = 0;
uint8_t payloadBuf[128]; // Buffer for string commands

// ── CAPTOR X Jackpot Roller Animation ─────────────────────────────────────────
#define ROLLER_COUNT 8
const char* const roller_chars[ROLLER_COUNT] = {
  "KDFGMXJYAC", // ends with C
  "WSNTNQPLHA", // ends with A
  "APFKCVWRHP", // ends with P
  "CHJPZUNMXT", // ends with T
  "KDFGMXJYBO", // ends with O
  "WSNTNQPLSR", // ends with R
  "APFKCVWRH ", // ends with  (space)
  "CHJPZUTMWX"  // ends with X
};

const int roller_char_len = 10;
const double H = 32.0; // Cell height per character
const double TotalH = roller_char_len * H; // 320.0
const double Y_CENTER = 32.0; // Y coordinate for centering the letter

double scroll_y[ROLLER_COUNT];
double speed[ROLLER_COUNT];
double max_speed[ROLLER_COUNT];
double acceleration[ROLLER_COUNT];
bool stopping[ROLLER_COUNT];
bool stopped[ROLLER_COUNT];

unsigned long stop_start_time = 0;
bool host_connecting = false;

void initRollers() {
  // Simple analog read on unused pin to seed random
  randomSeed(analogRead(0) + millis());
  for (int i = 0; i < ROLLER_COUNT; i++) {
    scroll_y[i] = random(0, (int)TotalH);
    speed[i] = 0.0;
    max_speed[i] = random(120, 200) / 10.0; // 12.0 to 20.0 pixels per frame
    acceleration[i] = random(2, 5) / 10.0;  // 0.2 to 0.5 acceleration
    stopping[i] = false;
    stopped[i] = false;
  }
  stop_start_time = 0;
  host_connecting = false;
  stop_complete_time = 0;
}

void updateRoller(int col, bool trigger_stop) {
  if (stopped[col]) {
    scroll_y[col] = 288.0;
    return;
  }

  double decel = 0.25;

  if (trigger_stop) {
    if (!stopping[col]) {
      // Calculate stopping distance (discrete time correction included)
      double stop_dist = 0.5 * speed[col] * speed[col] / decel - 0.5 * speed[col];
      
      double dist_to_target = 288.0 - scroll_y[col];
      while (dist_to_target < 0) dist_to_target += TotalH;

      double diff = dist_to_target - stop_dist;
      diff = fmod(diff, TotalH);
      if (diff < 0) diff += TotalH;

      if (diff < speed[col]) {
        // Shift position to align perfectly with the target deceleration path
        scroll_y[col] = 288.0 - stop_dist;
        scroll_y[col] = fmod(scroll_y[col], TotalH);
        if (scroll_y[col] < 0) scroll_y[col] += TotalH;
        stopping[col] = true;
      }
    }
  }

  if (stopping[col]) {
    speed[col] -= decel;
    if (speed[col] <= 0) {
      speed[col] = 0;
      scroll_y[col] = 288.0;
      stopped[col] = true;
    } else {
      scroll_y[col] += speed[col];
    }
  } else {
    // Normal rolling (ease-in or constant speed)
    if (speed[col] < max_speed[col]) {
      speed[col] += acceleration[col];
      if (speed[col] > max_speed[col]) speed[col] = max_speed[col];
    }
    scroll_y[col] += speed[col];
  }

  scroll_y[col] = fmod(scroll_y[col], TotalH);
  if (scroll_y[col] < 0) scroll_y[col] += TotalH;
}

void drawRollers() {
  u8g2.clearBuffer();

  for (int col = 0; col < ROLLER_COUNT; col++) {
    int col_center_x = 11 + col * 15;

    for (int i = 0; i < roller_char_len; i++) {
      double diff_y = (i * H) - scroll_y[col];
      diff_y = fmod(diff_y, TotalH);
      if (diff_y < -TotalH / 2) diff_y += TotalH;
      if (diff_y > TotalH / 2) diff_y -= TotalH;

      // Only draw characters on the front half, and dynamically narrow the window as the reels stop
      double max_draw_diff = 80.0;
      if (host_connecting) {
        max_draw_diff = 12.0 + speed[col] * 4.5;
      }
      if (abs(diff_y) <= max_draw_diff && abs(diff_y) <= 80.0) {
        double y_proj = Y_CENTER + diff_y;
        double diff = abs(y_proj - 32.0);

        int w, h;
        double draw_y;
        const unsigned char* bitmap_ptr = nullptr;
        char letter = roller_chars[col][i];
        int idx = letter - 'A';
        
        if (idx >= 0 && idx < 26) {
          if (diff <= 10.0) {
            w = vin_mono_w_L;
            h = vin_mono_h_L;
            draw_y = y_proj - (vin_mono_h_L / 2.0);
            bitmap_ptr = (const unsigned char*)pgm_read_ptr(&(vin_mono_font_map_L[idx]));
          } else if (diff <= 22.0) {
            w = vin_mono_w_M;
            h = vin_mono_h_M;
            draw_y = y_proj - (vin_mono_h_M / 2.0);
            bitmap_ptr = (const unsigned char*)pgm_read_ptr(&(vin_mono_font_map_M[idx]));
          } else {
            w = vin_mono_w_S;
            h = vin_mono_h_S;
            draw_y = y_proj - (vin_mono_h_S / 2.0);
            bitmap_ptr = (const unsigned char*)pgm_read_ptr(&(vin_mono_font_map_S[idx]));
          }
          
          if (draw_y >= -h && draw_y <= SCREEN_HEIGHT && bitmap_ptr != nullptr) {
            u8g2.drawXBMP(col_center_x - w / 2, (int)draw_y, w, h, bitmap_ptr);
          }
        }
      }
    }
  }

  u8g2.sendBuffer();
}

// ── helper: process complete packet payload ──────────────────────────────────
void processPacket() {
  if (packetType == 0x01) { // Binary Frame
    lastDataTime = millis();
    if (!connected) {
      if (!host_connecting) {
        host_connecting = true;
        stop_start_time = millis();
      }
    } else {
      if (screenPowerState) {
        u8g2.clearBuffer();
        u8g2.drawBitmap(0, 0, 16, 64, imgBuffer);
        u8g2.sendBuffer();
      }
    }
    Serial.println("[ACK]");
  }
  else if (packetType == 0x02) { // Command String
    String cmd = String((char*)payloadBuf);
    if (cmd == "PING") {
      Serial.println("[PONG]");
    }
    else if (cmd.startsWith("BRIGHT:")) {
      int idx = cmd.indexOf(':');
      if (idx != -1) {
        int val = cmd.substring(idx + 1).toInt();
        if (val >= 0 && val <= 255) {
          if (val == 0) {
            u8g2.setPowerSave(1);
          } else {
            u8g2.setPowerSave(0);
            u8g2.setContrast(val);
            // Dynamically scale VCOMH deselect level and pre-charge period to achieve true dimming to black
            if (val < 30) {
              u8g2.sendF("ca", 0xDB, 0x00); // Lowest VCOMH deselect level (dimmest)
              u8g2.sendF("ca", 0xD9, 0x11); // Lowest precharge period
            } else if (val < 100) {
              u8g2.sendF("ca", 0xDB, 0x20); // Medium VCOMH
              u8g2.sendF("ca", 0xD9, 0x22); // Medium precharge period
            } else {
              u8g2.sendF("ca", 0xDB, 0x40); // Maximum VCOMH (brightest)
              u8g2.sendF("ca", 0xD9, 0xF1); // High precharge to fix column banding
            }
          }
        }
      }
    }
    else if (cmd.startsWith("INVERT:")) {
      int idx = cmd.indexOf(':');
      if (idx != -1) {
        int val = cmd.substring(idx + 1).toInt();
        u8g2.sendF("c", val == 1 ? 0xA7 : 0xA6);
      }
    }
  }
}

// ── helper: handle incoming serial data with state machine ───────────────────
void handleSerial() {
  // Parser Watchdog: Reset state machine to STATE_MAGIC_1 if packet parsing takes too long (> 100ms)
  if (pState != STATE_MAGIC_1 && (millis() - packetStartTime > 100)) {
    pState = STATE_MAGIC_1;
  }

  while (Serial.available()) {
    uint8_t c = Serial.read();
    
    // Set start time when starting to parse a new packet
    if (pState == STATE_MAGIC_1 && c == 0xAA) {
      packetStartTime = millis();
    }
    
    switch (pState) {
      case STATE_MAGIC_1:
        if (c == 0xAA) pState = STATE_MAGIC_2;
        break;
      case STATE_MAGIC_2:
        if (c == 0x55) pState = STATE_MAGIC_3;
        else if (c == 0xAA) pState = STATE_MAGIC_2; // handle 0xAA, 0xAA, 0x55 sequence
        else pState = STATE_MAGIC_1;
        break;
      case STATE_MAGIC_3:
        if (c == 0xAA) pState = STATE_MAGIC_4;
        else pState = STATE_MAGIC_1;
        break;
      case STATE_MAGIC_4:
        if (c == 0x55) pState = STATE_TYPE;
        else if (c == 0xAA) pState = STATE_MAGIC_2; // handle 0xAA, 0x55, 0xAA, 0xAA, 0x55 sequence
        else pState = STATE_MAGIC_1;
        break;
      case STATE_TYPE:
        packetType = c;
        pState = STATE_LEN_HI;
        break;
      case STATE_LEN_HI:
        packetLen = ((uint16_t)c) << 8;
        pState = STATE_LEN_LO;
        break;
      case STATE_LEN_LO:
        packetLen |= c;
        payloadIdx = 0;
        if (packetLen == 0) {
          processPacket();
          pState = STATE_MAGIC_1;
        } else {
          pState = STATE_PAYLOAD;
        }
        break;
      case STATE_PAYLOAD:
        if (packetType == 0x01) { // Binary Frame
          if (payloadIdx < 1024) {
            imgBuffer[payloadIdx] = c;
          }
          payloadIdx++;
          if (payloadIdx >= packetLen || payloadIdx >= 1024) {
            processPacket();
            pState = STATE_MAGIC_1;
          }
        } else { // Command String
          if (payloadIdx < 127) {
            payloadBuf[payloadIdx] = c;
          }
          payloadIdx++;
          if (payloadIdx >= packetLen) {
            uint16_t termIdx = payloadIdx;
            if (termIdx > 127) termIdx = 127;
            payloadBuf[termIdx] = '\0';
            processPacket();
            pState = STATE_MAGIC_1;
          }
        }
        break;
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
void setup() {
  Serial.setRxBufferSize(4096);
  Serial.begin(BAUD);
  Serial.setTimeout(10); // 10ms timeout for readBytes

  // Configure mechanical button pin with internal pullup
  pinMode(SWITCH_PIN, INPUT_PULLUP);
  pinMode(SWITCH_CYCLE_PIN, INPUT_PULLUP);

  // Enable internal pullups on SDA/SCL explicitly before Wire.begin
  pinMode(I2C_SDA, INPUT_PULLUP);
  pinMode(I2C_SCL, INPUT_PULLUP);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000); // 400kHz fast mode I2C for stability

  #if defined(WIRE_HAS_TIMEOUT)
    Wire.setWireTimeout(25000, true); // 25ms timeout, auto-reset bus on timeout
  #else
    Wire.setTimeOut(25); // fallback for older cores
  #endif

  u8g2.setI2CAddress(OLED_ADDRESS);
  u8g2.begin();
  u8g2.clearBuffer();
  
  // Optimized SSD1309 register tuning: High pre-charge to fix column banding, and standard clock frequency for bright, stable display
  u8g2.sendF("ca", 0xD9, 0xF1); // Max Pre-charge Period (Phase 1 = 1 clock, Phase 2 = 15 clocks) to equalize columns
  u8g2.sendF("ca", 0xDB, 0x40); // High VCOMH Deselect Level to minimize row/column crosstalk
  u8g2.sendF("ca", 0xD5, 0x70); // Standard Display Clock Divide Ratio for stable, bright operation

  // Check switch state at startup
  screenPowerState = true; // Default to ON
  
  initRollers();
  drawRollers();
}

// ─────────────────────────────────────────────────────────────────────────────
void loop() {
  // 1. Process serial updates to keep buffer fresh
  handleSerial();

  // 2. Momentary Switch Toggle Logic (Edge Detection on GPIO 3 - Cycle Sub-Layouts)
  bool buttonState = digitalRead(SWITCH_PIN);
  if (buttonState == LOW && lastButtonState == HIGH) {
    delay(50); // Debounce press
    if (digitalRead(SWITCH_PIN) == LOW) {
      Serial.println("SUB");
      while (digitalRead(SWITCH_PIN) == LOW) {
        handleSerial();
      }
      delay(50); // Debounce release
    }
  }
  lastButtonState = buttonState;

  // Momentary Cycle Switch Toggle Logic (Simple debounced single click)
  bool cycleButtonState = digitalRead(SWITCH_CYCLE_PIN);
  if (cycleButtonState == LOW && lastCycleButtonState == HIGH) {
    delay(50); // Debounce press
    if (digitalRead(SWITCH_CYCLE_PIN) == LOW) {
      Serial.println("CYCLE");
      while (digitalRead(SWITCH_CYCLE_PIN) == LOW) {
        handleSerial();
      }
      delay(50); // Debounce release
    }
  }
  lastCycleButtonState = cycleButtonState;

  // 3. Connection Timeout Check
  if ((connected || host_connecting) && (millis() - lastDataTime > 2000)) {
    connected = false;
    initRollers();
  }

  // 4. Rendering CAPTOR X Jackpot Slot Reels if Disconnected/Connecting and Screen is ON
  if (!connected && screenPowerState) {
    unsigned long now = millis();
    
    // Smooth 40 FPS updates (every 25ms)
    static unsigned long last_frame_time = 0;
    if (now - last_frame_time >= 25) {
      last_frame_time = now;
      
      bool all_stopped = true;
      for (int i = 0; i < ROLLER_COUNT; i++) {
        // Trigger stop for roller i if host is connecting and stagger delay has elapsed
        bool trigger_stop_i = host_connecting && (now - stop_start_time >= (unsigned long)(i * 150));
        
        // Update roller i physics
        updateRoller(i, trigger_stop_i);
        
        if (!stopped[i]) {
          all_stopped = false;
        }
      }
      
      drawRollers();
      
      // If host is connecting and all rollers have stopped on "CAPTOR X"
      if (host_connecting && all_stopped) {
        if (stop_complete_time == 0) {
          stop_complete_time = now;
        }
        
        // Wait 800ms to show the "CAPTOR X" jackpot on screen before switching to host graphics
        if (now - stop_complete_time >= 800) {
          connected = true;
          host_connecting = false;
          stop_complete_time = 0;
          
          // Draw the latest host screen immediately
          if (screenPowerState) {
            u8g2.clearBuffer();
            u8g2.drawBitmap(0, 0, 16, 64, imgBuffer);
            u8g2.sendBuffer();
          }
        }
      }
    }
  }
}

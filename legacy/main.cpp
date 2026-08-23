#include <Arduino.h>
#include <Wire.h>
#include <U8g2lib.h>

// ── display config ────────────────────────────────────────────────────────────
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
#define OLED_ADDRESS  0x7A  // 0x3D in 7-bit translates to 0x7A in 8-bit for U8g2

// Default I2C pins for ESP32-C3 SuperMini
#define I2C_SDA 8
#define I2C_SCL 9

// Momentary keyboard switch pin
#define SWITCH_PIN 3

U8G2_SSD1309_128X64_NONAME0_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);

#define BAUD 460800

// ── global variables ─────────────────────────────────────────────────────────
uint8_t imgBuffer[1024];

// State variables
bool lastButtonState = HIGH;
bool screenPowerState = true; // Start turned ON
bool connected = false;
unsigned long lastDataTime = 0;
int animFrame = 0;
unsigned long lastAnimTime = 0;
unsigned long packetStartTime = 0;

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

// ── helper: draw loading animation ───────────────────────────────────────────
void drawLoadingAnimation(int frame) {
  u8g2.clearBuffer();
  int cx = SCREEN_WIDTH / 2;
  int cy = SCREEN_HEIGHT / 2;
  int r = 12;
  
  // Draw spinning dots (circular loading animation)
  for (int i = 0; i < 8; i++) {
    float angle = i * (2 * PI / 8) + (frame * 0.2);
    int x = cx + r * cos(angle);
    int y = cy + r * sin(angle);
    // Draw dots of different sizes to indicate movement
    u8g2.drawDisc(x, y, (i == 7) ? 3 : ((i > 4) ? 2 : 1));
  }
  
  u8g2.sendBuffer();
}

// ── helper: process complete packet payload ──────────────────────────────────
void processPacket() {
  if (packetType == 0x01) { // Binary Frame
    connected = true;
    lastDataTime = millis();
    if (screenPowerState) {
      u8g2.clearBuffer();
      u8g2.drawBitmap(0, 0, 16, 64, imgBuffer);
      u8g2.sendBuffer();
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
          u8g2.setContrast(val);
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
  
  // Render initial loading animation immediately
  drawLoadingAnimation(0);
}

// ─────────────────────────────────────────────────────────────────────────────
void loop() {
  // 1. Process serial updates to keep buffer fresh
  handleSerial();

  // 2. Momentary Switch Toggle Logic (Edge Detection)
  bool buttonState = digitalRead(SWITCH_PIN);
  if (buttonState == LOW && lastButtonState == HIGH) {
    delay(50); // Debounce press
    if (digitalRead(SWITCH_PIN) == LOW) {
      screenPowerState = !screenPowerState;
      
      if (screenPowerState) {
        u8g2.setPowerSave(0); // Display ON
        // Force immediate redraw of latest image buffer
        u8g2.clearBuffer();
        u8g2.drawBitmap(0, 0, 16, 64, imgBuffer);
        u8g2.sendBuffer();
      } else {
        u8g2.clearBuffer();
        u8g2.sendBuffer();
        u8g2.setPowerSave(1); // Display OFF
      }
      
      // Wait for release while continuing to parse serial bytes (prevent blockages)
      while (digitalRead(SWITCH_PIN) == LOW) {
        handleSerial();
      }
      delay(50); // Debounce release
    }
  }
  lastButtonState = buttonState;

  // 3. Connection Timeout Check
  if (connected && (millis() - lastDataTime > 2000)) {
    connected = false;
  }

  // 4. Rendering Local Loader if Disconnected and Screen is ON
  if (!connected && screenPowerState) {
    unsigned long now = millis();
    if (now - lastAnimTime >= 100) {
      lastAnimTime = now;
      animFrame++;
      drawLoadingAnimation(animFrame);
    }
  }
}

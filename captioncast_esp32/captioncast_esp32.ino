/*
  Captor Core — ESP32-C3 SuperMini firmware (Client display)
  SSD1309 I2C OLED (128x64)

  Wiring (I2C):
    OLED SDA → GPIO 8  (ESP32-C3 SDA)
    OLED SCL → GPIO 9  (ESP32-C3 SCL)
    OLED VCC → 3.3V
    OLED GND → GND

  Momentary Switch:
    Switch Pin 1 → GPIO 3
    Switch Pin 2 → GND

  Libraries needed (Arduino Library Manager):
    - U8g2 (by oliver)
*/

#include <Wire.h>
#include <U8g2lib.h>
// ── Captor OS boot log simulation ────────────────────────────────────────────
const char* const boot_messages[] PROGMEM = {
  "Booting Captor OS...",
  "CPU: ESP32-C3 @ 160MHz",
  "Core: RISC-V 32-bit",
  "Memory: 400KB SRAM",
  "Memory: 4MB Flash",
  "Crystal: 40MHz detected",
  "I2C: SDA=8 SCL=9 init",
  "OLED: SSD1309 (0x3C) found",
  "OLED: 128x64 pixels config",
  "OLED: Contrast 255 set",
  "FS: Mount SPIFFS...",
  "FS: Mount OK (1.2MB free)",
  "Config: Load config.json",
  "Config: Loaded successfully",
  "Serial: Baud 460800 set",
  "Serial: RX buffer 4KB ready",
  "UART0: Interrupts enabled",
  "WDT: Enabled (100ms)",
  "GPIO: Switch pin 3 pullup",
  "Audio: Downmix average ready",
  "VAD: Whisper VAD engine",
  "VAD: Silence timeout 3.0s",
  "Font: Vin Mono Pro loaded",
  "Font: Pixellari load OK",
  "Font: VCR OSD load OK",
  "Font: blipfest 07 load OK",
  "Font: bpixel load OK",
  "Font: cubemel load OK",
  "Font: doomalpha04 load OK",
  "Font: freedoomr10 load OK",
  "System: OK (up 0.5s)",
  "Network: Offline (no Wi-Fi)",
  "Bridge: UART0 listen...",
  "Bridge: Queue init OK",
  "System: Ready. Waiting host..."
};
const int boot_msg_count = 35;

// ── display config ────────────────────────────────────────────────────────────
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT  64
#define OLED_ADDRESS  0x78  // 0x3C in 7-bit translates to 0x78 in 8-bit for U8g2

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

#define MAX_LOG_LINES 9
String log_lines[MAX_LOG_LINES];
int current_log_line_count = 0;
int next_msg_idx = 0;
unsigned long next_log_delay = 30;

void addLogLine(const String& line) {
  if (current_log_line_count < MAX_LOG_LINES) {
    log_lines[current_log_line_count] = line;
    current_log_line_count++;
  } else {
    for (int i = 0; i < MAX_LOG_LINES - 1; i++) {
      log_lines[i] = log_lines[i + 1];
    }
    log_lines[MAX_LOG_LINES - 1] = line;
  }
}

void generateNextBootLine() {
  if (next_msg_idx >= boot_msg_count) {
    return; // Don't loop; stay in wait state
  }
  
  char buffer[32];
  strcpy_P(buffer, (char*)pgm_read_ptr(&(boot_messages[next_msg_idx])));
  
  float f_time = millis() / 1000.0;
  char line_buf[64];
  snprintf(line_buf, sizeof(line_buf), "[%6.2f] %s", f_time, buffer);
  
  addLogLine(String(line_buf));
  next_msg_idx++;
}

void drawLoadingAnimation(int frame) {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_4x6_tr);
  for (int i = 0; i < current_log_line_count; i++) {
    if (i == current_log_line_count - 1 && next_msg_idx >= boot_msg_count) {
      // Append blinking cursor to final log line when idle
      if ((millis() / 500) % 2 == 0) {
        String lastLine = log_lines[i] + "_";
        u8g2.drawStr(0, (i + 1) * 7 - 1, lastLine.c_str());
      } else {
        u8g2.drawStr(0, (i + 1) * 7 - 1, log_lines[i].c_str());
      }
    } else {
      u8g2.drawStr(0, (i + 1) * 7 - 1, log_lines[i].c_str());
    }
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
  Serial.setTimeout(10); // 10ms timeout

  // Configure mechanical button pin with internal pullup
  pinMode(SWITCH_PIN, INPUT_PULLUP);

  // I2C pins — configured for ESP32-C3 SuperMini using custom SDA/SCL pins
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000); // 400kHz fast mode I2C for stability

  u8g2.setI2CAddress(OLED_ADDRESS);
  u8g2.begin();
  u8g2.clearBuffer();

  // Balanced SSD1309 hardware register tuning to reduce power load and fix motion dimming
  u8g2.sendF("ca", 0xD9, 0x25); // Moderate Pre-charge Period (Phase 1 = 5 clocks, Phase 2 = 2 clocks)
  u8g2.sendF("ca", 0xDB, 0x30); // Default VCOMH Deselect Level to reduce current spikes
  u8g2.sendF("ca", 0xD5, 0x70); // Default Display Clock Divide Ratio to reduce power consumption

  // Check switch state at startup
  screenPowerState = true; // Default to ON
  
  // Render initial loading animation immediately
  generateNextBootLine();
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
    next_msg_idx = 0;
    current_log_line_count = 0;
  }

  // 4. Rendering Local Loader if Disconnected and Screen is ON
  if (!connected && screenPowerState) {
    unsigned long now = millis();
    if (now - lastAnimTime >= next_log_delay) {
      lastAnimTime = now;
      generateNextBootLine();
      drawLoadingAnimation(0);
      if (next_msg_idx >= boot_msg_count) {
        next_log_delay = 500; // blink cursor every 500ms when idle
      } else {
        next_log_delay = random(30, 85); // average of ~57ms per line to finish in 2s
      }
    }
  }
}

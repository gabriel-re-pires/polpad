// Firmware do macropad Polpad (ESP32-C3).
//
// Com o host presente, as teclas vão pela USB serial (JSON Lines, ver
// docs/PROTOCOLO.md) e o PC executa as ações. Sem host por HOST_TIMEOUT_MS,
// vira teclado BLE com os atalhos de config.h (o C3 não tem USB HID). Os
// eventos de tecla vão pela serial nos dois modos.
//
// Placa "ESP32C3 Dev Module", USB CDC On Boot ligado. Bibliotecas e
// gravação: firmware/README.md.

#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <Wire.h>

#include "config.h"
#include "espera_anim.h"

// Depois do config.h, que define (ou não) ENABLE_BLE.
#ifdef ENABLE_BLE
#include <NimBLEDevice.h>
#include <NimBLEHIDDevice.h>
#endif

constexpr char FW_VERSION[] = "2.1.0";

// KEY_INDEX precisa ter cada tecla 0..KEY_COUNT-1 exatamente uma vez.
constexpr bool keyIndexIsValid() {
  for (int k = 0; k < KEY_COUNT; k++) {
    int found = 0;
    for (int r = 0; r < KEY_ROWS; r++)
      for (int c = 0; c < KEY_COLS; c++)
        if (KEY_INDEX[r][c] == k) found++;
    if (found != 1) return false;
  }
  for (int r = 0; r < KEY_ROWS; r++)
    for (int c = 0; c < KEY_COLS; c++)
      if (KEY_INDEX[r][c] < -1 || KEY_INDEX[r][c] >= KEY_COUNT) return false;
  return true;
}
static_assert(keyIndexIsValid(),
              "KEY_INDEX deve conter cada tecla 0..KEY_COUNT-1 exatamente uma vez");

// =================================================================== display
// clkDuring = clkAfter: senão a biblioteca volta o I2C a 100 kHz após cada
// envio.
Adafruit_SSD1306 display(OLED_W, OLED_H, &Wire, -1, OLED_I2C_HZ, OLED_I2C_HZ);
bool displayOk = false;

uint8_t imageBuffer[OLED_W * OLED_H / 8];

// ================================================================ BLE HID
#ifdef ENABLE_BLE
constexpr uint8_t REPORT_ID_KEYBOARD = 1;
constexpr uint8_t REPORT_ID_CONSUMER = 2;

// ID 1 = teclado padrão (com relatório de saída dos LEDs, que alguns
// sistemas esperam); ID 2 = consumer control, um usage de 16 bits.
static const uint8_t HID_REPORT_MAP[] = {
    // ---------------------------------------------------- teclado (ID 1)
    0x05, 0x01,        // Usage Page (Generic Desktop)
    0x09, 0x06,        // Usage (Keyboard)
    0xA1, 0x01,        // Collection (Application)
    0x85, REPORT_ID_KEYBOARD,  //   Report ID (1)
    0x05, 0x07,        //   Usage Page (Keyboard/Keypad)
    0x19, 0xE0,        //   Usage Minimum (Left Control)
    0x29, 0xE7,        //   Usage Maximum (Right GUI)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0x01,        //   Logical Maximum (1)
    0x75, 0x01,        //   Report Size (1)
    0x95, 0x08,        //   Report Count (8)
    0x81, 0x02,        //   Input (Data, Var, Abs)      ; modificadores
    0x95, 0x01,        //   Report Count (1)
    0x75, 0x08,        //   Report Size (8)
    0x81, 0x01,        //   Input (Const)               ; byte reservado
    0x95, 0x05,        //   Report Count (5)
    0x75, 0x01,        //   Report Size (1)
    0x05, 0x08,        //   Usage Page (LEDs)
    0x19, 0x01,        //   Usage Minimum (Num Lock)
    0x29, 0x05,        //   Usage Maximum (Kana)
    0x91, 0x02,        //   Output (Data, Var, Abs)     ; LEDs
    0x95, 0x01,        //   Report Count (1)
    0x75, 0x03,        //   Report Size (3)
    0x91, 0x01,        //   Output (Const)              ; preenchimento
    0x95, 0x06,        //   Report Count (6)
    0x75, 0x08,        //   Report Size (8)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0x65,        //   Logical Maximum (101)
    0x05, 0x07,        //   Usage Page (Keyboard/Keypad)
    0x19, 0x00,        //   Usage Minimum (0)
    0x29, 0x65,        //   Usage Maximum (101)
    0x81, 0x00,        //   Input (Data, Array, Abs)    ; 6 teclas
    0xC0,              // End Collection
    // ------------------------------------------- consumer control (ID 2)
    0x05, 0x0C,        // Usage Page (Consumer)
    0x09, 0x01,        // Usage (Consumer Control)
    0xA1, 0x01,        // Collection (Application)
    0x85, REPORT_ID_CONSUMER,  //   Report ID (2)
    0x15, 0x00,        //   Logical Minimum (0)
    0x26, 0xFF, 0x03,  //   Logical Maximum (0x3FF)
    0x19, 0x00,        //   Usage Minimum (0)
    0x2A, 0xFF, 0x03,  //   Usage Maximum (0x3FF)
    0x75, 0x10,        //   Report Size (16)
    0x95, 0x01,        //   Report Count (1)
    0x81, 0x00,        //   Input (Data, Array, Abs)
    0xC0,              // End Collection
};

NimBLEServer *bleServer = nullptr;
NimBLEHIDDevice *bleHid = nullptr;
NimBLECharacteristic *bleKeyboardInput = nullptr;
NimBLECharacteristic *bleConsumerInput = nullptr;

// Escrito pelos callbacks da NimBLE, em outra tarefa do FreeRTOS.
volatile bool bleConnected = false;

class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer *server, NimBLEConnInfo &connInfo) override {
    bleConnected = true;
    // Intervalo 7,5–15 ms para baixa latência; supervision timeout 4 s.
    server->updateConnParams(connInfo.getConnHandle(), 6, 12, 0, 400);
  }
  void onDisconnect(NimBLEServer *server, NimBLEConnInfo &connInfo,
                    int reason) override {
    (void)connInfo;
    (void)reason;
    bleConnected = server->getConnectedCount() > 0;
  }
};
#endif  // ENABLE_BLE

// ================================================================ estado
bool keyState[KEY_COUNT] = {false};
bool keyPending[KEY_COUNT] = {false};  // leitura diferente do estado
uint32_t keyPendingSince[KEY_COUNT] = {0};

uint32_t lastHostMessageAt = 0;
bool hostPresent = false;

// Passo da animação de espera já desenhado; -1 força redesenho.
int32_t waitingStepShown = -1;

#ifdef ENABLE_BLE
uint8_t currentKeyboardReport[8] = {0};
uint16_t currentConsumerUsage = 0;
#endif

// A mensagem "img" chega a ~1,4 KB.
constexpr size_t LINE_BUFFER_SIZE = 2048;
char lineBuffer[LINE_BUFFER_SIZE];
size_t lineLength = 0;
bool discardingLine = false;

// ==================================================================== setup

void setup() {
  // Antes do begin(): o "img" chega de uma vez e o padrão do HWCDC é 256 B.
  Serial.setRxBufferSize(4096);
  Serial.setTxBufferSize(1024);
  Serial.begin(115200);  // USB CDC: o baud rate é ignorado
  // Não travar o loop quando ninguém lê a porta no PC.
  Serial.setTxTimeoutMs(5);

  setupMatrix();

  Wire.begin(OLED_SDA, OLED_SCL);
  Wire.setClock(OLED_I2C_HZ);
  // periphBegin = false: o Wire já foi iniciado com os pinos certos.
  displayOk = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR, true, false);
  if (displayOk) {
    display.setTextWrap(false);
    display.setTextColor(SSD1306_WHITE);
  }

#ifdef ENABLE_BLE
  setupBle();
#endif
  showWaitingScreen();
  sendHello();
}

// ===================================================================== loop

void loop() {
  scanKeys();
  readSerial();
  updateHostPresence();
  updateWaitingScreen();
}

// ======================================================== matriz de teclas

// O lado acionado fica em alta impedância e só o pino da vez vira OUTPUT
// LOW, para nunca forçar HIGH contra o resto do circuito. O lado lido tem
// pull-up.
void setupMatrix() {
  for (uint8_t r = 0; r < KEY_ROWS; r++) {
    pinMode(ROW_PINS[r], DIODE_COL2ROW ? INPUT : INPUT_PULLUP);
  }
  for (uint8_t c = 0; c < KEY_COLS; c++) {
    pinMode(COL_PINS[c], DIODE_COL2ROW ? INPUT_PULLUP : INPUT);
  }
}

void debounceKey(int8_t index, bool pressed, uint32_t now) {
  if (index < 0) return;
  if (pressed == keyState[index]) {
    keyPending[index] = false;
    return;
  }
  if (!keyPending[index]) {
    keyPending[index] = true;
    keyPendingSince[index] = now;
  } else if (now - keyPendingSince[index] >= DEBOUNCE_MS) {
    keyState[index] = pressed;
    keyPending[index] = false;
    onKeyEvent((uint8_t)index, pressed);
  }
}

void scanKeys() {
  uint32_t now = millis();
  if (DIODE_COL2ROW) {
    for (uint8_t r = 0; r < KEY_ROWS; r++) {
      pinMode(ROW_PINS[r], OUTPUT);
      digitalWrite(ROW_PINS[r], LOW);
      delayMicroseconds(SCAN_SETTLE_US);
      for (uint8_t c = 0; c < KEY_COLS; c++) {
        debounceKey(KEY_INDEX[r][c], digitalRead(COL_PINS[c]) == LOW, now);
      }
      pinMode(ROW_PINS[r], INPUT);
    }
  } else {
    for (uint8_t c = 0; c < KEY_COLS; c++) {
      pinMode(COL_PINS[c], OUTPUT);
      digitalWrite(COL_PINS[c], LOW);
      delayMicroseconds(SCAN_SETTLE_US);
      for (uint8_t r = 0; r < KEY_ROWS; r++) {
        debounceKey(KEY_INDEX[r][c], digitalRead(ROW_PINS[r]) == LOW, now);
      }
      pinMode(COL_PINS[c], INPUT);
    }
  }
}

void onKeyEvent(uint8_t index, bool pressed) {
  // Sempre pela serial: o software recebe eventos antes do primeiro ping.
  char msg[48];
  int n = snprintf(msg, sizeof(msg), "{\"t\":\"key\",\"k\":%u,\"e\":\"%s\"}\n",
                   index, pressed ? "down" : "up");
  writeSerial(msg, (size_t)n);

#ifdef ENABLE_BLE
  if (!hostPresent && bleConnected) {
    const FallbackKey &fb = FALLBACK_KEYS[index];
    if (fb.consumer != 0) {
      sendConsumer(pressed ? fb.consumer : 0);
    } else if (fb.key != 0 || fb.modifiers != 0) {
      if (pressed) {
        sendKeyboard(fb.modifiers, fb.key);
      } else {
        sendKeyboard(0, 0);
      }
    }
  }
#endif
}

// ================================================================= BLE HID
#ifdef ENABLE_BLE

void setupBle() {
  NimBLEDevice::init(BLE_DEVICE_NAME);
  // "Just works": bonding e LE Secure Connections, sem MITM (não há onde
  // digitar senha).
  NimBLEDevice::setSecurityAuth(true, false, true);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);

  bleServer = NimBLEDevice::createServer();
  bleServer->setCallbacks(new ServerCallbacks());
  bleServer->advertiseOnDisconnect(true);

  bleHid = new NimBLEHIDDevice(bleServer);
  bleHid->setManufacturer(BLE_MANUFACTURER);
  // Fonte USB-IF; VID/PID genéricos de protótipo.
  bleHid->setPnp(0x02, 0x303A, 0x8001, 0x0200);
  bleHid->setHidInfo(0x00, 0x01);  // flags: RemoteWake
  bleHid->setReportMap((uint8_t *)HID_REPORT_MAP, sizeof(HID_REPORT_MAP));
  bleKeyboardInput = bleHid->getInputReport(REPORT_ID_KEYBOARD);
  bleHid->getOutputReport(REPORT_ID_KEYBOARD);  // LEDs (ignorados)
  bleConsumerInput = bleHid->getInputReport(REPORT_ID_CONSUMER);
  bleHid->setBatteryLevel(BLE_BATTERY_LEVEL);

  bleServer->start();

  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  adv->setAppearance(HID_KEYBOARD);
  adv->addServiceUUID(bleHid->getHidService()->getUUID());
  adv->setName(BLE_DEVICE_NAME);
  adv->start();
}

void sendKeyboard(uint8_t modifiers, uint8_t key) {
  currentKeyboardReport[0] = modifiers;
  currentKeyboardReport[1] = 0;
  currentKeyboardReport[2] = key;
  for (uint8_t i = 3; i < 8; i++) currentKeyboardReport[i] = 0;
  if (bleKeyboardInput == nullptr) return;
  bleKeyboardInput->setValue(currentKeyboardReport, sizeof(currentKeyboardReport));
  bleKeyboardInput->notify();
}

void sendConsumer(uint16_t usage) {
  currentConsumerUsage = usage;
  uint8_t report[2] = {(uint8_t)(usage & 0xFF), (uint8_t)(usage >> 8)};
  if (bleConsumerInput == nullptr) return;
  bleConsumerInput->setValue(report, sizeof(report));
  bleConsumerInput->notify();
}

// Evita tecla presa no PC quando o host chega com uma tecla segurada.
void releaseAllBle() {
  if (!bleConnected) return;
  bool keyboardDown = false;
  for (uint8_t i = 0; i < 8; i++) keyboardDown |= currentKeyboardReport[i] != 0;
  if (keyboardDown) sendKeyboard(0, 0);
  if (currentConsumerUsage != 0) sendConsumer(0);
}

#endif  // ENABLE_BLE

// =========================================================== serial (host)

// Linha inteira ou nada: sem espaço no TX (ninguém lendo), descarta em vez
// de bloquear ou mandar meia linha.
void writeSerial(const char *data, size_t length) {
  if ((size_t)Serial.availableForWrite() < length) return;
  Serial.write((const uint8_t *)data, length);
}

void sendHello() {
  char msg[96];
  int n = snprintf(msg, sizeof(msg),
                   "{\"t\":\"hello\",\"fw\":\"%s\",\"keys\":%u,"
                   "\"screen\":{\"w\":%d,\"h\":%d}}\n",
                   FW_VERSION, KEY_COUNT, OLED_W, OLED_H);
  writeSerial(msg, (size_t)n);
}

void readSerial() {
  // Limite por volta do loop para não atrasar a varredura.
  int budget = 512;
  while (budget-- > 0 && Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      if (!discardingLine) {
        lineBuffer[lineLength] = '\0';
        handleLine(lineBuffer);
      }
      lineLength = 0;
      discardingLine = false;
    } else if (discardingLine) {
      continue;
    } else if (lineLength < LINE_BUFFER_SIZE - 1) {
      lineBuffer[lineLength++] = ch;
    } else {
      // Linha maior que o buffer: descarta até o '\n', senão o final seria
      // lido como linha nova.
      lineLength = 0;
      discardingLine = true;
    }
  }
}

void handleLine(const char *line) {
  if (line[0] != '{') return;  // lixo/eco

  JsonDocument doc;
  if (deserializeJson(doc, line) != DeserializationError::Ok) return;
  const char *type = doc["t"];
  if (type == nullptr) return;

  lastHostMessageAt = millis();
  if (!hostPresent) onHostArrived();

  if (strcmp(type, "ping") == 0) {
    writeSerial("{\"t\":\"pong\"}\n", 13);
  } else if (strcmp(type, "text") == 0) {
    showTextScreen(doc["lines"]);
  } else if (strcmp(type, "img") == 0) {
    showImageScreen(doc["d"]);
  }
}

void onHostArrived() {
  hostPresent = true;
#ifdef ENABLE_BLE
  releaseAllBle();
#endif
  sendHello();  // o host reenvia o perfil ao receber o hello
  showHostConnectedScreen();
}

void updateHostPresence() {
  if (hostPresent && (millis() - lastHostMessageAt) >= HOST_TIMEOUT_MS) {
    hostPresent = false;
    showWaitingScreen();
  }
}

// ================================================================== display

#ifdef ENABLE_BLE
// Runa do Bluetooth (5x9).
static const uint8_t BLE_ICON[] PROGMEM = {
    0x20, 0x30, 0xA8, 0x70, 0x20, 0x70, 0xA8, 0x30, 0x20,
};
#endif

void showWaitingScreen() {
  waitingStepShown = -1;
  updateWaitingScreen();
}

// Só redesenha quando o passo da animação muda: cada envio ao display leva
// ~25 ms no I2C.
void updateWaitingScreen() {
  if (hostPresent || !displayOk) return;
  int32_t step = (int32_t)(millis() / ESPERA_QUADRO_MS);
  if (step == waitingStepShown) return;
  waitingStepShown = step;

  display.clearDisplay();
  display.drawBitmap((OLED_W - ESPERA_LADO) / 2, 0,
                     ESPERA_POLVO[step % ESPERA_QUADROS], ESPERA_LADO,
                     ESPERA_LADO, SSD1306_WHITE);

  // Centraliza contando os três pontos, para o texto não andar.
  constexpr int16_t CELL_W = 6;
  constexpr int16_t textChars = sizeof(ESPERA_TEXTO) - 1;
  int16_t x = (OLED_W - (textChars + 3) * CELL_W) / 2;
  display.setTextSize(1);
  display.setCursor(x, ESPERA_TEXTO_Y);
  display.print(ESPERA_TEXTO);
  uint8_t dots = (millis() / ESPERA_PONTOS_MS) % 4;
  for (uint8_t i = 0; i < dots; i++) display.print('.');
  int16_t tilX = x + ESPERA_TIL_EM * CELL_W;
  for (const auto &p : ESPERA_TIL) {
    display.drawPixel(tilX + p[0], ESPERA_TEXTO_Y + p[1], SSD1306_WHITE);
  }

#ifdef ENABLE_BLE
  if (bleConnected) {
    display.drawBitmap(OLED_W - 6, 0, BLE_ICON, 5, 9, SSD1306_WHITE);
  }
#endif
  display.display();
}

void showHostConnectedScreen() {
  if (!displayOk) return;
  display.clearDisplay();
  display.setTextSize(2);
  drawCentered("PC", 14);
  drawCentered("conectado", 36);
  display.display();
}

void drawCentered(const char *text, int16_t y) {
  int16_t bx, by;
  uint16_t bw, bh;
  display.getTextBounds(text, 0, 0, &bx, &by, &bw, &bh);
  int16_t x = (OLED_W - (int16_t)bw) / 2;
  display.setCursor(x > 0 ? x : 0, y);
  display.print(text);
}

void showTextScreen(JsonArrayConst lines) {
  if (!displayOk) return;
  const char *texts[3];
  uint8_t count = 0;
  for (JsonVariantConst v : lines) {
    if (count >= 3) break;
    const char *text = v.as<const char *>();
    if (text != nullptr) texts[count++] = text;
  }
  display.clearDisplay();
  uint8_t size = (count <= 1) ? 2 : 1;
  display.setTextSize(size);
  int16_t lineHeight = 8 * size + 4;
  int16_t y = (OLED_H - count * lineHeight + 4) / 2;
  for (uint8_t i = 0; i < count; i++) {
    drawCentered(texts[i], y);
    y += lineHeight;
  }
  display.display();
}

void showImageScreen(const char *base64Data) {
  if (!displayOk || base64Data == nullptr) return;
  size_t written = base64Decode(base64Data, imageBuffer, sizeof(imageBuffer));
  if (written != sizeof(imageBuffer)) return;
  display.clearDisplay();
  // "xbm1" do protocolo já é o formato do drawBitmap (linhas, MSB primeiro).
  display.drawBitmap(0, 0, imageBuffer, OLED_W, OLED_H, SSD1306_WHITE);
  display.display();
}

// =================================================================== base64

int8_t base64Value(char ch) {
  if (ch >= 'A' && ch <= 'Z') return ch - 'A';
  if (ch >= 'a' && ch <= 'z') return ch - 'a' + 26;
  if (ch >= '0' && ch <= '9') return ch - '0' + 52;
  if (ch == '+') return 62;
  if (ch == '/') return 63;
  return -1;
}

// Ignora '=' e caracteres inválidos. Retorna os bytes escritos, ou 0 se não
// couber em maxOut.
size_t base64Decode(const char *input, uint8_t *output, size_t maxOut) {
  size_t outLength = 0;
  uint32_t accumulator = 0;
  uint8_t bits = 0;
  for (const char *p = input; *p != '\0'; p++) {
    int8_t value = base64Value(*p);
    if (value < 0) continue;
    accumulator = ((accumulator << 6) | (uint32_t)value) & 0xFFFFFF;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      if (outLength >= maxOut) return 0;
      output[outLength++] = (uint8_t)(accumulator >> bits);
    }
  }
  return outLength;
}

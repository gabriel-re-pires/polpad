// =========================================================================
// Firmware do macropad ESP32-C3 — projeto Polpad  (versão 2.0.2)
//
// Arquitetura híbrida:
//   * MODO ESTENDIDO (host presente): eventos de tecla vão pela USB serial
//     (JSON Lines, ver docs/PROTOCOLO.md) e o software no PC executa as
//     ações; o display mostra o ícone/nome do perfil enviado pelo host.
//   * MODO AUTÔNOMO (sem host): o dispositivo atua como teclado Bluetooth
//     LE (BLE HID) com os atalhos fixos definidos em config.h.
//
// O ESP32-C3 não tem USB HID nativo (a USB dele é um periférico fixo
// Serial/JTAG), por isso o "teclado de verdade" do modo autônomo é BLE.
//
// O host envia "ping" a cada 3 s; a ausência de mensagens válidas por
// HOST_TIMEOUT_MS caracteriza o modo autônomo. Os eventos de tecla são
// SEMPRE enviados pela serial, nos dois modos.
//
// O modo autônomo é opcional: comente ENABLE_BLE em config.h para
// compilar só com o modo estendido (ver firmware/README.md).
//
// Bibliotecas (Gerenciador de Bibliotecas do Arduino IDE):
//   - Adafruit SSD1306 (+ Adafruit GFX, Adafruit BusIO)
//   - ArduinoJson 7.x
// E, apenas com ENABLE_BLE ligado:
//   - NimBLE-Arduino 2.5.x  (o HID BLE é implementado aqui mesmo, com
//     NimBLEHIDDevice — NÃO usa a biblioteca ESP32-BLE-Keyboard)
//
// Placa: "ESP32C3 Dev Module", USB CDC On Boot: "Enabled"
// (FQBN esp32:esp32:esp32c3:CDCOnBoot=cdc). Ver firmware/README.md.
// =========================================================================

#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <Wire.h>

#include "config.h"

// Depois do config.h, que é quem define (ou não) ENABLE_BLE.
#ifdef ENABLE_BLE
#include <NimBLEDevice.h>
#include <NimBLEHIDDevice.h>
#endif

constexpr char FW_VERSION[] = "2.0.2";

// ------------------------------------------- verificações de config.h
// Confere, em tempo de compilação, que KEY_INDEX mapeia exatamente as
// teclas 0..KEY_COUNT-1, cada uma uma única vez.
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
// clkDuring = clkAfter = 400 kHz: a Adafruit_SSD1306 troca o clock do I2C
// antes/depois de cada transferência; com os dois iguais o barramento fica
// sempre em 400 kHz (o padrão dela "devolveria" 100 kHz após cada envio).
Adafruit_SSD1306 display(OLED_W, OLED_H, &Wire, -1, OLED_I2C_HZ, OLED_I2C_HZ);
bool displayOk = false;

uint8_t imageBuffer[OLED_W * OLED_H / 8];  // 1024 bytes (1 bpp)

// ================================================================ BLE HID
#ifdef ENABLE_BLE
// IDs de relatório (precisam bater com o report map abaixo).
constexpr uint8_t REPORT_ID_KEYBOARD = 1;
constexpr uint8_t REPORT_ID_CONSUMER = 2;

// Report map HID:
//   ID 1 = teclado padrão: 1 byte de modificadores, 1 reservado, 6 teclas
//          (+ relatório de saída de 1 byte para os LEDs Num/Caps/Scroll,
//          que alguns sistemas esperam de um teclado);
//   ID 2 = consumer control: um usage de 16 bits (teclas de mídia).
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

// Alterado pelos callbacks da NimBLE (outra tarefa do FreeRTOS); o loop
// só observa e redesenha a tela de status quando muda.
volatile bool bleConnected = false;

class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer *server, NimBLEConnInfo &connInfo) override {
    bleConnected = true;
    // Intervalo de conexão curto (7,5–15 ms) para baixa latência de tecla;
    // latência 0; supervision timeout 4 s (unidade de 10 ms).
    server->updateConnParams(connInfo.getConnHandle(), 6, 12, 0, 400);
  }
  void onDisconnect(NimBLEServer *server, NimBLEConnInfo &connInfo,
                    int reason) override {
    (void)connInfo;
    (void)reason;
    // O anúncio é reiniciado automaticamente (advertiseOnDisconnect).
    bleConnected = server->getConnectedCount() > 0;
  }
};
#endif  // ENABLE_BLE

// ================================================================ estado
// Debounce por tempo de estabilidade.
bool keyState[KEY_COUNT] = {false};       // estado debounced (true = pressionada)
bool keyPending[KEY_COUNT] = {false};     // leitura diferente do estado?
uint32_t keyPendingSince[KEY_COUNT] = {0};  // desde quando (ms)

// Presença do host.
uint32_t lastHostMessageAt = 0;
bool hostPresent = false;
bool hostScreenReceived = false;  // host já mandou text/img nesta sessão?

#ifdef ENABLE_BLE
// Tela de status: último estado de BLE desenhado.
bool statusShownBleConnected = false;

// Relatórios BLE atuais (para soltar só o tipo correspondente).
uint8_t currentKeyboardReport[8] = {0};
uint16_t currentConsumerUsage = 0;
#endif

// Linha de entrada da serial (a mensagem "img" chega a ~1,4 KB).
constexpr size_t LINE_BUFFER_SIZE = 2048;
char lineBuffer[LINE_BUFFER_SIZE];
size_t lineLength = 0;
bool discardingLine = false;  // linha longa demais: descarta até o '\n'

// ==================================================================== setup

void setup() {
  // O buffer de RX precisa ser configurado ANTES do begin(): uma mensagem
  // "img" (~1,4 KB) chega de uma vez e o padrão do HWCDC é só 256 bytes.
  Serial.setRxBufferSize(4096);
  Serial.setTxBufferSize(1024);
  Serial.begin(115200);  // no C3 é USB CDC: o baud rate é ignorado
  // Escritas na serial nunca devem travar o loop por muito tempo (ex.: PC
  // ligado à USB mas sem nenhum programa lendo a porta).
  Serial.setTxTimeoutMs(5);

  setupMatrix();

  Wire.begin(OLED_SDA, OLED_SCL);
  Wire.setClock(OLED_I2C_HZ);
  // periphBegin = false: o Wire já foi iniciado acima com os pinos certos.
  displayOk = display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR, true, false);
  if (displayOk) {
    display.setTextWrap(false);
    display.setTextColor(SSD1306_WHITE);
  }

#ifdef ENABLE_BLE
  setupBle();
#endif
  showStatusScreen();
  sendHello();
}

// ===================================================================== loop

void loop() {
  scanKeys();
  readSerial();
  updateHostPresence();
#ifdef ENABLE_BLE
  updateStatusScreen();
#endif
}

// ======================================================== matriz de teclas

// Conforme a orientação dos diodos, um lado da matriz é "acionado" (levado
// a LOW, um pino por vez) e o outro é "lido" (com pull-up).
void setupMatrix() {
  // Pinos acionados ficam em alta impedância (INPUT) quando inativos; só o
  // pino da vez vira OUTPUT LOW. Assim nunca há dois pinos acionados ao
  // mesmo tempo e nada é forçado em HIGH contra o resto do circuito.
  for (uint8_t r = 0; r < KEY_ROWS; r++) {
    pinMode(ROW_PINS[r], DIODE_COL2ROW ? INPUT : INPUT_PULLUP);
  }
  for (uint8_t c = 0; c < KEY_COLS; c++) {
    pinMode(COL_PINS[c], DIODE_COL2ROW ? INPUT_PULLUP : INPUT);
  }
}

// Aplica o debounce por tempo de estabilidade a uma leitura crua.
void debounceKey(int8_t index, bool pressed, uint32_t now) {
  if (index < 0) return;  // posição vazia da matriz
  if (pressed == keyState[index]) {
    keyPending[index] = false;  // voltou ao estado atual: era ruído/bounce
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
    // Linha em LOW, colunas lidas (LOW = tecla pressionada).
    for (uint8_t r = 0; r < KEY_ROWS; r++) {
      pinMode(ROW_PINS[r], OUTPUT);
      digitalWrite(ROW_PINS[r], LOW);
      delayMicroseconds(SCAN_SETTLE_US);
      for (uint8_t c = 0; c < KEY_COLS; c++) {
        debounceKey(KEY_INDEX[r][c], digitalRead(COL_PINS[c]) == LOW, now);
      }
      pinMode(ROW_PINS[r], INPUT);  // solta a linha antes da próxima
    }
  } else {
    // Coluna em LOW, linhas lidas (LOW = tecla pressionada).
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
  // Sempre reporta pela serial: se o software acabou de abrir, ele já
  // recebe eventos mesmo antes do primeiro ping.
  char msg[48];
  int n = snprintf(msg, sizeof(msg), "{\"t\":\"key\",\"k\":%u,\"e\":\"%s\"}\n",
                   index, pressed ? "down" : "up");
  writeSerial(msg, (size_t)n);

#ifdef ENABLE_BLE
  // Modo autônomo: replica o atalho fixo via teclado BLE.
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
  // Pareamento "just works": bonding ligado, sem MITM (não há tela/teclado
  // para senha), LE Secure Connections ligado — como teclados BLE comuns.
  NimBLEDevice::setSecurityAuth(true, false, true);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);

  bleServer = NimBLEDevice::createServer();
  bleServer->setCallbacks(new ServerCallbacks());
  bleServer->advertiseOnDisconnect(true);  // volta a anunciar ao desconectar

  bleHid = new NimBLEHIDDevice(bleServer);
  bleHid->setManufacturer(BLE_MANUFACTURER);
  // PnP: fonte do VID = 0x02 (USB-IF). VID/PID genéricos de protótipo.
  bleHid->setPnp(0x02, 0x303A, 0x8001, 0x0200);  // AJUSTAR se tiverem VID/PID
  bleHid->setHidInfo(0x00, 0x01);  // país 0; flags: RemoteWake
  bleHid->setReportMap((uint8_t *)HID_REPORT_MAP, sizeof(HID_REPORT_MAP));
  bleKeyboardInput = bleHid->getInputReport(REPORT_ID_KEYBOARD);
  bleHid->getOutputReport(REPORT_ID_KEYBOARD);  // LEDs (ignorados)
  bleConsumerInput = bleHid->getInputReport(REPORT_ID_CONSUMER);
  bleHid->setBatteryLevel(BLE_BATTERY_LEVEL);

  bleServer->start();

  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  adv->setAppearance(HID_KEYBOARD);  // 0x03C1
  adv->addServiceUUID(bleHid->getHidService()->getUUID());  // 0x1812
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

// Solta tudo o que estiver "pressionado" no lado BLE (usado quando o host
// aparece com uma tecla segurada, para não deixar tecla presa no PC).
void releaseAllBle() {
  if (!bleConnected) return;
  bool keyboardDown = false;
  for (uint8_t i = 0; i < 8; i++) keyboardDown |= currentKeyboardReport[i] != 0;
  if (keyboardDown) sendKeyboard(0, 0);
  if (currentConsumerUsage != 0) sendConsumer(0);
}

#endif  // ENABLE_BLE

// =========================================================== serial (host)

// Escreve uma mensagem completa ou nada: se o buffer de TX não comporta a
// linha inteira (ninguém lendo a porta), descarta em vez de bloquear ou de
// mandar meia linha.
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
  // Limita o trabalho por volta do loop para a varredura não atrasar.
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
      // continua descartando até o fim da linha
    } else if (lineLength < LINE_BUFFER_SIZE - 1) {
      lineBuffer[lineLength++] = ch;
    } else {
      // Linha maior que o buffer: descarta o resto dela inteira (em vez de
      // recomeçar no meio e interpretar o final como uma linha nova).
      lineLength = 0;
      discardingLine = true;
    }
  }
}

void handleLine(const char *line) {
  if (line[0] != '{') return;  // ignora lixo/eco

  JsonDocument doc;
  if (deserializeJson(doc, line) != DeserializationError::Ok) return;
  const char *type = doc["t"];
  if (type == nullptr) return;

  // Mensagem válida: o host está presente.
  lastHostMessageAt = millis();
  if (!hostPresent) {
    onHostArrived();
  }

  if (strcmp(type, "ping") == 0) {
    writeSerial("{\"t\":\"pong\"}\n", 13);
  } else if (strcmp(type, "text") == 0) {
    hostScreenReceived = true;
    showTextScreen(doc["lines"]);
  } else if (strcmp(type, "img") == 0) {
    hostScreenReceived = true;
    showImageScreen(doc["d"]);
  }
}

// Transição ausente -> presente (primeira mensagem válida após o timeout).
void onHostArrived() {
  hostPresent = true;
  hostScreenReceived = false;
#ifdef ENABLE_BLE
  releaseAllBle();
#endif
  sendHello();         // o host (re)envia o perfil ao receber o hello
  showHostConnectedScreen();  // até chegar o primeiro text/img
}

void updateHostPresence() {
  if (hostPresent && (millis() - lastHostMessageAt) >= HOST_TIMEOUT_MS) {
    hostPresent = false;
    showStatusScreen();  // host saiu: informa o modo autônomo
  }
}

// ================================================================== display

#ifdef ENABLE_BLE
void updateStatusScreen() {
  // Redesenha a tela de status se o estado do BLE mudou enquanto ela está
  // visível (host ausente).
  bool connected = bleConnected;
  if (!hostPresent && connected != statusShownBleConnected) {
    showStatusScreen();
  }
}
#endif

void showStatusScreen() {
#ifdef ENABLE_BLE
  statusShownBleConnected = bleConnected;
#endif
  if (!displayOk) return;
  display.clearDisplay();
  display.setTextSize(2);
  display.setCursor(16, 8);
  display.print("macropad");
  display.setTextSize(1);
  display.setCursor(10, 34);
  display.print("Aguardando host...");
  display.setCursor(10, 48);
#ifdef ENABLE_BLE
  display.print(statusShownBleConnected ? "BLE: conectado" : "BLE: pareavel");
#else
  display.print("Modo USB apenas");
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

// Escreve um texto centralizado horizontalmente na altura y.
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
  if (written != sizeof(imageBuffer)) return;  // payload inválido
  display.clearDisplay();
  // Formato "xbm1" do protocolo = formato nativo do drawBitmap
  // (varredura por linhas, MSB primeiro, 1 = pixel aceso).
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
  return -1;  // '=' ou caractere inválido
}

// Decodifica base64 (ignora '=' e caracteres inválidos). Retorna o número
// de bytes escritos, ou 0 se o resultado não couber em maxOut.
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
      if (outLength >= maxOut) return 0;  // payload maior que o esperado
      output[outLength++] = (uint8_t)(accumulator >> bits);
    }
  }
  return outLength;
}

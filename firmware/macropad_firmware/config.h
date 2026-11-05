// =========================================================================
// Configuração do hardware
//
// Os valores desta seção descrevem o PCB real do macropad: foram extraídos
// da netlist do projeto no EasyEDA e conferidos no hardware em 03/11/2026
// (ver docs/PINAGEM.md). Ao portar para outra placa, é esta seção que muda.
// =========================================================================
#pragma once

#include <Arduino.h>

// ======================================================== modo híbrido
// Comente a linha abaixo para compilar SEM o modo autônomo (teclado
// Bluetooth). O macropad continua completo pela USB — que é como ele
// funciona com o software aberto — e a compilação passa a exigir apenas
// Adafruit SSD1306 e ArduinoJson: a NimBLE-Arduino nem precisa estar
// instalada. Serve para validar matriz, display e comunicação sem a parte
// BLE.
#define ENABLE_BLE

// ============================================================== teclas
// 18 chaves mecânicas com diodo, ligadas eletricamente numa matriz de
// 4 linhas x 5 colunas (20 posições, 18 ocupadas). As duas posições vazias
// ficam na linha 0, colunas 0 e 1 — é onde estão o módulo ESP32-C3 e o OLED.
//
// Layout físico (vista de cima) e índice das teclas usado no protocolo
// (ordem de leitura: esquerda -> direita, cima -> baixo):
//
//            col 0   col 1   col 2   col 3   col 4
//   linha 0  [MCU]   [OLED]    0       1       2
//   linha 1    3       4       5       6       7
//   linha 2    8       9      10      11      12
//   linha 3   13      14      15      16      17
//
// A orientação elétrica e os GPIOs foram conferidos contra o PCB em
// 03/11/2026: a pinagem veio da netlist do projeto no EasyEDA e foi
// confirmada no hardware, tecla por tecla, com um sketch que varre a
// matriz nos dois sentidos possíveis. O procedimento e os resultados estão
// em docs/PINAGEM.md. KEY_INDEX já estava correto.
constexpr uint8_t KEY_ROWS = 4;
constexpr uint8_t KEY_COLS = 5;
constexpr uint8_t KEY_COUNT = 18;

// Índice da tecla (0..17) em cada posição da matriz; -1 = posição vazia.
constexpr int8_t KEY_INDEX[KEY_ROWS][KEY_COLS] = {
    {-1, -1, 0, 1, 2},     // linha 0 (colunas 0 e 1 vazias: MCU/OLED)
    {3, 4, 5, 6, 7},       // linha 1
    {8, 9, 10, 11, 12},    // linha 2
    {13, 14, 15, 16, 17},  // linha 3
};

// ------------------------------------------------------------- GPIOs
// ESP32-C3 SuperMini expõe: GPIO 0-10, 20, 21 (+ 5V/GND/3V3).
//
// Pinagem real da placa (netlist do EasyEDA, conferida no hardware):
//   * Linhas  (saídas, LOW durante a varredura): GPIO 10, 7, 6, 5
//     — é o lado dos DIODOS; de cima para baixo na grade.
//   * Colunas (INPUT_PULLUP):                     GPIO 0, 1, 2, 3, 4
//     — é o lado dos SOQUETES Kailh; da esquerda para a direita.
//   * OLED I2C: SDA = GPIO 8, SCL = GPIO 9
//
// GPIO 20 e 21 (RX/TX) ficaram sem uso na placa.
//
// O raciocínio abaixo sobre pinos de strapping se confirma na prática: dos
// pinos de strapping do C3 (2, 8, 9), nenhum virou linha. O 2 é coluna, o 8
// e o 9 ficaram com o I2C, e o 2 entra no barramento em HIGH por pull-up.
//
// Pinos evitados:
//   * GPIO2 — pino de strapping (amostrado no reset para escolher o modo de
//     boot); fica livre como reserva.
//   * GPIO20 — U0RXD: a ROM do bootloader escuta a UART0 no boot; ruído de
//     uma linha de matriz ali não tem vantagem nenhuma. Fica livre.
//   * GPIO8/9 — também são strapping (GPIO9 = botão BOOT da SuperMini;
//     GPIO8 = LED azul onboard na maioria das SuperMini). Ficam com o I2C.
//
// Por que pinos de strapping NÃO podem ser LINHAS, mas podem ser colunas
// ou I2C:
//   * O nível dos pinos de strapping é lido no instante do reset (ex.:
//     GPIO9 em LOW no reset = modo download, a placa não executa o
//     firmware). Uma linha da matriz é ligada, através das teclas, a todas
//     as colunas; se a orientação de algum diodo estiver errada, um diodo
//     estiver em curto, ou o pino precisar ser acionado como saída enquanto
//     o botão BOOT/LED da placa também o puxa, uma tecla segurada durante o
//     reset pode levar o pino a LOW e mudar o modo de boot (ou causar curto
//     entre a saída e o botão BOOT).
//   * Colunas só são puxadas para LOW quando o FIRMWARE aciona uma linha —
//     algo que nunca acontece durante o reset — e em repouso ficam em HIGH
//     (pull-up). Idem para o I2C, que em repouso fica em HIGH pelos
//     pull-ups do barramento, exatamente o nível que GPIO8/9 precisam para
//     um boot normal pela flash.
// CONFERIDO contra o PCB em 03/11/2026 (ver docs/PINAGEM.md): os valores
// abaixo saem da netlist do projeto no EasyEDA e foram confirmados tecla a
// tecla no hardware. Não são mais suposição.
constexpr uint8_t ROW_PINS[KEY_ROWS] = {10, 7, 6, 5};
constexpr uint8_t COL_PINS[KEY_COLS] = {0, 1, 2, 3, 4};

// Orientação dos diodos — CONFERIDA: a varredura de teste detectou 613
// eventos no sentido COL2ROW e nenhum no sentido oposto.
//   true  = "COL2ROW" (convenção QMK): cátodo (faixa do diodo) voltado para
//           a LINHA. O firmware leva a linha a LOW e lê as colunas.
//   false = "ROW2COL": cátodo voltado para a COLUNA. O firmware leva a
//           coluna a LOW e lê as linhas (as linhas ficam com pull-up).
constexpr bool DIODE_COL2ROW = true;

// Debounce por tempo de estabilidade: a leitura precisa ficar diferente do
// estado atual por este tempo, contínuo, antes de o estado mudar.
constexpr uint32_t DEBOUNCE_MS = 5;

// Tempo de estabilização após acionar uma linha, antes de ler as colunas.
constexpr uint32_t SCAN_SETTLE_US = 30;

// ============================================================= display
// OLED 0,96" SSD1306 128x64 via I2C.
constexpr uint8_t OLED_SDA = 8;      // conferido na netlist
constexpr uint8_t OLED_SCL = 9;      // conferido na netlist
constexpr uint8_t OLED_ADDR = 0x3C;  // 0x3C é o padrão da maioria dos módulos
constexpr int16_t OLED_W = 128;
constexpr int16_t OLED_H = 64;
constexpr uint32_t OLED_I2C_HZ = 400000;

// ================================================================ host
// O software no PC envia "ping" a cada 3 s; sem nenhuma mensagem válida
// por este tempo, o firmware considera o host ausente e ativa o modo
// autônomo (teclado BLE).
constexpr uint32_t HOST_TIMEOUT_MS = 10000;

// ============================================================ modo BLE
#define BLE_DEVICE_NAME "Polpad"
#define BLE_MANUFACTURER "Polpad"
constexpr uint8_t BLE_BATTERY_LEVEL = 100;  // sem medição de bateria (fixo)

// ---------------------------------------------- códigos HID (teclado)
// Modificadores (bitmask do 1º byte do relatório de teclado).
constexpr uint8_t KEY_MOD_LCTRL = 0x01;
constexpr uint8_t KEY_MOD_LSHIFT = 0x02;
constexpr uint8_t KEY_MOD_LALT = 0x04;
constexpr uint8_t KEY_MOD_LGUI = 0x08;  // tecla Windows / Command
constexpr uint8_t KEY_MOD_RCTRL = 0x10;
constexpr uint8_t KEY_MOD_RSHIFT = 0x20;
constexpr uint8_t KEY_MOD_RALT = 0x40;
constexpr uint8_t KEY_MOD_RGUI = 0x80;

// Usages da página "Keyboard/Keypad" (0x07) da especificação HID Usage
// Tables. Só um subconjunto; acrescente o que precisar. (O HIDKeyboardTypes.h
// da NimBLE não traz esses códigos de forma utilizável, por isso ficam aqui.)
constexpr uint8_t HID_KEY_NONE = 0x00;
constexpr uint8_t HID_KEY_A = 0x04;
constexpr uint8_t HID_KEY_C = 0x06;
constexpr uint8_t HID_KEY_D = 0x07;
constexpr uint8_t HID_KEY_E = 0x08;
constexpr uint8_t HID_KEY_F = 0x09;
constexpr uint8_t HID_KEY_S = 0x16;
constexpr uint8_t HID_KEY_T = 0x17;
constexpr uint8_t HID_KEY_V = 0x19;
constexpr uint8_t HID_KEY_X = 0x1B;
constexpr uint8_t HID_KEY_Z = 0x1D;
constexpr uint8_t HID_KEY_ENTER = 0x28;
constexpr uint8_t HID_KEY_ESCAPE = 0x29;
constexpr uint8_t HID_KEY_BACKSPACE = 0x2A;
constexpr uint8_t HID_KEY_TAB = 0x2B;
constexpr uint8_t HID_KEY_SPACE = 0x2C;
constexpr uint8_t HID_KEY_F1 = 0x3A;  // F2..F12 = 0x3B..0x45
constexpr uint8_t HID_KEY_PRINT_SCREEN = 0x46;
constexpr uint8_t HID_KEY_DELETE = 0x4C;
constexpr uint8_t HID_KEY_ARROW_RIGHT = 0x4F;
constexpr uint8_t HID_KEY_ARROW_LEFT = 0x50;
constexpr uint8_t HID_KEY_ARROW_DOWN = 0x51;
constexpr uint8_t HID_KEY_ARROW_UP = 0x52;

// Usages da página "Consumer" (0x0C) — teclas de mídia.
constexpr uint16_t CONSUMER_NONE = 0x0000;
constexpr uint16_t CONSUMER_PLAY_PAUSE = 0x00CD;
constexpr uint16_t CONSUMER_NEXT_TRACK = 0x00B5;
constexpr uint16_t CONSUMER_PREV_TRACK = 0x00B6;
constexpr uint16_t CONSUMER_STOP = 0x00B7;
constexpr uint16_t CONSUMER_MUTE = 0x00E2;
constexpr uint16_t CONSUMER_VOLUME_UP = 0x00E9;
constexpr uint16_t CONSUMER_VOLUME_DOWN = 0x00EA;

// ------------------------------------------- atalhos do modo autônomo
// Cada tecla envia UMA das opções:
//   - tecla de mídia: consumer != 0 (modifiers/key são ignorados)
//   - combinação: modifiers (bitmask KEY_MOD_*) + key (HID_KEY_*)
// Tudo zerado = a tecla não faz nada no modo BLE (mas continua sendo
// reportada pela serial).
struct FallbackKey {
  uint16_t consumer;  // CONSUMER_*, ou 0
  uint8_t modifiers;  // KEY_MOD_* combinados com |, ou 0
  uint8_t key;        // HID_KEY_*, ou 0
};

constexpr FallbackKey FB_MEDIA(uint16_t usage) { return {usage, 0, 0}; }
constexpr FallbackKey FB_KEY(uint8_t mods, uint8_t key) { return {0, mods, key}; }
constexpr FallbackKey FB_NONE = {0, 0, 0};

const FallbackKey FALLBACK_KEYS[KEY_COUNT] = {
    // linha 0 — mídia
    /*  0 */ FB_MEDIA(CONSUMER_PLAY_PAUSE),
    /*  1 */ FB_MEDIA(CONSUMER_PREV_TRACK),
    /*  2 */ FB_MEDIA(CONSUMER_NEXT_TRACK),
    // linha 1 — volume e área de transferência
    /*  3 */ FB_MEDIA(CONSUMER_VOLUME_DOWN),
    /*  4 */ FB_MEDIA(CONSUMER_VOLUME_UP),
    /*  5 */ FB_MEDIA(CONSUMER_MUTE),
    /*  6 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_C),  // copiar
    /*  7 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_V),  // colar
    // linha 2 — edição
    /*  8 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_X),  // recortar
    /*  9 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_Z),  // desfazer
    /* 10 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_A),  // selecionar tudo
    /* 11 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_S),  // salvar
    /* 12 */ FB_KEY(KEY_MOD_LGUI, HID_KEY_D),   // mostrar área de trabalho
    // linha 3 — sistema
    /* 13 */ FB_KEY(KEY_MOD_LGUI, HID_KEY_E),                      // Explorer
    /* 14 */ FB_KEY(KEY_MOD_LALT, HID_KEY_TAB),                    // Alt+Tab
    /* 15 */ FB_KEY(KEY_MOD_LCTRL | KEY_MOD_LSHIFT, HID_KEY_ESCAPE),  // Gerenciador de Tarefas
    /* 16 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_F),  // localizar
    /* 17 */ FB_NONE,                           // livre
};

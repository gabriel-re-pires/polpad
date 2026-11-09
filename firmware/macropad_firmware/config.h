// Configuração do hardware: valores do PCB real (netlist do EasyEDA,
// conferida no hardware em 03/11/2026, ver docs/PINAGEM.md).
#pragma once

#include <Arduino.h>

// Comente para compilar sem o modo autônomo (teclado BLE); aí a
// NimBLE-Arduino nem precisa estar instalada.
#define ENABLE_BLE

// ============================================================== teclas
// Matriz 4x5 com 18 chaves; as posições vazias são o ESP32-C3 e o OLED.
// Índice usado no protocolo:
//
//            col 0   col 1   col 2   col 3   col 4
//   linha 0  [MCU]   [OLED]    0       1       2
//   linha 1    3       4       5       6       7
//   linha 2    8       9      10      11      12
//   linha 3   13      14      15      16      17
constexpr uint8_t KEY_ROWS = 4;
constexpr uint8_t KEY_COLS = 5;
constexpr uint8_t KEY_COUNT = 18;

// -1 = posição vazia.
constexpr int8_t KEY_INDEX[KEY_ROWS][KEY_COLS] = {
    {-1, -1, 0, 1, 2},
    {3, 4, 5, 6, 7},
    {8, 9, 10, 11, 12},
    {13, 14, 15, 16, 17},
};

// Linhas = lado dos diodos (de cima para baixo); colunas = lado dos
// soquetes (da esquerda para a direita). GPIO 20/21 ficam livres.
//
// Pinos de strapping do C3 (2, 8, 9) não podem ser linhas: uma tecla
// segurada no reset os levaria a LOW e mudaria o modo de boot. Como coluna
// ou I2C não há risco, porque em repouso ficam em HIGH (pull-up).
constexpr uint8_t ROW_PINS[KEY_ROWS] = {10, 7, 6, 5};
constexpr uint8_t COL_PINS[KEY_COLS] = {0, 1, 2, 3, 4};

// true = COL2ROW (cátodo para a linha): a linha vai a LOW e as colunas são
// lidas. false = o contrário. Conferido no hardware: COL2ROW.
constexpr bool DIODE_COL2ROW = true;

// A leitura precisa ficar diferente do estado por este tempo contínuo.
constexpr uint32_t DEBOUNCE_MS = 5;

// Espera após acionar uma linha, antes de ler as colunas.
constexpr uint32_t SCAN_SETTLE_US = 30;

// ============================================================= display
// SSD1306 128x64 via I2C.
constexpr uint8_t OLED_SDA = 8;
constexpr uint8_t OLED_SCL = 9;
constexpr uint8_t OLED_ADDR = 0x3C;
constexpr int16_t OLED_W = 128;
constexpr int16_t OLED_H = 64;
constexpr uint32_t OLED_I2C_HZ = 400000;

// ================================================================ host
// O host manda ping a cada 3 s; sem mensagem válida por este tempo, entra
// o modo autônomo.
constexpr uint32_t HOST_TIMEOUT_MS = 10000;

// ============================================================ modo BLE
#define BLE_DEVICE_NAME "Polpad"
#define BLE_MANUFACTURER "Polpad"
constexpr uint8_t BLE_BATTERY_LEVEL = 100;  // sem medição de bateria

// Modificadores (bitmask do 1º byte do relatório de teclado).
constexpr uint8_t KEY_MOD_LCTRL = 0x01;
constexpr uint8_t KEY_MOD_LSHIFT = 0x02;
constexpr uint8_t KEY_MOD_LALT = 0x04;
constexpr uint8_t KEY_MOD_LGUI = 0x08;  // Windows / Command
constexpr uint8_t KEY_MOD_RCTRL = 0x10;
constexpr uint8_t KEY_MOD_RSHIFT = 0x20;
constexpr uint8_t KEY_MOD_RALT = 0x40;
constexpr uint8_t KEY_MOD_RGUI = 0x80;

// Subconjunto da página HID Keyboard/Keypad (0x07). O HIDKeyboardTypes.h
// da NimBLE não traz esses códigos de forma utilizável.
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

// Página Consumer (0x0C): teclas de mídia.
constexpr uint16_t CONSUMER_NONE = 0x0000;
constexpr uint16_t CONSUMER_PLAY_PAUSE = 0x00CD;
constexpr uint16_t CONSUMER_NEXT_TRACK = 0x00B5;
constexpr uint16_t CONSUMER_PREV_TRACK = 0x00B6;
constexpr uint16_t CONSUMER_STOP = 0x00B7;
constexpr uint16_t CONSUMER_MUTE = 0x00E2;
constexpr uint16_t CONSUMER_VOLUME_UP = 0x00E9;
constexpr uint16_t CONSUMER_VOLUME_DOWN = 0x00EA;

// Atalhos do modo autônomo: tecla de mídia (consumer != 0) ou combinação
// modifiers + key. Tudo zerado = nada no BLE (a serial reporta igual).
struct FallbackKey {
  uint16_t consumer;
  uint8_t modifiers;
  uint8_t key;
};

constexpr FallbackKey FB_MEDIA(uint16_t usage) { return {usage, 0, 0}; }
constexpr FallbackKey FB_KEY(uint8_t mods, uint8_t key) { return {0, mods, key}; }
constexpr FallbackKey FB_NONE = {0, 0, 0};

const FallbackKey FALLBACK_KEYS[KEY_COUNT] = {
    // linha 0: mídia
    /*  0 */ FB_MEDIA(CONSUMER_PLAY_PAUSE),
    /*  1 */ FB_MEDIA(CONSUMER_PREV_TRACK),
    /*  2 */ FB_MEDIA(CONSUMER_NEXT_TRACK),
    // linha 1: volume e área de transferência
    /*  3 */ FB_MEDIA(CONSUMER_VOLUME_DOWN),
    /*  4 */ FB_MEDIA(CONSUMER_VOLUME_UP),
    /*  5 */ FB_MEDIA(CONSUMER_MUTE),
    /*  6 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_C),  // copiar
    /*  7 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_V),  // colar
    // linha 2: edição
    /*  8 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_X),  // recortar
    /*  9 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_Z),  // desfazer
    /* 10 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_A),  // selecionar tudo
    /* 11 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_S),  // salvar
    /* 12 */ FB_KEY(KEY_MOD_LGUI, HID_KEY_D),   // área de trabalho
    // linha 3: sistema
    /* 13 */ FB_KEY(KEY_MOD_LGUI, HID_KEY_E),                         // Explorer
    /* 14 */ FB_KEY(KEY_MOD_LALT, HID_KEY_TAB),                       // Alt+Tab
    /* 15 */ FB_KEY(KEY_MOD_LCTRL | KEY_MOD_LSHIFT, HID_KEY_ESCAPE),  // Gerenciador
    /* 16 */ FB_KEY(KEY_MOD_LCTRL, HID_KEY_F),  // localizar
    /* 17 */ FB_NONE,
};

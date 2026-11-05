# Protocolo de comunicação host ↔ macropad

Este documento é o **contrato entre o software de configuração (host) e o
firmware do ESP32-C3**. Quem for implementar o firmware deve seguir
exatamente estas mensagens.

## Transporte

- **USB CDC serial** (a porta serial nativa do ESP32-C3 via USB Serial/JTAG).
- **115200 bps**, 8N1.
- Mensagens **JSON em uma única linha**, terminadas por `\n` (JSON Lines).
- O host tolera linhas que não sejam JSON (logs de boot do ESP32 são
  ignorados), mas o firmware **não deve** imprimir logs após o boot para
  não poluir o canal.
- O firmware deve suportar linhas de entrada de até **2048 bytes**
  (necessário para a mensagem de imagem).

## Identificação da porta

O host procura portas com o VID USB da Espressif (`0x303A`) e confirma o
dispositivo com um handshake: envia `ping` e espera `pong` ou `hello`
em até 2 segundos.

## Mensagens: dispositivo → host

| Mensagem | Quando enviar |
|---|---|
| `{"t":"hello","fw":"2.0.0","keys":18,"screen":{"w":128,"h":64}}` | ao iniciar e **na primeira mensagem válida após um período sem host** (ver *Heartbeat*). Não a cada `ping`: o host responde a todo `hello` reenviando o quadro do display (~1,4 KB), então `hello` a cada 3 s desperdiçaria o canal. |
| `{"t":"pong"}` | em resposta a todo `ping` |
| `{"t":"key","k":0,"e":"down"}` | tecla pressionada (`k` = índice 0–17) |
| `{"t":"key","k":0,"e":"up"}` | tecla solta |

### Índice das teclas

O índice segue a **ordem de leitura do layout físico** do PCB, que é uma
grade de 4 linhas × 5 colunas com as duas primeiras posições da linha de
cima vazias (ali ficam o módulo ESP32-C3 e o display):

```
              [ 0] [ 1] [ 2]
    [ 3] [ 4] [ 5] [ 6] [ 7]
    [ 8] [ 9] [10] [11] [12]
    [13] [14] [15] [16] [17]
```

A tabela é a mesma nos dois lados: `KEY_LAYOUT` em
`src/polpad/core/models.py` e `KEY_INDEX` em
`firmware/macropad_firmware/config.h`. A matriz elétrica (que GPIO é linha
e qual é coluna) é detalhe do firmware; o host só conhece o índice.

O firmware deve aplicar *debounce* por tempo de estabilidade (~5 ms) antes
de reportar eventos. Eventos de tecla que o host receber **antes** da
resposta ao seu primeiro `ping` são considerados represados (gerados
enquanto ninguém lia a porta) e descartados.

## Mensagens: host → dispositivo

| Mensagem | Efeito |
|---|---|
| `{"t":"ping"}` | responder `pong` (precedido de `hello` se o host estava ausente); também funciona como *heartbeat* |
| `{"t":"text","lines":["VS Code"]}` | limpar o display e exibir até 3 linhas centralizadas (fonte 5x7 da Adafruit GFX; 1 linha em tamanho 2, mais de uma em tamanho 1; altura de linha `8*tamanho + 4`; bloco centralizado verticalmente) |
| `{"t":"img","fmt":"xbm1","d":"<base64>"}` | exibir imagem em tela cheia |

**Na prática o host só usa `img`.** Toda a composição (ícone do perfil,
nome centralizado, tela personalizada com hora e data) é feita no PC com a
mesma fonte do firmware
(`core/oled_render.py`, `core/display.py`), e o resultado vai como bitmap.
Isso mantém o firmware mínimo e garante que o preview na interface seja
idêntico ao hardware. `text` continua no contrato como recurso de
diagnóstico e para hosts simples.

O host suprime o reenvio de um quadro idêntico ao último enviado, exceto
após um `hello` (o dispositivo pode ter reiniciado). Na troca de perfil
com a tela personalizada, o host envia o ícone e, 1,5 s depois, a tela
montada: dois `img` em sequência. O firmware mantém buffer de recepção
de 4 KB e I2C a 400 kHz, para que o redesenho de um quadro (~25 ms) não
faça o próximo transbordar.

### Formato de imagem `xbm1`

- 128×64 pixels, 1 bit por pixel → **1024 bytes**, codificados em base64
  (~1368 caracteres).
- Varredura por linhas; 8 pixels por byte; **bit mais significativo =
  pixel mais à esquerda**; `1` = pixel aceso.
- Com a biblioteca Adafruit SSD1306, basta decodificar o base64 para um
  buffer de 1024 bytes e chamar
  `display.drawBitmap(0, 0, buffer, 128, 64, SSD1306_WHITE)`.

## Sequência típica

```
Firmware                     Host (software)
   |<------ ping ------------------|   (host encontrou a porta)
   |------- hello ---------------->|   (primeiro contato após boot/timeout)
   |------- pong ----------------->|
   |<------ img -------------------|   (tela do perfil ativo)
   |------- key k=4 down --------->|   (host executa a ação da tecla 4)
   |------- key k=4 up ----------->|
   |------- key k=17 down -------->|   (tecla de modo: host troca o perfil)
   |<------ img -------------------|   (tela do novo perfil)
   |<------ ping ------------------|   (a cada 3 s)
   |------- pong ----------------->|   (sem hello: o host já é conhecido)
```

Observação de arquitetura: **toda a lógica de atalhos fica no host**. O
firmware só reporta teclas e desenha o que o host mandar. Isso permite
perfis ilimitados, ações complexas (comandos de terminal, Home Assistant)
e reconfiguração sem regravar o firmware.

## Heartbeat e modo híbrido

O host envia `ping` a cada **3 segundos** enquanto conectado. O firmware
considera o host **presente** se recebeu qualquer mensagem válida nos
últimos **10 segundos**; caso contrário, entra no **modo autônomo**:
atua como teclado Bluetooth (BLE HID) com atalhos fixos gravados no
firmware. Os eventos de tecla continuam sendo emitidos pela serial em
ambos os modos (assim o software "pega" o dispositivo imediatamente ao
abrir). Quando o host volta a ser visto depois de ausente, o firmware
envia um `hello`: é o gatilho para o host restaurar o display. A
implementação de referência está em `firmware/`.

Por que BLE e não USB HID: o periférico USB do ESP32-C3 é um controlador
Serial/JTAG de função fixa; ele **não** consegue se apresentar como
teclado HID (isso exige ESP32-S2/S3). O modo autônomo via Bluetooth é a
forma de o dispositivo funcionar "sem driver" em qualquer computador ou
celular.

### Esqueleto do lado do firmware (Arduino, pseudocódigo)

```cpp
void loop() {
  // 1. Varre a matriz de teclas com debounce; em cada mudança:
  //    Serial.printf("{\"t\":\"key\",\"k\":%d,\"e\":\"%s\"}\n", k, down ? "down" : "up");
  // 2. Lê linhas da Serial; usa ArduinoJson para decodificar:
  //    - "ping" -> responde pong (+ hello antes, se o host estava ausente)
  //    - "text" -> display.clearDisplay(); imprime as linhas; display.display();
  //    - "img"  -> base64-decode de d para buf[1024]; drawBitmap; display.display();
}
```

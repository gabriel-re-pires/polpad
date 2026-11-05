# Firmware do macropad (ESP32-C3)

Firmware de referência (v2.0.2) que implementa o contrato de
[docs/PROTOCOLO.md](../docs/PROTOCOLO.md) e o **modo híbrido**:

- **Modo estendido**: com o software aberto no PC (mesmo em segundo
  plano na bandeja), as teclas são reportadas pela USB serial e o
  software executa as ações. O display mostra o que o software compõe
  (mapa de teclas do perfil, ícone ou nome).
- **Modo autônomo**: sem o software (ou em outro computador/tablet),
  o macropad funciona como **teclado Bluetooth LE (BLE HID)**, reconhecido
  nativamente pelo sistema, com os atalhos fixos de `config.h`.

A detecção é automática. O software envia `ping` a cada 3 s; ficando
10 s sem mensagens válidas, o firmware assume que o host saiu e passa a
replicar as teclas via BLE. Ele volta sozinho quando o software reabre.
Os eventos de tecla saem pela serial **nos dois modos**. O `hello` é
enviado no boot e a cada vez que o host passa de ausente para presente
(não a cada `ping`).

O ESP32-C3 **não tem USB HID nativo**: a USB dele é um periférico fixo
Serial/JTAG (CDC). Por isso o teclado do modo autônomo é BLE, não USB.

## Hardware

- ESP32-C3 SuperMini (GPIO 0–10, 20, 21).
- 18 chaves com diodo numa matriz elétrica **4 linhas × 5 colunas**
  (20 posições, 18 ocupadas).
- OLED SSD1306 128×64 I2C (endereço 0x3C), I2C a 400 kHz.

Layout físico e índice das teclas (o mesmo da grade do software):

|         | col 0 | col 1  | col 2 | col 3 | col 4 |
|---------|-------|--------|-------|-------|-------|
| linha 0 | (MCU) | (OLED) | 0     | 1     | 2     |
| linha 1 | 3     | 4      | 5     | 6     | 7     |
| linha 2 | 8     | 9      | 10    | 11    | 12    |
| linha 3 | 13    | 14     | 15    | 16    | 17    |

Pinagem padrão (**a confirmar contra o PCB**):

| Função | GPIOs |
|---|---|
| Linhas (saída LOW na varredura) | 0, 1, 3, 10 |
| Colunas (INPUT_PULLUP) | 4, 5, 6, 7, 21 |
| OLED SDA / SCL | 8 / 9 |
| Livres | 2, 20 |

GPIO 2, 8 e 9 são pinos de *strapping*. Eles não são usados como linhas
da matriz; a justificativa está nos comentários de `config.h`. Na
SuperMini, o GPIO8 também tem o LED azul onboard, que pode piscar junto
com o tráfego do I2C. Isso é normal.

## O que ajustar antes de gravar

Tudo fica em **`macropad_firmware/config.h`**. Os itens marcados com
`AJUSTAR` são:

1. `ROW_PINS` / `COL_PINS`: GPIOs da matriz conforme o PCB.
2. `KEY_INDEX`: tabela linha × coluna → índice da tecla (-1 = vazio).
   Se no PCB as linhas e colunas estiverem trocadas em relação à tabela
   acima, corrija aqui. Uma verificação em tempo de compilação garante que
   cada tecla 0–17 aparece exatamente uma vez.
3. `DIODE_COL2ROW`: `true` se o cátodo (faixa) do diodo estiver voltado
   para a linha (o firmware leva a linha a LOW e lê as colunas). Use
   `false` se estiver voltado para a coluna.
4. `OLED_SDA` / `OLED_SCL` / `OLED_ADDR`: I2C do display.
5. `FALLBACK_KEYS`: os 18 atalhos do modo autônomo. Cada tecla usa
   `FB_MEDIA(CONSUMER_...)`, `FB_KEY(KEY_MOD_..., HID_KEY_...)` ou
   `FB_NONE`. O padrão é:
   - 0–2: play/pause, anterior, próxima
   - 3–7: vol−, vol+, mudo, Ctrl+C, Ctrl+V
   - 8–12: Ctrl+X, Ctrl+Z, Ctrl+A, Ctrl+S, Win+D
   - 13–17: Win+E, Alt+Tab, Ctrl+Shift+Esc, Ctrl+F, (nada)

Além deles, `ENABLE_BLE` liga o modo autônomo: comente para compilar sem
ele (ver [Compilar sem o Bluetooth](#compilar-sem-o-bluetooth)).

## Bibliotecas

Instale pelo Gerenciador de Bibliotecas ou pelo `arduino-cli lib install`:

- **Adafruit SSD1306** (instala junto Adafruit GFX e Adafruit BusIO)
- **ArduinoJson** 7.x (testado com 7.4.3)
- **NimBLE-Arduino** 2.5.x (testado com 2.5.0) — só com o modo autônomo
  ligado (`ENABLE_BLE`)

A biblioteca **ESP32-BLE-Keyboard (T-vK) não é mais usada**: ela está sem
manutenção e não compila no arduino-esp32 3.x. O teclado BLE é
implementado diretamente no `.ino` com o `NimBLEHIDDevice` da
NimBLE-Arduino.

## Compilação

Use o core **esp32:esp32 3.3.x** (testado com 3.3.10).

Arduino IDE: placa **ESP32C3 Dev Module**, **USB CDC On Boot: Enabled**.
Essa opção é essencial: sem ela, o `Serial` não sai pela USB. Use
**Partition Scheme: Default 4MB with spiffs (1.2MB APP)**, que é suficiente.

Pelo arduino-cli:

```
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc --warnings default macropad_firmware
```

(Acrescente `--config-file <caminho do arduino-cli.yaml>` se usar o
arduino-cli embutido no Arduino IDE.) Resultado de referência:

```
Sketch uses 630553 bytes (48%) of program storage space. Maximum is 1310720 bytes.
Global variables use 27620 bytes (8%) of dynamic memory, leaving 300060 bytes for local variables. Maximum is 327680 bytes.
```

Para gravar, acrescente `-u -p COMx` ou use o botão Upload da IDE. Se a
placa não entrar em modo de gravação, segure **BOOT**, toque **RESET** e
solte BOOT.

### Compilar sem o Bluetooth

O modo autônomo é opcional. Comentando esta linha no `config.h`:

```cpp
#define ENABLE_BLE
```

o firmware compila apenas com Adafruit SSD1306 e ArduinoJson — a
NimBLE-Arduino nem precisa estar instalada. O macropad continua completo
pela USB, que é como ele funciona com o software aberto; some apenas o
teclado Bluetooth de quando o software está fechado, e o display passa a
mostrar "Modo USB apenas" na tela de espera.

Serve para testar o hardware por partes: valida a matriz de teclas, o
display e a comunicação com o software antes da parte BLE. Depois é só
descomentar.

## Pareamento Bluetooth (modo autônomo)

1. Ligue o macropad. A tela mostra "Aguardando host..." e "BLE: pareavel".
2. No Windows, abra *Configurações → Bluetooth e dispositivos → Adicionar
   dispositivo → Bluetooth*. No Android/macOS, abra a tela de Bluetooth.
3. Escolha **"Polpad"**. O pareamento é do tipo *just works*, sem
   PIN, e o vínculo fica salvo nos dois lados.
4. A tela passa a mostrar "BLE: conectado".

Se o pareamento ficar inconsistente (ex.: depois de regravar com outra
configuração de BLE), remova o dispositivo no sistema e pareie de novo.
Se ainda assim não funcionar, grave com *Erase All Flash Before Sketch
Upload: Enabled* para apagar os vínculos salvos no ESP32.

Os atalhos BLE só são enviados quando o **host está ausente** e há uma
central BLE conectada. Com o software aberto, as teclas vão apenas pela
serial (o software decide o que fazer), mesmo que o BLE esteja pareado.

## Procedimento de teste

1. **Serial sem o software**: abra o Monitor Serial (qualquer baud) e
   reinicie a placa. Deve aparecer
   `{"t":"hello","fw":"2.0.2","keys":18,"screen":{"w":128,"h":64}}`.
   Como o reset derruba a USB, o monitor pode perder essa linha. Nesse
   caso, use o passo 3.
2. **Teclas**: pressione cada tecla e confira se aparece
   `{"t":"key","k":N,"e":"down"}` e depois `"up"`, com o N da tabela de
   layout. Índices trocados indicam que `ROW_PINS`, `COL_PINS` ou
   `KEY_INDEX` precisam de ajuste. Se nenhuma tecla responder, teste
   `DIODE_COL2ROW = false`.
3. **Protocolo manual**: no Monitor Serial (final de linha "Nova linha"),
   envie `{"t":"ping"}`. A resposta é `hello` (primeira mensagem após
   ausência) e `pong`. Os próximos `ping` só respondem `pong`. A tela mostra
   "PC conectado". Envie `{"t":"text","lines":["Teste"]}` e o texto deve
   aparecer grande e centralizado.
4. **Software**: feche o monitor e abra o software do PC. O status deve
   mudar para "Conectado" e o display deve mostrar o perfil ativo.
5. **Modo autônomo**: feche o software (Sair na bandeja). Em cerca de
   10 s o display volta a "Aguardando host...". Com o macropad pareado via
   Bluetooth, as teclas enviam os atalhos fixos (teste play/pause e
   volume).
6. **Volta ao host**: reabra o software. O firmware reenvia `hello`, o
   software reenvia o perfil e as teclas deixam de ir pelo BLE.

## Publicar uma versão

O configurador grava uma **imagem única** (bootloader + tabela de
partições + aplicação), o que o dispensa de conhecer o layout de
partições escolhido na compilação. A Arduino IDE, porém, exporta os três
arquivos separados — `tools/merge_firmware.py` os funde:

1. Atualize `FW_VERSION` no `.ino` (é ele quem aparece no aplicativo e
   nomeia o arquivo gerado).
2. Na Arduino IDE: **Sketch → Exportar Binário Compilado**.
3. Na raiz do projeto:

   ```powershell
   .venv\Scripts\python tools\merge_firmware.py
   ```

   Sem argumentos o script procura a exportação dentro de `firmware/`;
   passe a pasta se ela estiver em outro lugar. O resultado é
   `dist\firmware-<versao>.bin`.
4. Anexe esse arquivo ao *release* do GitHub. O nome precisa casar com
   `firmware*.bin` — é assim que o aplicativo o encontra entre os anexos.

Para testar antes de publicar, use **Arquivo .bin no computador** no
diálogo de gravação; a exportação crua (`*.ino.bin`) também serve, e vai
para 0x10000 preservando o bootloader já gravado no chip.

## Observações

- Texto no display: o software converte acentos para ASCII antes de
  enviar, porque a fonte da Adafruit GFX não tem acentuação.
- O firmware não imprime logs de texto livre na serial, porque o canal é
  exclusivo do protocolo.
- Linhas recebidas com mais de 2048 bytes são descartadas inteiras, até
  o próximo `\n`.
- Se nenhum programa estiver lendo a porta, as mensagens que não couberem
  no buffer de TX são descartadas, para não travar a varredura.

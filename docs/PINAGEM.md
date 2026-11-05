# Pinagem do PCB

Este documento registra como a pinagem em
`firmware/macropad_firmware/config.h` foi obtida, para que ninguém precise
descobrir de novo — e para que uma eventual divergência futura possa ser
rastreada até a evidência.

Levantada em 03/11/2026 a partir do projeto do PCB no EasyEDA e conferida
no hardware montado.

## Como foi levantada

O projeto do PCB foi desenhado **sem esquemático**: os componentes foram
posicionados e as trilhas roteadas direto no editor de placa. Como
consequência, o EasyEDA não oferece exportação de netlist, e os pads do
módulo ESP32-C3 e do OLED aparecem sem net atribuída — quem carrega as
nets são pads soltos sobrepostos ao footprint.

A pinagem foi então reconstruída pela geometria, a partir do arquivo
`.json` do projeto (`Arquivo → Exportar → EasyEDA`): para cada trilha, os
vértices foram cruzados com as coordenadas dos pads, e os pads do módulo
foram identificados pelos rótulos de serigrafia do próprio footprint.

O resultado foi confirmado no hardware com um sketch que varre a matriz
nos **dois sentidos possíveis** e reporta, por tecla, o GPIO da linha, o
GPIO da coluna e o designador do soquete. Todas as teclas responderam na
posição prevista.

## Matriz

Quatro linhas por cinco colunas, 20 posições para 18 teclas. As duas
posições do canto superior esquerdo não têm tecla: é onde o módulo
ESP32-C3 e o display OLED ficam montados.

|            | **GPIO0** | **GPIO1** | **GPIO2** | **GPIO3** | **GPIO4** |
|------------|-----------|-----------|-----------|-----------|-----------|
| **GPIO10** | —         | —         | SW10      | SW11      | SW18      |
| **GPIO7**  | SW1       | SW4       | SW9       | SW12      | SW17      |
| **GPIO6**  | SW2       | SW5       | SW8       | SW13      | SW16      |
| **GPIO5**  | SW3       | SW6       | SW7       | SW14      | SW15      |

- **Linhas** (saídas, acionadas em LOW na varredura) — lado dos **diodos**:
  GPIO 10, 7, 6, 5, de cima para baixo.
- **Colunas** (`INPUT_PULLUP`) — lado dos **soquetes Kailh**:
  GPIO 0, 1, 2, 3, 4, da esquerda para a direita.

A contagem fecha pelos dois lados: 3+3+4+4+4 = 18 pelo lado dos soquetes e
5+5+5+3 = 18 pelo lado dos diodos.

### Índice da tecla por designador

| Índice | Soquete | Índice | Soquete | Índice | Soquete |
|--------|---------|--------|---------|--------|---------|
| 0      | SW10    | 6      | SW12    | 12     | SW16    |
| 1      | SW11    | 7      | SW17    | 13     | SW3     |
| 2      | SW18    | 8      | SW2     | 14     | SW6     |
| 3      | SW1     | 9      | SW5     | 15     | SW7     |
| 4      | SW4     | 10     | SW8     | 16     | SW14    |
| 5      | SW9     | 11     | SW13    | 17     | SW15    |

O índice segue a ordem de leitura da grade (0 = primeira posição com tecla,
no alto à esquerda). Note que ele **não** acompanha a numeração dos
designadores: a tecla 0 é o SW10.

## Orientação dos diodos

`DIODE_COL2ROW = true`, ou seja, cátodo voltado para a linha.

Confirmado por experimento, não por inspeção visual do componente: a
varredura de teste percorreu a matriz nos dois sentidos a cada ciclo e
registrou **613 detecções no sentido COL2ROW e nenhuma no sentido oposto**.

## Display

OLED SSD1306 128x64 por I2C: **SDA = GPIO8**, **SCL = GPIO9**, alimentado
em 3V3. Endereço 0x3C.

## Pinos livres

GPIO 20 e 21 (RX/TX da UART0) não são usados pela placa.

Dos pinos de strapping do ESP32-C3 (2, 8 e 9), nenhum é linha da matriz:
o GPIO2 é coluna e fica em HIGH por pull-up em repouso, e o GPIO8/9 ficam
com o I2C, que também repousa em HIGH. É a condição que o C3 precisa no
reset para dar boot pela flash.

## Teclas com defeito na primeira placa montada

Na primeira unidade montada, **SW7 (índice 15)** e **SW14 (índice 16)** não
respondem. Ambas estão na linha GPIO5, que funciona nas outras três teclas,
e nas colunas GPIO2 e GPIO3, que funcionam nas outras seis — o defeito é
pontual nos dois cruzamentos.

Não é diodo invertido: um diodo ao contrário teria sido detectado no
sentido oposto da varredura, que deu zero. Aponta para circuito aberto nos
diodos D25 (do SW7) e D30 (do SW14), ou nos soquetes.

É um defeito de montagem daquela unidade, não do projeto.

# Polpad — análise completa e proposta de projeto

*Revisão de 27/10/2026, sobre o estado do repositório após o commit
`862aa26` e as mudanças descritas na seção 6.*

## 1. Resumo executivo

O repositório contém **os dois lados** do produto: o **firmware em C++**
(Arduino) que roda no ESP32-C3 soldado no PCB (`firmware/`) e o
**software de configuração em Python/Qt** que roda no PC
(`src/polpad/`), além de documentação, testes e um empacotador para
`.exe`. O software já era funcional e bem estruturado (camadas, 72
testes, lint e tipos limpos, executável único). O firmware existia como
"referência" nunca compilada nem gravada.

Os quatro problemas que mais importavam, e o que foi feito com cada um:

| # | Problema | Impacto | Situação |
|---|---|---|---|
| 1 | O texto original prometia "reconhecido nativamente como teclado USB HID"; o **ESP32-C3 não tem USB HID** (a USB dele é Serial/JTAG de função fixa). | Promessa inviável; revisores podem cobrar. | Decisão: manter o C3 com arquitetura **híbrida** (USB serial + software; Bluetooth LE HID sem software). O texto do artigo precisa refletir isso (seção 10). |
| 2 | Software e firmware assumiam uma grade **3×6**; o PCB é **4×5 com 18 posições ocupadas** (linha de cima só com 3 teclas, à direita). | Teclas na tela não correspondiam às físicas. | **Corrigido** nos dois lados a partir de uma única tabela de layout. |
| 3 | O display mostrava só o nome ou o ícone do perfil. A tese do projeto é "teclas rotuladas pelo display". | A hipótese central não estava materializada. | **Implementado** o mapa de teclas no OLED (nome do perfil + abreviação de cada tecla na posição física, com destaque da tecla pressionada), composto no PC com a mesma fonte do firmware. |
| 4 | Firmware dependia de biblioteca sem manutenção (ESP32-BLE-Keyboard) que não compila no core atual; nunca foi compilado. | Risco de não gravar nunca. | **Reescrito** com NimBLE 2.5 nativo, matriz 4×5, debounce correto, buffers dimensionados. **Compila** (630 KB, 48 % da flash, sem avisos). |

O que **não** foi possível fazer aqui e fica para o bancada: gravar o
firmware, confirmar os GPIOs e a orientação dos diodos contra o PCB (os
arquivos do esquemático não estão no disco), parear o BLE e medir
latência. A seção 8 traz o roteiro.

## 2. O que existe no repositório

```
firmware/macropad_firmware/   firmware ESP32-C3 (Arduino C++): .ino + config.h
src/polpad/                 software do PC (Python 3.11+, PySide6)
  core/      modelos, layout, perfis, persistência, telas do display, controlador
  device/    protocolo JSON-serial, enlace pyserial, simulador
  actions/   motor de ações (registry + duas filas de execução)
  integrations/  Home Assistant, OBS Studio, app em foco (Win32)
  ui/        janela principal, grade, editor de ações, bandeja, diálogos
tests/                        100 testes unitários (unittest)
tools/                        gerador de ícone e do executável (PyInstaller)
docs/                         PROTOCOLO.md, ARQUITETURA.md, este documento
```

Linhas de código (antes desta revisão): ≈5.600 de Python, 270 de C++.
Qualidade: `ruff` (inclui regras de segurança do bandit) e `mypy`
limpos; executável único de 61 MB publicado em release no GitHub.

**Como funciona (arquitetura host-agent).** O firmware é propositalmente
"burro": varre a matriz, reporta `{"t":"key","k":N,"e":"down|up"}` pela
USB serial e desenha o que o PC manda. Toda a inteligência (perfis,
atalhos, macros, integrações) fica no software, que roda na bandeja do
Windows. Vantagens: perfis ilimitados sem regravar firmware, ações que um
teclado HID não faz (comandos, HTTP, OBS, Home Assistant), display
atualizado pelo PC. Sem o software, o firmware vira teclado Bluetooth com
atalhos fixos.

## 3. Realidade do hardware

### 3.1 ESP32-C3 e USB HID

O ESP32-C3 expõe pela USB apenas o controlador **USB Serial/JTAG**, de
função fixa (CDC-ACM + JTAG). Não há controlador USB OTG programável, o
que exclui TinyUSB e qualquer classe HID pela USB. Isso é confirmado pela
Espressif e pela lista de alvos do TinyUSB (ESP32-S2/S3/P4). O
`docs/ARQUITETURA.md` já registrava o fato; o resumo do artigo, não.

Alternativas avaliadas:

| Opção | O que muda | Custo | Veredito |
|---|---|---|---|
| **A. Manter o C3, arquitetura híbrida** (USB serial + software; BLE HID autônomo) | Nada no hardware; reescrever a promessa do artigo. | Zero | **Recomendada.** É o que está implementado. O "sem driver" vale para o BLE em qualquer SO/celular; pela USB, o software é a inteligência. |
| B. Trocar por ESP32-S3 (USB OTG + BLE) | Novo PCB ou módulo compatível; TinyUSB HID + CDC composto. | Refabricar e ressoldar | Só se houver uma segunda rodada de PCB. Ganha "USB HID de verdade" mantendo o resto. |
| C. Chip ponte serial→HID (CH9329) ou ATmega32U4 auxiliar | Chip extra no PCB. | Novo PCB | Mais peças para o mesmo resultado da opção B. Não recomendada. |

### 3.2 Layout do PCB

Pelas imagens do PCB: 18 switches em **4 linhas × 5 colunas**, com as
duas primeiras posições da linha de cima ocupadas pelo módulo e pelo
display. Índice das teclas (ordem de leitura) usado em todo o projeto:

```
              [ 0] [ 1] [ 2]
    [ 3] [ 4] [ 5] [ 6] [ 7]
    [ 8] [ 9] [10] [11] [12]
    [13] [14] [15] [16] [17]
```

Fonte única no software: `KEY_LAYOUT` em `src/polpad/core/models.py`.
No firmware: `KEY_INDEX` em `config.h` (com `static_assert` de
consistência). A matriz elétrica pode ser 4×5 em qualquer orientação; o
host só conhece o índice.

### 3.3 Pinos do ESP32-C3 SuperMini

O módulo expõe GPIO 0–10, 20 e 21 (13 GPIOs). A matriz 4×5 precisa de 9 e
o I2C de 2, total 11. Restrições:

- **GPIO 2, 8 e 9 são de *strapping*** (lidos no reset). GPIO 9 é o
  botão BOOT (LOW no reset = modo download); GPIO 8 tem o LED azul da
  placa.
- Pinos de strapping **não podem ser linhas de varredura** (uma tecla
  segurada no reset poderia levá-los a LOW), mas **podem ser colunas**
  (ficam em HIGH pelo pull-up, só vão a LOW quando o firmware aciona uma
  linha) ou **I2C** (repouso em HIGH).
- GPIO 20/21 são a UART0; com a USB CDC em uso ficam livres.

Escolha padrão no `config.h` (marcada **AJUSTAR** até conferência com o
esquemático): linhas 0, 1, 3, 10; colunas 4, 5, 6, 7, 21; I2C SDA 8 /
SCL 9 (padrão Arduino do C3). GPIO 2 e 20 ficam livres. A orientação dos
diodos é configurável (`DIODE_COL2ROW`).

**Pendência:** não há arquivo de esquemático/PCB no disco. É preciso
abrir o projeto da placa (EasyEDA/KiCad/Proteus) e conferir: quais GPIOs
vão para linhas, quais para colunas, o lado do diodo, e os pinos do
header do OLED. Sem isso nada funciona, e é a primeira tarefa de bancada.

### 3.4 Display

SSD1306 128×64 I2C. Um quadro são 1024 bytes; a 400 kHz o `display()`
leva ~25 ms (a 100 kHz, ~90 ms). Por isso o firmware fixa 400 kHz e o
buffer de recepção da USB em 4 KB: o host manda até dois quadros em
sequência (tecla destacada e depois normal).

A fonte do firmware (Adafruit GFX 5×7) dá 21 colunas × 8 linhas de
texto. Um mapa de 5 colunas × 3 caracteres + 4 espaços = 19 caracteres
cabe; 4 caracteres por tecla não cabem. Daí a abreviação de 3 letras.

## 4. Diagnóstico do firmware (versão anterior) e o que mudou

| Achado | Problema | Correção |
|---|---|---|
| Matriz 3×6 | Não é o PCB. | Matriz 4×5 + tabela `KEY_INDEX`, posições vazias = -1. |
| Biblioteca ESP32-BLE-Keyboard (T-vK) | Sem manutenção; não compila no core esp32 3.x; precisava de fork. | Teclado BLE HID implementado direto com `NimBLEHIDDevice` (NimBLE 2.5): report map de teclado + consumer control, bonding *just works*, re-anúncio ao desconectar. |
| `hello` a cada `ping` | O host reenviava o quadro do display (1,4 KB) a cada 3 s. | `hello` só no boot e na transição ausente→presente. |
| Debounce por "lockout" | Um bounce na borda dos 5 ms podia gerar toque duplo. | Debounce por tempo de estabilidade, por tecla. |
| Buffer RX padrão (256 B) | Uma mensagem `img` de 1,4 KB transbordava se o loop estivesse ocupado desenhando. | `setRxBufferSize(4096)` antes do `begin()`. |
| Escrita na serial bloqueante | Com o cabo ligado e nenhum programa lendo, o HWCDC do core 3.3 bloqueia ~2 s por escrita, travando a varredura. | `setTxTimeoutMs(5)`, TX de 1 KB, descarte de mensagem inteira quando não cabe. |
| Linha longa demais | Reiniciava o buffer no meio e interpretava o resto como linha nova. | Flag "descartar até o `\n`". |
| I2C a 100 kHz | Redesenho lento. | 400 kHz nos dois parâmetros do construtor (senão a lib volta a 100 kHz após cada envio). |
| Pinos de strapping como linhas | Risco de modo download com tecla segurada. | Estratégia documentada em `config.h`; linhas em alta impedância quando inativas. |

Resultado: compila com `esp32:esp32:esp32c3:CDCOnBoot=cdc`, 630.553
bytes (48 %), 27,6 KB de RAM estática, sem avisos. Comando completo em
`firmware/README.md`.

O que ainda pode ser necessário após o teste em bancada: inverter
`DIODE_COL2ROW`, trocar linhas por colunas, ajustar o endereço do OLED
(0x3C ou 0x3D), e, se o Windows não aceitar os parâmetros de conexão
BLE, remover a chamada `updateConnParams`.

## 5. Diagnóstico do software (versão anterior) e o que mudou

### 5.1 Defeitos e limitações encontrados

| Onde | Achado | Correção |
|---|---|---|
| `device/link.py` `_handshake` | Descartava o resto do buffer após o `pong`: o `hello` que vem junto se perdia e o display só atualizava 3 s depois. | O handshake devolve as mensagens já decodificadas e o resto do buffer. |
| `device/link.py` | Teclas represadas no firmware (cabo ligado, app fechado) eram executadas ao abrir o app: ações fantasmas. | Eventos de tecla recebidos antes do `pong` são descartados. |
| `device/link.py` `_run` | Avisava "desconectado" para portas que nunca passaram no handshake. | Só avisa quedas de conexões anunciadas. |
| `core/controller.py` | Reenviava o display a cada `hello` (3 s). | Quadro idêntico não é reenviado; `hello` força. |
| `ui/key_grid.py`, `simulator_window.py`, `app_icon.py` | Grade 3×6. | Derivam de `KEY_LAYOUT`; a linha de cima mostra o espaço do módulo. |
| `ui/oled_preview.py` | Preview de texto com Arial 22/14 px: não era "exatamente o que aparecerá no OLED". | Renderização com a fonte real da GFX (`core/oled_font.py`, `core/oled_render.py`), idêntica pixel a pixel. |
| `ui/settings_dialog.py` | Nota dizia que o token fica em texto no arquivo; já estava no Credential Manager. | Nota corrigida. |
| `ui/action_editor.py` | Atalho só por digitação (`ctrl+shift+p`). | Campo **Gravar**: pressione a combinação e ela é transcrita. |
| Display | Só nome/ícone do perfil. | Mapa de teclas (seção 6.2), campo "No display" por ação, destaque da tecla pressionada, opções em Configurações. |

Não alterados, mas registrados para a próxima fase:

- `integrations/foreground.py` usa `ctypes` sem `restype/argtypes`
  (funciona porque handles do Windows cabem em 32 bits, mas é frágil);
  e consulta o app em foco por *polling* de 1 s. Um `SetWinEventHook`
  (`EVENT_SYSTEM_FOREGROUND`) dá troca instantânea sem polling.
- O `QKeySequenceEdit` mostra o placeholder em inglês ("Press shortcut")
  por limitação do Qt.
- Perfis e "apps vinculados" cobrem a configuração por aplicativo, mas a
  interface não deixa isso evidente (ver seção 7).
- Sem assinatura de código: o SmartScreen avisa na primeira execução.

### 5.2 O que foi adicionado

- `core/models.py`: `GRID_ROWS/GRID_COLS/KEY_LAYOUT/key_at`,
  `Action.short` + `display_short`, `short_label()`,
  `Settings.display_mode` ("mapa"/"icone") e `Settings.key_feedback`.
  Arquivos de configuração antigos continuam válidos (campos novos têm
  padrão).
- `core/oled_font.py` (tabela da fonte 5×7, BSD) e `core/oled_render.py`
  (desenho de texto idêntico ao `display.print()` do firmware, tela
  `text` reproduzida com a mesma geometria).
- `core/display.py`: `keymap_frame`, `profile_frame`, `title_frame`
  (nomes longos descem de tamanho em vez de cortar), `frame_payload`,
  `frame_from_message`.
- `core/controller.py`: composição do quadro, supressão de reenvio,
  destaque da tecla com temporizador injetado (`schedule`), sem Qt.
- 28 testes novos: layout, abreviações, fonte (geometria bit a bit),
  mapa, handshake, retorno visual.

## 6. Comparação com a referência (Raccoon Panel) e o que adotar

As capturas do Raccoon Panel mostram um produto com knob, LEDs RGB,
Pomodoro, Wallpaper Engine e SignalRGB. Nada disso se aplica ao macropad
(só teclas, 18, OLED mono, sem LED). O que **vale adotar** é o modelo de
interação:

| Recurso da referência | No macropad hoje | Proposta |
|---|---|---|
| Abas por assunto (Computer control, Home Assistant, Other) | Tudo numa janela + diálogo de configurações | Abas: **Teclas**, **Aplicativos**, **Integrações**, **Dispositivo**. |
| *Global* vs *Program specific* com seletor de programa e "Add running program" | Perfis + "Apps vinculados" (escondido num botão) | Trazer o vínculo com aplicativo para o primeiro plano: o seletor de perfil mostra o(s) executável(is) vinculado(s), botão "Adicionar programa em execução" (lista de janelas abertas), e um perfil **Global** que vale quando nenhum app vinculado está em foco. |
| Mockup do dispositivo à esquerda, sempre visível, com o conteúdo da tela | Grade + preview do OLED (já no layout real) | Manter; o mapa de teclas já aparece no preview. |
| Por botão: *Name*, *Picture*, *Does what, in order* (lista de passos) | Rótulo, abreviação, uma ação (ou uma macro com passos) | Unificar: **toda tecla é uma lista de passos**; uma ação simples é uma lista de um passo. O editor deixa de ter o tipo "Macro" como caso especial. |
| Knob (esquerda/aperto/direita) | Não existe | Não se aplica. |
| Cores por botão | Não existe | Não se aplica (OLED mono). |

O modelo de dados já suporta tudo isso: `Profile.auto_apps` é o vínculo
com programas; `macro.steps` é a lista de passos. A mudança é de
interface, não de domínio.

### 6.1 Wireframe proposto (janela principal)

```
┌ Polpad ──────────────────────────────────────────────────────────────┐
│ ● Conectado (COM5)      Perfil ativo: VS Code ▾     [Dispositivo…]  │
├──────────────┬───────────────────────────────────────────────────────┤
│ Perfis       │ [Teclas] [Aplicativos] [Integrações]                 │
│  Global      │                                                       │
│  VS Code ●   │   ┌ display ─────────┐        Tecla 6 — Recortar      │
│  Premiere    │   │ VS Code          │        Nome   [Recortar     ]  │
│  OBS         │   │     SAL PAL ABR  │        No display [REC]        │
│              │   │ COP COL REC DES… │        Faz, nesta ordem:       │
│ [+] [Export] │   └──────────────────┘        1. Atalho  Ctrl+X   [x] │
│              │        [1][2][3]              [+ passo]  [Testar 3 s] │
│              │   [4][5][6][7][8]                                     │
│              │   [9]…                                                │
└──────────────┴───────────────────────────────────────────────────────┘
```

Aba **Aplicativos**: lista de executáveis vinculados ao perfil
selecionado, botão "Adicionar programa em execução" (enumera janelas
visíveis via `EnumWindows`), e a chave "Trocar automaticamente". Aba
**Integrações**: Home Assistant e OBS (com "Testar"). Diálogo
**Dispositivo**: porta, tecla de modo (com captura), modo do display,
retorno visual, iniciar com o Windows, versão do firmware recebida no
`hello`.

### 6.2 O mapa de teclas no OLED

```
┌────────────────────────────┐
│█████████ VS Code ██████████│  faixa invertida com o nome do perfil
│            SAL PAL ABR     │
│  COP COL ▓REC▓ DES REF     │  tecla pressionada invertida por 250 ms
│  TER NRD  -   -  MUD       │  "-" = tecla sem ação
│  PLA  -   -   -  MOD       │  MOD = tecla de modo
└────────────────────────────┘
```

Abreviação: campo "No display" (3 caracteres) ou derivada do rótulo
(iniciais de palavras compostas, ex.: *Ctrl+Shift+P* → CSP; senão as 3
primeiras letras). Acentos removidos (a fonte não os tem).

## 7. Proposta de arquitetura final

```
          USB CDC (JSON Lines)                     BLE HID (sem o PC)
PC ◄───────────────────────────► ESP32-C3 ◄──────────────────────► celular/tablet/PC
│  ping/img  │  key/hello/pong   │  matriz 4×5, debounce, OLED      atalhos fixos
│                                 │  hello só na chegada do host
▼
Software (bandeja do Windows)
├ Controller: tecla → ação / tecla de modo → perfil / quadro do display
├ ActionRunner: fila "entrada" (teclado, comandos) + fila "rede" (HTTP, OBS, HA)
├ Store: config.json atômico + ícones; segredos no Credential Manager
├ Foreground: app em foco → perfil vinculado (edge-triggered)
└ UI (PySide6): grade no layout real, preview pixel-exato, simulador
```

Decisões mantidas: lógica no host, firmware mínimo, JSON legível no
fio (fácil de depurar com um monitor serial), simulador que implementa a
mesma interface do enlace. Decisão nova: **composição do display no
host** (o firmware só desenha bitmaps), que torna as telas testáveis e o
preview exato.

## 8. Roadmap por fases

| Fase | Entrega | Critério de aceite | Esforço |
|---|---|---|---|
| **0. Esta revisão** | Layout real, mapa no OLED, firmware compilável, handshake robusto, gravação de atalhos, docs. | 100 testes passando; firmware compila. | feito |
| **1. Bancada** | Pinos confirmados, firmware gravado, BLE pareado. | Cada tecla reporta seu índice; display mostra o mapa; sem o app, play/pause funciona via BLE no Windows e no celular; latência tecla→ação < 50 ms medida (seção 9). | 1–2 dias |
| **2. Interface v2** | Abas, perfil Global, "Adicionar programa em execução", tecla = lista de passos, `SetWinEventHook`. | Usuário cria um perfil por app sem abrir diálogos escondidos; macro e ação simples no mesmo editor. | 3–5 dias |
| **3. Entrega** | Instalador (Inno Setup) ou `.exe` assinado, ícone/imagens do projeto, manual do usuário de 2 páginas, release no GitHub com o `.bin` do firmware. | Instala e roda num Windows limpo sem Python; SmartScreen sem aviso (se assinado). | 2 dias |
| **4. Avaliação (artigo)** | Experimento de usabilidade. | Dados coletados com o protocolo da seção 9.3; capítulo de resultados. | 1 semana (coleta) |
| **5. Extras** | Camadas por tecla segurada, perfil por janela (título), suporte a Linux (xdotool/ydotool), configuração pelo navegador. | Opcional. | — |

## 9. Plano de testes

### 9.1 Automatizados (já existem)

`python -m unittest discover -t .` cobre modelos, persistência
tolerante a corrupção, protocolo, fonte e telas do display, controlador
(tecla → ação, tecla de modo, retorno visual), filas de ações, rodízio
de portas, handshake, exportação/importação, cofre de segredos.

### 9.2 Bancada (fase 1)

1. Conferir no esquemático: GPIO de cada linha/coluna, lado do diodo,
   pinos do header do OLED. Ajustar `config.h`.
2. Compilar e gravar (`firmware/README.md`). Abrir o monitor serial e
   enviar `{"t":"ping"}`: deve vir `hello` e `pong`.
3. Pressionar as 18 teclas na ordem do layout e conferir os índices.
   Índices trocados → trocar linhas/colunas ou `KEY_INDEX`; nenhuma
   tecla → inverter `DIODE_COL2ROW`.
4. Abrir o software: status "Conectado", mapa no OLED, tecla acende ao
   pressionar (no OLED e na grade).
5. Fechar o software: em 10 s o OLED volta a "Aguardando host". Parear
   "Polpad" no Windows e no celular; testar mídia e Ctrl+C/V.
6. Reabrir o software: deve retomar sem reiniciar o macropad.
7. **Latência**: gravar com o celular em câmera lenta (240 fps) a tecla
   e a tela do PC; contar quadros entre o toque e a reação. Alternativa:
   ação "Digitar texto" num editor com timestamp.

### 9.3 Usabilidade (fase 4, para o artigo)

- **Tarefa**: sequência de 10 comandos num aplicativo (ex.: VS Code ou
  Premiere) por três métodos: menus, atalhos de teclado, macropad.
- **Medidas**: tempo por comando (KLM como previsão, cronômetro como
  observação), erros, e questionário **SUS** (System Usability Scale)
  ao final. 8–12 participantes, ordem dos métodos balanceada.
- **Hipóteses**: macropad mais rápido que menus; sem a desvantagem de
  memorização dos atalhos (o display rotula as teclas).

## 10. Recomendações para o texto do artigo

1. **Resumo e seção 2.6**: substituir "reconhecido nativamente como um
   teclado padrão USB (HID), dispensando a instalação de drivers" por
   algo como: "opera em dois modos: conectado por USB a um computador com
   o software de configuração, que executa as ações; ou, sem o software,
   como teclado Bluetooth LE padrão (HID), reconhecido nativamente por
   qualquer sistema". Justificar com a limitação do periférico USB do
   ESP32-C3 (citar o datasheet/TRM, já nas referências).
2. **Seção 2.7 (display)**: descrever o mapa de teclas como a forma de
   "informar dinamicamente a função associada a cada tecla", com a
   restrição de 3 caracteres (21 colunas de texto) e o destaque da tecla
   pressionada como *feedback* (Norman).
3. **Quadro comparativo**: na linha "Este trabalho", a plataforma é
   "ESP32-C3 (USB serial + BLE HID)".
4. **Metodologia**: incluir a arquitetura host-agent e o motivo (perfis
   ilimitados, ações além do HID), o protocolo JSON Lines, o simulador
   como ferramenta de desenvolvimento, e os testes automatizados.
5. **Figuras**: captura da interface com a grade no layout real e o
   preview; foto do OLED com o mapa; diagrama da seção 7.

## 11. Perguntas em aberto (precisam de você)

1. Esquemático/PCB: quais GPIOs vão para linhas, colunas e OLED? Lado do
   diodo? (Abra o projeto da placa ou meça com multímetro.)
2. O módulo é mesmo o ESP32-C3 SuperMini de 16 pinos? (O footprint 2×8
   sugere que sim.)
3. O display é soldado na placa ou ligado por cabo ao header de 4 pinos?
   Qual a ordem dos pinos do header (GND-VCC-SCL-SDA ou VCC-GND-SCL-SDA)?
4. Há interesse na interface v2 (seção 6.1) antes da defesa, ou a
   prioridade é a bancada e a avaliação?

## Apêndice — comandos

```powershell
# software
.venv\Scripts\python -m polpad                 # rodar
.venv\Scripts\python -m unittest discover -t .   # testes
.venv\Scripts\ruff check . ; .venv\Scripts\mypy  # qualidade
.venv\Scripts\python tools\build_exe.py          # executável

# firmware (arduino-cli embutido no Arduino IDE 2)
& "$env:LOCALAPPDATA\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" `
  compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc `
  --config-file "$env:USERPROFILE\.arduinoIDE\arduino-cli.yaml" `
  --warnings default firmware\macropad_firmware
# gravar: acrescente -u -p COMx
```

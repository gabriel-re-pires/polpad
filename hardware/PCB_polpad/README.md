# Placa do Polpad

PCB do macropad no EasyEDA Pro: ESP32-C3 SuperMini, 18 soquetes hot-swap MX
com diodos 1N4148W e OLED 0,96" I2C.

| Arquivo | O que é |
|---|---|
| `Macropad_polpad.epcb` | Placa (layout e roteamento) |
| `ProDoc_P1_2026-11-08.epro2` | Projeto com o esquemático |
| `Gerber_Macropad_polpad_2026-11-08.zip` | Gerbers e furação para fabricar |
| `PCB_Macropad_polpad_2026-11-08.pdf` | Desenho da placa |
| `SCH_Schematic1_2026-11-08.pdf` | Esquemático |
| `Polpad_lista_de_ligacoes.pdf` | Ligações tecla a tecla, pinos do C3 e o que conferir antes de fabricar |

A pinagem usada no firmware (`firmware/macropad_firmware/config.h`) vem da
placa, não do esquemático: o esquemático ainda mostra um S2 Mini e diodos PTH.
A lista de ligações detalha as diferenças.

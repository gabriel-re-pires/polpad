"""Gera a animação da tela de espera do firmware (o polvo girando os tentáculos).

Gira o logo e cola o corpo parado por cima. Os 8 tentáculos se repetem a cada
45°, então ``QUADROS`` quadros cobrindo 45° fecham a volta sem pulo.

    .venv\\Scripts\\python tools\\animacao_espera.py [--gif prévia.gif]

Grava ``firmware/macropad_firmware/espera_anim.h``; ``--gif`` grava também uma
prévia ampliada da tela inteira.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from polpad.core import oled_render

LOGO = RAIZ / "src" / "polpad" / "ui" / "assets" / "polvo-roxo-256.png"
SAIDA = RAIZ / "firmware" / "macropad_firmware" / "espera_anim.h"

LADO = 48  # px do polvo no display
QUADROS = 12  # quadros para girar 45°
QUADRO_MS = 100
CENTRO = 128  # centro do corpo no logo de 256 px
RAIO_CORPO = 69  # raio do corpo no logo de 256 px (com folga da borda)
LIMIAR = 110  # opacidade (0-255) a partir da qual o pixel acende

# Texto da tela. A fonte do display não tem "ã": o til é desenhado à parte.
TEXTO = "Aguardando conexao"
TIL_EM = TEXTO.index("conexao") + 5  # o "a" de "conexao"
TEXTO_Y = 55
PONTOS_MS = 400  # cada passo de "", ".", "..", "..."


def quadros() -> list[Image.Image]:
    """Os quadros do polvo, em modo "1", com ``LADO`` x ``LADO`` px."""
    return quadros_em([45 * i / QUADROS for i in range(QUADROS)])


def quadros_em(angulos: list[float]) -> list[Image.Image]:
    """O polvo com os tentáculos girados de cada ângulo (graus, horário)."""
    logo = Image.open(LOGO).convert("RGBA").getchannel("A")
    corpo = Image.new("L", logo.size, 0)
    ImageDraw.Draw(corpo).ellipse(
        (
            CENTRO - RAIO_CORPO,
            CENTRO - RAIO_CORPO,
            CENTRO + RAIO_CORPO,
            CENTRO + RAIO_CORPO,
        ),
        fill=255,
    )
    parado = ImageChops.multiply(logo, corpo)  # corpo e olhos, sem giro
    resultado = []
    for angulo in angulos:
        # Ângulo negativo: no PIL, positivo gira no sentido anti-horário.
        girado = logo.rotate(
            -angulo, resample=Image.BICUBIC, center=(CENTRO, CENTRO)
        )
        fora = ImageChops.multiply(girado, ImageChops.invert(corpo))
        alfa = ImageChops.add(fora, parado)
        pequeno = alfa.resize((LADO, LADO), Image.LANCZOS)
        resultado.append(pequeno.point(lambda v: 255 if v >= LIMIAR else 0, "1"))
    return resultado


def bytes_xbm(quadro: Image.Image) -> bytes:
    """Linhas de cima para baixo, MSB primeiro, 1 = aceso (``drawBitmap``)."""
    pixels = quadro.load()
    largura = (LADO + 7) // 8
    saida = bytearray()
    for y in range(LADO):
        for bloco in range(largura):
            byte = 0
            for bit in range(8):
                x = bloco * 8 + bit
                if x < LADO and pixels[x, y]:
                    byte |= 0x80 >> bit
            saida.append(byte)
    return bytes(saida)


def cabecalho(lista: list[Image.Image]) -> str:
    linhas = [
        "// Gerado por tools/animacao_espera.py — não edite à mão.",
        "// Polvo da tela de espera: corpo parado, tentáculos girando 45° em",
        f"// {QUADROS} quadros ({LADO}x{LADO} px, 1 bpp, formato do drawBitmap).",
        "#pragma once",
        "",
        "#include <Arduino.h>",
        "",
        f"constexpr int16_t ESPERA_LADO = {LADO};",
        f"constexpr uint8_t ESPERA_QUADROS = {QUADROS};",
        f"constexpr uint32_t ESPERA_QUADRO_MS = {QUADRO_MS};",
        "",
        "// Texto embaixo do polvo. A fonte não tem \"ã\": o til sai dos pixels",
        "// ESPERA_TIL, relativos à célula do caractere ESPERA_TIL_EM.",
        f'constexpr char ESPERA_TEXTO[] = "{TEXTO}";',
        f"constexpr int16_t ESPERA_TEXTO_Y = {TEXTO_Y};",
        f"constexpr uint8_t ESPERA_TIL_EM = {TIL_EM};",
        "constexpr int8_t ESPERA_TIL[][2] = {"
        + ", ".join(f"{{{dx}, {dy}}}" for dx, dy in TIL)
        + "};",
        f"constexpr uint32_t ESPERA_PONTOS_MS = {PONTOS_MS};",
        "",
        "static const uint8_t ESPERA_POLVO[ESPERA_QUADROS]"
        f"[{(LADO + 7) // 8 * LADO}] PROGMEM = {{",
    ]
    for quadro in lista:
        dados = bytes_xbm(quadro)
        linhas.append("    {")
        for i in range(0, len(dados), 12):
            trecho = ", ".join(f"0x{b:02X}" for b in dados[i : i + 12])
            linhas.append(f"        {trecho},")
        linhas.append("    },")
    linhas.append("};")
    return "\n".join(linhas) + "\n"


def tela(polvo: Image.Image, pontos: int) -> Image.Image:
    """A tela inteira como o firmware desenha."""
    frame = oled_render.new_frame()
    frame.paste(polvo, ((oled_render.SCREEN_W - LADO) // 2, 0))
    largura = oled_render.text_width(TEXTO + "...")
    x = (oled_render.SCREEN_W - largura) // 2
    oled_render.draw_text(frame, x, TEXTO_Y, TEXTO + "." * pontos)
    til_x = x + TIL_EM * 6
    pixels = frame.load()
    for dx, dy in TIL:
        pixels[til_x + dx, TEXTO_Y + dy] = 255
    return frame


# Til sobre o "a", relativo ao canto da célula do caractere.
TIL = ((1, -1), (2, -2), (3, -1), (4, -2))


def gif(lista: list[Image.Image], destino: Path, escala: int = 4) -> None:
    passos_pontos = PONTOS_MS // QUADRO_MS
    total = QUADROS * 4 * passos_pontos // _mdc(QUADROS, 4 * passos_pontos)
    imagens = []
    for i in range(total):
        frame = tela(lista[i % QUADROS], (i // passos_pontos) % 4)
        grande = frame.convert("L").resize(
            (frame.width * escala, frame.height * escala), Image.NEAREST
        )
        # Branco-azulado de OLED sobre preto.
        imagens.append(
            Image.merge(
                "RGB",
                (
                    grande.point(lambda v: 200 if v else 0),
                    grande.point(lambda v: 235 if v else 0),
                    grande.point(lambda v: 255 if v else 0),
                ),
            )
        )
    imagens[0].save(
        destino,
        save_all=True,
        append_images=imagens[1:],
        duration=QUADRO_MS,
        loop=0,
    )


def _mdc(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gif", type=Path, help="grava também uma prévia em GIF")
    args = parser.parse_args()
    lista = quadros()
    SAIDA.write_text(cabecalho(lista), encoding="utf-8", newline="\n")
    print(f"{len(lista)} quadros gravados em {SAIDA}")
    if args.gif:
        gif(lista, args.gif)
        print(f"prévia em {args.gif}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Desenho de texto 1 bpp idêntico ao da Adafruit GFX no firmware.

O firmware desenha texto com ``display.print()`` usando a fonte clássica
5x7 da Adafruit GFX. Reproduzir aqui exatamente o mesmo algoritmo — mesma
tabela de glifos (:mod:`oled_font`), mesma célula de 6x8, mesma escala
inteira — garante que o preview na interface e o simulador mostrem,
pixel a pixel, o que o display físico exibe.

Também é o que permite ao host **renderizar telas inteiras** (como o mapa
de teclas) e enviá-las ao dispositivo como imagem: o firmware só precisa
saber desenhar bitmaps, e toda a composição fica no PC, onde é fácil de
testar.
"""

from __future__ import annotations

from PIL import Image

from . import oled_font
from .models import SCREEN_H, SCREEN_W

# Colunas e linhas de texto disponíveis no display com a fonte em tamanho 1.
TEXT_COLS = SCREEN_W // oled_font.CELL_W  # 21
TEXT_ROWS = SCREEN_H // oled_font.CELL_H  # 8


def new_frame(fill: int = 0) -> Image.Image:
    """Quadro vazio do tamanho do display (modo "1": 0 = apagado, 255 = aceso)."""
    return Image.new("1", (SCREEN_W, SCREEN_H), fill)


def text_width(text: str, size: int = 1) -> int:
    """Largura em pixels como ``getTextBounds`` da GFX a calcula.

    A GFX inclui a coluna de espaçamento de cada caractere, inclusive do
    último — é com essa largura que o firmware centraliza as linhas.
    """
    return len(text) * oled_font.CELL_W * size


def draw_text(
    frame: Image.Image,
    x: int,
    y: int,
    text: str,
    size: int = 1,
    color: int = 255,
) -> None:
    """Desenha ``text`` com o canto superior esquerdo em (x, y).

    Equivale a ``setCursor(x, y); setTextSize(size); print(text)`` no
    firmware. Caracteres fora do ASCII não existem na fonte e saem como
    ``?``, como o próprio host já normaliza antes de enviar.
    """
    pixels = frame.load()
    if pixels is None:  # pragma: no cover — imagem recém-criada sempre carrega
        raise ValueError("não foi possível acessar os pixels do quadro")
    cursor = x
    for ch in text:
        code = ord(ch) if ord(ch) < 256 else ord("?")
        columns = oled_font.glyph(code)
        for col, bits in enumerate(columns):
            for row in range(oled_font.GLYPH_H):
                if not bits & (1 << row):
                    continue
                px = cursor + col * size
                py = y + row * size
                for dx in range(size):
                    for dy in range(size):
                        xx, yy = px + dx, py + dy
                        if 0 <= xx < SCREEN_W and 0 <= yy < SCREEN_H:
                            pixels[xx, yy] = color
        cursor += oled_font.CELL_W * size


def draw_text_centered(
    frame: Image.Image, y: int, text: str, size: int = 1, color: int = 255
) -> None:
    """Centraliza horizontalmente, como o firmware faz nas telas de texto."""
    x = (SCREEN_W - text_width(text, size)) // 2
    draw_text(frame, max(x, 0), y, text, size, color)


def fill_rect(
    frame: Image.Image, x: int, y: int, w: int, h: int, color: int = 255
) -> None:
    """Retângulo preenchido, recortado aos limites do display."""
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, SCREEN_W), min(y + h, SCREEN_H)
    if x1 > x0 and y1 > y0:
        frame.paste(color, (x0, y0, x1, y1))


def render_text_lines(lines: list[str]) -> Image.Image:
    """Reproduz a tela de texto do firmware (mensagem ``text``).

    Espelha ``showTextScreen`` do firmware: até três linhas; uma linha só
    sai em tamanho 2, mais de uma em tamanho 1; altura de linha
    ``8*size + 4``; bloco centralizado verticalmente.
    """
    frame = new_frame()
    lines = [ln for ln in lines[:3] if ln is not None]
    count = len(lines)
    if count == 0:
        return frame
    size = 2 if count <= 1 else 1
    line_height = oled_font.CELL_H * size + 4
    y = (SCREEN_H - count * line_height + 4) // 2
    for text in lines:
        draw_text_centered(frame, y, text, size)
        y += line_height
    return frame

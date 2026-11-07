"""Composição das telas exibidas no display OLED do macropad.

Toda a composição acontece no host: o quadro é montado como imagem 1 bpp
com a mesma fonte do firmware (:mod:`oled_render`) e enviado pela
mensagem ``img``. O firmware só desenha bitmaps, o que mantém a lógica
de apresentação em Python — testável, e idêntica no preview, no simulador
e no hardware.

Telas (``Profile.display.mode`` — cada perfil escolhe a sua):

``icone``          a imagem do perfil, ocupando a altura do display, sem
                   texto. Perfil sem imagem mostra o nome em letras grandes.
``personalizado``  uma tela montada com os elementos escolhidos: nome do
                   perfil numa faixa invertida no topo, hora em letras
                   grandes, data e um texto livre. Ao trocar de perfil, a
                   tela do ícone aparece por um instante antes dela (ver
                   :class:`~polpad.core.controller.Controller`).

O mapa de teclas (abreviação de cada tecla na posição física) deixou de
ir para o display: ele vive só na interface, onde cabe o rótulo inteiro.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Any

from PIL import Image

from . import icons, oled_render
from .models import SCREEN_H, SCREEN_W, Profile
from .oled_font import CELL_H

# Tela do ícone: o desenho cabe em 128x60, com 2 px livres em cima e embaixo.
ICON_MARGIN = 2
ICON_AREA = (SCREEN_W, SCREEN_H - 2 * ICON_MARGIN)

# Tela personalizada.
_HEADER_H = CELL_H + 2           # faixa invertida de 10 px com o nome
_CLOCK_SIZE = 3                  # hora em células de 18x24 px
_GAP = 4

# A fonte do display só tem ASCII: sem acento em "sáb".
_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
_MONTHS = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)


def profile_frame(profile: Profile, now: datetime | None = None) -> Image.Image:
    """Quadro do perfil conforme o modo de exibição configurado nele."""
    if profile.display.mode == "personalizado":
        return custom_frame(profile, now or datetime.now())
    return icon_frame(profile)


def icon_frame(profile: Profile) -> Image.Image:
    """Tela do ícone: só o desenho, ocupando a altura do display.

    Sem ícone (ou com um arquivo que sumiu/corrompeu), cai para o nome em
    letras grandes — o display nunca fica em branco.
    """
    if profile.icon_path:
        try:
            bitmap = icons.icon_bitmap(profile.icon_path, *ICON_AREA)
        except Exception:  # Pillow levanta tipos variados
            bitmap = None
        if bitmap is not None:
            frame = oled_render.new_frame()
            frame.paste(bitmap, (0, ICON_MARGIN))
            return frame
    return title_frame(profile.name)


def date_text(now: datetime) -> str:
    """Data curta em português, só com ASCII: ``ter, 03 nov 2026``."""
    weekday, month = _WEEKDAYS[now.weekday()], _MONTHS[now.month - 1]
    return f"{weekday}, {now.day:02d} {month} {now.year}"


def custom_frame(profile: Profile, now: datetime) -> Image.Image:
    """Tela personalizada: faixa com o perfil, hora, data e texto livre.

    Os elementos ligados são empilhados e centralizados na área abaixo da
    faixa. Sem nenhum elemento, mostra o nome do perfil.
    """
    cfg = profile.display
    text = _ascii(cfg.text).strip()[: oled_render.TEXT_COLS]
    blocks: list[tuple[str, int]] = []  # (texto, tamanho da fonte)
    if cfg.show_time:
        blocks.append((f"{now.hour:02d}:{now.minute:02d}", _CLOCK_SIZE))
    if cfg.show_date:
        blocks.append((date_text(now), 1))
    if text:
        blocks.append((text, 1))
    if not blocks and not cfg.show_profile:
        return title_frame(profile.name)

    frame = oled_render.new_frame()
    top = 0
    if cfg.show_profile:
        title = _ascii(profile.name).strip()[: oled_render.TEXT_COLS] or "?"
        if blocks:
            oled_render.fill_rect(frame, 0, 0, SCREEN_W, _HEADER_H, 255)
            oled_render.draw_text_centered(frame, 1, title, 1, color=0)
            top = _HEADER_H
        else:
            return title_frame(profile.name)

    height = sum(CELL_H * size for _, size in blocks) + _GAP * (len(blocks) - 1)
    y = top + (SCREEN_H - top - height + 1) // 2
    for content, size in blocks:
        oled_render.draw_text_centered(frame, y, content, size)
        y += CELL_H * size + _GAP
    return frame


def title_frame(name: str) -> Image.Image:
    """Nome do perfil centralizado, no maior tamanho em que couber.

    A tela ``text`` do firmware usa sempre tamanho 2 para uma linha, o que
    corta nomes com mais de 10 caracteres. Como aqui o host compõe o quadro,
    nomes longos descem para o tamanho 1 e quebram em até três linhas.
    """
    cols = oled_render.TEXT_COLS
    text = _ascii(name).strip() or "?"
    if oled_render.text_width(text, 2) <= SCREEN_W:
        return oled_render.render_text_lines([text])
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= cols:
            current = candidate
            continue
        if current:
            lines.append(current)
        # Palavra maior que a linha quebra em pedaços, em vez de ser cortada.
        while len(word) > cols:
            lines.append(word[:cols])
            word = word[cols:]
        current = word
    if current:
        lines.append(current)
    lines = lines[:3]
    if len(lines) > 1:
        return oled_render.render_text_lines(lines)
    # Uma linha só: render_text_lines a desenharia em tamanho 2 (o que corta
    # acima de 10 letras), então ela vai em tamanho 1, na mesma altura.
    frame = oled_render.new_frame()
    line_height = CELL_H + 4
    oled_render.draw_text_centered(frame, (SCREEN_H - line_height + 4) // 2, lines[0], 1)
    return frame


def frame_payload(frame: Image.Image) -> str:
    """Empacota um quadro 1 bpp no payload base64 da mensagem ``img``."""
    return base64.b64encode(icons.pack_bits(frame)).decode("ascii")


def frame_from_message(message: dict[str, Any]) -> Image.Image | None:
    """Reconstrói o quadro que o firmware exibiria para uma mensagem ``text``/``img``.

    Usado pelo preview e pelo simulador — por isso precisa reproduzir o
    firmware com exatidão, e não apenas "parecer".
    """
    kind = message.get("t")
    if kind == "text":
        return oled_render.render_text_lines(
            [str(ln) for ln in message.get("lines", [])]
        )
    if kind == "img":
        try:
            return icons.unpack_bits(base64.b64decode(message.get("d", "")))
        except (ValueError, binascii.Error):
            return None
    return None


def _ascii(text: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


__all__ = [
    "custom_frame",
    "date_text",
    "frame_from_message",
    "frame_payload",
    "icon_frame",
    "profile_frame",
    "title_frame",
]

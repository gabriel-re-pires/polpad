"""Conversão de imagens para o formato do display OLED (SSD1306, 1 bpp).

O display de 0,96" tem 128x64 pixels monocromáticos: só existe "aceso" e
"apagado". Qualquer imagem escolhida pelo usuário precisa ser reduzida e
convertida para 1 bit por pixel, e o resultado depende muito de COMO essa
conversão decide o que acende.

A versão anterior achatava a transparência sobre fundo preto e aplicava
difusão de erro sobre a luminância. Com isso os casos mais comuns de
ícone sumiam do display:

* pictograma escuro em fundo transparente (o formato típico de ícones
  baixados da internet): o desenho preto sobre o fundo preto ficava
  inteiramente apagado — tela vazia;
* logo em fundo branco (JPG, print de tela): o fundo acendia o display
  inteiro e o desenho virava um ruído de pontos.

Agora:

1. o **canal alfa define a forma** — o que é opaco é desenho, o que é
   transparente é fundo, independentemente da cor;
2. sem transparência, o **fundo é deduzido da borda** da imagem; fundo
   claro é invertido, para o fundo ficar apagado como no resto da tela;
3. desenho predominantemente escuro é invertido, para acender;
4. as margens vazias são recortadas, para o desenho ocupar a área toda;
5. pictogramas usam **limiar** (bordas nítidas); só fotografias usam
   difusão de erro (Floyd–Steinberg), onde ela ajuda.

Formato de empacotamento ("xbm1"): varredura por linhas, 8 pixels por
byte, bit mais significativo = pixel mais à esquerda, 1 = pixel aceso.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import cast

from PIL import Image, ImageChops, ImageOps

from .models import SCREEN_H, SCREEN_W

# Abaixo disto o pixel é considerado transparente (fundo).
_ALPHA_MIN = 128
# Uma imagem "tem transparência" se ao menos esta fração for transparente.
_ALPHA_FRACTION = 0.02
# Acima disto de cores distintas (após reduzir), a imagem é tratada como
# fotografia e convertida com difusão de erro.
_PHOTO_COLORS = 48


def _open_rgba(path: str | Path) -> Image.Image:
    with Image.open(path) as img:
        img.load()
        return img.convert("RGBA")


def _has_alpha(alpha: Image.Image) -> bool:
    hist = alpha.histogram()
    transparent = sum(hist[:_ALPHA_MIN])
    return transparent >= _ALPHA_FRACTION * alpha.width * alpha.height


def _mean(img: Image.Image, mask: Image.Image | None = None) -> float:
    hist = img.histogram(mask)
    total = sum(hist)
    if total == 0:
        return 0.0
    return sum(i * n for i, n in enumerate(hist)) / total


def _border_mean(gray: Image.Image) -> float:
    """Luminância média da moldura de 1 px — o "fundo" de uma imagem opaca."""
    w, h = gray.size
    mask = Image.new("L", (w, h), 255)
    if w > 2 and h > 2:
        mask.paste(0, (1, 1, w - 1, h - 1))
    return _mean(gray, mask)


def _intensity(img: Image.Image) -> tuple[Image.Image, bool]:
    """Mapa de intensidade (0 = apagado, 255 = aceso) e se é uma fotografia.

    Concentra as decisões descritas no cabeçalho do módulo.
    """
    alpha = img.getchannel("A")
    gray = img.convert("RGB").convert("L")

    if _has_alpha(alpha):
        shape = alpha.point(lambda a: 255 if a >= _ALPHA_MIN else 0)
        # Desenho escuro sobre transparente: inverte para ele acender. Um
        # pictograma preto liso vira um pictograma branco liso; um logo
        # colorido mantém os detalhes internos (o "furo" escuro continua
        # apagado).
        if _mean(gray, shape) < 128:
            gray = ImageOps.invert(gray)
        # Fora da forma, tudo apagado.
        gray = ImageChops.multiply(gray, shape)
        return gray, False

    background = _border_mean(gray)
    # Imagem praticamente uniforme (um quadrado de uma cor só): não há
    # fundo a separar; inverter apagaria tudo.
    lo, hi = cast(tuple[int, int], gray.getextrema())
    uniforme = hi - lo < 16
    if background >= 128 and not uniforme:
        gray = ImageOps.invert(gray)
    small = img.convert("RGB").resize((32, 32), Image.Resampling.NEAREST)
    colors = small.getcolors(32 * 32) or []
    return gray, len(colors) > _PHOTO_COLORS


def _trim(gray: Image.Image) -> Image.Image:
    """Recorta as margens apagadas, para o desenho ocupar a área disponível."""
    box = gray.point(lambda v: 255 if v >= 64 else 0).getbbox()
    if box is None:
        return gray
    return gray.crop(box)


def icon_bitmap(path: str | Path, width: int, height: int | None = None) -> Image.Image:
    """Converte a imagem em um bitmap 1 bpp que cabe em ``width`` x ``height``.

    O desenho é ampliado ou reduzido mantendo a proporção (``thumbnail``
    só reduziria, e um ícone 16x16 ficaria minúsculo) e centralizado em
    um quadro do tamanho pedido, de fundo apagado.
    """
    height = width if height is None else height
    gray, photo = _intensity(_open_rgba(path))
    gray = _trim(gray)

    escala = min(width / gray.width, height / gray.height)
    novo = (max(1, round(gray.width * escala)), max(1, round(gray.height * escala)))
    if novo != gray.size:
        # Ampliar pictogramas com LANCZOS borra as bordas antes do limiar;
        # ampliações inteiras ficam nítidas com NEAREST.
        filtro = (
            Image.Resampling.NEAREST
            if escala >= 2 and not photo
            else Image.Resampling.LANCZOS
        )
        gray = gray.resize(novo, filtro)

    if photo:
        gray = ImageOps.autocontrast(gray, cutoff=1)
        mono = gray.convert("1")  # Floyd–Steinberg
    else:
        mono = gray.point(lambda v: 255 if v >= 128 else 0).convert("1", dither=None)

    canvas = Image.new("1", (width, height), 0)
    canvas.paste(mono, ((width - mono.width) // 2, (height - mono.height) // 2))
    return canvas


def load_for_oled(path: str | Path, invert: bool = False) -> Image.Image:
    """Imagem convertida ocupando o display inteiro (128x64, 1 bpp)."""
    mono = icon_bitmap(path, SCREEN_W, SCREEN_H)
    if invert:
        mono = mono.point(lambda p: 255 - p)
    return mono


def pack_bits(mono: Image.Image) -> bytes:
    """Empacota uma imagem 1 bpp no formato ``xbm1`` (MSB primeiro)."""
    if mono.size != (SCREEN_W, SCREEN_H):
        raise ValueError(f"imagem deve ter {SCREEN_W}x{SCREEN_H}, tem {mono.size}")
    pixels = mono.load()
    if pixels is None:  # pragma: no cover — imagem válida sempre carrega
        raise ValueError("não foi possível acessar os pixels da imagem")
    data = bytearray()
    for y in range(SCREEN_H):
        for x0 in range(0, SCREEN_W, 8):
            byte = 0
            for bit in range(8):
                if pixels[x0 + bit, y]:
                    byte |= 0x80 >> bit
            data.append(byte)
    return bytes(data)


def icon_payload(path: str | Path) -> str:
    """Converte a imagem do perfil no payload base64 enviado ao firmware."""
    return base64.b64encode(pack_bits(load_for_oled(path))).decode("ascii")


def unpack_bits(data: bytes) -> Image.Image:
    """Inverso de :func:`pack_bits` (usado no preview e no simulador)."""
    expected = SCREEN_W * SCREEN_H // 8
    if len(data) != expected:
        raise ValueError(f"payload deve ter {expected} bytes, tem {len(data)}")
    mono = Image.new("1", (SCREEN_W, SCREEN_H), 0)
    pixels = mono.load()
    if pixels is None:  # pragma: no cover — imagem recém-criada sempre carrega
        raise ValueError("não foi possível acessar os pixels da imagem")
    i = 0
    for y in range(SCREEN_H):
        for x0 in range(0, SCREEN_W, 8):
            byte = data[i]
            i += 1
            for bit in range(8):
                if byte & (0x80 >> bit):
                    pixels[x0 + bit, y] = 255
    return mono


def lit_fraction(mono: Image.Image) -> float:
    """Fração de pixels acesos — a interface avisa quando sai quase vazio."""
    hist = mono.convert("L").histogram()
    return sum(hist[128:]) / (mono.width * mono.height)


def validar_imagem(path: str | Path) -> None:
    """Levanta exceção se o arquivo não servir como ícone.

    Chamada ANTES de copiar a imagem para o diretório de dados, para o
    erro aparecer no momento da escolha e não depois, silenciosamente,
    com o display caindo para o nome do perfil.
    """
    icon_bitmap(path, SCREEN_H)

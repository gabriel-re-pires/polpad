"""Ícone do aplicativo: o polvo-encoder roxo, de fundo transparente.

O polvo visto de cima, com os braços girando em volta da cabeça como um
encoder. A variante roxa (#7A2EF0) sem fundo funciona sobre a barra de
tarefas clara e a escura — a branca sumiria na clara, e a preta, na
escura — e os olhos vazados mostram o fundo em vez de um branco fixo.

Os arquivos vêm do pacote de ícones do projeto (``docs/marca/polvo-encoder``)
e ficam em ``ui/assets``: PNGs por tamanho (16 e 24 px já são a versão
simplificada, de 6 braços, que não vira borrão) e o ``.ico`` usado no
executável (ver ``tools/make_icon.py``).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

ASSETS = Path(__file__).resolve().parent / "assets"
ICO_PATH = ASSETS / "polvo-roxo.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _png(size: int) -> Path:
    return ASSETS / f"polvo-roxo-{size}.png"


def render(size: int = 64) -> QPixmap:
    """O ícone em ``size`` px: o arquivo exato ou o próximo maior, reduzido."""
    candidates = [s for s in SIZES if s >= size] or [SIZES[-1]]
    pixmap = QPixmap(str(_png(candidates[0])))
    if pixmap.isNull() or pixmap.width() == size:
        return pixmap
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def icon() -> QIcon:
    """Ícone com todas as resoluções (o Windows escolhe a de cada lugar)."""
    result = QIcon()
    for size in SIZES:
        path = _png(size)
        if path.exists():
            result.addFile(str(path))
    return result

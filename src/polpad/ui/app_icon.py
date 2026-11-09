"""Ícone do aplicativo: o polvo-encoder roxo, de fundo transparente.

A variante roxa sem fundo funciona em barra de tarefas clara e escura. Os PNGs
(16 e 24 px já simplificados) e o ``.ico`` ficam em ``ui/assets`` e vêm de
``docs/marca/polvo-encoder`` (ver ``tools/make_icon.py``).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

ASSETS = Path(__file__).resolve().parent / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _png(size: int) -> Path:
    return ASSETS / f"polvo-roxo-{size}.png"


def icon() -> QIcon:
    """Ícone com todas as resoluções (o Windows escolhe a de cada lugar)."""
    result = QIcon()
    for size in SIZES:
        path = _png(size)
        if path.exists():
            result.addFile(str(path))
    return result

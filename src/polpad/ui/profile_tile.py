"""Ladrilho quadrado do perfil: a imagem do ícone ou as iniciais do nome.

A imagem preenche o quadrado inteiro ("cover"): é ampliada até cobrir os
dois lados e recortada no centro, sem deformar. A escala é feita a partir
do arquivo original, direto no tamanho físico da tela (considerando o
fator de escala do Windows), com filtragem suave — por isso não perde
qualidade nem fica serrilhada.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPixmap

from . import style

_cache: dict[tuple[str, str, int, float], QPixmap] = {}


def monogram(name: str) -> str:
    # Só palavras com letra ou número: "OBS — Live" vira "OL", não "O—".
    words = [w for w in re.split(r"\s+", name.strip()) if any(c.isalnum() for c in w)]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def forget() -> None:
    """Descarta o cache (o ícone de um perfil pode ter mudado no disco)."""
    _cache.clear()


def tile(icon_path: str | None, name: str, size: int, ratio: float = 1.0) -> QPixmap:
    """Ladrilho de ``size`` px lógicos com cantos arredondados."""
    key = (icon_path or "", name, size, ratio)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    physical = max(1, round(size * ratio))
    pm = QPixmap(physical, physical)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    rect = QRectF(0, 0, size, size)
    radius = max(4.0, size * 0.24)
    clip = QPainterPath()
    clip.addRoundedRect(rect, radius, radius)

    image = QImage(icon_path) if icon_path else QImage()
    if not image.isNull():
        # Cobre o quadrado (KeepAspectRatioByExpanding) e recorta o centro.
        scaled = image.scaled(
            physical, physical, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        x = (scaled.width() - physical) // 2
        y = (scaled.height() - physical) // 2
        cropped = scaled.copy(x, y, physical, physical)
        cropped.setDevicePixelRatio(ratio)
        p.setClipPath(clip)
        p.fillRect(rect, QColor("#0E1014"))
        p.drawImage(rect, cropped)
        p.setClipping(False)
    else:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(style.BG_RAISED))
        p.drawPath(clip)
        font = QFont()
        font.setPixelSize(max(9, round(size * 0.34)))
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        p.setPen(QColor(style.TEXT_MUTED))
        p.drawText(rect, Qt.AlignCenter, monogram(name))

    # Contorno fino por cima, para o ladrilho não se misturar ao fundo.
    p.setPen(QColor(255, 255, 255, 22))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.end()
    _cache[key] = pm
    return pm

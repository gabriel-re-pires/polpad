"""Ícones de traço desenhados com QPainter (grade de 24 px, traço 1,8 px).

Evita empacotar fonte de ícones ou SVGs. Cada glifo recebe o ``QPainter`` já
escalado para a grade 24x24.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import style

Glyph = Callable[[QPainter], None]


def _refresh(p: QPainter) -> None:
    path = QPainterPath()
    path.arcMoveTo(QRectF(5, 5, 14, 14), 40)
    path.arcTo(QRectF(5, 5, 14, 14), 40, 290)
    p.drawPath(path)
    # ponta da seta no início do arco
    a = math.radians(40)
    tip = QPointF(12 + 7 * math.cos(a), 12 - 7 * math.sin(a))
    p.drawLine(tip, tip + QPointF(-4.2, -0.6))
    p.drawLine(tip, tip + QPointF(0.4, 4.2))


def _settings(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 2.8, 2.8)
    path = QPainterPath()
    teeth = 8
    for i in range(teeth * 2):
        ang = math.pi * 2 * i / (teeth * 2)
        r = 8.2 if i % 2 == 0 else 6.4
        for da in (-0.17, 0.17):
            pt = QPointF(12 + r * math.cos(ang + da), 12 + r * math.sin(ang + da))
            if path.elementCount() == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)


def _plus(p: QPainter) -> None:
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _more(p: QPainter) -> None:
    pen = p.pen()
    p.setPen(Qt.NoPen)
    p.setBrush(pen.color())
    for x in (6, 12, 18):
        p.drawEllipse(QPointF(x, 12), 1.6, 1.6)


def _chip(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(7, 7, 10, 10), 2, 2)
    for i in (10, 14):
        p.drawLine(QPointF(i, 3.5), QPointF(i, 7))
        p.drawLine(QPointF(i, 17), QPointF(i, 20.5))
        p.drawLine(QPointF(3.5, i), QPointF(7, i))
        p.drawLine(QPointF(17, i), QPointF(20.5, i))


def _image(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(4, 5, 16, 14), 3, 3)
    p.drawEllipse(QPointF(9, 10), 1.6, 1.6)
    path = QPainterPath(QPointF(4.5, 17))
    path.lineTo(10, 12.5)
    path.lineTo(13.5, 15.5)
    path.lineTo(16, 13.5)
    path.lineTo(19.5, 16.5)
    p.drawPath(path)


def _play(p: QPainter) -> None:
    path = QPainterPath(QPointF(8, 5.5))
    path.lineTo(18.5, 12)
    path.lineTo(8, 18.5)
    path.closeSubpath()
    p.drawPath(path)


def _trash(p: QPainter) -> None:
    p.drawLine(QPointF(4.5, 7), QPointF(19.5, 7))
    p.drawLine(QPointF(9.5, 7), QPointF(10, 4.5))
    p.drawLine(QPointF(10, 4.5), QPointF(14, 4.5))
    p.drawLine(QPointF(14, 4.5), QPointF(14.5, 7))
    path = QPainterPath(QPointF(6.5, 7))
    path.lineTo(7.5, 19.5)
    path.lineTo(16.5, 19.5)
    path.lineTo(17.5, 7)
    p.drawPath(path)


def _edit(p: QPainter) -> None:
    path = QPainterPath(QPointF(5, 19))
    path.lineTo(5.5, 15.5)
    path.lineTo(15.5, 5.5)
    path.lineTo(18.5, 8.5)
    path.lineTo(8.5, 18.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(13.5, 7.5), QPointF(16.5, 10.5))


def _check(p: QPainter) -> None:
    path = QPainterPath(QPointF(5.5, 12.5))
    path.lineTo(10, 17)
    path.lineTo(18.5, 7.5)
    p.drawPath(path)


def _import(p: QPainter) -> None:
    p.drawLine(QPointF(12, 4), QPointF(12, 15))
    p.drawLine(QPointF(12, 15), QPointF(8, 11))
    p.drawLine(QPointF(12, 15), QPointF(16, 11))
    p.drawLine(QPointF(5, 19.5), QPointF(19, 19.5))


def _back(p: QPainter) -> None:
    p.drawLine(QPointF(19, 12), QPointF(5, 12))
    path = QPainterPath(QPointF(11, 6))
    path.lineTo(5, 12)
    path.lineTo(11, 18)
    p.drawPath(path)


def _menu(p: QPainter) -> None:
    for y in (7, 12, 17):
        p.drawLine(QPointF(4.5, y), QPointF(19.5, y))


def _panel(p: QPainter, left: bool) -> None:
    p.drawRoundedRect(QRectF(3.5, 5, 17, 14), 3, 3)
    x = 9 if left else 15
    p.drawLine(QPointF(x, 5), QPointF(x, 19))


def _panel_left(p: QPainter) -> None:
    _panel(p, True)


def _panel_right(p: QPainter) -> None:
    _panel(p, False)


GLYPHS: dict[str, Glyph] = {
    "back": _back,
    "menu": _menu,
    "panel-left": _panel_left,
    "panel-right": _panel_right,
    "refresh": _refresh,
    "settings": _settings,
    "plus": _plus,
    "more": _more,
    "chip": _chip,
    "image": _image,
    "play": _play,
    "trash": _trash,
    "edit": _edit,
    "check": _check,
    "import": _import,
}


def pixmap(name: str, color: str = style.TEXT_MUTED, size: int = 18) -> QPixmap:
    """Desenha o glifo em ``size`` px lógicos (nítido em telas de alta densidade)."""
    ratio = 2.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24, size / 24)
    pen = QPen(QColor(color), 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    GLYPHS[name](p)
    p.end()
    return pm


def icon(
    name: str,
    color: str = style.TEXT_MUTED,
    size: int = 18,
    hover: str | None = None,
) -> QIcon:
    """``QIcon`` com os estados normal, desabilitado e (opcional) de foco do mouse."""
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Normal)
    result.addPixmap(pixmap(name, style.TEXT_FAINT, size), QIcon.Disabled)
    if hover is not None:
        result.addPixmap(pixmap(name, hover, size), QIcon.Active)
    return result

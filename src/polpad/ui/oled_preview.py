"""Widget que reproduz, pixel a pixel, o display OLED do macropad.

Os quadros saem das mesmas mensagens do protocolo e do mesmo algoritmo do
firmware (:mod:`polpad.core.oled_render`). Cada pixel é um ponto com fresta,
para deixar evidente que o display é de 1 bit e baixa resolução.
"""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..core import oled_render
from ..core.models import SCREEN_H, SCREEN_W
from . import style

# Fração do passo de cada pixel que fica acesa (o resto é a fresta).
_DOT = 0.84


class OledPreview(QWidget):
    """Display 128x64 em matriz de pontos; o tamanho do ponto acompanha o widget."""

    def __init__(self, pixel: float = 2.0, padding: int = 10) -> None:
        super().__init__()
        self._pixel = pixel
        self._padding = padding
        self._frame: Image.Image = oled_render.render_text_lines(["macropad"])
        self._cache: QPixmap | None = None
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

    def show_frame(self, frame: Image.Image) -> None:
        self._frame = frame.convert("1")
        self._cache = None
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 — API Qt
        return QSize(
            round(SCREEN_W * self._pixel) + 2 * self._padding,
            round(SCREEN_H * self._pixel) + 2 * self._padding,
        )

    def minimumSizeHint(self) -> QSize:  # noqa: N802 — API Qt
        return QSize(SCREEN_W + 2 * self._padding, SCREEN_H + 2 * self._padding)

    def resizeEvent(self, event) -> None:  # noqa: N802 — API Qt
        self._cache = None
        super().resizeEvent(event)

    def _glass(self) -> QRectF:
        """Retângulo do vidro, na proporção 2:1 do display, centralizado."""
        avail_w = self.width() - 2 * self._padding
        avail_h = self.height() - 2 * self._padding
        step = max(min(avail_w / SCREEN_W, avail_h / SCREEN_H), 0.5)
        # Passo inteiro em pixels físicos deixa os pontos iguais; só se encolher pouco.
        ratio = self.devicePixelRatioF() or 1.0
        snapped = int(step * ratio) / ratio
        if snapped >= 0.8 * step:
            step = snapped
        w, h = step * SCREEN_W, step * SCREEN_H
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _render(self) -> QPixmap:
        ratio = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * ratio), int(self.height() * ratio))
        pm.setDevicePixelRatio(ratio)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)

        glass = self._glass()
        pad = self._padding
        bezel = glass.adjusted(-pad, -pad, pad, pad)
        p.setPen(QColor(style.BORDER))
        p.setBrush(QColor("#05080A"))
        p.drawRoundedRect(bezel.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        step = glass.width() / SCREEN_W
        # Fresta só com pontos grandes; em escalas pequenas ela vira moiré.
        ratio = self.devicePixelRatioF() or 1.0
        if step * ratio >= 3:
            # Fresta de um pixel físico (ou proporcional, em escalas grandes).
            dot = step - 1 / ratio
            if step * ratio >= 6:
                dot = min(dot, step * _DOT)
        else:
            dot = step
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(style.OLED_OFF))
        p.drawRect(glass)
        p.setBrush(QColor(style.OLED_LIT))
        device_step = step * ratio
        crisp = abs(device_step - round(device_step))
        p.setRenderHint(QPainter.Antialiasing, crisp > 0.01)
        data = self._frame.convert("L").tobytes()
        x0, y0 = glass.x(), glass.y()
        for y in range(SCREEN_H):
            row = y * SCREEN_W
            for x in range(SCREEN_W):
                if data[row + x]:
                    p.drawRect(QRectF(x0 + x * step, y0 + y * step, dot, dot))
        p.end()
        return pm

    def paintEvent(self, _event) -> None:  # noqa: N802 — API Qt
        if self._cache is None:
            self._cache = self._render()
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        p.end()

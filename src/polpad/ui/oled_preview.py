"""Widget que reproduz o conteúdo do display OLED do macropad.

Usado no aparelho da janela principal, no inspetor de ícone e no
simulador. Os quadros são reconstruídos a partir das mesmas mensagens do
protocolo ("text" e "img") com a mesma fonte e o mesmo algoritmo do
firmware (:mod:`polpad.core.oled_render`), de modo que o que se vê aqui
é, pixel a pixel, o que o SSD1306 mostra.

Cada pixel é desenhado como um ponto separado dos vizinhos por uma fresta
— como os pixels de um OLED de verdade vistos de perto. Isso deixa claro
para quem configura que o display é de 1 bit e baixa resolução, e que é
por isso que o ícone precisa ser simples.
"""

from __future__ import annotations

from typing import Any

from PIL import Image
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..core import display, oled_render
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

    # ----------------------------------------------------------------- API

    def show_message(self, message: dict[str, Any]) -> None:
        frame = display.frame_from_message(message)
        if frame is not None:
            self.show_frame(frame)

    def show_frame(self, frame: Image.Image) -> None:
        self._frame = frame.convert("1")
        self._cache = None
        self.update()

    # -------------------------------------------------------------- tamanho

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

    # -------------------------------------------------------------- desenho

    def _glass(self) -> QRectF:
        """Retângulo do vidro, na proporção 2:1 do display, centralizado."""
        avail_w = self.width() - 2 * self._padding
        avail_h = self.height() - 2 * self._padding
        step = max(min(avail_w / SCREEN_W, avail_h / SCREEN_H), 0.5)
        # Passo inteiro em pixels físicos deixa todos os pontos iguais. Só
        # vale a pena se encolher pouco; senão fica o passo fracionário.
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
        # A fresta entre pontos só aparece com pontos grandes; em escalas
        # pequenas ela vira moiré.
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

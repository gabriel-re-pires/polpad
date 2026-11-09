"""Seletor de porta que também mostra o estado da conexão.

Conectado, mostra a porta com a bolinha verde; sem conexão, a escolha (porta
ou "Busca automática", sempre por último na lista) com um anel apagado.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QComboBox, QStyle, QStyleOptionComboBox, QStylePainter

from . import style

_DOT = 10


def _dot(filled: bool) -> QIcon:
    ratio = 2.0
    pm = QPixmap(int(_DOT * ratio), int(_DOT * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(1, 1, _DOT - 2, _DOT - 2)
    if filled:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(style.SUCCESS))
        p.drawEllipse(r)
    else:
        p.setPen(QPen(QColor(style.TEXT_FAINT), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(r.adjusted(0.5, 0.5, -0.5, -0.5))
    p.end()
    return QIcon(pm)


class PortCombo(QComboBox):
    """``currentData()`` é a porta escolhida, ou ``None`` para a busca automática."""

    def __init__(self, auto_label: str) -> None:
        super().__init__()
        self._auto_label = auto_label
        self._connected: str | None = None
        self._on = _dot(True)
        self._off = _dot(False)
        self.setIconSize(QSize(_DOT, _DOT))
        self.setAccessibleName("Conexão com o macropad")
        self.set_ports([], None)

    def set_ports(self, ports: list[tuple[str, str]], selected: str | None) -> None:
        """Recria a lista (sem disparar sinais) mantendo a escolha ``selected``."""
        self.blockSignals(True)
        try:
            self.clear()
            for device, description in ports:
                label = f"{device} — {description}" if description else device
                self.addItem(label, device)
            self.addItem(self._auto_label, None)
            index = self.findData(selected) if selected else -1
            self.setCurrentIndex(index if index >= 0 else self.count() - 1)
        finally:
            self.blockSignals(False)
        self._update_icons()

    def set_connected(self, port: str | None) -> None:
        self._connected = port
        self._update_icons()
        if port:
            self.setToolTip(f"Macropad conectado em {port}")
        else:
            self.setToolTip(
                "Procurando o macropad… Conecte-o por um cabo USB de dados."
            )
        self.update()

    def _update_icons(self) -> None:
        for i in range(self.count()):
            data = self.itemData(i)
            on = self._connected is not None and data == self._connected
            self.setItemIcon(i, self._on if on else QIcon())

    def paintEvent(self, _event) -> None:  # noqa: N802 — API Qt
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        if self._connected:
            opt.currentText = self._connected
            opt.currentIcon = self._on
        else:
            data = self.currentData()
            opt.currentText = data if data else self._auto_label
            opt.currentIcon = self._off
        painter.drawComplexControl(QStyle.CC_ComboBox, opt)
        painter.drawControl(QStyle.CE_ComboBoxLabel, opt)

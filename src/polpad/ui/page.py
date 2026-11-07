"""Página aberta no lugar das colunas, como a das Configurações.

Cabeçalho com "Voltar" (Esc) e o título; abaixo, uma coluna centralizada
que rola. Quem herda põe o conteúdo em :attr:`body` e, se quiser, botões
à direita do cabeçalho em :attr:`header`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import glyphs, style
from .inspector import FitScrollArea

MAX_W = 720
MIN_W = 480


class Page(QWidget):
    """``closed``: o usuário pediu para voltar à tela inicial."""

    closed = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = QHBoxLayout()
        self.header.setContentsMargins(28, 20, 28, 12)
        self.header.setSpacing(12)
        self.back_button = QPushButton("Voltar")
        self.back_button.setObjectName("ghost")
        self.back_button.setIcon(glyphs.icon("back", style.TEXT))
        self.back_button.setShortcut("Esc")
        self.back_button.setToolTip("Voltar (Esc)")
        self.back_button.clicked.connect(self.closed.emit)
        self.header.addWidget(self.back_button)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("headline")
        self.header.addWidget(self.title_label)
        self.header.addStretch(1)
        root.addLayout(self.header)

        self._scroll = FitScrollArea()
        content = QWidget()
        outer = QHBoxLayout(content)
        outer.setContentsMargins(28, 4, 28, 28)
        column = QWidget()
        column.setMaximumWidth(MAX_W)
        column.setMinimumWidth(MIN_W)
        # A coluna cresce até MAX_W; o que sobra vai para as margens.
        outer.addStretch(1)
        outer.addWidget(column, 100)
        outer.addStretch(1)
        self.body = QVBoxLayout(column)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(16)
        self.body.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(content)
        root.addWidget(self._scroll, stretch=1)

    @staticmethod
    def card(title: str, caption: str = "") -> tuple[QFrame, QVBoxLayout]:
        """Cartão com título, no mesmo estilo dos das Configurações."""
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        if caption:
            text = QLabel(caption)
            text.setObjectName("caption")
            text.setWordWrap(True)
            layout.addWidget(text)
        return frame, layout

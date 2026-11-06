"""Versão do Polpad no centro da barra inferior.

O ``QStatusBar`` só põe widgets à esquerda ou à direita, e esconde os da
esquerda enquanto mostra uma mensagem. Este rótulo fica por cima da
barra, sempre centralizado, e só se esconde quando uma mensagem longa
chegaria até ele.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QLabel, QStatusBar

#: Folga entre o fim da mensagem e o começo da versão.
GAP = 16
#: Recuo do texto da mensagem dentro da barra.
MESSAGE_INDENT = 8


class StatusVersion(QLabel):
    def __init__(self, text: str, bar: QStatusBar) -> None:
        super().__init__(text, bar)
        self.setObjectName("statusVersion")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._bar = bar
        bar.installEventFilter(self)
        bar.messageChanged.connect(self._on_message)
        self.show()
        self._place()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 — API Qt
        if watched is self._bar and event.type() in (QEvent.Resize, QEvent.Show):
            self._place()
        return False

    def _place(self) -> None:
        self.adjustSize()
        x = (self._bar.width() - self.width()) // 2
        y = (self._bar.height() - self.height()) // 2
        self.move(x, y)
        self._on_message(self._bar.currentMessage())

    def _on_message(self, message: str) -> None:
        width = self._bar.fontMetrics().horizontalAdvance(message)
        self.setVisible(MESSAGE_INDENT + width + GAP <= self.x())

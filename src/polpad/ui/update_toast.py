"""Aviso de atualização no canto inferior direito da tela.

Janela própria, sem moldura e sempre por cima, que não rouba o foco de
quem está digitando. Aparece mesmo com o Polpad escondido na bandeja.
O mesmo aviso mostra versão nova, instalação pendente, progresso,
resultado de uma troca e erros.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import app_icon

MARGIN = 16
WIDTH = 360


def toast_position(available: QRect, size: QSize, margin: int = MARGIN) -> QPoint:
    """Canto inferior direito da área útil (acima da barra de tarefas)."""
    return QPoint(
        available.x() + available.width() - margin - size.width(),
        available.y() + available.height() - margin - size.height(),
    )


class UpdateToast(QWidget):
    update_clicked = Signal()
    install_now_clicked = Signal()
    details_clicked = Signal()
    retry_clicked = Signal()
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(WIDTH)
        self._action = ""

        card = QFrame(self)
        card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 12, 10, 12)
        layout.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(app_icon.icon().pixmap(QSize(36, 36)))
        icon.setAlignment(Qt.AlignTop)
        layout.addWidget(icon)

        texts = QVBoxLayout()
        texts.setSpacing(4)
        self.title = QLabel()
        self.title.setObjectName("sectionTitle")
        self.title.setWordWrap(True)
        self.detail = QLabel()
        self.detail.setObjectName("hint")
        self.detail.setWordWrap(True)
        self.details_link = QLabel('<a href="novidades">Ver novidades</a>')
        self.details_link.linkActivated.connect(lambda _href: self.details_clicked.emit())
        self.action_button = QPushButton()
        self.action_button.setObjectName("primary")
        self.action_button.clicked.connect(self._on_action)
        texts.addWidget(self.title)
        texts.addWidget(self.detail)
        texts.addWidget(self.details_link)
        texts.addWidget(self.action_button, 0, Qt.AlignLeft)
        layout.addLayout(texts, 1)

        self.close_button = QToolButton()
        self.close_button.setText("✕")
        self.close_button.setToolTip("Fechar")
        self.close_button.setAutoRaise(True)
        self.close_button.clicked.connect(self._on_close)
        layout.addWidget(self.close_button, 0, Qt.AlignTop)

    # ------------------------------------------------------------ estados

    def show_available(self, version: str, current: str) -> None:
        self._show(
            f"Nova versão do Polpad: {version}",
            f"Você está na {current}",
            "Atualizar",
            "update",
        )

    def show_pending(self, version: str) -> None:
        self._show(
            f"O Polpad {version} será instalado quando você sair",
            "",
            "Instalar agora",
            "install_now",
        )

    def show_updated(self, version: str) -> None:
        self._show(f"Polpad atualizado para {version}", "", "", "")

    def show_failed(self, version: str, log_path: Path) -> None:
        self._show(
            f"A atualização para {version} não foi concluída",
            f"Detalhes em {log_path}",
            "Tentar de novo",
            "retry",
            details=False,
        )

    def show_error(self, text: str) -> None:
        self.detail.setText(text)
        self.detail.show()
        self.action_button.setText("Tentar de novo")
        self._action = "retry"
        self.action_button.show()
        self.close_button.show()
        self._place()

    def show_progress(self, text: str) -> None:
        self.detail.setText(text)
        self.detail.show()
        self.action_button.hide()
        self.details_link.hide()
        self.close_button.hide()
        self._place()

    # ------------------------------------------------------------ interno

    def _show(
        self, title: str, detail: str, action: str, kind: str, details: bool = True
    ) -> None:
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.details_link.setVisible(details)
        self.action_button.setText(action)
        self.action_button.setVisible(bool(action))
        self.close_button.show()
        self._action = kind
        self.show()
        self._place()

    def _place(self) -> None:
        self.adjustSize()
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            self.move(toast_position(screen.availableGeometry(), self.size()))

    def _on_action(self) -> None:
        signal = {
            "update": self.update_clicked,
            "install_now": self.install_now_clicked,
            "retry": self.retry_clicked,
        }.get(self._action)
        if signal is not None:
            signal.emit()

    def _on_close(self) -> None:
        self.hide()
        self.dismissed.emit()

"""Aviso de atualização no canto inferior direito da tela.

Janela sem moldura, sempre por cima e sem roubar o foco; aparece mesmo com o
Polpad na bandeja. Avisos informativos somem após 5 s (exceto com o mouse em
cima); progresso e erros ficam até o usuário agir.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QEnterEvent, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import app_icon, style

MARGIN = 16
WIDTH = 360
#: Quanto tempo um aviso informativo fica na tela.
VISIBLE_MS = 5000
LINK = f'<a href="novidades" style="color: {style.ACCENT_HOVER};">Ver novidades</a>'

#: ``notify(título, detalhe)`` ou ``notify(título, detalhe, tag=...)``.
Notify = Callable[..., object]


def toast_position(available: QRect, size: QSize, margin: int = MARGIN) -> QPoint:
    """Canto inferior direito da área útil (acima da barra de tarefas)."""
    return QPoint(
        available.x() + available.width() - margin - size.width(),
        available.y() + available.height() - margin - size.height(),
    )


class UpdateToast(QWidget):
    update_clicked = Signal()
    install_now_clicked = Signal()
    flash_clicked = Signal()
    details_clicked = Signal()
    retry_clicked = Signal()
    dismissed = Signal()

    def __init__(
        self, parent: QWidget | None = None, notify: Notify | None = None
    ) -> None:
        super().__init__(
            parent,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        # Só o cartão arredondado aparece: sem o retângulo escuro atrás.
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH)
        self._action = ""
        # Repassa o aviso à central de notificações (ver notification_center).
        self._notify = notify
        self._auto_hide = False
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(VISIBLE_MS)
        self.hide_timer.timeout.connect(self.hide)

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
        self.details_link = QLabel(LINK)
        self.details_link.linkActivated.connect(lambda _href: self.details_clicked.emit())
        self.action_button = QPushButton()
        self.action_button.setObjectName("primary")
        self.action_button.clicked.connect(self._on_action)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addWidget(self.details_link, 0, Qt.AlignVCenter)
        actions.addStretch(1)
        actions.addWidget(self.action_button, 0, Qt.AlignVCenter)
        texts.addWidget(self.title)
        texts.addWidget(self.detail)
        texts.addLayout(actions)
        layout.addLayout(texts, 1)

        self.close_button = QToolButton()
        self.close_button.setObjectName("toastClose")
        self.close_button.setText("✕")
        self.close_button.setToolTip("Fechar")
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self._on_close)
        layout.addWidget(self.close_button, 0, Qt.AlignTop)

    @property
    def current_action(self) -> str:
        """O que o botão faz agora: "update", "install_now", "retry", "flash" ou ""."""
        return self._action

    def show_available(self, version: str, current: str) -> None:
        self._show(
            f"Nova versão do Polpad: {version}",
            f"Você está na {current}",
            "Atualizar",
            "update",
        )

    def show_firmware_available(self, version: str, current: str) -> None:
        """Firmware novo para o macropad; "Gravar" abre a página de gravação."""
        self._show(
            f"Firmware {version} disponível para o macropad",
            f"O seu está com o {current}",
            "Gravar",
            "flash",
            details=False,
            tag="firmware",
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
        self._stay()
        self.detail.setText(text)
        self.detail.show()
        self.action_button.setText("Tentar de novo")
        self._action = "retry"
        self.action_button.show()
        self.close_button.show()
        self._place()

    def show_progress(self, text: str) -> None:
        self._stay()
        self.detail.setText(text)
        self.detail.show()
        self.action_button.hide()
        self.details_link.hide()
        self.close_button.hide()
        self._place()

    def _show(
        self,
        title: str,
        detail: str,
        action: str,
        kind: str,
        details: bool = True,
        tag: str | None = None,
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
        self._auto_hide = True
        self.hide_timer.start()
        if self._notify is not None:
            if tag is None:
                self._notify(title, detail)
            else:
                self._notify(title, detail, tag=tag)

    def _stay(self) -> None:
        """Progresso e erros esperam o usuário: não somem sozinhos."""
        self._auto_hide = False
        self.hide_timer.stop()

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802 — API Qt
        # Quem vai clicar em "Atualizar" não pode ver o aviso sumir.
        self.hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 — API Qt
        if self._auto_hide and self.isVisible():
            self.hide_timer.start()
        super().leaveEvent(event)

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
            "flash": self.flash_clicked,
        }.get(self._action)
        if signal is not None:
            signal.emit()

    def _on_close(self) -> None:
        self.hide_timer.stop()
        self.hide()
        self.dismissed.emit()

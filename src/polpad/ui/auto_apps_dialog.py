"""Diálogo de vínculo de aplicativos a um perfil (troca automática).

Lista de executáveis (no Linux, a classe da janela) que ativam o perfil ao
ganhar o foco. "Capturar" espera 3 s e registra o app em foco.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Profile
from ..integrations import foreground


class AutoAppsDialog(QDialog):
    def __init__(self, parent: QWidget | None, profile: Profile) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Apps vinculados — {profile.name}")
        self.setMinimumWidth(420)
        self._profile = profile

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Quando um destes aplicativos ganhar o foco, o perfil "
            f"“{profile.name}” é ativado automaticamente (requer a opção "
            "correspondente em Configurações). A tecla de modo continua "
            "funcionando normalmente."
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        layout.addWidget(hint)

        self._list = QListWidget()
        self._list.addItems(profile.auto_apps)
        layout.addWidget(self._list, stretch=1)

        self._status = QLabel("")
        self._status.setObjectName("hint")
        layout.addWidget(self._status)

        row = QHBoxLayout()
        self._capture_button = QPushButton("Capturar app em foco (3 s)")
        self._capture_button.clicked.connect(self._capture)
        add_button = QPushButton("Adicionar…")
        add_button.clicked.connect(self._add_manual)
        remove_button = QPushButton("Remover")
        remove_button.clicked.connect(self._remove)
        row.addWidget(self._capture_button)
        row.addWidget(add_button)
        row.addWidget(remove_button)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        salvar = buttons.button(QDialogButtonBox.Ok)
        salvar.setText("Salvar")
        salvar.setObjectName("primary")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _capture(self) -> None:
        self._capture_button.setEnabled(False)
        self._status.setText("Leve o foco ao aplicativo desejado…")

        def grab() -> None:
            exe = foreground.foreground_exe()
            self._capture_button.setEnabled(True)
            if exe:
                self._add(exe)
                self._status.setText(f"Capturado: {exe}")
            else:
                self._status.setText("Não foi possível identificar o aplicativo.")

        QTimer.singleShot(3000, grab)

    def _add_manual(self) -> None:
        exe, ok = QInputDialog.getText(
            self,
            "Adicionar aplicativo",
            f"Nome do aplicativo (ex.: {foreground.EXAMPLE}):",
        )
        if ok and exe.strip():
            self._add(exe.strip().lower())

    def _add(self, exe: str) -> None:
        existing = [self._list.item(i).text() for i in range(self._list.count())]
        if exe not in existing:
            self._list.addItem(exe)

    def _remove(self) -> None:
        row = self._list.currentRow()
        if row >= 0:
            self._list.takeItem(row)

    def _accept(self) -> None:
        self._profile.auto_apps = [
            self._list.item(i).text().lower() for i in range(self._list.count())
        ]
        self.accept()

"""Página "Versão e atualizações", aberta no lugar das colunas.

Só mostra estado e emite pedidos: quem consulta o GitHub, baixa, instala
e restaura é o :class:`~polpad.ui.update_controller.UpdateController`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..update.backup import Backup
from ..update.policy import is_downgrade
from ..update.releases import AppRelease
from . import style
from .page import Page

KIND_LABELS = {
    "windows": "Instalado pelo instalador do Windows",
    "linux_menu": "Instalado no menu do Linux",
    "nao_instalado": "Não instalado",
    "desenvolvimento": "Instalação de desenvolvimento: atualize com git pull",
}


@dataclass
class VersionView:
    current: str
    kind: str
    last_check: datetime | None
    update: AppRelease | None
    releases: list[AppRelease] = field(default_factory=list)
    backups: list[Backup] = field(default_factory=list)
    notify: bool = True
    auto: bool = False
    error: str = ""
    busy: str = ""


def _date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return ""


def _clear(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget() if item is not None else None
        if widget is not None:
            widget.deleteLater()


class VersionPage(Page):
    """Página "Versão e atualizações"; ``closed`` volta à tela inicial."""

    check_requested = Signal()
    update_requested = Signal(object)
    install_requested = Signal(object)
    restore_requested = Signal(object)
    open_backups_requested = Signal()
    notify_changed = Signal(bool)
    auto_changed = Signal(bool)
    linux_install_requested = Signal()
    linux_uninstall_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Versão e atualizações", parent)
        self._view: VersionView | None = None
        self._release_buttons: dict[str, QPushButton] = {}
        self._release_texts: dict[str, str] = {}
        self._backup_buttons: list[QPushButton] = []

        card, layout = self.card("Esta instalação")
        self.version_label = QLabel()
        self.version_label.setObjectName("headline")
        self.kind_label = QLabel()
        self.kind_label.setObjectName("hint")
        layout.addWidget(self.version_label)
        layout.addWidget(self.kind_label)
        self.body.addWidget(card)

        card, layout = self.card("Atualizações")
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMinimumHeight(110)
        self.update_button = QPushButton("Atualizar")
        self.update_button.setObjectName("primary")
        self.update_button.clicked.connect(self._on_update)
        self.busy_label = QLabel()
        self.busy_label.setObjectName("hint")
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {style.DANGER};")
        check_row = QHBoxLayout()
        self.last_check_label = QLabel()
        self.last_check_label.setObjectName("hint")
        self.check_button = QPushButton("Verificar agora")
        self.check_button.clicked.connect(self.check_requested.emit)
        check_row.addWidget(self.last_check_label, 1)
        check_row.addWidget(self.check_button)
        for widget in (self.status_label, self.notes):
            layout.addWidget(widget)
        layout.addWidget(self.update_button, 0, Qt.AlignLeft)
        layout.addWidget(self.busy_label)
        layout.addWidget(self.error_label)
        layout.addLayout(check_row)
        self.body.addWidget(card)

        card, layout = self.card("Opções")
        self.notify_box = QCheckBox("Avisar quando houver nova versão")
        self.notify_box.toggled.connect(self.notify_changed.emit)
        self.auto_box = QCheckBox(
            "Atualizar automaticamente (baixa em segundo plano e instala ao sair "
            "do Polpad)"
        )
        self.auto_box.toggled.connect(self.auto_changed.emit)
        layout.addWidget(self.notify_box)
        layout.addWidget(self.auto_box)
        self.body.addWidget(card)

        card, layout = self.card("Versões anteriores")
        self._releases_layout = QVBoxLayout()
        layout.addLayout(self._releases_layout)
        self.body.addWidget(card)

        card, layout = self.card("Cópias dos perfis")
        self._backups_layout = QVBoxLayout()
        layout.addLayout(self._backups_layout)
        open_folder = QPushButton("Abrir pasta")
        open_folder.clicked.connect(self.open_backups_requested.emit)
        layout.addWidget(open_folder, 0, Qt.AlignLeft)
        self.body.addWidget(card)

        self.linux_install_button: QPushButton | None = None
        self.linux_uninstall_button: QPushButton | None = None
        if sys.platform.startswith("linux"):
            card, layout = self.card("Menu de aplicativos")
            row = QHBoxLayout()
            self.linux_install_button = QPushButton("Instalar no menu")
            self.linux_install_button.clicked.connect(self.linux_install_requested.emit)
            self.linux_uninstall_button = QPushButton("Remover instalação")
            self.linux_uninstall_button.clicked.connect(
                self.linux_uninstall_requested.emit
            )
            row.addWidget(self.linux_install_button)
            row.addWidget(self.linux_uninstall_button)
            row.addStretch(1)
            layout.addLayout(row)
            self.body.addWidget(card)

    def set_view(self, view: VersionView) -> None:
        self._view = view
        dev = view.kind == "desenvolvimento"
        self.version_label.setText(f"{APP_NAME} {view.current}")
        self.kind_label.setText(KIND_LABELS.get(view.kind, view.kind))

        if view.update is None:
            self.status_label.setText("Você está na versão mais recente")
            self.notes.hide()
            self.update_button.hide()
        else:
            self.status_label.setText(f"Nova versão {view.update.version} disponível")
            self.notes.setMarkdown(view.update.notes or "Sem notas.")
            self.notes.show()
            self.update_button.show()
        self.update_button.setEnabled(not dev and not view.busy)
        self.check_button.setEnabled(not dev and not view.busy)
        self.busy_label.setText(view.busy)
        self.busy_label.setVisible(bool(view.busy))
        self.error_label.setText(view.error)
        self.error_label.setVisible(bool(view.error))
        self.last_check_label.setText(
            f"Última verificação: {view.last_check:%d/%m/%Y %H:%M}"
            if view.last_check
            else "Ainda não verificado"
        )

        for box, value in ((self.notify_box, view.notify), (self.auto_box, view.auto)):
            box.blockSignals(True)
            box.setChecked(value)
            box.blockSignals(False)
            box.setEnabled(not dev)

        self._fill_releases(view, dev)
        self._fill_backups(view)
        if self.linux_install_button is not None and self.linux_uninstall_button:
            installed = view.kind == "linux_menu"
            self.linux_install_button.setEnabled(not dev and not installed)
            self.linux_uninstall_button.setEnabled(installed)

    def release_buttons(self) -> dict[str, QPushButton]:
        return dict(self._release_buttons)

    def release_texts(self) -> dict[str, str]:
        return dict(self._release_texts)

    def backup_buttons(self) -> list[QPushButton]:
        return list(self._backup_buttons)

    def _fill_releases(self, view: VersionView, dev: bool) -> None:
        _clear(self._releases_layout)
        self._release_buttons.clear()
        self._release_texts.clear()
        if not view.releases:
            self._releases_layout.addWidget(QLabel("Nenhuma versão encontrada."))
        for release in view.releases:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            date = _date(release.published_at)
            text = f"{release.version}" + (f" — {date}" if date else "")
            if release.version == view.current:
                text += " (instalada)"
            elif not release.installable:
                text += (
                    f' — anterior ao instalador · <a href="{release.html_url}">'
                    "ver no GitHub</a>"
                )
            label = QLabel(text)
            label.setOpenExternalLinks(True)
            label.setToolTip(release.notes)
            line.addWidget(label, 1)
            self._release_texts[release.version] = text
            if release.installable and release.version != view.current:
                button = QPushButton("Instalar esta versão")
                button.setEnabled(not dev and not view.busy)
                button.clicked.connect(lambda _=False, r=release: self._on_install(r))
                line.addWidget(button)
                self._release_buttons[release.version] = button
            self._releases_layout.addWidget(row)

    def _fill_backups(self, view: VersionView) -> None:
        _clear(self._backups_layout)
        self._backup_buttons.clear()
        if not view.backups:
            self._backups_layout.addWidget(QLabel("Nenhuma cópia ainda."))
        for item in view.backups:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.addWidget(QLabel(f"{item.created:%d/%m/%Y %H:%M} — {item.label}"), 1)
            button = QPushButton("Restaurar")
            button.setEnabled(not view.busy)
            button.clicked.connect(lambda _=False, b=item: self._on_restore(b))
            line.addWidget(button)
            self._backup_buttons.append(button)
            self._backups_layout.addWidget(row)

    def _confirm(self, text: str) -> bool:
        answer = QMessageBox.question(self, APP_NAME, text)
        return answer == QMessageBox.Yes

    def _on_update(self) -> None:
        if self._view is not None and self._view.update is not None:
            self.update_requested.emit(self._view.update)

    def _on_install(self, release: AppRelease) -> None:
        view = self._view
        if view is None:
            return
        text = f"Instalar a versão {release.version}? Seus perfis serão copiados antes."
        downgrade = is_downgrade(release.version, view.current)
        if downgrade:
            text = f"Voltar para a {release.version}? Seus perfis serão copiados antes."
            if view.auto:
                text += " A atualização automática será desligada."
        if not self._confirm(text):
            return
        if downgrade and view.auto:
            self.auto_changed.emit(False)
        self.install_requested.emit(release)

    def _on_restore(self, item: Backup) -> None:
        text = (
            f"Restaurar os perfis da cópia de {item.created:%d/%m/%Y %H:%M}? "
            "O estado atual é copiado antes e o Polpad será reiniciado."
        )
        if self._confirm(text):
            self.restore_requested.emit(item)

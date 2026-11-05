"""Página de configurações globais.

Abre dentro da janela principal (no lugar do aparelho), com um botão
"Voltar" — não é mais um diálogo por cima da janela.

- Tecla de modo: escolhida na lista ou capturada pressionando a tecla
  física no próprio macropad ("defina no próprio teclado").
- Comportamento: troca automática de perfil e início com o sistema.
- Integrações Home Assistant e OBS Studio, com teste de conexão.

O que o display mostra fica no inspetor, ao lado da prévia do aparelho.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..actions.base import ActionError
from ..core import autostart, secrets
from ..core.models import KEY_COUNT, Profile, Settings
from ..integrations import home_assistant, obs
from . import glyphs, style
from .inspector import FitScrollArea


def _secrets_note() -> str:
    """Onde ficam o token e a senha — depende do cofre disponível."""
    conselho = (
        "Ainda assim, use um token exclusivo para o macropad e revogue-o se "
        "necessário."
    )
    if not secrets.available():
        return (
            "Nenhum chaveiro do sistema disponível (no Linux, instale o "
            "gnome-keyring ou o KWallet): o token e a senha ficam no "
            f"config.json da pasta de configuração. {conselho}"
        )
    cofre = (
        "no Gerenciador de Credenciais do Windows"
        if sys.platform == "win32"
        else "no chaveiro do sistema"
    )
    return f"O token e a senha ficam {cofre}, não em arquivo. {conselho}"


def _section(title: str, caption: str = "") -> tuple[QFrame, QFormLayout]:
    card = QFrame()
    card.setObjectName("card")
    outer = QVBoxLayout(card)
    outer.setContentsMargins(20, 16, 20, 18)
    outer.setSpacing(6)
    label = QLabel(title)
    label.setObjectName("sectionTitle")
    outer.addWidget(label)
    if caption:
        cap = QLabel(caption)
        cap.setObjectName("caption")
        cap.setWordWrap(True)
        outer.addWidget(cap)
    form = QFormLayout()
    form.setContentsMargins(0, 8, 0, 0)
    form.setHorizontalSpacing(16)
    form.setVerticalSpacing(10)
    form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    outer.addLayout(form)
    return card, form


class SettingsPage(QWidget):
    """Configurações em página. ``saved``/``closed`` voltam à tela inicial."""

    saved = Signal()
    closed = Signal()

    def __init__(self, settings: Settings, profiles: list[Profile] | None = None) -> None:
        super().__init__()
        self._settings = settings
        # Usados apenas para avisar se a tecla de modo escolhida já tem ação.
        self._profiles = profiles or []
        # Ativado enquanto o usuário estiver "capturando" a tecla de modo.
        self.capturing_mode_key = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ------------------------------------------------------- cabeçalho
        header = QHBoxLayout()
        header.setContentsMargins(28, 20, 28, 12)
        header.setSpacing(12)
        back = QPushButton("Voltar")
        back.setObjectName("ghost")
        back.setIcon(glyphs.icon("back", style.TEXT))
        back.setShortcut("Esc")
        back.setToolTip("Voltar sem salvar (Esc)")
        back.clicked.connect(self.closed.emit)
        header.addWidget(back)
        title = QLabel("Configurações")
        title.setObjectName("headline")
        header.addWidget(title)
        header.addStretch(1)
        save = QPushButton("Salvar")
        save.setObjectName("primary")
        save.setIcon(glyphs.icon("check", style.ACCENT_TEXT))
        save.clicked.connect(self._accept)
        header.addWidget(save)
        root.addLayout(header)

        # -------------------------------------------------------- conteúdo
        scroll = FitScrollArea()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(28, 4, 28, 28)
        column.setSpacing(16)
        column.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        card, form = _section(
            "Tecla de modo",
            "A tecla que passa para o próximo perfil da lista.",
        )
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Desabilitada", None)
        for i in range(KEY_COUNT):
            self._mode_combo.addItem(f"Tecla {i + 1}", i)
        index = self._mode_combo.findData(settings.mode_key)
        self._mode_combo.setCurrentIndex(max(index, 0))
        form.addRow("Tecla:", self._mode_combo)
        self._capture_button = QPushButton("Capturar do macropad")
        self._capture_button.setToolTip(
            "Clique e em seguida pressione, no macropad, a tecla que "
            "alternará os perfis."
        )
        self._capture_button.clicked.connect(self._start_capture)
        form.addRow("", self._capture_button)
        column.addWidget(card)

        card, form = _section("Comportamento")
        self._auto_switch_check = QCheckBox(
            "Trocar de perfil automaticamente pelo aplicativo em foco"
        )
        self._auto_switch_check.setToolTip(
            "Vincule aplicativos a um perfil pelo menu «Perfil» → «Apps "
            "vinculados». A tecla de modo continua funcionando e prevalece "
            "até o foco mudar para outro app vinculado."
        )
        self._auto_switch_check.setChecked(settings.auto_switch_enabled)
        form.addRow(self._auto_switch_check)
        self._autostart_check = QCheckBox(
            f"Iniciar com o {autostart.SYSTEM_NAME} (em segundo plano, na bandeja)"
        )
        self._autostart_check.setChecked(settings.start_with_windows)
        form.addRow(self._autostart_check)
        column.addWidget(card)

        card, form = _section(
            "Home Assistant",
            "Para teclas que acendem luzes ou chamam serviços da casa.",
        )
        self._ha_url = QLineEdit(settings.ha_url)
        self._ha_url.setPlaceholderText("http://homeassistant.local:8123")
        form.addRow("URL:", self._ha_url)
        self._ha_token = QLineEdit(settings.ha_token)
        self._ha_token.setEchoMode(QLineEdit.Password)
        self._ha_token.setPlaceholderText("Token de acesso de longa duração")
        form.addRow("Token:", self._ha_token)
        test_button = QPushButton("Testar conexão")
        test_button.clicked.connect(self._test_ha)
        form.addRow("", test_button)
        column.addWidget(card)

        card, form = _section(
            "OBS Studio",
            "Trocar cena, mutar o microfone, gravar e transmitir (obs-websocket).",
        )
        self._obs_host = QLineEdit(settings.obs_host)
        self._obs_host.setPlaceholderText("localhost")
        form.addRow("Host:", self._obs_host)
        self._obs_port = QSpinBox()
        self._obs_port.setRange(1, 65535)
        self._obs_port.setValue(settings.obs_port)
        form.addRow("Porta:", self._obs_port)
        self._obs_password = QLineEdit(settings.obs_password)
        self._obs_password.setEchoMode(QLineEdit.Password)
        self._obs_password.setPlaceholderText(
            "Senha do WebSocket (Ferramentas → Configurações do WebSocket)"
        )
        form.addRow("Senha:", self._obs_password)
        obs_test = QPushButton("Testar conexão")
        obs_test.clicked.connect(self._test_obs)
        form.addRow("", obs_test)
        column.addWidget(card)

        note = QLabel(_secrets_note())
        note.setWordWrap(True)
        note.setObjectName("caption")
        column.addWidget(note)

        for i in range(column.count()):
            item = column.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setMaximumWidth(720)
                widget.setMinimumWidth(480)

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    # ------------------------------------------------------------- captura

    def _start_capture(self) -> None:
        self.capturing_mode_key = True
        self._capture_button.setText("Pressione uma tecla no macropad…")
        self._capture_button.setEnabled(False)

    def key_captured(self, key: int) -> None:
        """Chamado pela janela principal quando o dispositivo envia uma tecla."""
        if not self.capturing_mode_key:
            return
        self.capturing_mode_key = False
        index = self._mode_combo.findData(key)
        if index >= 0:
            self._mode_combo.setCurrentIndex(index)
        self._capture_button.setText("Capturar do macropad")
        self._capture_button.setEnabled(True)

    # -------------------------------------------------------------- HA

    def _test_ha(self) -> None:
        url = self._ha_url.text().strip()
        token = self._ha_token.text().strip()
        if not url or not token:
            QMessageBox.warning(self, "Home Assistant", "Preencha URL e token.")
            return
        try:
            message = home_assistant.check_connection(url, token)
        except ActionError as exc:
            QMessageBox.critical(self, "Home Assistant", f"Falha no teste: {exc}")
            return
        QMessageBox.information(self, "Home Assistant", f"Conectado: {message}")

    def _test_obs(self) -> None:
        try:
            message = obs.check_connection(
                self._obs_host.text().strip() or "localhost",
                self._obs_port.value(),
                self._obs_password.text(),
            )
        except ActionError as exc:
            QMessageBox.critical(self, "OBS Studio", f"Falha no teste: {exc}")
            return
        QMessageBox.information(self, "OBS Studio", f"Conectado: {message}")

    def _confirm_mode_key(self, key: int) -> bool:
        """Avisa se a tecla escolhida já tem ação configurada.

        Como tecla de modo ela passa a só alternar perfis; sem o aviso, a
        ação some da grade sem explicação.
        """
        afetados = [p.name for p in self._profiles if p.action_for(key) is not None]
        if not afetados:
            return True
        lista = ", ".join(f"“{nome}”" for nome in afetados)
        answer = QMessageBox.question(
            self,
            "Tecla de modo",
            f"A tecla {key + 1} já tem ação configurada em: {lista}.\n\n"
            "Como tecla de modo ela passará a apenas alternar perfis, e essas "
            "ações ficarão inacessíveis (elas não são apagadas — voltam se "
            "você escolher outra tecla de modo).\n\nUsar a tecla mesmo assim?",
        )
        return answer == QMessageBox.Yes

    def _accept(self) -> None:
        mode_key = self._mode_combo.currentData()
        if mode_key is not None and not self._confirm_mode_key(mode_key):
            return
        self._settings.mode_key = mode_key
        self._settings.auto_switch_enabled = self._auto_switch_check.isChecked()
        self._settings.start_with_windows = self._autostart_check.isChecked()
        self._settings.ha_url = self._ha_url.text().strip()
        self._settings.ha_token = self._ha_token.text().strip()
        self._settings.obs_host = self._obs_host.text().strip() or "localhost"
        self._settings.obs_port = self._obs_port.value()
        self._settings.obs_password = self._obs_password.text()
        self.saved.emit()

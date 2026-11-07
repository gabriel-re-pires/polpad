"""Janela principal do configurador.

Layout em três colunas sob uma barra superior::

    ┌──────────────────────────────────────────────────────────────────┐
    │ 🐙 Polpad                                 [● COM8          ▾]  ☰  │
    ├─────────────┬──────────────────────────────────┬─────────────────┤
    │ Perfis + ⚙ ◧│  VS Code ●                       │◨ VS Code        │
    │ ▣ VS Code ● │  ┌────────────────────────────┐  │ [prévia ícone]  │
    │ ▣ OBS       │  │ [OLED ]   [ ] [ ] [ ]      │  │ Tela do display │
    │ ▣ Jogos     │  │ [ ] [ ] [ ] [ ] [ ]        │  │ Teclas: 5 de 18 │
    │             │  │ [ ] [ ] [ ] [ ] [ ]        │  │  1 Copiar  C+C  │
    │             │  │ [ ] [ ] [ ] [ ] [ ]        │  │  2 Colar   C+V  │
    │             │  └────────────────────────────┘  │                 │
    └─────────────┴──────────────────────────────────┴─────────────────┘

O aparelho no centro é o protagonista: tem a forma do PCB e o display
na posição real, mostrando o mesmo quadro que o OLED físico. Cada coluna
lateral recolhe pelo ícone ◧/◨ no próprio cabeçalho e vira um trilho fino
(o de perfis mantém os ladrilhos). A coluna da direita mostra o perfil do
centro — ícone, tela do display e resumo das teclas — e, ao clicar numa
tecla, os detalhes dela. O seletor de porta mostra a conexão (bolinha
verde). Configurações, gravação do firmware e nova busca de portas ficam
no menu ☰. O editor de ação e as configurações abrem como página no lugar
das colunas, com "Voltar".
"""

from __future__ import annotations

import copy
import logging
import sys
import threading
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..app import AUTO_PORT, MacropadApp
from ..core import autostart, reset
from ..core.controller import Controller
from ..core.models import Action, Profile
from ..device import serial_access
from ..device.link import available_ports, permission_hint
from . import app_icon, glyphs, style
from .action_page import ActionEditorPage
from .collapsible import RAIL_W, CollapsibleSide, bare_icon_button
from .flash_dialog import FlashPage
from .inspector import Inspector
from .key_grid import DeviceView
from .port_combo import PortCombo
from .profile_panel import ProfilePanel
from .settings_dialog import SettingsPage
from .status_version import StatusVersion

if TYPE_CHECKING:
    from .update_controller import UpdateController

log = logging.getLogger(__name__)


class _Stage(QWidget):
    """Área central. Um clique que não cai numa tecla (nem num botão)
    chega até aqui — as teclas e os botões consomem os próprios cliques,
    o resto (fundo, corpo do aparelho, display, títulos) os repassa."""

    background_clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 — API Qt
        if event.button() == Qt.LeftButton:
            self.background_clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    # (liberado?, erro) — emitido pela thread que pede a senha ao pkexec.
    _access_done = Signal(bool, str)

    def __init__(self, core: MacropadApp) -> None:
        super().__init__()
        self._core = core
        self._editing_profile_id: str | None = core.store.active_profile_id
        self._selected_key: int | None = None
        self._settings_page: SettingsPage | None = None
        # Página aberta no lugar das colunas (configurações ou editor de ação).
        self._overlay: QWidget | None = None
        # Ação copiada pelo menu de contexto da grade, para colar em outra tecla.
        self._clipboard_action: Action | None = None
        # Porta e versão anunciadas pelo dispositivo — usadas pelo diálogo de
        # gravação para pré-selecionar a porta e comparar com o release.
        self._connected_port: str | None = None
        self._device_version: str | None = None
        # Portas sem permissão de acesso (Linux) para as quais já oferecemos
        # liberar o acesso, e a que espera a janela aparecer para oferecer.
        self._access_offered: set[str] = set()
        self._access_pending: str | None = None

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(_app_icon())
        self.resize(1280, 760)
        self.setMinimumSize(1040, 620)
        self._quitting = False
        self._updates: UpdateController | None = None
        self._setup_tray()

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_top_bar())

        # --------------------------------------------------------- conteúdo
        self._profile_panel = ProfilePanel(core.store)
        self._profile_panel.profile_selected.connect(self._on_edit_profile)
        self._profile_panel.activate_requested.connect(core.controller.activate_profile)
        self._profile_panel.profiles_changed.connect(self._refresh_all)

        self._inspector = Inspector(core.store)
        card = self._inspector.key_card
        card.edit_requested.connect(self._edit_key)
        card.test_requested.connect(self._test_key)
        card.clear_requested.connect(self._clear_key)
        card.settings_requested.connect(self._open_settings)
        self._inspector.back_requested.connect(self._back_to_profile)
        self._inspector.keys_card.key_chosen.connect(self._choose_key)
        self._inspector.icon_card.icon_changed.connect(self._on_icon_changed)
        self._inspector.display_card.display_settings_changed.connect(
            self._on_display_settings_changed
        )

        self._splitter = splitter = QSplitter()
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        self._left = CollapsibleSide(
            self._profile_panel,
            "left",
            self._profile_panel.header,
            "os perfis",
            rail_extra=self._profile_panel.rail(),
        )
        self._right = CollapsibleSide(
            self._inspector, "right", self._inspector.header, "o painel do perfil"
        )
        self._left.collapsed_changed.connect(lambda c: self._on_side_collapsed(0, c))
        self._right.collapsed_changed.connect(lambda c: self._on_side_collapsed(2, c))
        splitter.addWidget(self._left)
        splitter.addWidget(self._build_stage())
        splitter.addWidget(self._right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([270, 660, 330])
        # Página 0: as três colunas. Página 1: configurações (criada ao abrir).
        self._pages = QStackedWidget()
        self._pages.addWidget(splitter)
        root_layout.addWidget(self._pages, stretch=1)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self._version_label = StatusVersion(f"{APP_NAME} {__version__}", self.statusBar())

        # ------------------------------------------------------------ sinais
        core.bridge.state.connect(self._set_connected)
        core.bridge.port_denied.connect(self._on_port_denied)
        self._access_done.connect(self._on_access_done)
        core.bridge.message.connect(self._on_device_message)
        core.bridge.action_error.connect(self._on_action_error)
        core.bridge.profile_changed.connect(self._on_active_profile_changed)

        # ---------------------------------------------------------- atalhos
        QShortcut(QKeySequence("Ctrl+,"), self, self._open_settings)
        QShortcut(QKeySequence("F5"), self, self._reload_ports)

        # A hora da tela personalizada muda sozinha: o aparelho da tela
        # acompanha o que o controlador envia ao display.
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._on_clock)
        self._clock_timer.start()

        self._set_connected(False, "")
        # Sem isto o foco inicial cai no botão de menu, que abre contornado.
        QTimer.singleShot(0, self._profile_panel.setFocus)
        self._restore_layout()
        self._refresh_all()
        self._start_initial_link()
        self._refresh_autostart()

    def _refresh_autostart(self) -> None:
        """Regrava a inicialização com o sistema, se estiver ligada.

        A entrada guarda o caminho do executável: depois de mover o
        aplicativo, ela apontaria para um arquivo que não existe mais.
        """
        if not self._core.store.settings.start_with_windows:
            return
        try:
            autostart.apply(True)
        except OSError:
            self.statusBar().showMessage(
                "Não foi possível atualizar a inicialização com o "
                f"{autostart.SYSTEM_NAME}.",
                6000,
            )

    # ------------------------------------------------------------ montagem

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        top = QHBoxLayout(bar)
        top.setContentsMargins(20, 12, 12, 12)
        top.setSpacing(10)

        mark = QLabel()
        mark.setPixmap(_app_icon().pixmap(QSize(30, 30)))
        top.addWidget(mark)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("appTitle")
        sub = QLabel("Configurador")
        sub.setObjectName("appSubtitle")
        titles.addWidget(name)
        titles.addWidget(sub)
        top.addLayout(titles)
        top.addStretch(1)

        self._port_combo = PortCombo(AUTO_PORT)
        self._port_combo.setMinimumWidth(170)
        self._port_combo.setMaximumWidth(300)
        self._port_combo.setSizeAdjustPolicy(
            PortCombo.AdjustToMinimumContentsLengthWithIcon
        )
        self._port_combo.setMinimumContentsLength(14)
        self._reload_ports()
        self._port_combo.currentIndexChanged.connect(self._on_port_selected)
        top.addWidget(self._port_combo)

        # Menu sanduíche no canto direito: só o ícone, sem caixa de botão.
        top.addSpacing(4)
        menu_btn = bare_icon_button("menu", "Menu")
        menu_btn.setIconSize(QSize(20, 20))
        menu_btn.setIcon(glyphs.icon("menu", style.TEXT_MUTED, size=20, hover=style.TEXT))
        menu_btn.setPopupMode(menu_btn.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(menu_btn)
        settings_act = menu.addAction(
            glyphs.icon("settings", style.TEXT), "Configurações\tCtrl+,"
        )
        settings_act.triggered.connect(self._open_settings)
        updates_act = menu.addAction(
            glyphs.icon("import", style.TEXT), "Versão e atualizações"
        )
        updates_act.triggered.connect(self._open_updates)
        flash_act = menu.addAction(glyphs.icon("chip", style.TEXT), "Gravar firmware")
        flash_act.triggered.connect(self._open_flash_page)
        ports_act = menu.addAction(
            glyphs.icon("refresh", style.TEXT), "Procurar portas novamente\tF5"
        )
        ports_act.triggered.connect(self._reload_ports)
        menu.addSeparator()
        quit_act = menu.addAction("Sair")
        quit_act.triggered.connect(self.quit_app)
        menu_btn.setMenu(menu)
        top.addWidget(menu_btn)
        return bar

    def _on_side_collapsed(self, index: int, collapsed: bool) -> None:
        """Repassa a largura entre a coluna e o centro.

        Recolhida, a coluna fica com a largura do trilho e o resto vai para
        o aparelho; expandida, volta à largura que tinha. O QSplitter não
        faz isso sozinho: ele mantém a fatia e deixa um vazio ao lado.
        """
        sizes = self._splitter.sizes()
        side = self._splitter.widget(index)
        want = RAIL_W if collapsed else getattr(side, "expanded_width", sizes[index])
        delta = want - sizes[index]
        sizes[index] = want
        sizes[1] = max(sizes[1] - delta, 200)
        self._splitter.setSizes(sizes)

    def _build_stage(self) -> QWidget:
        stage = _Stage()
        # Clicar fora das teclas volta a coluna da direita ao perfil.
        stage.background_clicked.connect(self._back_to_profile)
        layout = QVBoxLayout(stage)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(12)
        self._profile_title = QLabel()
        self._profile_title.setObjectName("headline")
        head.addWidget(self._profile_title)
        # Perfil em uso no aparelho: só uma bolinha verde, como na lista.
        self._active_dot = QLabel()
        self._active_dot.setFixedSize(10, 10)
        self._active_dot.setStyleSheet(f"background:{style.SUCCESS}; border-radius:5px;")
        self._active_dot.setToolTip("Perfil ativo no macropad")
        self._active_dot.setAccessibleName("Perfil ativo no macropad")
        head.addWidget(self._active_dot)
        head.addStretch(1)
        self._activate_btn = QPushButton("Ativar no macropad")
        self._activate_btn.setObjectName("primary")
        self._activate_btn.setIcon(glyphs.icon("check", style.ACCENT_TEXT))
        self._activate_btn.clicked.connect(self._activate_editing)
        head.addWidget(self._activate_btn)
        layout.addLayout(head)

        self._stage_hint = QLabel(
            "Clique numa tecla para ver a ação. Clique duplo ou Enter abre o editor."
        )
        self._stage_hint.setObjectName("hint")
        layout.addWidget(self._stage_hint)

        self._device = DeviceView()
        self._device.key_clicked.connect(self._on_key_selected)
        self._device.key_activated.connect(self._edit_key)
        self._device.key_menu_requested.connect(self._on_key_menu)
        layout.addWidget(self._device, stretch=1)
        return stage

    # -------------------------------------------------------------- layout

    def _restore_layout(self) -> None:
        """Recupera posição, tamanho e divisão da sessão anterior."""
        settings = QSettings()
        geometry = settings.value("janela/geometria")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self._fit_to_screen()
        # Chave nova: o estado salvo pela versão de duas colunas não serve.
        splitter_state = settings.value("janela/colunas")
        if splitter_state is not None:
            self._splitter.restoreState(splitter_state)
        for side, key in (
            (self._left, "janela/perfis_recolhidos"),
            (self._right, "janela/detalhes_recolhidos"),
        ):
            side.set_collapsed(str(settings.value(key, "false")).lower() == "true")

    def _fit_to_screen(self) -> None:
        """Na primeira abertura, cabe na área útil da tela.

        O tamanho padrão (1280×760) passa da área útil de um notebook
        1366×768 — painéis e barra de tarefas tomam parte da altura — e o
        rodapé ficava escondido atrás deles.
        """
        screen = self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        title_bar = 40  # a moldura da janela não entra no resize()
        width = max(min(self.width(), area.width()), self.minimumWidth())
        height = max(min(self.height(), area.height() - title_bar), self.minimumHeight())
        self.resize(width, height)

    def _save_layout(self) -> None:
        settings = QSettings()
        settings.setValue("janela/geometria", self.saveGeometry())
        settings.setValue("janela/colunas", self._splitter.saveState())
        settings.setValue("janela/perfis_recolhidos", self._left.collapsed)
        settings.setValue("janela/detalhes_recolhidos", self._right.collapsed)

    # ------------------------------------------------------------- bandeja

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(_app_icon(), self)
        self._tray.setToolTip(APP_NAME)
        menu = QMenu()
        open_action = QAction("Abrir configurador", menu)
        open_action.triggered.connect(self.present)
        menu.addAction(open_action)
        menu.addSeparator()
        # O aplicativo passa a maior parte do tempo oculto na bandeja: trocar
        # de perfil daqui evita ter que reabrir a janela.
        self._tray_profiles_menu = menu.addMenu("Trocar perfil")
        menu.addSeparator()
        quit_action = QAction("Sair", menu)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        # A referência precisa sobreviver: o QMenu não tem pai.
        self._tray_menu = menu
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: self.present() if reason == QSystemTrayIcon.Trigger else None
        )
        self._tray.show()

    def present(self) -> None:
        """Mostra a janela, restaurada e à frente.

        Usada pelo ícone da bandeja e quando uma segunda instância pede
        que esta apareça — nos dois casos a janela pode estar minimizada,
        e ``showNormal()`` a restaura preservando a distinção entre
        minimizada e maximizada.
        """
        if self.isMaximized():
            self.showMaximized()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def set_update_controller(self, controller: UpdateController) -> None:
        self._updates = controller
        controller.show_page = self._show_version_page

    def _open_updates(self) -> None:
        if self._updates is not None:
            self._updates.open_page()

    def _show_version_page(self, page: QWidget) -> None:
        """Mostra "Versão e atualizações" (também vem de "Ver novidades")."""
        self.present()
        if page is self._overlay:
            return
        if self._show_overlay(page):
            page.closed.connect(self._close_overlay)

    def quit_app(self) -> None:
        """Encerra de verdade (fechar a janela apenas minimiza à bandeja)."""
        if self._overlay is not None and not self._can_leave(self._overlay):
            # Gravação do firmware em andamento: sair agora estragaria o chip.
            self.present()
            return
        if self._updates is not None:
            # Atualização automática pendente: instala ao sair, sem reabrir.
            self._updates.before_quit()
        self._quitting = True
        self.close()

    # ------------------------------------------------------------- conexão

    def _reload_ports(self) -> None:
        """Atualiza a lista de portas mantendo a escolha atual."""
        current = (
            self._port_combo.currentData()
            if self._port_combo.count()
            else self._core.store.settings.serial_port
        )
        self._port_combo.set_ports(available_ports(), current)
        self._port_combo.set_connected(self._connected_port)

    def _start_initial_link(self) -> None:
        # set_ports não dispara currentIndexChanged: o enlace é criado uma
        # vez só, aqui (criar e destruir em sequência fazia o "hello" do
        # firmware se perder na troca).
        self._port_combo.set_ports(
            available_ports(), self._core.store.settings.serial_port
        )
        self._on_port_selected()

    def _on_port_selected(self) -> None:
        # None = busca automática. Escolher de novo é um pedido explícito:
        # se a porta continuar sem permissão, vale oferecer a liberação outra vez.
        self._access_offered.clear()
        self._core.use_port(self._port_combo.currentData())

    def _on_port_denied(self, port: str) -> None:
        """O macropad está ligado, mas o sistema não deixa abrir a porta."""
        message = f"Sem permissão para abrir {port}."
        self._port_combo.setToolTip(message)
        self.statusBar().showMessage(message, 8000)
        if not sys.platform.startswith("linux") or port in self._access_offered:
            return
        if self.isVisible():
            self._offer_port_access(port)
            return
        # Na bandeja (inicialização automática): avisa e pergunta quando a
        # janela abrir, em vez de soltar uma janela de senha sozinha na tela.
        self._access_pending = port
        tray = getattr(self, "_tray", None)
        if tray is not None and tray.isVisible():
            tray.showMessage(
                APP_NAME,
                "O macropad está ligado, mas falta permissão para acessá-lo. "
                "Abra o Polpad para liberar.",
                QSystemTrayIcon.Warning,
                8000,
            )

    def showEvent(self, event) -> None:  # noqa: N802 — API Qt
        super().showEvent(event)
        if self._access_pending:
            port, self._access_pending = self._access_pending, None
            # Depois do show: a caixa de diálogo precisa da janela já na tela.
            QTimer.singleShot(0, lambda: self._offer_port_access(port))

    def _offer_port_access(self, port: str) -> None:
        if port in self._access_offered or self._connected_port:
            return
        self._access_offered.add(port)
        manual = f"Para resolver à mão: {permission_hint()}."
        intro = (
            f"O macropad está em {port}, mas o Linux não deixa o seu usuário "
            "abrir essa porta."
        )
        if not serial_access.can_grant():
            QMessageBox.warning(self, APP_NAME, f"{intro}\n\n{manual}")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(APP_NAME)
        box.setText(intro)
        box.setInformativeText(
            "O Polpad pode liberar o acesso agora. O sistema pede a senha de "
            "administrador uma vez, e não é preciso sair da sessão."
        )
        grant = box.addButton("Liberar acesso", QMessageBox.AcceptRole)
        box.addButton("Agora não", QMessageBox.RejectRole)
        box.setDefaultButton(grant)
        box.exec()
        if box.clickedButton() is not grant:
            self.statusBar().showMessage(manual, 15000)
            return
        self.statusBar().showMessage("Aguardando a senha de administrador…")
        threading.Thread(
            target=self._grant_port_access, daemon=True, name="serial-access"
        ).start()

    def _grant_port_access(self) -> None:
        """Roda fora da thread da UI: o pkexec espera a senha ser digitada."""
        try:
            serial_access.grant()
        except serial_access.GrantCancelledError:
            self._access_done.emit(False, "")
        except serial_access.GrantError as exc:
            self._access_done.emit(False, str(exc))
        else:
            self._access_done.emit(True, "")

    def _on_access_done(self, ok: bool, error: str) -> None:
        log.info(
            "liberação de acesso à porta: %s",
            "concluída" if ok else (error or "senha não informada"),
        )
        if ok:
            # O enlace tenta a porta de novo a cada 2 s e conecta sozinho.
            self.statusBar().showMessage("Acesso liberado. Conectando ao macropad…", 8000)
            return
        if not error:
            self.statusBar().showMessage(
                "Acesso não liberado. Escolha a porta de novo para tentar outra vez.",
                10000,
            )
            return
        self.statusBar().clearMessage()
        QMessageBox.warning(
            self,
            APP_NAME,
            "Não foi possível liberar o acesso à porta do macropad.\n\n"
            f"{error}\n\nPara resolver à mão: {permission_hint()}.",
        )

    def _set_connected(self, connected: bool, port: str) -> None:
        self._connected_port = port if connected else None
        if not connected:
            # A versão pertence ao dispositivo que saiu: mantê-la faria o
            # diálogo de gravação comparar com um firmware que não está mais lá.
            self._device_version = None
        self._port_combo.set_connected(port if connected else None)
        if connected and self._device_version:
            self._port_combo.setToolTip(
                f"Macropad conectado em {port} (firmware {self._device_version})"
            )
        if hasattr(self, "_tray"):
            state = f"conectado ({port})" if connected else "desconectado"
            self._tray.setToolTip(f"{APP_NAME} — {state}")

    # ------------------------------------------------------------- eventos

    def _on_device_message(self, message: dict[str, Any]) -> None:
        if message.get("t") == "hello":
            version = str(message.get("fw") or "").strip()
            if version and version != self._device_version:
                self._device_version = version
                if self._connected_port:
                    self._set_connected(True, self._connected_port)
            return
        if message.get("t") != "key" or message.get("e") != "down":
            return
        key = int(message.get("k", -1))
        page = self._settings_page
        if page is not None and page.capturing_mode_key:
            page.key_captured(key)
            return
        # Acende a tecla no aparelho da tela: confirma visualmente que o
        # dispositivo chegou até o software, mesmo quando a ação não tem
        # efeito visível.
        self._device.flash(key)
        self.statusBar().showMessage(f"Tecla {key + 1} pressionada", 1500)

    def _on_action_error(self, message: str) -> None:
        """Reporta a falha de uma ação onde o usuário possa vê-la.

        A barra de status não serve quando a janela está oculta na bandeja
        — que é o estado normal de uso —, então nesse caso a notificação
        vai pelo ícone da bandeja.
        """
        self.statusBar().showMessage(f"Erro: {message}", 6000)
        if not self.isVisible() and self._tray.isVisible():
            self._tray.showMessage(APP_NAME, message, QSystemTrayIcon.Warning, 5000)

    def _on_active_profile_changed(self, profile: Profile) -> None:
        self.statusBar().showMessage(f"Perfil ativo: {profile.name}", 3000)
        self._refresh_all()
        if self._core.controller.splashing:
            # O display mostra o ícone por um instante e volta ao mapa; o
            # preview acompanha a volta.
            QTimer.singleShot(int(Controller.SPLASH_S * 1000) + 60, self._refresh_preview)

    def _on_edit_profile(self, profile_id: str) -> None:
        if profile_id != self._editing_profile_id:
            # Outro perfil no centro: a coluna da direita volta à visão dele.
            self._selected_key = None
        self._editing_profile_id = profile_id
        self._refresh_stage()
        self._refresh_preview()

    def _on_icon_changed(self) -> None:
        self._profile_panel.refresh()
        self._refresh_preview()
        # Ícone novo no perfil ativo: o aparelho mostra na hora.
        if self._editing_profile_id == self._core.store.active_profile_id:
            self._core.controller.push_display()

    def _on_display_settings_changed(self) -> None:
        self._core.controller.push_display()
        self._refresh_preview()

    def _activate_editing(self) -> None:
        if self._editing_profile_id:
            self._core.controller.activate_profile(self._editing_profile_id)

    # --------------------------------------------------------------- teclas

    def _editing_profile(self) -> Profile | None:
        return self._core.store.profile_by_id(self._editing_profile_id)

    def _on_key_selected(self, key: int) -> None:
        self._selected_key = key
        self._refresh_key_card()

    def _choose_key(self, key: int) -> None:
        """Tecla escolhida no resumo da coluna da direita."""
        self._device.set_selected(key)
        self._device.focus_key(key)
        self._on_key_selected(key)

    def _back_to_profile(self) -> None:
        self._selected_key = None
        self._device.set_selected(None)
        self._refresh_key_card()

    def _edit_key(self, key: int) -> None:
        profile = self._editing_profile()
        if profile is None:
            return
        self._selected_key = key
        self._device.set_selected(key)
        if key == self._core.store.settings.mode_key:
            self._refresh_key_card()
            self.statusBar().showMessage(
                "Esta é a tecla de modo — altere em Configurações para reutilizá-la.",
                5000,
            )
            return
        page = ActionEditorPage(
            key, profile.action_for(key), profile.name, self._core.runner
        )
        page.done.connect(lambda editor, k=key: self._on_action_edited(k, editor))
        page.closed.connect(self._close_overlay)
        if not self._show_overlay(page):
            page.deleteLater()
            return
        page.focus_form()

    def _on_action_edited(self, key: int, editor) -> None:
        self._close_overlay()
        profile = self._editing_profile()
        if profile is None:
            return
        action = editor.result_action
        if editor.remove_requested:
            profile.bindings.pop(key, None)
        elif action is not None and action.type == "mode_switch":
            self._make_mode_key(key)
            return
        elif action is not None:
            profile.bindings[key] = action
        self._save_bindings()

    def _make_mode_key(self, key: int) -> None:
        """ "Alternar perfil" vira a tecla de modo, que vale em todos os perfis."""
        store = self._core.store
        afetados = store.mode_switch_conflicts(key)
        if afetados:
            lista = ", ".join(f"“{nome}”" for nome in afetados)
            answer = QMessageBox.question(
                self,
                "Tecla de modo",
                f"Para trocar de perfil em qualquer perfil, a tecla {key + 1} vira "
                f"a tecla de modo. Ela já tem ação em: {lista}.\n\nEssas ações "
                "ficam guardadas, mas sem efeito enquanto esta for a tecla de "
                "modo. Continuar?",
            )
            if answer != QMessageBox.Yes:
                return
        store.promote_to_mode_key(key)
        self._save_bindings()
        self._refresh_all()
        self.statusBar().showMessage(
            f"A tecla {key + 1} agora troca de perfil em todos os perfis "
            "(depois do último, volta ao primeiro).",
            6000,
        )

    def _test_key(self, key: int) -> None:
        profile = self._editing_profile()
        action = profile.action_for(key) if profile else None
        if action is not None:
            self._test_action(action)

    def _clear_key(self, key: int) -> None:
        profile = self._editing_profile()
        if profile is None or profile.action_for(key) is None:
            return
        profile.bindings.pop(key, None)
        self._save_bindings()
        self.statusBar().showMessage(f"Tecla {key + 1} limpa.", 3000)

    def _save_bindings(self) -> None:
        self._core.store.save()
        self._profile_panel.refresh()
        self._refresh_stage()
        # O mapa do display mostra as abreviações: se este é o perfil
        # ativo, o aparelho precisa do quadro novo.
        if self._editing_profile_id == self._core.store.active_profile_id:
            self._core.controller.push_display()
        self._refresh_preview()

    def _on_key_menu(self, key: int) -> None:
        """Menu de contexto da tecla: operações rápidas sem abrir o editor."""
        profile = self._editing_profile()
        if profile is None:
            return
        self._on_key_selected(key)
        self._device.set_selected(key)
        if key == self._core.store.settings.mode_key:
            self.statusBar().showMessage(
                "Esta é a tecla de modo — altere em Configurações para reutilizá-la.",
                5000,
            )
            return

        action = profile.action_for(key)
        menu = QMenu(self)

        editar = menu.addAction("Editar…")
        testar = menu.addAction("Testar (3 s)")
        menu.addSeparator()
        copiar = menu.addAction("Copiar ação")
        colar = menu.addAction("Colar ação")
        menu.addSeparator()
        limpar = menu.addAction("Limpar tecla")

        for item in (testar, copiar, limpar):
            item.setEnabled(action is not None)
        colar.setEnabled(self._clipboard_action is not None)

        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return
        if chosen is editar:
            self._edit_key(key)
        elif chosen is testar and action is not None:
            self._test_action(action)
        elif chosen is copiar and action is not None:
            self._clipboard_action = copy.deepcopy(action)
            self.statusBar().showMessage(f"Ação da tecla {key + 1} copiada.", 3000)
        elif chosen is colar and self._clipboard_action is not None:
            profile.bindings[key] = copy.deepcopy(self._clipboard_action)
            self._save_bindings()
        elif chosen is limpar:
            self._clear_key(key)

    def _test_action(self, action: Action) -> None:
        """Executa a ação após um intervalo, como faz o editor.

        O atraso existe para o usuário levar o foco à janela alvo: um
        atalho como Ctrl+C iria para o configurador se disparasse já.
        """
        self.statusBar().showMessage(
            "Executando em 3 segundos — leve o foco à janela alvo…", 3000
        )
        QTimer.singleShot(3000, lambda: self._core.runner.submit(action))

    # --------------------------------------------------------------- diálogos

    def _open_flash_page(self) -> None:
        """Abre a gravação do firmware, já apontada para a porta em uso."""
        if isinstance(self._overlay, FlashPage):
            return
        page = FlashPage(
            self._core,
            current_port=self._connected_port,
            device_version=self._device_version,
        )
        page.closed.connect(self._close_overlay)
        page.running_changed.connect(self._on_flash_running)
        if not self._show_overlay(page):
            page.deleteLater()

    def _on_flash_running(self, running: bool) -> None:
        # Trocar de porta no meio da gravação religaria o enlace na COM que
        # o esptool está usando.
        self._port_combo.setEnabled(not running)
        if not running:
            # A gravação reinicia o ESP32: as portas podem ter mudado de número.
            self._reload_ports()

    def _show_overlay(self, page: QWidget) -> bool:
        """Mostra ``page`` no lugar das colunas (uma por vez).

        Devolve ``False`` se a página aberta não pode ser deixada agora.
        """
        if page is self._overlay:
            self._pages.setCurrentWidget(page)
            return True
        if not self._close_overlay():
            return False
        self._overlay = page
        self._pages.addWidget(page)
        self._pages.setCurrentWidget(page)
        return True

    def _can_leave(self, page: QWidget) -> bool:
        """Páginas com ``leave()`` (a do firmware) podem recusar a saída."""
        leave = getattr(page, "leave", None)
        return bool(leave()) if callable(leave) else True

    def _close_overlay(self) -> bool:
        page = self._overlay
        if page is None:
            return True
        if not self._can_leave(page):
            return False
        self._overlay = None
        self._settings_page = None
        self._pages.setCurrentIndex(0)
        self._pages.removeWidget(page)
        page.deleteLater()
        return True

    def _open_settings(self) -> None:
        """Abre as configurações como página, no lugar das colunas."""
        if self._settings_page is not None:
            return
        uninstall = (
            self._updates.uninstall_support()
            if self._updates is not None
            else (False, "Indisponível nesta execução.")
        )
        page = SettingsPage(
            self._core.store.settings, self._core.store.profiles, uninstall=uninstall
        )
        page.saved.connect(self._on_settings_saved)
        page.closed.connect(self._close_overlay)
        page.reset_settings_requested.connect(self._reset_settings)
        page.reset_profiles_requested.connect(self._reset_profiles)
        if self._updates is not None:
            page.uninstall_requested.connect(self._updates.uninstall)
        if not self._show_overlay(page):
            page.deleteLater()
            return
        self._settings_page = page

    def _close_settings(self) -> None:
        self._close_overlay()

    def _on_settings_saved(self) -> None:
        self._core.store.save()
        try:
            autostart.apply(self._core.store.settings.start_with_windows)
        except OSError:
            self.statusBar().showMessage(
                "Não foi possível atualizar a inicialização com o "
                f"{autostart.SYSTEM_NAME}.",
                6000,
            )
        self._core.controller.push_display()
        self._close_settings()
        self._refresh_all()
        self.statusBar().showMessage("Configurações salvas.", 3000)

    def _reset_settings(self) -> None:
        try:
            reset.reset_settings(self._core.store, __version__)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Não foi possível restaurar: {exc}")
            return
        try:
            autostart.apply(self._core.store.settings.start_with_windows)
        except OSError:
            log.warning("não foi possível desligar a inicialização automática")
        self._core.controller.push_display()
        self._close_settings()
        self._refresh_all()
        self.statusBar().showMessage("Configurações restauradas ao padrão.", 4000)

    def _reset_profiles(self) -> None:
        try:
            reset.reset_profiles(self._core.store, __version__)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Não foi possível apagar: {exc}")
            return
        self._editing_profile_id = None
        active = self._core.store.active_profile_id
        if active is not None:
            self._core.controller.activate_profile(active)
        self._close_settings()
        self._refresh_all()
        self.statusBar().showMessage("Perfis apagados.", 4000)

    # ------------------------------------------------------------ refresh

    def _refresh_all(self) -> None:
        self._profile_panel.refresh()
        self._refresh_stage()
        self._refresh_preview()
        self._refresh_tray_profiles()

    def _refresh_tray_profiles(self) -> None:
        """Reconstrói o submenu de perfis da bandeja."""
        menu = self._tray_profiles_menu
        menu.clear()
        profiles = self._core.store.profiles
        menu.setEnabled(bool(profiles))
        active_id = self._core.store.active_profile_id
        for profile in profiles:
            action = menu.addAction(profile.name)
            action.setCheckable(True)
            action.setChecked(profile.id == active_id)
            action.triggered.connect(
                lambda _checked=False, pid=profile.id: (
                    self._core.controller.activate_profile(pid)
                )
            )

    def _refresh_stage(self) -> None:
        """Cabeçalho do perfil em edição, aparelho e inspetor."""
        profile = self._editing_profile()
        if profile is None:
            profile = self._core.store.active_profile
            self._editing_profile_id = profile.id if profile else None
        is_active = (
            profile is not None and profile.id == self._core.store.active_profile_id
        )
        self._profile_title.setText(profile.name if profile else "Nenhum perfil")
        self._active_dot.setVisible(is_active)
        self._activate_btn.setVisible(profile is not None and not is_active)
        self._device.refresh(profile, self._core.store.settings.mode_key)
        self._device.set_selected(self._selected_key)
        self._refresh_key_card()
        self._inspector.set_title(profile.name if profile else "Perfil")
        self._inspector.icon_card.show_profile(profile)
        self._inspector.display_card.show_profile(profile)
        self._inspector.keys_card.show_profile(
            profile, self._core.store.settings.mode_key
        )
        self._inspector.refit()

    def _refresh_key_card(self) -> None:
        profile = self._editing_profile()
        key = self._selected_key
        action = profile.action_for(key) if (profile and key is not None) else None
        self._inspector.key_card.show_key(
            key, action, key is not None and key == self._core.store.settings.mode_key
        )
        if key is None:
            self._inspector.show_profile_view()
        else:
            self._inspector.show_key_view()

    def _on_clock(self) -> None:
        if (
            self.isVisible()
            and (shown := self._core.store.profile_by_id(self._editing_profile_id))
            is not None
            and shown.display.mode == "personalizado"
        ):
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        """Mostra no aparelho da tela o display do perfil em edição.

        O quadro vem do mesmo código que o envia ao dispositivo, então o
        preview nunca diverge do hardware. Para o perfil ativo ele espelha
        o aparelho (inclusive o ícone da troca); para os outros, mostra a
        tela que o display terá quando o perfil for ativado.
        """
        store = self._core.store
        profile = store.profile_by_id(self._editing_profile_id) or store.active_profile
        if profile is None:
            return
        frame = self._core.controller.preview_frame(profile)
        if frame is not None:
            self._device.oled.show_frame(frame)

    # ------------------------------------------------------------ ciclo

    def closeEvent(self, event) -> None:  # noqa: N802 — API Qt
        # Nos dois caminhos (esconder ou sair) o layout atual é o que o
        # usuário quer reencontrar na próxima abertura.
        self._save_layout()
        if not self._quitting and self._tray.isVisible():
            # Fechar a janela apenas esconde: o macropad continua funcionando.
            # Sem aviso na bandeja: repetido a cada sessão, só incomodava.
            event.ignore()
            self.hide()
            return
        super().closeEvent(event)
        self._shutdown_and_quit()

    def quit_for_switch(self) -> None:
        """Sai para uma troca de versão, restauração ou reinício.

        Passa pelo mesmo encerramento de "Sair" (para o enlace serial, grava
        a configuração, apaga o aviso), mas sem instalar a atualização
        pendente: quem chama já cuidou da troca.
        """
        self._quitting = True
        self._save_layout()
        self.hide()
        self._shutdown_and_quit()

    def _shutdown_and_quit(self) -> None:
        self._tray.hide()
        if self._updates is not None:
            self._updates.shutdown()
        self._core.shutdown()
        # Com setQuitOnLastWindowClosed(False), o loop de eventos precisa
        # ser encerrado explicitamente.
        from PySide6.QtWidgets import QApplication

        QApplication.quit()


def _app_icon() -> QIcon:
    """Ícone do aplicativo (ver :mod:`polpad.ui.app_icon`)."""
    return app_icon.icon()

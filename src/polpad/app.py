"""Raiz de composição: monta store -> runner -> controller -> enlace serial.

O domínio não conhece Qt; a UI conversa com ele pelo
:class:`~polpad.ui.bridge.DeviceBridge`.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QTimer

from .actions.base import ActionContext
from .actions.executor import ActionRunner
from .core.controller import Controller
from .core.store import Store
from .device.link import DeviceLink, SerialLink
from .integrations import foreground
from .ui.bridge import DeviceBridge, UiRelay

log = logging.getLogger(__name__)

AUTO_PORT = "Busca automática"


class MacropadApp:
    def __init__(self) -> None:
        self.store = Store()
        self.store.load()

        self.bridge = DeviceBridge()
        # Falhas ao gravar a configuração vão para a barra de status.
        self.store.on_error = self.bridge.action_error.emit
        self.runner = ActionRunner(
            context=ActionContext(
                settings=self.store.settings,
                request_mode_switch=self._request_mode_switch,
            ),
            on_error=self.bridge.action_error.emit,
        )
        self.controller = Controller(
            store=self.store,
            runner=self.runner,
            send=self._send,
            on_profile_changed=self.bridge.profile_changed.emit,
            # Controlador livre de Qt: o temporizador é injetado.
            schedule=lambda seconds, fn: QTimer.singleShot(int(seconds * 1000), fn),
        )
        # O Controller não é QObject: ligar o sinal direto a ele faria
        # handle_message rodar na thread serial (store, config.json e display
        # fora da UI, e o QTimer de `schedule` nunca dispararia). O relay,
        # criado na thread da UI, torna a entrega "queued".
        self._ui_relay = UiRelay(self.controller.handle_message)
        self.bridge.message.connect(self._ui_relay.deliver)

        self.link: DeviceLink | None = None
        # Restaurada depois de uma pausa (gravação do firmware).
        self._port_choice: str | None = None
        self._paused = False

        # Troca de perfil pelo app em foco: só reage quando o foco muda, então
        # uma troca manual vale até o usuário focar outro app vinculado.
        self._last_exe: str | None = None
        self._foreground_timer = QTimer()
        self._foreground_timer.setInterval(1000)
        self._foreground_timer.timeout.connect(self._poll_foreground)
        self._foreground_timer.start()

        # Relógio da tela personalizada; o quadro só é reenviado se mudou.
        self._clock_timer = QTimer()
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self.controller.tick)
        self._clock_timer.start()

    def use_port(self, port: str | None) -> None:
        """Ativa o enlace: uma COM específica ou a busca automática (``None``)."""
        self._stop_link()
        self._port_choice = port
        self._paused = False
        preferred = None if port in (None, AUTO_PORT) else port
        self.store.settings.serial_port = preferred
        self.store.save()
        self.link = SerialLink(
            on_message=self.bridge.emit_message,
            on_state=self.bridge.emit_state,
            preferred_port=preferred,
            on_denied=self.bridge.emit_port_denied,
        )
        self.link.start()

    def pause_link(self) -> bool:
        """Solta a porta serial para o esptool gravar o firmware.

        ``True`` se havia enlace ativo; aí o chamador deve chamar
        :meth:`resume_link` depois.
        """
        if self._paused or not isinstance(self.link, SerialLink):
            return False
        log.info("pausando o enlace serial")
        self.link.stop()
        self.link = None
        self._paused = True
        return True

    def resume_link(self) -> None:
        """Reativa o enlace pausado por :meth:`pause_link`."""
        if not self._paused:
            return
        log.info("retomando o enlace serial")
        self.use_port(self._port_choice)

    def _stop_link(self) -> None:
        if self.link is not None:
            self.link.stop()
            self.link = None

    def _send(self, message: dict[str, Any]) -> None:
        if self.link is not None:
            self.link.send(message)

    def _poll_foreground(self) -> None:
        exe = foreground.foreground_exe()
        if exe == self._last_exe:
            return
        self._last_exe = exe
        if not self.store.settings.auto_switch_enabled:
            return
        profile = foreground.match_profile(self.store.profiles, exe)
        if profile is not None and profile.id != self.store.active_profile_id:
            self.controller.activate_profile(profile.id)

    def _request_mode_switch(self) -> None:
        """Chamado pela ação "mode_switch" (thread de ações); repassa à UI."""
        self.bridge.message.emit({"t": "_mode_switch"})

    def shutdown(self) -> None:
        self._foreground_timer.stop()
        self._stop_link()
        self.runner.stop()
        self.store.save()

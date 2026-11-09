"""Controlador central: liga o dispositivo, os perfis e o motor de ações.

Tecla de modo troca o perfil; as demais enfileiram a ação no ActionRunner.
Não conhece Qt nem pyserial; ``schedule`` e ``clock`` são injetados para
testes isolados.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..actions.executor import ActionRunner
from ..device import protocol
from . import display
from .models import Profile
from .store import Store

log = logging.getLogger(__name__)

Scheduler = Callable[[float, Callable[[], None]], None]


class Controller:
    # Tempo do ícone na tela após uma troca de perfil.
    SPLASH_S = 1.5

    def __init__(
        self,
        store: Store,
        runner: ActionRunner,
        send: Callable[[dict[str, Any]], None],
        on_profile_changed: Callable[[Profile], None] | None = None,
        schedule: Scheduler | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._store = store
        self._runner = runner
        self._send = send
        self._on_profile_changed = on_profile_changed or (lambda p: None)
        self._schedule = schedule
        self._clock = clock
        # Último payload enviado: evita reenviar 1,4 KB quando nada mudou.
        self._last_payload: str | None = None
        # O contador invalida o fim agendado de uma troca anterior.
        self._splash_token = 0
        self._splashing = False
        # "Capturar do macropad": a próxima tecla vai para cá, sem executar nada.
        self.key_capture: Callable[[int], None] | None = None

    def handle_message(self, message: dict[str, Any]) -> None:
        """Processa uma mensagem vinda do dispositivo (ou do simulador)."""
        kind = message.get("t")
        if kind == "hello":
            # O dispositivo (re)iniciou: a tela dele não é o nosso quadro.
            self.push_display(force=True)
        elif kind == "key" and message.get("e") == "down":
            key = int(message.get("k", -1))
            capture = self.key_capture
            if capture is not None:
                self.key_capture = None
                capture(key)
                return
            self._handle_key(key)
        elif kind == "_mode_switch":
            # Gerada pela ação "mode_switch" (ver app.py).
            self.switch_mode()

    def _handle_key(self, key: int) -> None:
        if key == self._store.settings.mode_key:
            self.switch_mode()
            return
        profile = self._store.active_profile
        if profile is None:
            return
        action = profile.action_for(key)
        if action is None:
            log.debug("tecla %d sem ação no perfil %s", key, profile.name)
            return
        self._runner.submit(action)

    def switch_mode(self) -> None:
        """Avança para o próximo perfil (tecla de modo)."""
        profile = self._store.next_profile()
        self._show_profile()
        self._on_profile_changed(profile)

    def activate_profile(self, profile_id: str) -> None:
        """Ativa um perfil escolhido na interface."""
        if self._store.profile_by_id(profile_id) is None:
            return
        self._store.active_profile_id = profile_id
        self._store.save()
        self._show_profile()
        profile = self._store.active_profile
        if profile is not None:
            self._on_profile_changed(profile)

    def _show_profile(self) -> None:
        """Atualiza o display após uma troca de perfil.

        No modo ``personalizado`` mostra o ícone por :attr:`SPLASH_S` antes da tela.
        """
        profile = self._store.active_profile
        wants_splash = (
            profile is not None
            and profile.display.mode == "personalizado"
            and profile.display.icon_splash
            and self._schedule is not None
        )
        if not wants_splash or profile is None or self._schedule is None:
            self.push_display()
            return
        self._splash_token += 1
        token = self._splash_token
        self._splashing = True
        self._send_frame(display.icon_frame(profile), force=False)

        def end() -> None:
            if self._splash_token == token and self._splashing:
                self._splashing = False
                self.push_display()

        self._schedule(self.SPLASH_S, end)

    @property
    def splashing(self) -> bool:
        """O display está mostrando o ícone de uma troca de perfil?"""
        return self._splashing

    def current_frame(self):
        """Quadro que o display deve mostrar agora (também usado pelo preview)."""
        profile = self._store.active_profile
        if profile is None:
            return None
        if self._splashing:
            return display.icon_frame(profile)
        return display.profile_frame(profile, self._clock())

    def preview_frame(self, profile: Profile):
        """Quadro de ``profile`` para a prévia: o ativo mostra o que está no aparelho."""
        if profile.id == self._store.active_profile_id:
            return self.current_frame()
        return display.profile_frame(profile, self._clock())

    def tick(self) -> None:
        """Chamado a cada segundo; como quadros repetidos não saem, é 1 msg/min."""
        profile = self._store.active_profile
        if (
            profile is not None
            and profile.display.mode == "personalizado"
            and not self._splashing
        ):
            self.push_display()

    def push_display(self, force: bool = False) -> None:
        """Envia o quadro do perfil ativo; repetidos são suprimidos, salvo ``force``."""
        # Qualquer quadro normal encerra o ícone da troca de perfil.
        self._splashing = False
        frame = self.current_frame()
        if frame is None:
            return
        self._send_frame(frame, force)

    def _send_frame(self, frame, force: bool) -> None:
        payload = display.frame_payload(frame)
        if not force and payload == self._last_payload:
            return
        self._last_payload = payload
        self._send(protocol.msg_image(payload))

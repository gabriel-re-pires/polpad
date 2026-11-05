"""Controlador central: liga o dispositivo, os perfis e o motor de ações.

Fluxo principal (executa a cada tecla pressionada no macropad):

    evento "key down" -> é a tecla de modo?  -> alterna o perfil ativo
                                                e atualiza o display
                      -> senão               -> resolve a ação no perfil
                                                ativo e a enfileira no
                                                ActionRunner

O controlador não conhece Qt nem pyserial: recebe eventos já decodificados
e fala com o dispositivo por meio da interface ``DeviceLink``. Os serviços
de tempo de que precisa são injetados — ``schedule(segundos, função)``
(fim do ícone na troca de perfil) e ``clock()`` (hora da tela
personalizada), que o host chama a cada segundo por :meth:`tick`. Isso o
torna testável de forma isolada (ver ``tests/test_controller.py``).
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
    # Tempo em que o ícone do perfil fica na tela após uma troca de perfil.
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
        # Ícone mostrado após a troca de perfil. O contador invalida o
        # retorno agendado de uma troca anterior (trocas em sequência).
        self._splash_token = 0
        self._splashing = False

    # ------------------------------------------------------------ eventos

    def handle_message(self, message: dict[str, Any]) -> None:
        """Processa uma mensagem vinda do dispositivo (ou do simulador)."""
        kind = message.get("t")
        if kind == "hello":
            # O dispositivo (re)iniciou ou acabou de nos ver: o que ele tem
            # na tela não é o nosso quadro, então o reenvio é forçado.
            self.push_display(force=True)
        elif kind == "key" and message.get("e") == "down":
            self._handle_key(int(message.get("k", -1)))
        elif kind == "_mode_switch":
            # Mensagem interna gerada pela ação "mode_switch" (ver app.py).
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

    # ------------------------------------------------------------- perfil

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

    # ------------------------------------------------------------ display

    def _show_profile(self) -> None:
        """Atualiza o display após uma troca de perfil.

        No modo ``personalizado``, o ícone do perfil (ou o nome, sem ícone)
        aparece primeiro — é o que identifica o perfil de relance — e, após
        :attr:`SPLASH_S`, dá lugar à tela montada. No modo ``icone`` a tela
        já é o ícone.
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

    def tick(self) -> None:
        """Chamado pelo host a cada segundo: atualiza a hora da tela personalizada.

        Quadros iguais ao último não são reenviados, então na prática sai
        uma mensagem por minuto.
        """
        profile = self._store.active_profile
        if (
            profile is not None
            and profile.display.mode == "personalizado"
            and not self._splashing
        ):
            self.push_display()

    def push_display(self, force: bool = False) -> None:
        """Envia ao display o quadro do perfil ativo.

        Quadros idênticos ao último enviado são suprimidos (a troca de
        perfil pela interface, por exemplo, dispara vários ``refresh``),
        exceto quando ``force`` — após um ``hello`` o dispositivo pode ter
        reiniciado e perdido a tela.
        """
        # Qualquer quadro "normal" encerra o ícone da troca de perfil.
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

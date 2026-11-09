"""Ponte entre threads de backend e a thread da interface Qt.

O sinal só é entregue na thread da UI ("queued") se o receptor for um QObject
que vive nela; ligado a função solta ou a objeto comum, a conexão é direta e
roda na thread que emitiu. Por isso o ``Controller`` usa um :class:`UiRelay`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot


class DeviceBridge(QObject):
    message = Signal(dict)          # mensagem decodificada do dispositivo
    state = Signal(bool, str)       # (conectado?, nome da porta)
    port_denied = Signal(str)       # o sistema negou acesso a esta porta
    action_error = Signal(str)      # erro reportado pelo ActionRunner
    profile_changed = Signal(object)  # Profile ativado (pela tecla de modo ou UI)

    def emit_message(self, message: dict[str, Any]) -> None:
        self.message.emit(message)

    def emit_state(self, connected: bool, port: str) -> None:
        self.state.emit(connected, port)

    def emit_port_denied(self, port: str) -> None:
        self.port_denied.emit(port)


class UiRelay(QObject):
    """Encaminha mensagens a um callback na thread da UI; instancie nela."""

    def __init__(self, handler: Callable[[dict[str, Any]], None]) -> None:
        super().__init__()
        self._handler = handler

    @Slot(dict)
    def deliver(self, message: dict[str, Any]) -> None:
        self._handler(message)

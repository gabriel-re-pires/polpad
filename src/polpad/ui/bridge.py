"""Ponte entre threads de backend e a thread da interface Qt.

Os callbacks do enlace serial e do motor de ações executam em threads
próprias. Emitir um sinal Qt de outra thread é seguro, mas a entrega só
acontece na thread da UI quando o RECEPTOR é um QObject que vive nela —
aí o Qt usa uma conexão "queued". Ligar o sinal a uma função solta, ou a
um método de um objeto que não seja QObject, produz conexão DIRETA: o
código executa na thread que emitiu.

Por isso existe :class:`UiRelay`. Quem trata as mensagens do dispositivo
em código livre de Qt (o ``Controller``) liga o sinal a um relay criado
na thread da interface, e não diretamente ao próprio método.
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
    """Encaminha mensagens para um callback, sempre na thread da UI.

    Instancie na thread da interface. Como o relay é um QObject que mora
    nela, a conexão ``message -> deliver`` vira "queued" quando o sinal
    parte de outra thread, e ``handler`` executa na thread da UI.
    """

    def __init__(self, handler: Callable[[dict[str, Any]], None]) -> None:
        super().__init__()
        self._handler = handler

    @Slot(dict)
    def deliver(self, message: dict[str, Any]) -> None:
        self._handler(message)

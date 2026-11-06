"""Garante uma única instância do aplicativo em execução.

Duas instâncias disputariam a mesma porta serial e colocariam dois ícones
na bandeja. Em vez de simplesmente recusar a segunda, usamos um socket
local (named pipe no Windows): a instância nova avisa a que já roda e
sai, e a original traz sua janela para frente — o comportamento esperado
de quem clica no atalho enquanto o aplicativo está oculto na bandeja.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "Polpad-instancia-unica"
_TIMEOUT_MS = 300

log = logging.getLogger(__name__)


class SingleInstance(QObject):
    """Dono do socket local; emite ``activated`` quando outra instância chega."""

    activated = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server: QLocalServer | None = None

    def try_acquire(self, wait_s: float = 0.0) -> bool:
        """``True`` se esta é a única instância; ``False`` se já havia outra.

        Quando devolve ``False``, a instância que já roda foi avisada e
        deve mostrar sua janela — o chamador só precisa encerrar.

        ``wait_s`` é para o Polpad reaberto depois de uma atualização: a
        instância antiga pode levar alguns instantes para sair, e a nova
        espera por ela em vez de se encerrar.
        """
        deadline = time.monotonic() + wait_s
        while True:
            socket = QLocalSocket()
            socket.connectToServer(SERVER_NAME)
            if not socket.waitForConnected(_TIMEOUT_MS):
                break
            if time.monotonic() >= deadline:
                socket.write(b"activate")
                socket.waitForBytesWritten(_TIMEOUT_MS)
                socket.disconnectFromServer()
                return False
            socket.abort()
            QCoreApplication.processEvents()
            time.sleep(0.2)

        # Ninguém atendeu. Pode ser um socket órfão de um encerramento
        # anormal: removê-lo é seguro justamente porque a conexão falhou.
        QLocalServer.removeServer(SERVER_NAME)

        server = QLocalServer(self)
        server.newConnection.connect(self._on_new_connection)
        if not server.listen(SERVER_NAME):
            # Sem o socket o aplicativo ainda funciona; apenas perde a
            # proteção contra instâncias duplicadas.
            log.warning(
                "não foi possível escutar em %s: %s",
                SERVER_NAME,
                server.errorString(),
            )
            return True

        self._server = server
        return True

    def release(self) -> None:
        """Deixa de ser a instância única (antes de abrir outra)."""
        if self._server is not None:
            self._server.close()
            self._server = None

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        connection = self._server.nextPendingConnection()
        if connection is not None:
            connection.disconnected.connect(connection.deleteLater)
        log.info("outra instância foi aberta; trazendo a janela para frente")
        self.activated.emit()

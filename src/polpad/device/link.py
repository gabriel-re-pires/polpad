"""Enlace com o macropad pela porta serial (USB CDC).

``SerialLink`` acha a porta, faz o handshake, lê mensagens e reconecta numa
thread própria; os callbacks rodam nela (a UI os converte em sinais Qt).
"""

from __future__ import annotations

import errno
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import serial
from serial.tools import list_ports

from . import protocol

log = logging.getLogger(__name__)


class DeviceLink(Protocol):
    """Interface comum ao enlace serial e ao simulador."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def send(self, message: dict[str, Any]) -> None: ...
    @property
    def connected(self) -> bool: ...


def _has_hardware(port: Any) -> bool:
    """Se há um dispositivo de verdade por trás da porta.

    O Linux lista dezenas de ``/dev/ttyS*`` inexistentes, com ``hwid`` "n/a" e
    sem VID; no Windows as portas não USB trazem o barramento no ``hwid``.
    """
    return port.vid is not None or (port.hwid or "n/a") != "n/a"


def available_ports() -> list[tuple[str, str]]:
    """Lista (porta, descrição) das portas seriais presentes, o macropad
    (VID da Espressif) primeiro."""
    ports = [p for p in list_ports.comports() if _has_hardware(p)]
    ports.sort(key=lambda p: p.vid != protocol.ESPRESSIF_VID)
    return [(p.device, p.description or "") for p in ports]


def serial_group() -> str:
    """Grupo dono das portas seriais no Linux (``uucp`` no Arch, ``dialout``
    no Debian/Ubuntu/Fedora), lido do próprio dispositivo quando possível."""
    if sys.platform == "win32":  # não há grupos POSIX (nem o módulo grp)
        return "dialout"
    import grp

    for device in ("/dev/ttyACM0", "/dev/ttyUSB0", "/dev/ttyS0"):
        try:
            return grp.getgrgid(os.stat(device).st_gid).gr_name
        except (OSError, KeyError):
            continue
    return "dialout"


def permission_hint() -> str:
    """Como liberar o acesso às portas seriais no Linux."""
    group = serial_group()
    return (
        f"adicione seu usuário ao grupo {group} "
        f"(sudo usermod -aG {group} $USER) e entre de novo na sessão"
    )


def _read_available(ser: Any) -> bytes:
    """Lê o que já chegou, sem esperar juntar mais.

    ``ser.read(n)`` só volta antes do timeout com ``n`` bytes; um bloco fixo
    fazia cada tecla (~30 bytes) esperar o timeout inteiro.
    """
    return ser.read(ser.in_waiting or 1)


class SerialLink:
    RECONNECT_DELAY_S = 2.0
    HANDSHAKE_TIMEOUT_S = 2.0
    # Avisa o firmware que o host está presente (no modo híbrido, segura o BLE).
    HEARTBEAT_S = 3.0
    # Handshakes sem resposta antes de deixar a porta em paz (cobre o firmware
    # ainda inicializando quando a porta aparece).
    MAX_HANDSHAKE_FAILURES = 3

    def __init__(
        self,
        on_message: Callable[[dict[str, Any]], None],
        on_state: Callable[[bool, str], None],
        preferred_port: str | None = None,
        on_denied: Callable[[str], None] | None = None,
    ) -> None:
        self._on_message = on_message
        self._on_state = on_state
        self._on_denied = on_denied
        self.preferred_port = preferred_port
        self._serial: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._write_lock = threading.Lock()
        # Handshakes sem resposta por porta. No limite, a porta (outra placa
        # ESP32, não o macropad) fica de fora até ser desconectada.
        self._failures: dict[str, int] = {}
        self._announced = False
        # Portas sem permissão já avisadas (uma vez cada).
        self._denied: set[str] = set()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="serial-link")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._close()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def send(self, message: dict[str, Any]) -> None:
        ser = self._serial
        if ser is None or not ser.is_open:
            return
        try:
            with self._write_lock:
                ser.write(protocol.encode(message))
        except (serial.SerialException, OSError):
            self._close()

    def _run(self) -> None:
        while self._running:
            port = self._find_port()
            if port is None:
                time.sleep(self.RECONNECT_DELAY_S)
                continue
            self._attempt(port)
            time.sleep(self.RECONNECT_DELAY_S)

    def _attempt(self, port: str) -> None:
        """Uma tentativa de conexão: abre, faz o handshake e lê até cair."""
        self._announced = False
        try:
            self._connect_and_read(port)
        except (serial.SerialException, OSError) as exc:
            # EACCES no Linux: fora do grupo da porta. Não conta como falha de
            # handshake, para conectar assim que o acesso for liberado.
            if exc.errno == errno.EACCES:
                self._report_denied(port)
        finally:
            self._close()
            # Falha no handshake não conta como conexão caída.
            if self._announced:
                self._announced = False
                log.info("conexão com o macropad em %s encerrada", port)
                self._on_state(False, port)

    def _report_denied(self, port: str) -> None:
        """Avisa (uma vez por porta), no log e na interface, que o acesso foi negado."""
        if port in self._denied:
            return
        self._denied.add(port)
        hint = permission_hint() if os.name == "posix" else "porta em uso?"
        log.warning("sem permissão para abrir %s: %s", port, hint)
        if self._on_denied is not None:
            self._on_denied(port)

    def _candidates(self) -> list[str]:
        """Portas plausíveis, das mais prováveis para as menos."""
        ports = list_ports.comports()
        if self.preferred_port:
            return [p.device for p in ports if p.device == self.preferred_port]
        # Só o VID do macropad. Abrir a porta de outra placa a ocupa (no
        # Windows o acesso é exclusivo: o Arduino IDE não consegue gravar) e
        # ainda pode resetá-la, como acontece com o Arduino Uno.
        return [p.device for p in ports if p.vid == protocol.ESPRESSIF_VID]

    def _find_port(self) -> str | None:
        """Próxima porta, em rodízio para não travar numa que não é o macropad."""
        candidatos = self._candidates()
        # Porta desconectada recomeça do zero quando voltar.
        self._failures = {
            porta: n for porta, n in self._failures.items() if porta in candidatos
        }
        if self.preferred_port:
            # Escolha do usuário: insiste nela.
            return candidatos[0] if candidatos else None
        pendentes = [
            c
            for c in candidatos
            if self._failures.get(c, 0) < self.MAX_HANDSHAKE_FAILURES
        ]
        if not pendentes:
            return None
        return min(pendentes, key=lambda c: self._failures.get(c, 0))

    def _handshake_failed(self, port: str) -> None:
        falhas = self._failures.get(port, 0) + 1
        self._failures[port] = falhas
        if falhas == self.MAX_HANDSHAKE_FAILURES and not self.preferred_port:
            log.info("%s não é o macropad; fica de fora até ser desconectada", port)

    def _handshake_ok(self, port: str) -> None:
        self._failures.pop(port, None)

    def _connect_and_read(self, port: str) -> None:
        ser = serial.Serial(port, protocol.BAUD_RATE, timeout=0.5)
        self._serial = ser
        ok, buffer, pending = self._handshake(ser)
        if not ok:
            log.debug("%s não respondeu ao handshake", port)
            self._handshake_failed(port)
            return
        self._handshake_ok(port)
        # Se o acesso for negado de novo (outro usuário na sessão), avisa outra vez.
        self._denied.discard(port)
        self._announced = True
        log.info("macropad conectado em %s", port)
        self._on_state(True, port)
        # Entrega o que veio junto com o handshake (tipicamente o ``hello``).
        for early in pending:
            self._on_message(early)
        last_ping = time.monotonic()
        while self._running and ser.is_open:
            now = time.monotonic()
            if now - last_ping >= self.HEARTBEAT_S:
                last_ping = now
                self.send(protocol.msg_ping())
            chunk = _read_available(ser)
            if not chunk:
                continue
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                message = protocol.decode(line)
                if message is not None:
                    self._on_message(message)

    def _handshake(
        self, ser: serial.Serial
    ) -> tuple[bool, bytes, list[dict[str, Any]]]:
        """Confirma que a porta é do macropad antes de anunciá-la.

        Devolve ``(reconhecido, resto do buffer, mensagens já decodificadas)``.
        Só o ``pong`` reconhece: um ``hello`` antigo pode vir represado com
        teclas apertadas com o app fechado, que não devem ser executadas.
        O ``hello`` logo antes do ``pong`` é mantido (primeira tela do display).
        """
        with self._write_lock:
            ser.write(protocol.encode(protocol.msg_ping()))
        deadline = time.monotonic() + self.HANDSHAKE_TIMEOUT_S
        buffer = b""
        pending: list[dict[str, Any]] = []
        recognized = False
        # ``hello`` visto antes do ``pong``: só é atual se nada vier entre os dois.
        hello: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            chunk = _read_available(ser)
            if not chunk:
                if recognized:
                    break
                continue
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                decoded = protocol.decode(line)
                if decoded is None:
                    continue
                if recognized:
                    pending.append(decoded)
                    continue
                # Teclas antes do ``pong`` são antigas (represadas): descarta.
                kind = decoded.get("t")
                if kind == "pong":
                    recognized = True
                    if hello is not None:
                        pending.append(hello)
                    pending.append(decoded)
                elif kind == "hello":
                    hello = decoded
                else:
                    # Algo veio entre o hello e o pong: o hello era antigo.
                    hello = None
            if recognized and not buffer:
                break
        return recognized, buffer, pending

    def _close(self) -> None:
        ser = self._serial
        self._serial = None
        if ser is not None:
            try:
                ser.close()
            except Exception:  # cabo removido: o driver lança tipos variados
                log.debug("falha ao fechar a porta serial", exc_info=True)

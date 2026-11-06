"""Enlace com o dispositivo físico via porta serial (USB CDC).

``SerialLink`` roda uma thread própria que:
  1. localiza a porta do macropad (preferindo o VID da Espressif ou a
     porta fixada nas configurações);
  2. faz o handshake ``ping``/``hello``;
  3. lê mensagens continuamente e as repassa aos callbacks;
  4. reconecta automaticamente se o cabo for removido.

Os callbacks são invocados na thread do enlace — a camada de UI os
converte em sinais Qt (ver ``ui.bridge``).
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

    O Linux cria dezenas de ``/dev/ttyS*`` para UARTs que a máquina não
    tem, e o pyserial lista todas, com ``hwid`` "n/a" e sem VID. No
    Windows só aparecem portas existentes, e as que não são USB trazem o
    identificador do barramento (``ACPI\\PNP0501\\1``) no ``hwid``.
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

    ``ser.read(n)`` só volta antes do timeout quando já há ``n`` bytes; uma
    tecla tem ~30 bytes, então pedir um bloco fixo fazia cada aperto
    esperar o timeout inteiro da porta. Com nada no buffer, ``read(1)``
    volta assim que o primeiro byte chega.
    """
    return ser.read(ser.in_waiting or 1)


class SerialLink:
    RECONNECT_DELAY_S = 2.0
    HANDSHAKE_TIMEOUT_S = 2.0
    # Ping periódico: mantém o firmware ciente de que o host está presente
    # (no modo híbrido, o firmware desativa o fallback BLE enquanto isso).
    HEARTBEAT_S = 3.0

    def __init__(
        self,
        on_message: Callable[[dict[str, Any]], None],
        on_state: Callable[[bool, str], None],
        preferred_port: str | None = None,
        on_denied: Callable[[str], None] | None = None,
    ) -> None:
        self._on_message = on_message
        self._on_state = on_state
        # Chamado (uma vez por porta) quando o sistema nega acesso à porta.
        self._on_denied = on_denied
        self.preferred_port = preferred_port
        self._serial: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._write_lock = threading.Lock()
        # Portas que responderam algo que não é o macropad. Guardá-las evita
        # insistir para sempre na mesma quando há outros dispositivos USB.
        self._rejected: set[str] = set()
        # Se a conexão atual já foi anunciada à interface como ativa.
        self._announced = False
        # Portas sem permissão de acesso já avisadas no log (uma vez cada).
        self._denied: set[str] = set()

    # ------------------------------------------------------------- ciclo

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

    # ----------------------------------------------------------- interno

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
            # No Linux, quem não está no grupo dono da porta recebe EACCES.
            # A porta não vai para ``_rejected``: liberado o acesso, a
            # próxima tentativa já conecta.
            if exc.errno == errno.EACCES:
                self._report_denied(port)
        finally:
            self._close()
            # Só avisa a queda de uma conexão que chegou a ser anunciada;
            # uma porta que falhou no handshake nunca "conectou".
            if self._announced:
                self._announced = False
                log.info("conexão com o macropad em %s encerrada", port)
                self._on_state(False, port)

    def _report_denied(self, port: str) -> None:
        """Avisa (uma vez por porta) que o sistema negou acesso a ela.

        Só o log não bastava: a interface seguia em "Procurando o
        macropad…" com ele ligado, e o usuário ia testar porta por porta.
        """
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
        espressif = [p.device for p in ports if p.vid == protocol.ESPRESSIF_VID]
        outras = [
            p.device
            for p in ports
            if p.vid is not None and p.device not in espressif
        ]
        return espressif + outras

    def _find_port(self) -> str | None:
        """Escolhe a próxima porta a tentar, alternando entre as candidatas.

        Sem o rodízio, uma primeira porta que não fosse o macropad (outro
        conversor USB-serial, por exemplo) seria tentada indefinidamente e
        o dispositivo real nunca seria encontrado.
        """
        candidatos = self._candidates()
        if not candidatos:
            self._rejected.clear()
            return None
        pendentes = [c for c in candidatos if c not in self._rejected]
        if not pendentes:
            # Todas já falharam: recomeça a rodada (o macropad pode ter sido
            # ligado depois, ou o firmware ainda estava inicializando).
            self._rejected.clear()
            pendentes = candidatos
        return pendentes[0]

    def _connect_and_read(self, port: str) -> None:
        ser = serial.Serial(port, protocol.BAUD_RATE, timeout=0.5)
        self._serial = ser
        ok, buffer, pending = self._handshake(ser)
        if not ok:
            log.debug("%s não respondeu ao handshake", port)
            self._rejected.add(port)
            return
        self._rejected.discard(port)
        # Se o acesso for negado de novo (outro usuário na sessão), avisa outra vez.
        self._denied.discard(port)
        self._announced = True
        log.info("macropad conectado em %s", port)
        self._on_state(True, port)
        # O que chegou junto com a resposta do handshake (tipicamente o
        # ``hello`` logo após o ``pong``) é entregue, não descartado.
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
        """Confirma que a porta pertence ao macropad antes de anunciá-la.

        Devolve ``(reconhecido, resto do buffer, mensagens já decodificadas)``.
        O firmware responde ao ``ping`` com ``pong`` e, se acabou de nos
        ver, um ``hello`` na sequência — frequentemente no mesmo pacote.
        Descartar o resto do buffer perderia esse ``hello`` (e com ele a
        primeira atualização do display).
        """
        with self._write_lock:
            ser.write(protocol.encode(protocol.msg_ping()))
        deadline = time.monotonic() + self.HANDSHAKE_TIMEOUT_S
        buffer = b""
        pending: list[dict[str, Any]] = []
        recognized = False
        while time.monotonic() < deadline:
            chunk = _read_available(ser)
            if not chunk:
                if recognized:
                    break
                continue
            buffer += chunk
            # Só linhas completas: decodificar fragmentos daria resultados
            # imprevisíveis a cada leitura parcial.
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                decoded = protocol.decode(line)
                if decoded is None:
                    continue
                if decoded.get("t") in ("pong", "hello"):
                    recognized = True
                # Eventos de tecla que chegam ANTES da resposta ao ping
                # ficaram represados no firmware enquanto ninguém lia a
                # porta (o cabo estava ligado, o aplicativo não): são
                # antigos e executá-los agora dispararia ações fantasmas.
                if recognized:
                    pending.append(decoded)
            if recognized and not buffer:
                # Resposta completa já em mãos: não há por que esperar o
                # resto do timeout.
                break
        return recognized, buffer, pending

    def _close(self) -> None:
        ser = self._serial
        self._serial = None
        if ser is not None:
            try:
                ser.close()
            except Exception:  # fechar é best-effort
                # O cabo já pode ter sido removido; o driver lança tipos
                # variados nesse caso e o enlace vai reconectar de todo jeito.
                log.debug("falha ao fechar a porta serial", exc_info=True)

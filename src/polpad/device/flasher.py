"""Gravação do firmware no ESP32-C3 via ``esptool``, sem Qt.

O release publica a imagem completa (bootloader + partições + aplicação, ver
``tools/merge_firmware.py``), gravada em 0x0; o ``*.ino.bin`` da Arduino IDE
traz só a aplicação e vai para 0x10000. O progresso vem trocando o logger
global do esptool, sob lock e desfeito no ``finally``.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

log = logging.getLogger(__name__)

CHIP = "esp32c3"
# Rápido e ainda estável em conversores USB-serial baratos; o USB nativo ignora.
FLASH_BAUD = 460800

#: Imagem completa (bootloader + partições + aplicação).
MERGED_OFFSET = 0x0
#: Aplicação isolada, como a Arduino IDE exporta em ``*.ino.bin``.
APP_OFFSET = 0x10000

#: Primeiro byte de toda imagem de firmware da Espressif.
_ESP_IMAGE_MAGIC = 0xE9
_MAX_IMAGE_BYTES = 16 * 1024 * 1024

# Sequências ANSI que o esptool usa para redesenhar a barra de progresso.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

_swap_lock = threading.Lock()


class FlashError(RuntimeError):
    """Falha ao gravar — mensagem já pronta para exibição ao usuário."""


class FlashCancelledError(FlashError):
    """A gravação foi interrompida a pedido do usuário."""


@dataclass(frozen=True)
class FirmwareImage:
    """Um arquivo ``.bin`` e o endereço em que ele deve ser gravado."""

    path: Path
    offset: int
    version: str = ""

    @property
    def app_only(self) -> bool:
        return self.offset != MERGED_OFFSET

    @classmethod
    def from_path(cls, path: Path | str, version: str = "") -> FirmwareImage:
        path = Path(path)
        return cls(path=path, offset=guess_offset(path), version=version)


def guess_offset(path: Path | str) -> int:
    """Endereço pelo nome: ``*.ino.bin`` é só a aplicação; o resto, imagem completa."""
    return APP_OFFSET if Path(path).name.lower().endswith(".ino.bin") else MERGED_OFFSET


def validate(image: FirmwareImage) -> None:
    """Recusa arquivos que claramente não são um firmware do ESP32."""
    path = image.path
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FlashError(f"Não foi possível ler {path.name}: {exc}") from exc
    if size == 0:
        raise FlashError(f"{path.name} está vazio.")
    if size > _MAX_IMAGE_BYTES:
        raise FlashError(
            f"{path.name} tem {size / 1024 / 1024:.1f} MB — grande demais "
            "para a memória flash do ESP32-C3."
        )
    try:
        with path.open("rb") as handle:
            magic = handle.read(1)
    except OSError as exc:
        raise FlashError(f"Não foi possível ler {path.name}: {exc}") from exc
    if not magic or magic[0] != _ESP_IMAGE_MAGIC:
        raise FlashError(
            f"{path.name} não parece um firmware do ESP32 (o arquivo deveria "
            f"começar com 0x{_ESP_IMAGE_MAGIC:02X}). Confira se você não "
            "selecionou o .elf ou o .zip por engano."
        )


def flash(
    port: str,
    image: FirmwareImage,
    on_log: Callable[[str], None] | None = None,
    on_progress: Callable[[int], None] | None = None,
    cancel: threading.Event | None = None,
    baud: int = FLASH_BAUD,
) -> None:
    """Grava ``image`` no macropad em ``port``; levanta :class:`FlashError` em falha.

    A porta precisa estar livre (ver ``MacropadApp.pause_link``).
    """
    validate(image)

    argv = [
        "--chip",
        CHIP,
        "--port",
        port,
        "--baud",
        str(baud),
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "write-flash",
        "--flash-size",
        "detect",
        "--compress",
        hex(image.offset),
        str(image.path),
    ]
    log.info("gravando %s em %s (offset 0x%X)", image.path.name, port, image.offset)
    _run_esptool(argv, on_log=on_log, on_progress=on_progress, cancel=cancel)
    log.info("gravação concluída em %s", port)


def _run_esptool(
    argv: list[str],
    on_log: Callable[[str], None] | None,
    on_progress: Callable[[int], None] | None,
    cancel: threading.Event | None,
) -> None:
    """Executa o esptool no processo atual, com o logger redirecionado.

    Em processo porque no executável do PyInstaller não há Python para invocar.
    """
    try:
        import esptool
        from esptool.logger import log as esptool_log
    except ImportError as exc:  # pragma: no cover - dependência declarada
        raise FlashError(
            "O componente de gravação (esptool) não está instalado. "
            'Reinstale as dependências com: pip install -e "."'
        ) from exc

    logger_class = _callback_logger_class()
    with _swap_lock:
        restore = _snapshot_logger(esptool_log)
        logger_class.bind(on_log, on_progress, cancel)
        try:
            esptool_log.set_logger(logger_class())
            esptool.main(argv)
        except FlashCancelledError:
            raise
        except SystemExit as exc:  # o esptool encerra assim em erro de uso
            raise FlashError(_describe(exc)) from exc
        except Exception as exc:
            raise FlashError(_describe(exc)) from exc
        finally:
            restore()
            logger_class.bind(None, None, None)


def _snapshot_logger(esptool_log: Any) -> Callable[[], None]:
    """Guarda o logger ativo do esptool e devolve a função que o restaura.

    Até o 5.x antigo, ``set_logger`` troca a *classe* de ``log``. Com esp-pylib
    (5.6+), ``log`` é um proxy de ``EspLog.instance`` e ``set_logger`` troca a
    instância por um ``_LegacyLoggerAdapter``; aí é a instância que se restaura.
    """
    try:
        from esp_pylib.logger import EspLog
    except ImportError:
        EspLog = None  # type: ignore[misc,assignment]  # noqa: N806 - nome da classe importada

    if EspLog is not None and not hasattr(type(esptool_log), "set_logger"):
        previous_instance = EspLog.instance

        def restore() -> None:
            EspLog.instance = previous_instance

        return restore

    previous_class = type(esptool_log)

    def restore_class() -> None:
        esptool_log.__class__ = previous_class

    return restore_class


def _describe(exc: BaseException) -> str:
    """Traduz as falhas mais comuns do esptool para algo acionável."""
    text = str(exc).strip() or exc.__class__.__name__
    lowered = text.lower()
    if "no serial data received" in lowered or "failed to connect" in lowered:
        return (
            "O ESP32-C3 não respondeu. Confira se o cabo USB transmite dados "
            "(não só carga) e, se a placa não tiver reset automático, segure "
            "BOOT, toque em RESET, solte BOOT e grave de novo.\n\n"
            f"Detalhe: {text}"
        )
    # Linux sem acesso ao grupo da porta. Vem antes porque o esptool embrulha
    # este erro na mesma frase "the port is busy or doesn't exist".
    if "permission denied" in lowered:
        from .link import permission_hint

        return (
            f"Sem permissão para abrir a porta serial: {permission_hint()}."
            f"\n\nDetalhe: {text}"
        )
    # Pela mensagem do esptool não dá para separar os dois casos.
    ocupada = "busy" in lowered or "access is denied" in lowered
    inexistente = "could not open" in lowered or "doesn't exist" in lowered
    if ocupada and inexistente:
        return (
            "Não foi possível abrir a porta: ou ela está em uso por outro "
            "programa (Monitor Serial da Arduino IDE, por exemplo), ou o "
            "macropad foi desconectado. Feche os outros programas, reconecte "
            f"o cabo e atualize a lista de portas.\n\nDetalhe: {text}"
        )
    if ocupada or "permission" in lowered:
        return (
            "A porta está ocupada. Feche o Monitor Serial da Arduino IDE (ou "
            "qualquer outro programa usando essa COM) e tente novamente.\n\n"
            f"Detalhe: {text}"
        )
    if inexistente or "does not exist" in lowered:
        return (
            "A porta selecionada não existe mais. Reconecte o macropad e "
            f"atualize a lista de portas.\n\nDetalhe: {text}"
        )
    if "wrong chip" in lowered or "not an esp32-c3" in lowered:
        return (
            "O dispositivo nessa porta não é um ESP32-C3. Confira se a porta "
            f"selecionada é mesmo a do macropad.\n\nDetalhe: {text}"
        )
    return text


_logger_class: type[Any] | None = None


def _callback_logger_class() -> type[Any]:
    """Cria (uma vez) a subclasse de ``TemplateLogger`` que alimenta a UI.

    Montada aqui para não importar o esptool junto com o módulo. Os callbacks
    são atributos de classe porque ``set_logger`` troca só a classe do logger.
    """
    global _logger_class
    if _logger_class is not None:
        return _logger_class

    from esptool.logger import TemplateLogger

    class _CallbackLogger(TemplateLogger):
        on_log: ClassVar[Callable[[str], None] | None] = None
        on_progress: ClassVar[Callable[[int], None] | None] = None
        cancel: ClassVar[threading.Event | None] = None

        @classmethod
        def bind(
            cls,
            on_log: Callable[[str], None] | None,
            on_progress: Callable[[int], None] | None,
            cancel: threading.Event | None,
        ) -> None:
            cls.on_log = staticmethod(on_log) if on_log else None
            cls.on_progress = staticmethod(on_progress) if on_progress else None
            cls.cancel = cancel

        @classmethod
        def _emit(cls, text: str) -> None:
            callback = cls.on_log
            if callback is None:
                return
            for line in _ANSI.sub("", text).replace("\r", "\n").splitlines():
                stripped = line.strip()
                if stripped:
                    callback(stripped)

        def print(self, *args: Any, **kwargs: Any) -> None:
            self._check_cancel()
            self._emit(" ".join(str(arg) for arg in args))

        def note(self, message: str) -> None:
            self._emit(f"Nota: {message}")

        def warning(self, message: str) -> None:
            self._emit(f"Aviso: {message}")

        def error(self, message: str) -> None:
            self._emit(str(message))

        def stage(self, finish: bool = False) -> None:
            """Sem colapso de etapas: no log da janela tudo deve permanecer."""

        def progress_bar(
            self,
            cur_iter: int,
            total_iters: int,
            prefix: str = "",
            suffix: str = "",
            bar_length: int = 30,
        ) -> None:
            self._check_cancel()
            callback = type(self).on_progress
            if callback is not None and total_iters:
                callback(max(0, min(100, round(100 * cur_iter / total_iters))))

        def set_verbosity(self, verbosity: str) -> None:
            """A verbosidade de terminal não se aplica à janela."""

        @classmethod
        def _check_cancel(cls) -> None:
            # O esptool não expõe cancelamento, mas chama o logger a cada bloco.
            event = cls.cancel
            if event is not None and event.is_set():
                raise FlashCancelledError("Gravação cancelada.")

    _logger_class = _CallbackLogger
    return _CallbackLogger

"""Configuração de log do aplicativo.

O aplicativo roda normalmente sob ``pythonw.exe`` (sem console), onde
``sys.stdout``/``sys.stderr`` são ``None`` e qualquer mensagem — inclusive
o traceback de uma exceção não tratada — se perderia. Por isso o log vai
para um arquivo rotativo em ``%APPDATA%/Polpad/logs/``, e o
console só é usado quando existe (execução via ``python -m polpad``).
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from .store import default_data_dir

LOG_FILE = "polpad.log"
MAX_BYTES = 512 * 1024
BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(name)s %(levelname)s: %(message)s"

log = logging.getLogger(__name__)


def log_dir() -> Path:
    return default_data_dir() / "logs"


def setup(level: int = logging.INFO) -> Path | None:
    """Instala os handlers de log. Devolve o caminho do arquivo, se houver.

    Falhar ao criar o arquivo de log nunca deve impedir o aplicativo de
    abrir: nesse caso restam apenas os handlers de console (se existirem).
    """
    root = logging.getLogger()
    root.setLevel(level)
    # O obsws_python registra em INFO os parâmetros de conexão com a senha
    # do OBS em texto claro; dele só interessam avisos e erros.
    logging.getLogger("obsws_python").setLevel(logging.WARNING)
    formatter = logging.Formatter(_FORMAT)

    # Console: só quando há um terminal de verdade (python.exe).
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        root.addHandler(console)

    path = log_dir() / LOG_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("sem log em arquivo (%s): %s", path, exc)
        return None

    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    _install_excepthook()
    return path


def _install_excepthook() -> None:
    """Registra tracebacks não tratados no log antes de o app morrer."""
    previous = sys.excepthook

    def handler(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        logging.getLogger("polpad").critical(
            "exceção não tratada", exc_info=(exc_type, exc, tb)
        )
        previous(exc_type, exc, tb)

    sys.excepthook = handler

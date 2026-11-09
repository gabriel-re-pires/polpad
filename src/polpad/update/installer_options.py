"""Escolhas do instalador do Windows, aplicadas na primeira abertura.

O instalador grava ``opcoes-do-instalador.json`` em vez de mexer no
``config.json``; a instalação silenciosa (atualização) não grava.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..core.models import Settings

log = logging.getLogger(__name__)

OPTIONS_FILE = "opcoes-do-instalador.json"
#: Opções que o instalador pode definir (todas booleanas).
KEYS = ("start_with_windows", "update_notify")


def apply(data_dir: Path, settings: Settings) -> bool:
    """Aplica e apaga o arquivo. ``True`` se alguma configuração mudou."""
    path = data_dir / OPTIONS_FILE
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return False
    except OSError:
        log.warning("não foi possível ler %s", path, exc_info=True)
        return False
    try:
        options = json.loads(raw)
    except ValueError:
        log.warning("opções do instalador ilegíveis; ignoradas")
        options = {}
    changed = False
    if isinstance(options, dict):
        for key in KEYS:
            value = options.get(key)
            if isinstance(value, bool) and getattr(settings, key) != value:
                setattr(settings, key, value)
                changed = True
    try:
        path.unlink()
    except OSError:
        log.warning("não foi possível apagar %s", path, exc_info=True)
    return changed

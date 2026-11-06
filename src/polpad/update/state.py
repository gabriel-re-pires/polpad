"""Estado do atualizador, guardado fora das preferências do usuário.

``updates/estado.json`` lembra a última verificação, a atualização já
baixada à espera de instalação e a troca de versão em andamento. Um
arquivo ausente ou ilegível vale como estado vazio: no pior caso o
aplicativo verifica de novo.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def updates_dir(data_dir: Path) -> Path:
    return data_dir / "updates"


def state_path(data_dir: Path) -> Path:
    return updates_dir(data_dir) / "estado.json"


@dataclass
class Pending:
    """Versão baixada e conferida, à espera de instalação."""

    version: str
    path: str
    sha256: str


@dataclass
class Switch:
    """Troca de versão iniciada (conferida na próxima abertura)."""

    from_version: str
    to_version: str
    started: str


@dataclass
class UpdateState:
    last_check: str | None = None
    pending: Pending | None = None
    switch: Switch | None = None

    @classmethod
    def load(cls, path: Path) -> UpdateState:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("estado não é um objeto")
            return cls(
                last_check=raw.get("last_check"),
                pending=_load(Pending, raw.get("pending")),
                switch=_load(Switch, raw.get("switch")),
            )
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError, TypeError) as exc:
            log.warning("estado do atualizador ilegível (%s); recomeçando", exc)
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


def _load(kind: Any, raw: Any) -> Any:
    return kind(**raw) if isinstance(raw, dict) else None

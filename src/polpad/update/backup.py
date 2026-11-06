"""Cópias dos perfis feitas antes de qualquer troca de versão.

Copia só o que é do usuário — ``config.json`` e ``icons/`` —, não logs,
cache de firmware, downloads nem os próprios backups. Ficam as ``KEEP``
cópias mais recentes.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

KEEP = 5
CONFIG = "config.json"
ICONS = "icons"
META = "backup.json"


@dataclass(frozen=True)
class Backup:
    path: Path
    created: datetime
    from_version: str
    to_version: str

    @property
    def label(self) -> str:
        return f"{self.from_version} → {self.to_version}"


def backups_dir(data_dir: Path) -> Path:
    return data_dir / "backups"


def create(
    data_dir: Path, from_version: str, to_version: str, now: datetime | None = None
) -> Backup:
    created = now or datetime.now()
    name = f"{created:%Y%m%d-%H%M%S}-{from_version}-para-{to_version}"
    path = backups_dir(data_dir) / name
    suffix = 1
    while path.exists():
        suffix += 1
        path = backups_dir(data_dir) / f"{name}-{suffix}"
    path.mkdir(parents=True)
    if (data_dir / CONFIG).is_file():
        shutil.copy2(data_dir / CONFIG, path / CONFIG)
    if (data_dir / ICONS).is_dir():
        shutil.copytree(data_dir / ICONS, path / ICONS)
    meta = {"created": created.isoformat(), "from": from_version, "to": to_version}
    (path / META).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    _prune(data_dir)
    return Backup(path, created, from_version, to_version)


def list_backups(data_dir: Path) -> list[Backup]:
    """Cópias válidas, a mais recente primeiro."""
    result = []
    root = backups_dir(data_dir)
    if not root.is_dir():
        return []
    for path in root.iterdir():
        try:
            meta = json.loads((path / META).read_text(encoding="utf-8"))
            result.append(
                Backup(
                    path,
                    datetime.fromisoformat(meta["created"]),
                    str(meta["from"]),
                    str(meta["to"]),
                )
            )
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("backup ilegível ignorado: %s", path)
    result.sort(key=lambda b: b.created, reverse=True)
    return result


def restore(
    data_dir: Path, backup: Backup, current_version: str, now: datetime | None = None
) -> Backup:
    """Volta os perfis de ``backup``, guardando antes o estado atual."""
    safety = create(data_dir, current_version, "restauração", now=now)
    if (backup.path / CONFIG).is_file():
        shutil.copy2(backup.path / CONFIG, data_dir / CONFIG)
    if (backup.path / ICONS).is_dir():
        shutil.rmtree(data_dir / ICONS, ignore_errors=True)
        shutil.copytree(backup.path / ICONS, data_dir / ICONS)
    return safety


def _prune(data_dir: Path) -> None:
    for old in list_backups(data_dir)[KEEP:]:
        shutil.rmtree(old.path, ignore_errors=True)

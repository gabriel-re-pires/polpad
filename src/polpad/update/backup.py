"""Cópias dos perfis (``config.json`` e ``icons/``) antes de trocar de versão.

Ficam as ``KEEP`` mais recentes e, além delas, sempre a última de antes de uma
atualização, que as da Zona de risco não podem empurrar para fora.
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

# Por que a cópia foi feita.
UPDATE = "atualização"
RISK = "zona de risco"
RESTORE = "restauração"
# Cópias anteriores ao campo "kind": só o destino dizia o que eram.
_LEGACY_NOT_UPDATE = {"configurações padrão", "perfis apagados", "restauração"}


@dataclass(frozen=True)
class Backup:
    path: Path
    created: datetime
    from_version: str
    to_version: str
    kind: str = UPDATE

    @property
    def label(self) -> str:
        return f"{self.from_version} → {self.to_version}"


def backups_dir(data_dir: Path) -> Path:
    return data_dir / "backups"


def create(
    data_dir: Path,
    from_version: str,
    to_version: str,
    now: datetime | None = None,
    protect: Path | None = None,
    kind: str = UPDATE,
) -> Backup:
    """Copia os perfis. ``protect`` é poupada da limpeza das antigas."""
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
    meta = {
        "created": created.isoformat(),
        "from": from_version,
        "to": to_version,
        "kind": kind,
    }
    (path / META).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    _prune(data_dir, protect)
    return Backup(path, created, from_version, to_version, kind)


def list_backups(data_dir: Path) -> list[Backup]:
    """Cópias válidas, a mais recente primeiro."""
    result = []
    root = backups_dir(data_dir)
    if not root.is_dir():
        return []
    for path in root.iterdir():
        try:
            meta = json.loads((path / META).read_text(encoding="utf-8"))
            to_version = str(meta["to"])
            kind = meta.get("kind") or (
                RISK if to_version in _LEGACY_NOT_UPDATE else UPDATE
            )
            result.append(
                Backup(
                    path,
                    datetime.fromisoformat(meta["created"]),
                    str(meta["from"]),
                    to_version,
                    str(kind),
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
    # A cópia restaurada pode ser a mais antiga: só sai da lista depois.
    safety = create(
        data_dir, current_version, "restauração", now, backup.path, RESTORE
    )
    if (backup.path / CONFIG).is_file():
        shutil.copy2(backup.path / CONFIG, data_dir / CONFIG)
    if (backup.path / ICONS).is_dir():
        shutil.rmtree(data_dir / ICONS, ignore_errors=True)
        shutil.copytree(backup.path / ICONS, data_dir / ICONS)
    _prune(data_dir)
    return safety


def _prune(data_dir: Path, protect: Path | None = None) -> None:
    copias = list_backups(data_dir)
    poupadas = {protect}
    # A última cópia de antes de atualizar fica sempre, mesmo além de KEEP.
    ultima_atualizacao = next((b for b in copias if b.kind == UPDATE), None)
    if ultima_atualizacao is not None:
        poupadas.add(ultima_atualizacao.path)
    for old in copias[KEEP:]:
        if old.path not in poupadas:
            shutil.rmtree(old.path, ignore_errors=True)

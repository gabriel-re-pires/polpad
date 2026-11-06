"""Decisões do atualizador, sem efeitos colaterais.

Tudo aqui recebe o que precisa (relógio incluído) e devolve uma decisão:
é a parte que se testa por inteiro sem rede, sem Qt e sem arquivos.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from .github import is_newer
from .releases import AppRelease
from .state import Pending, Switch

CHECK_INTERVAL = timedelta(hours=24)
FIRST_CHECK_DELAY_MS = 10_000


def should_check(last_check: datetime | None, now: datetime) -> bool:
    """Sem registro, há mais de 24 h, ou com o relógio voltado para trás."""
    if last_check is None or last_check > now:
        return True
    return now - last_check >= CHECK_INTERVAL


def available_update(releases: list[AppRelease], current: str) -> AppRelease | None:
    """A versão instalável mais nova acima da atual."""
    candidates = [r for r in releases if r.installable and is_newer(r.version, current)]
    if not candidates:
        return None
    best = candidates[0]
    for release in candidates[1:]:
        if is_newer(release.version, best.version):
            best = release
    return best


def should_notify(
    update: AppRelease | None, notify_enabled: bool, dismissed: bool
) -> bool:
    return update is not None and notify_enabled and not dismissed


def pending_action(
    pending: Pending | None, current: str, file_exists: bool
) -> Literal["install", "discard", "none"]:
    if pending is None:
        return "none"
    if file_exists and is_newer(pending.version, current):
        return "install"
    return "discard"


def switch_outcome(
    switch: Switch | None, current: str
) -> Literal["ok", "failed", "none"]:
    if switch is None:
        return "none"
    return "ok" if switch.to_version == current else "failed"


def is_downgrade(target: str, current: str) -> bool:
    return is_newer(current, target)

"""Descoberta e download do firmware publicado no GitHub.

Usa o release mais recente que tenha um ``firmware*.bin`` anexado, com cache
em ``%APPDATA%/Polpad/firmware``; assim o firmware sai sem republicar o app.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.store import default_data_dir
from ..update import github
from ..update.github import is_newer, normalize_version

__all__ = [
    "ASSET_PATTERN",
    "FirmwareRelease",
    "ReleaseError",
    "cache_dir",
    "download",
    "is_newer",
    "latest_release",
    "normalize_version",
    "version_from_asset",
]

log = logging.getLogger(__name__)

#: ``firmware-1.2.0.bin``, ``firmware.bin``…
ASSET_PATTERN = re.compile(r"^firmware[\w.\-]*\.bin$", re.IGNORECASE)


class ReleaseError(github.GitHubError):
    """Falha ao consultar ou baixar o firmware publicado."""


@dataclass(frozen=True)
class FirmwareRelease:
    tag: str
    version: str
    asset_name: str
    url: str
    size: int
    notes: str = ""

    @property
    def cached_path(self) -> Path:
        # A tag no nome impede que releases diferentes se sobrescrevam no cache.
        return cache_dir() / f"{self.tag}-{self.asset_name}"


def cache_dir() -> Path:
    return default_data_dir() / "firmware"


def latest_release(session: Any | None = None) -> FirmwareRelease:
    """Firmware do release publicado mais recente que tenha um."""
    try:
        releases = github.published_releases(session)
    except github.GitHubError as exc:
        raise ReleaseError(str(exc)) from exc

    for payload in releases:
        asset = _pick_asset(payload.get("assets") or [])
        if asset is None:
            continue
        tag = str(payload.get("tag_name") or "").strip()
        asset_name = str(asset.get("name"))
        return FirmwareRelease(
            tag=tag or "release",
            # As tags versionam o aplicativo; a do firmware vem do nome do anexo.
            version=version_from_asset(asset_name) or normalize_version(tag),
            asset_name=asset_name,
            url=str(asset.get("browser_download_url")),
            size=int(asset.get("size") or 0),
            notes=str(payload.get("body") or ""),
        )
    raise ReleaseError(
        "Nenhum release publicado tem um binário de firmware (firmware*.bin). "
        "Grave a partir de um arquivo local."
    )


def _pick_asset(assets: Iterable[Any]) -> dict[str, Any] | None:
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if ASSET_PATTERN.match(name) and asset.get("browser_download_url"):
            return asset
    return None


def download(
    release: FirmwareRelease,
    on_progress: Callable[[int], None] | None = None,
    session: Any | None = None,
) -> Path:
    """Baixa (ou reaproveita do cache) o binário do release."""
    destination = release.cached_path
    if _is_cached(destination, release.size):
        log.info("firmware %s já estava em cache", release.tag)
        if on_progress is not None:
            on_progress(100)
        return destination
    try:
        return github.download(
            release.url, destination, release.size, on_progress, session
        )
    except github.GitHubError as exc:
        raise ReleaseError(f"Falha ao baixar o firmware.\n\n{exc}") from exc


def _is_cached(path: Path, expected_size: int) -> bool:
    try:
        if not path.is_file():
            return False
        return not expected_size or path.stat().st_size == expected_size
    except OSError:
        return False


def version_from_asset(asset_name: str) -> str:
    """Versão no nome do anexo (``firmware-2.0.0.bin``), ou "" se não houver.

    Exige um ponto, senão ``firmware-esp32c3.bin`` viraria a "versão 32".
    """
    match = re.search(r"\d+(?:\.\d+)+", asset_name or "")
    return match.group(0) if match else ""

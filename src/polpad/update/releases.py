"""Versões do aplicativo publicadas no GitHub.

Cada release traz um arquivo por sistema e um ``SHA256SUMS.txt``. Uma
versão só é instalável pelo aplicativo quando tem os dois: isso exclui,
sem número fixo no código, as versões anteriores ao instalador.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from . import github

WINDOWS_ASSET = "Polpad-Windows-Instalador.exe"
LINUX_ASSET = "Polpad-Linux-Instalador.tar.gz"
# Nomes até a 0.5.0: ainda aceitos, para instalar essas versões.
LEGACY_ASSETS = {
    WINDOWS_ASSET: "Polpad-Setup.exe",
    LINUX_ASSET: "Polpad-linux-x86_64.tar.gz",
}
SUMS_ASSET = "SHA256SUMS.txt"


def platform_asset(platform: str = sys.platform) -> str:
    return WINDOWS_ASSET if platform == "win32" else LINUX_ASSET


@dataclass(frozen=True)
class AppRelease:
    version: str
    tag: str
    name: str
    notes: str
    published_at: str
    html_url: str
    asset_name: str
    asset_url: str | None
    asset_size: int
    sums_url: str | None

    @property
    def installable(self) -> bool:
        return bool(self.asset_url and self.sums_url)


def _asset(assets: list[Any], name: str) -> dict[str, Any] | None:
    for asset in assets:
        if (
            isinstance(asset, dict)
            and asset.get("name") == name
            and asset.get("browser_download_url")
        ):
            return asset
    return None


def list_releases(
    session: Any | None = None, platform: str = sys.platform
) -> list[AppRelease]:
    """Versões publicadas, a mais nova primeiro."""
    name = platform_asset(platform)
    result = []
    for payload in github.published_releases(session):
        assets = payload.get("assets") or []
        found = name
        asset = _asset(assets, name)
        if asset is None:
            found = LEGACY_ASSETS[name]
            asset = _asset(assets, found)
            if asset is None:
                found = name
        sums = _asset(assets, SUMS_ASSET)
        tag = str(payload.get("tag_name") or "")
        result.append(
            AppRelease(
                version=github.normalize_version(tag),
                tag=tag,
                name=str(payload.get("name") or tag),
                notes=str(payload.get("body") or ""),
                published_at=str(payload.get("published_at") or ""),
                html_url=str(payload.get("html_url") or ""),
                asset_name=found,
                asset_url=str(asset["browser_download_url"]) if asset else None,
                asset_size=int(asset.get("size") or 0) if asset else 0,
                sums_url=str(sums["browser_download_url"]) if sums else None,
            )
        )
    return result


def parse_sums(text: str) -> dict[str, str]:
    """Lê o formato do ``sha256sum``: ``hash  nome`` ou ``hash *nome``."""
    sums = {}
    for line in text.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    return sums


def expected_sha256(release: AppRelease, session: Any | None = None) -> str:
    if not release.sums_url:
        raise github.GitHubError(f"O release {release.tag} não tem {SUMS_ASSET}.")
    sums = parse_sums(github.get_text(release.sums_url, session))
    try:
        return sums[release.asset_name]
    except KeyError:
        raise github.GitHubError(
            f"O {SUMS_ASSET} do release {release.tag} não traz a soma de "
            f"{release.asset_name}."
        ) from None

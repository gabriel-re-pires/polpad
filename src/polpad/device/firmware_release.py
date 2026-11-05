"""Descoberta e download do firmware publicado no GitHub.

O aplicativo consulta o *release* mais recente do repositório do projeto e
baixa o binário anexado para um cache em
``%APPDATA%/Polpad/firmware``. Assim o firmware pode ser
atualizado sem republicar o executável, e o usuário que só quer usar o
macropad não precisa de Arduino IDE nem de código-fonte.

O módulo é isolado do esptool e do Qt: recebe/devolve dados simples e é
testável com um cliente HTTP falso.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ..core.store import default_data_dir

log = logging.getLogger(__name__)

GITHUB_REPO = "gabriel-re-pires/polpad"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

#: Anexos aceitos como firmware. ``firmware-1.2.0.bin``, ``firmware.bin``…
ASSET_PATTERN = re.compile(r"^firmware[\w.\-]*\.bin$", re.IGNORECASE)

_TIMEOUT_S = 15.0
_CHUNK = 64 * 1024


class ReleaseError(RuntimeError):
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
        # O nome inclui a tag: releases diferentes nunca se sobrescrevem no
        # cache, e um download interrompido não passa por completo.
        return cache_dir() / f"{self.tag}-{self.asset_name}"


def cache_dir() -> Path:
    return default_data_dir() / "firmware"


# ------------------------------------------------------------------ consulta


def latest_release(session: Any | None = None) -> FirmwareRelease:
    """Devolve o firmware do release mais recente do repositório.

    ``session`` existe para os testes; em produção usa-se o ``requests``.
    """
    client = session if session is not None else requests
    try:
        response = client.get(
            LATEST_RELEASE_URL,
            timeout=_TIMEOUT_S,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise ReleaseError(
            "Não foi possível consultar o GitHub. Verifique a conexão com a "
            f"internet.\n\nDetalhe: {exc}"
        ) from exc
    except ValueError as exc:
        raise ReleaseError("O GitHub devolveu uma resposta inesperada.") from exc

    if not isinstance(payload, dict):
        raise ReleaseError("O GitHub devolveu uma resposta inesperada.")

    tag = str(payload.get("tag_name") or "").strip()
    asset = _pick_asset(payload.get("assets") or [])
    if asset is None:
        raise ReleaseError(
            f"O release {tag or 'mais recente'} não tem um binário de firmware "
            "anexado (esperado um arquivo firmware*.bin). Grave a partir de um "
            "arquivo local ou publique o binário no release."
        )
    asset_name = str(asset.get("name"))
    return FirmwareRelease(
        tag=tag or "release",
        # A versão é a do FIRMWARE, lida do nome do anexo: as tags do
        # repositório versionam o aplicativo, que tem numeração própria.
        # Sem número no nome, a tag é o melhor palpite disponível.
        version=version_from_asset(asset_name) or normalize_version(tag),
        asset_name=asset_name,
        url=str(asset.get("browser_download_url")),
        size=int(asset.get("size") or 0),
        notes=str(payload.get("body") or ""),
    )


def _pick_asset(assets: Iterable[Any]) -> dict[str, Any] | None:
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if ASSET_PATTERN.match(name) and asset.get("browser_download_url"):
            return asset
    return None


# ------------------------------------------------------------------ download


def download(
    release: FirmwareRelease,
    on_progress: Callable[[int], None] | None = None,
    session: Any | None = None,
) -> Path:
    """Baixa (ou reaproveita do cache) o binário do release.

    Escreve primeiro em ``.part`` e só então renomeia: um download
    interrompido nunca vira um arquivo aparentemente válido no cache — que
    seria gravado no macropad na tentativa seguinte.
    """
    destination = release.cached_path
    if _is_cached(destination, release.size):
        log.info("firmware %s já estava em cache", release.tag)
        if on_progress is not None:
            on_progress(100)
        return destination

    client = session if session is not None else requests
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = client.get(release.url, timeout=_TIMEOUT_S, stream=True)
        response.raise_for_status()
        total = release.size or int(response.headers.get("Content-Length") or 0)
        written = 0
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=_CHUNK):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
                if on_progress is not None and total:
                    on_progress(max(0, min(100, round(100 * written / total))))
        if total and written != total:
            raise ReleaseError(
                f"O download veio incompleto ({written} de {total} bytes). "
                "Tente novamente."
            )
        partial.replace(destination)
    except requests.RequestException as exc:
        _discard(partial)
        raise ReleaseError(
            f"Falha ao baixar o firmware.\n\nDetalhe: {exc}"
        ) from exc
    except OSError as exc:
        _discard(partial)
        raise ReleaseError(
            f"Não foi possível gravar o firmware em {cache_dir()}.\n\n"
            f"Detalhe: {exc}"
        ) from exc
    except ReleaseError:
        _discard(partial)
        raise

    if on_progress is not None:
        on_progress(100)
    return destination


def _is_cached(path: Path, expected_size: int) -> bool:
    try:
        if not path.is_file():
            return False
        return not expected_size or path.stat().st_size == expected_size
    except OSError:
        return False


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - limpeza é best-effort
        log.debug("não foi possível remover %s", path, exc_info=True)


# ------------------------------------------------------------------- versões


def normalize_version(tag: str) -> str:
    """Extrai ``1.2.0`` de tags como ``v1.2.0``, ``fw-1.2.0`` ou ``1.2.0``."""
    match = re.search(r"\d+(?:\.\d+)*", tag or "")
    return match.group(0) if match else (tag or "").strip()


def version_from_asset(asset_name: str) -> str:
    """Extrai a versão do firmware do nome do anexo (``firmware-2.0.0.bin``).

    É daqui que sai a versão comparada com a que o dispositivo anuncia no
    ``hello``, porque as tags do repositório versionam o *aplicativo* e
    não o firmware.

    Exige pelo menos um ponto (``2.0``), senão nomes como
    ``firmware-esp32c3.bin`` virariam a "versão 32". Devolve string vazia
    quando o nome não traz versão alguma — cabe a quem chama recorrer à
    tag.
    """
    match = re.search(r"\d+(?:\.\d+)+", asset_name or "")
    return match.group(0) if match else ""


def _parts(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version or ""))


def is_newer(candidate: str, installed: str) -> bool:
    """``True`` se ``candidate`` for uma versão posterior a ``installed``.

    Versões ilegíveis devolvem ``False``: na dúvida, o aplicativo não
    sugere uma atualização que pode não existir.
    """
    left, right = _parts(candidate), _parts(installed)
    if not left or not right:
        return False
    size = max(len(left), len(right))
    return left + (0,) * (size - len(left)) > right + (0,) * (size - len(right))

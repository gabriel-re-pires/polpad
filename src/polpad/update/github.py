"""Releases do repositório no GitHub, para o firmware e o atualizador.

Todo acesso à rede aceita um ``session`` falso nos testes.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

REPO = "gabriel-re-pires/polpad"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases"
#: Só para testes: troca a URL consultada por outra no mesmo formato.
RELEASES_URL_ENV = "POLPAD_RELEASES_URL"

_TIMEOUT_S = 15.0
_CHUNK = 64 * 1024


class GitHubError(RuntimeError):
    """Falha ao consultar ou baixar algo do GitHub."""


class DownloadCancelledError(GitHubError):
    """Download interrompido a pedido (o Polpad está saindo)."""


def releases_url() -> str:
    return os.environ.get(RELEASES_URL_ENV) or RELEASES_URL


def _client(session: Any | None) -> Any:
    return session if session is not None else requests


#: Limite de consultas da API (60 por hora por IP, sem login).
_RATE_LIMIT_STATUS = (403, 429)


def _network_error(exc: Exception) -> GitHubError:
    response = getattr(exc, "response", None)
    if (
        isinstance(exc, requests.HTTPError)
        and response is not None
        and response.status_code in _RATE_LIMIT_STATUS
    ):
        return GitHubError(
            "O GitHub limitou as consultas; tente de novo em alguns minutos."
            f"\n\nDetalhe: {exc}"
        )
    return GitHubError(
        "Não foi possível consultar o GitHub. Verifique a conexão com a "
        f"internet.\n\nDetalhe: {exc}"
    )


def get_json(url: str, session: Any | None = None) -> Any:
    try:
        response = _client(session).get(
            url, timeout=_TIMEOUT_S, headers={"Accept": "application/vnd.github+json"}
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise _network_error(exc) from exc
    except ValueError as exc:
        raise GitHubError("O GitHub devolveu uma resposta inesperada.") from exc


def get_text(url: str, session: Any | None = None) -> str:
    try:
        response = _client(session).get(url, timeout=_TIMEOUT_S)
        response.raise_for_status()
        return str(response.text)
    except requests.RequestException as exc:
        raise _network_error(exc) from exc


def published_releases(session: Any | None = None) -> list[dict[str, Any]]:
    """Releases publicados (sem rascunhos nem pré-lançamentos), o mais novo
    primeiro. Tags sem número de versão vão para o fim."""
    payload = get_json(releases_url(), session)
    if not isinstance(payload, list):
        raise GitHubError("O GitHub devolveu uma resposta inesperada.")
    releases = [
        r
        for r in payload
        if isinstance(r, dict) and not r.get("draft") and not r.get("prerelease")
    ]
    releases.sort(
        key=lambda r: version_key(normalize_version(str(r.get("tag_name") or ""))),
        reverse=True,
    )
    return releases


def download(
    url: str,
    destination: Path,
    expected_size: int = 0,
    on_progress: Callable[[int], None] | None = None,
    session: Any | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Path:
    """Baixa ``url`` para ``destination``; ``cancel`` é consultado a cada bloco.

    Grava em ``.part`` e só renomeia com o tamanho conferido.
    """
    partial = destination.with_name(destination.name + ".part")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = _client(session).get(url, timeout=_TIMEOUT_S, stream=True)
        response.raise_for_status()
        total = expected_size or int(response.headers.get("Content-Length") or 0)
        written = 0
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=_CHUNK):
                if cancel is not None and cancel():
                    raise DownloadCancelledError("Download cancelado.")
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
                if on_progress is not None and total:
                    on_progress(max(0, min(100, round(100 * written / total))))
        if total and written != total:
            raise GitHubError(
                f"O download veio incompleto ({written} de {total} bytes). "
                "Tente novamente."
            )
        partial.replace(destination)
    except requests.RequestException as exc:
        _discard(partial)
        raise GitHubError(f"Falha no download.\n\nDetalhe: {exc}") from exc
    except OSError as exc:
        _discard(partial)
        raise GitHubError(
            f"Não foi possível gravar em {destination.parent}.\n\nDetalhe: {exc}"
        ) from exc
    except GitHubError:
        _discard(partial)
        raise
    if on_progress is not None:
        on_progress(100)
    return destination


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - limpeza é best-effort
        log.debug("não foi possível remover %s", path, exc_info=True)


def normalize_version(tag: str) -> str:
    """Extrai ``1.2.0`` de tags como ``v1.2.0``, ``fw-1.2.0`` ou ``1.2.0``."""
    match = re.search(r"\d+(?:\.\d+)*", tag or "")
    return match.group(0) if match else (tag or "").strip()


def version_key(version: str) -> tuple[int, ...]:
    """Tupla comparável; vazia para versões sem número."""
    return tuple(int(part) for part in re.findall(r"\d+", version or ""))


def is_newer(candidate: str, installed: str) -> bool:
    """``True`` se ``candidate`` for posterior a ``installed``; ilegível dá ``False``."""
    left, right = version_key(candidate), version_key(installed)
    if not left or not right:
        return False
    size = max(len(left), len(right))
    return left + (0,) * (size - len(left)) > right + (0,) * (size - len(right))

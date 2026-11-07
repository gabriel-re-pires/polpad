"""Baixa uma versão conferindo a soma e faz a troca.

Windows: o instalador do Inno Setup troca os arquivos depois que o Polpad
se fecha (com a janela de progresso, ao atualizar pelo aviso). Linux: o
executável novo é extraído ao lado do atual e renomeado por cima dele — a
troca é instantânea e o processo em execução não é afetado.
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
import tarfile
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from . import github, releases
from .state import updates_dir

log = logging.getLogger(__name__)

ELF_MAGIC = b"\x7fELF"
# Desde a 0.6.0 o executável vem na pasta Polpad-Linux; antes, solto.
LINUX_MEMBERS = ("Polpad-Linux/Polpad", "Polpad")
_NEW_NAME = ".polpad.novo"


class InstallError(RuntimeError):
    """Falha ao preparar ou aplicar uma versão; a mensagem vai ao usuário."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(
    release: releases.AppRelease,
    data_dir: Path,
    on_progress: Callable[[int], None] | None = None,
    session: Any | None = None,
    cancel: Callable[[], bool] | None = None,
) -> tuple[Path, str]:
    """Baixa o arquivo da versão e confere o SHA-256 com o do release."""
    if not release.installable or release.asset_url is None:
        raise InstallError(
            f"A versão {release.version} não pode ser instalada pelo Polpad."
        )
    destination = updates_dir(data_dir) / release.tag / release.asset_name
    try:
        expected = releases.expected_sha256(release, session)
        github.download(
            release.asset_url,
            destination,
            release.asset_size,
            on_progress,
            session,
            cancel,
        )
    except github.GitHubError as exc:
        raise InstallError(str(exc)) from exc
    try:
        actual = sha256_file(destination)
    except OSError as exc:
        raise InstallError(
            f"Não foi possível gravar em {destination.parent}: {exc}"
        ) from exc
    if actual != expected:
        destination.unlink(missing_ok=True)
        log.warning("soma divergente para %s: %s != %s", destination, actual, expected)
        raise InstallError("O arquivo veio corrompido. Tente de novo.")
    return destination, actual


def windows_command(installer: Path, log_path: Path, relaunch: bool) -> list[str]:
    """Linha de comando do instalador.

    Atualizando pelo aviso (``relaunch``), o instalador mostra a janela de
    progresso: sem ela o Polpad some por alguns segundos e a pessoa tenta
    abri-lo de novo no meio da troca. Ao sair pela bandeja, em silêncio.
    """
    argv = [
        str(installer),
        "/SILENT" if relaunch else "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CLOSEAPPLICATIONS",
        f"/LOG={log_path}",
    ]
    if relaunch:
        argv.append("/ATUALIZACAO")
    return argv


def launch_detached(argv: list[str]) -> None:
    """Abre um processo que sobrevive ao fechamento do Polpad.

    ``PYINSTALLER_RESET_ENVIRONMENT`` faz o executável aberto se comportar
    como uma instância nova: sem isso, o Polpad empacotado em arquivo único
    (Linux) reusaria a pasta temporária desta instância — apagada quando
    ela sai — em vez de desempacotar a própria versão. O instalador do
    Windows repassa o mesmo ambiente ao Polpad que ele reabre.
    """
    log.info("abrindo: %s", argv)
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(argv, creationflags=flags, close_fds=True, env=env)  # noqa: S603
    else:
        subprocess.Popen(  # noqa: S603
            argv, start_new_session=True, close_fds=True, env=env
        )


def swap_linux(package: Path, target: Path) -> None:
    """Troca ``target`` pelo executável dentro de ``package`` (.tar.gz)."""
    new = target.parent / _NEW_NAME
    try:
        with tarfile.open(package, "r:gz") as tar:
            names = set(tar.getnames())
            member = next((m for m in LINUX_MEMBERS if m in names), LINUX_MEMBERS[-1])
            source = tar.extractfile(tar.getmember(member))
            if source is None:
                raise InstallError("O pacote não contém o executável do Polpad.")
            with source, new.open("wb") as handle:
                while block := source.read(1024 * 1024):
                    handle.write(block)
        with new.open("rb") as handle:
            if handle.read(len(ELF_MAGIC)) != ELF_MAGIC:
                raise InstallError("O pacote não contém um executável Linux válido.")
        new.chmod(0o755)
        os.replace(new, target)
    except PermissionError as exc:
        new.unlink(missing_ok=True)
        raise InstallError(f"Sem permissão para gravar em {target.parent}.") from exc
    except (KeyError, tarfile.TarError, EOFError, zlib.error) as exc:
        # Um .tar.gz cortado (download pela metade) termina em EOFError ou
        # zlib.error ao ler o membro, não em TarError.
        new.unlink(missing_ok=True)
        raise InstallError("O pacote baixado está danificado.") from exc
    except InstallError:
        new.unlink(missing_ok=True)
        raise
    except OSError as exc:
        new.unlink(missing_ok=True)
        raise InstallError(f"Não foi possível gravar em {target.parent}: {exc}") from exc


InstallKind = Literal["desenvolvimento", "windows", "linux_menu", "nao_instalado"]


def install_kind() -> InstallKind:
    if not getattr(sys, "frozen", False):
        return "desenvolvimento"
    executable = os.path.normcase(os.path.abspath(sys.executable))
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        folder = os.path.normcase(os.path.join(local, "Programs", "Polpad"))
        if local and executable.startswith(folder + os.sep):
            return "windows"
        return "nao_instalado"
    menu = os.path.normcase(str(Path.home() / ".local" / "bin" / "polpad"))
    return "linux_menu" if executable == menu else "nao_instalado"

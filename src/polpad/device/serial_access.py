"""Libera, no Linux, o acesso do usuário à porta serial do macropad.

Entrar no grupo ``uucp``/``dialout`` só vale após novo login; uma regra udev com
``TAG+="uaccess"`` (placas Espressif) vale na hora, instalada via ``pkexec``.
``ID_MM_DEVICE_IGNORE`` impede o ModemManager de ocupar a porta sondando-a.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

from . import protocol

# Antes de 73-seat-late.rules, que é quem aplica a marca ``uaccess``.
# PurePosixPath: o caminho é do Linux mesmo quando os testes rodam no Windows.
RULE_PATH = PurePosixPath("/etc/udev/rules.d/70-polpad.rules")

RULE = (
    "# Polpad: dá ao usuário da sessão ativa acesso ao macropad (placas da\n"
    "# Espressif), sem precisar entrar no grupo uucp/dialout.\n"
    "# Apagar este arquivo desfaz.\n"
    f'SUBSYSTEM=="tty", ATTRS{{idVendor}}=="{protocol.ESPRESSIF_VID:04x}", '
    'TAG+="uaccess", ENV{ID_MM_DEVICE_IGNORE}="1"\n'
)

# Uma chamada só (uma senha). ``settle`` espera o udev aplicar a permissão.
_SCRIPT = (
    'install -m 0644 "$1" "$2"'
    " && udevadm control --reload-rules"
    " && udevadm trigger --action=change --subsystem-match=tty"
    " && udevadm settle --timeout=10"
)

_PKEXEC_DISMISSED = 126  # ver ``man pkexec``


class GrantError(RuntimeError):
    """Não foi possível liberar o acesso — mensagem pronta para o usuário."""


class GrantCancelledError(GrantError):
    """O usuário fechou a janela que pede a senha."""


def can_grant() -> bool:
    """Se dá para liberar o acesso daqui (Linux com pkexec e udev)."""
    return (
        sys.platform.startswith("linux")
        and shutil.which("pkexec") is not None
        and shutil.which("udevadm") is not None
    )


def grant(run: Callable[..., Any] = subprocess.run) -> None:
    """Instala a regra udev pedindo a senha de administrador."""
    fd, tmp = tempfile.mkstemp(prefix="polpad-", suffix=".rules")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(RULE)
        argv = ["pkexec", "/bin/sh", "-c", _SCRIPT, "sh", tmp, str(RULE_PATH)]
        try:
            result = run(argv, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            raise GrantError(f"Não foi possível executar o pkexec: {exc}") from exc
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
    if result.returncode == _PKEXEC_DISMISSED:
        raise GrantCancelledError("A senha não foi informada.")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GrantError(detail or f"pkexec terminou com código {result.returncode}.")

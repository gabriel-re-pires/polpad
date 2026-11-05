"""Libera, no Linux, o acesso do usuário à porta serial do macropad.

A porta (``/dev/ttyACM0``) pertence a um grupo do sistema (``uucp`` no
Arch, ``dialout`` no Debian/Ubuntu/Fedora). Entrar nele resolve, mas só
depois de sair e entrar de novo na sessão — e até lá o macropad parece
apenas "desconectado".

Uma regra udev com ``TAG+="uaccess"`` resolve na hora: o systemd-logind
dá ao usuário da sessão ativa uma ACL sobre os dispositivos com essa
marca, como já faz com câmera e microfone. A regra vale só para placas da
Espressif (VID 303a) e é instalada uma vez, com a senha de administrador
pedida pelo ``pkexec``. Apagar o arquivo desfaz.

``ID_MM_DEVICE_IGNORE`` afasta o ModemManager, que sonda toda porta
``ttyACM`` nova com comandos AT e a deixa ocupada nos primeiros segundos.

O módulo não conhece Qt: a interface chama :func:`grant` numa thread.
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

# Instala a regra e a reaplica às portas já conectadas, numa chamada só
# (uma senha só). ``settle`` espera o udev terminar: a próxima tentativa
# do enlace já encontra a permissão no lugar.
_SCRIPT = (
    'install -m 0644 "$1" "$2"'
    " && udevadm control --reload-rules"
    " && udevadm trigger --action=change --subsystem-match=tty"
    " && udevadm settle --timeout=10"
)

# Códigos de saída do pkexec (ver ``man pkexec``).
_PKEXEC_DISMISSED = 126


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
    """Instala a regra udev pedindo a senha de administrador.

    Levanta :class:`GrantCancelledError` se a janela de senha for fechada e
    :class:`GrantError` em qualquer outra falha.
    """
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

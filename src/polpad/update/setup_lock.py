"""Trava do instalador: o Polpad não abre no meio de uma instalação.

O Inno Setup mantém o mutex ``MUTEX`` (``SetupMutex`` em ``tools/polpad.iss``)
enquanto recopia ``_internal``; roda antes de importar o Qt, só com ``ctypes``.
"""

from __future__ import annotations

import sys

MUTEX = "PolpadInstalando"
_SYNCHRONIZE = 0x00100000


def setup_running() -> bool:
    """Se o instalador do Polpad está rodando agora (só Windows)."""
    if sys.platform != "win32":
        return False
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    handle = kernel32.OpenMutexW(_SYNCHRONIZE, False, MUTEX)
    if not handle:
        return False
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return True

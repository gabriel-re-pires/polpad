"""Trava do instalador: o Polpad não abre no meio de uma instalação.

Enquanto o instalador do Inno Setup roda, ele mantém o mutex ``MUTEX``
(``SetupMutex`` em ``tools/polpad.iss``). Nesse intervalo a pasta
``_internal`` está sendo apagada e copiada de novo; um Polpad aberto
agora acharia o Qt pela metade e mostraria um erro do Python. A
conferência roda antes de qualquer import do Qt e usa só ``ctypes``.
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

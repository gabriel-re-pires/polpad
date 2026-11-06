"""O Polpad não abre enquanto o instalador troca os arquivos."""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from polpad import __main__ as entrada
from polpad.update import setup_lock

ISS = Path(__file__).resolve().parent.parent / "tools" / "polpad.iss"


class TravaTest(unittest.TestCase):
    def test_instalador_cria_a_trava_com_o_mesmo_nome(self):
        texto = ISS.read_text(encoding="utf-8")
        linha = re.search(r"^SetupMutex=(.+)$", texto, re.MULTILINE)
        self.assertIsNotNone(linha)
        self.assertIn(setup_lock.MUTEX, linha.group(1).split(","))

    @unittest.skipUnless(sys.platform == "win32", "trava do Windows")
    def test_enxerga_a_trava_do_instalador(self):
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        self.assertFalse(setup_lock.setup_running())
        handle = kernel32.CreateMutexW(None, False, setup_lock.MUTEX)
        self.assertTrue(handle)
        try:
            self.assertTrue(setup_lock.setup_running())
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        self.assertFalse(setup_lock.setup_running())

    def test_fora_do_windows_nunca_trava(self):
        with mock.patch.object(setup_lock.sys, "platform", "linux"):
            self.assertFalse(setup_lock.setup_running())

    def test_main_sai_sem_abrir_janela_durante_a_instalacao(self):
        with (
            mock.patch.object(setup_lock, "setup_running", return_value=True),
            mock.patch("PySide6.QtWidgets.QApplication") as qapp,
        ):
            self.assertEqual(entrada.main(), 0)
        qapp.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Página "Gravar firmware": estado durante a gravação e mensagem de sucesso."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from polpad.device.firmware_release import FirmwareRelease
from polpad.ui import flash_dialog

APP = QApplication.instance() or QApplication([])


class JobFalso(QObject):
    """Substitui o ``_FlashJob``: não abre porta nem roda o esptool."""

    log_line = Signal(str)
    progress = Signal(int)
    stage = Signal(str)
    ok = Signal()
    failed = Signal(str)
    finished = Signal()

    criados: ClassVar[list[JobFalso]] = []

    def __init__(self, port, release, local_path, cancel, parent=None) -> None:
        super().__init__(parent)
        self.release = release
        self.local_path = local_path
        self._rodando = False
        JobFalso.criados.append(self)

    def start(self) -> None:
        self._rodando = True

    def isRunning(self) -> bool:  # noqa: N802  (mesmo nome do QThread)
        return self._rodando


class PaginaGravandoTest(unittest.TestCase):
    def setUp(self):
        JobFalso.criados = []
        self.core = mock.Mock()
        self.core.pause_link.return_value = True
        patches = (
            mock.patch.object(
                flash_dialog, "available_ports", return_value=[("COM250", "porta falsa")]
            ),
            mock.patch.object(flash_dialog.FlashPage, "_check_release"),
            mock.patch.object(flash_dialog.FlashPage, "_confirm", return_value=True),
            mock.patch.object(flash_dialog, "_FlashJob", JobFalso),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.info = mock.patch.object(flash_dialog.QMessageBox, "information").start()
        self.addCleanup(mock.patch.stopall)

        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.bin_local = Path(pasta.name) / "meu.ino.bin"
        self.bin_local.write_bytes(b"\xE9" + b"\0" * 100)

        self.pagina = flash_dialog.FlashPage(self.core, current_port="COM250")
        self.addCleanup(self.pagina.deleteLater)
        self.pagina._on_release_found(
            FirmwareRelease("v2.1.0", "2.1.0", "fw.bin", "http://x", 1000)
        )

    def _escolher_arquivo_local(self):
        self.pagina._file_edit.setText(str(self.bin_local))
        self.pagina._file_radio.setChecked(True)
        self.pagina._refresh_enabled()

    def _mensagem_de_sucesso(self) -> str:
        self.info.assert_called_once()
        return self.info.call_args.args[2]

    def test_arquivo_local_nao_mostra_versao_do_release(self):
        self._escolher_arquivo_local()
        self.pagina._start()
        self.assertIsNone(JobFalso.criados[0].release)
        self.pagina._on_success()
        mensagem = self._mensagem_de_sucesso()
        self.assertIn("sucesso", mensagem)
        self.assertNotIn("2.1.0", mensagem)

    def test_release_mostra_a_versao(self):
        self.pagina._release_radio.setChecked(True)
        self.pagina._start()
        self.pagina._on_success()
        self.assertIn("(versão 2.1.0)", self._mensagem_de_sucesso())

    def test_controles_desabilitados_durante_a_gravacao(self):
        self._escolher_arquivo_local()
        self.pagina._start()
        self.assertTrue(JobFalso.criados[0].isRunning())
        self.assertFalse(self.pagina.back_button.isEnabled())
        self.assertFalse(self.pagina._port_combo.isEnabled())
        self.assertFalse(self.pagina._release_radio.isEnabled())
        self.assertFalse(self.pagina._file_radio.isEnabled())

    def test_controles_voltam_ao_terminar(self):
        self._escolher_arquivo_local()
        self.pagina._start()
        JobFalso.criados[0]._rodando = False
        self.pagina._on_finished()
        self.assertTrue(self.pagina.back_button.isEnabled())
        self.assertTrue(self.pagina._port_combo.isEnabled())
        self.assertTrue(self.pagina._file_radio.isEnabled())


if __name__ == "__main__":
    unittest.main()

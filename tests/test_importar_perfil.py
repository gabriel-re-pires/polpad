"""Importar perfil pela barra lateral: arquivos estranhos viram mensagem."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from polpad.core import profile_io
from polpad.core.models import Profile
from polpad.core.store import Store
from polpad.ui import profile_panel

from .apoio import CofreFalso

APP = QApplication.instance() or QApplication([])


class ImportarPerfilTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pasta = Path(self._tmp.name)
        self.store = Store(data_dir=self.pasta / "dados", vault=CofreFalso())
        self.store.load()
        self.painel = profile_panel.ProfilePanel(self.store)
        self.addCleanup(self.painel.deleteLater)
        self.critico = mock.patch.object(
            profile_panel.QMessageBox, "critical"
        ).start()
        self.addCleanup(mock.patch.stopall)

    def _importar(self, arquivo: Path) -> None:
        with mock.patch.object(
            profile_panel.QFileDialog,
            "getOpenFileName",
            return_value=(str(arquivo), ""),
        ):
            self.painel._import()

    def test_binario_renomeado_mostra_erro(self):
        png = self.pasta / "imagem.json"
        png.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x80" * 10)
        antes = len(self.store.profiles)
        self._importar(png)
        self.critico.assert_called_once()
        self.assertIn("inválido", self.critico.call_args.args[2])
        self.assertEqual(len(self.store.profiles), antes)

    def test_json_com_bom_e_aceito(self):
        # O Bloco de Notas antigo salva UTF-8 com BOM.
        arquivo = self.pasta / "perfil.json"
        texto = profile_io.to_json(Profile(name="Com BOM"))
        arquivo.write_bytes(texto.encode("utf-8-sig"))
        self._importar(arquivo)
        self.critico.assert_not_called()
        self.assertIn("Com BOM", [p.name for p in self.store.profiles])


if __name__ == "__main__":
    unittest.main()

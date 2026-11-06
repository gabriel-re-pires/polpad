"""Testes das escolhas feitas no instalador, aplicadas na primeira abertura."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from polpad.core.models import Settings
from polpad.update import installer_options


class OpcoesDoInstaladorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dados = Path(self._tmp.name)
        self.arquivo = self.dados / installer_options.OPTIONS_FILE

    def _gravar(self, conteudo: str) -> None:
        self.arquivo.write_text(conteudo, encoding="utf-8")

    def test_aplica_e_apaga(self):
        self._gravar(json.dumps({"start_with_windows": True, "update_notify": False}))
        settings = Settings()
        self.assertTrue(installer_options.apply(self.dados, settings))
        self.assertTrue(settings.start_with_windows)
        self.assertFalse(settings.update_notify)
        self.assertFalse(self.arquivo.exists())

    def test_sem_arquivo_nao_muda_nada(self):
        settings = Settings(start_with_windows=False)
        self.assertFalse(installer_options.apply(self.dados, settings))
        self.assertEqual(settings, Settings(start_with_windows=False))

    def test_arquivo_ilegivel_e_descartado(self):
        self._gravar("{")
        settings = Settings()
        self.assertFalse(installer_options.apply(self.dados, settings))
        self.assertEqual(settings, Settings())
        self.assertFalse(self.arquivo.exists())

    def test_so_valores_booleanos_valem(self):
        self._gravar(json.dumps({"start_with_windows": "sim", "update_notify": False}))
        settings = Settings()
        installer_options.apply(self.dados, settings)
        self.assertFalse(settings.start_with_windows)
        self.assertFalse(settings.update_notify)

    def test_arquivo_com_bom_do_instalador(self):
        # O Inno Setup grava UTF-8 com BOM.
        self.arquivo.write_bytes(b"\xef\xbb\xbf" + b'{"start_with_windows": true}')
        settings = Settings()
        self.assertTrue(installer_options.apply(self.dados, settings))
        self.assertTrue(settings.start_with_windows)


if __name__ == "__main__":
    unittest.main()

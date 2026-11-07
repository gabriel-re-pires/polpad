"""Renomear ou excluir o perfil ativo atualiza o display do aparelho."""

from __future__ import annotations

import base64
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from polpad.core import display, icons
from polpad.core.controller import Controller
from polpad.core.store import Store
from polpad.ui.main_window import MainWindow

from .apoio import CofreFalso

APP = QApplication.instance() or QApplication([])
AGORA = datetime(2026, 11, 7, 10, 30, 0)


class DisplayDoPerfilAtivoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        self.store.load()
        self.a = self.store.profiles[0]
        self.a.name = "A"
        self.b = self.store.add_profile("B")
        self.enviados = []
        self.agendado = []
        self.controller = Controller(
            store=self.store,
            runner=mock.Mock(),
            send=self.enviados.append,
            schedule=lambda _s, fn: self.agendado.append(fn),
            clock=lambda: AGORA,
        )
        self.controller.activate_profile(self.b.id)
        self.janela = mock.Mock()
        self.janela._core.controller = self.controller
        self.janela._core.store = self.store
        self.enviados.clear()

    def _quadros(self):
        return [m for m in self.enviados if m.get("t") == "img"]

    def _ultimo(self):
        return icons.unpack_bits(base64.b64decode(self._quadros()[-1]["d"])).tobytes()

    def test_renomear_o_perfil_ativo_atualiza_o_display(self):
        self.b.name = "Novo nome"
        MainWindow._refresh_all(self.janela)
        self.assertEqual(len(self._quadros()), 1)
        self.assertEqual(self._ultimo(), display.profile_frame(self.b, AGORA).tobytes())
        # Nada mudou: não reenvia.
        MainWindow._refresh_all(self.janela)
        self.assertEqual(len(self._quadros()), 1)

    def test_excluir_o_perfil_ativo_mostra_o_novo_ativo(self):
        self.store.remove_profile(self.b.id)
        MainWindow._refresh_all(self.janela)
        self.assertEqual(len(self._quadros()), 1)
        ativo = self.store.active_profile
        self.assertEqual(self._ultimo(), display.profile_frame(ativo, AGORA).tobytes())

    def test_nao_corta_o_icone_da_troca_de_perfil(self):
        self.a.display.mode = "personalizado"
        self.a.display.icon_splash = True
        self.controller.activate_profile(self.a.id)
        self.enviados.clear()
        MainWindow._refresh_all(self.janela)
        self.assertTrue(self.controller.splashing)
        self.assertEqual(self._quadros(), [])


if __name__ == "__main__":
    unittest.main()

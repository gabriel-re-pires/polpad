"""A tela do meio segue o perfil ativo no macropad, e as teclas só acendem nele."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from polpad.core.models import Action
from polpad.core.store import Store
from polpad.ui.main_window import MainWindow

from .apoio import CofreFalso

APP = QApplication.instance() or QApplication([])


class PerfilDoMacropadTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        self.store.load()
        self.a = self.store.profiles[0]
        self.b = self.store.add_profile("B")
        self.store.active_profile_id = self.a.id

    def _janela(self, editando):
        janela = mock.Mock()
        janela._core.store = self.store
        janela._core.controller.splashing = False
        janela._editing_profile_id = editando
        return janela

    def _tecla(self, janela, k):
        MainWindow._on_device_message(janela, {"t": "key", "k": k, "e": "down"})

    def test_troca_no_macropad_muda_a_tela_do_meio(self):
        janela = self._janela(self.a.id)
        MainWindow._on_active_profile_changed(janela, self.b)
        janela._profile_panel.select.assert_called_once_with(self.b.id)

    def test_tecla_acende_no_perfil_ativo(self):
        janela = self._janela(self.a.id)
        self._tecla(janela, 4)
        janela._device.flash.assert_called_once_with(4)

    def test_tecla_nao_acende_em_outro_perfil(self):
        janela = self._janela(self.b.id)
        self._tecla(janela, 4)
        janela._device.flash.assert_not_called()

    def test_edicao_vai_para_o_perfil_em_que_comecou(self):
        # O perfil pode trocar pelo macropad com o editor de ação aberto.
        janela = self._janela(self.b.id)
        editor = mock.Mock(remove_requested=False)
        editor.result_action = Action(type="text", params={"text": "oi"})
        MainWindow._on_action_edited(janela, 4, editor, self.a.id)
        self.assertIsNotNone(self.a.action_for(4))
        self.assertIsNone(self.b.action_for(4))


if __name__ == "__main__":
    unittest.main()

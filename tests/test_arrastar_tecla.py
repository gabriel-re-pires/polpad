"""Arrastar a ação de uma tecla para outra do mesmo perfil."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from polpad.core.models import Action, Profile
from polpad.core.store import Store
from polpad.ui.key_grid import DeviceView
from polpad.ui.main_window import MainWindow

from .apoio import CofreFalso

APP = QApplication.instance() or QApplication([])


def _acao(texto: str) -> Action:
    return Action(type="text", params={"text": texto}, label=texto)


class MoverNoPerfilTest(unittest.TestCase):
    def test_tecla_vazia_recebe_e_origem_fica_vazia(self):
        perfil = Profile(name="P", bindings={3: _acao("a")})
        perfil.move_binding(3, 9)
        self.assertIsNone(perfil.action_for(3))
        self.assertEqual(perfil.action_for(9).label, "a")

    def test_tecla_ocupada_troca_de_lugar(self):
        perfil = Profile(name="P", bindings={3: _acao("a"), 9: _acao("b")})
        perfil.move_binding(3, 9)
        self.assertEqual(perfil.action_for(3).label, "b")
        self.assertEqual(perfil.action_for(9).label, "a")

    def test_origem_vazia_nao_mexe_em_nada(self):
        perfil = Profile(name="P", bindings={9: _acao("b")})
        perfil.move_binding(3, 9)
        self.assertIsNone(perfil.action_for(3))
        self.assertEqual(perfil.action_for(9).label, "b")

    def test_mesma_tecla_nao_mexe_em_nada(self):
        perfil = Profile(name="P", bindings={3: _acao("a")})
        perfil.move_binding(3, 3)
        self.assertEqual(perfil.action_for(3).label, "a")


class MoverNaJanelaTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        self.store.load()
        self.perfil = self.store.profiles[0]
        self.perfil.bindings = {3: _acao("a"), 9: _acao("b")}
        self.janela = mock.Mock()
        self.janela._core.store = self.store
        self.janela._editing_profile.return_value = self.perfil

    def test_move_salva_e_seleciona_o_destino(self):
        MainWindow._move_key(self.janela, 3, 10)
        self.assertEqual(self.perfil.action_for(10).label, "a")
        self.janela._save_bindings.assert_called_once()
        self.janela._choose_key.assert_called_once_with(10)

    def test_troca_avisa_na_barra(self):
        MainWindow._move_key(self.janela, 3, 9)
        texto = self.janela.statusBar().showMessage.call_args[0][0]
        self.assertIn("trocadas", texto)

    def test_tecla_de_modo_nao_entra_na_troca(self):
        self.store.settings.mode_key = 9
        MainWindow._move_key(self.janela, 3, 9)
        MainWindow._move_key(self.janela, 9, 3)
        self.assertEqual(self.perfil.action_for(3).label, "a")
        self.assertEqual(self.perfil.action_for(9).label, "b")
        self.janela._save_bindings.assert_not_called()


class GradeTest(unittest.TestCase):
    def setUp(self):
        self.view = DeviceView()
        self.addCleanup(self.view.deleteLater)
        self.perfil = Profile(name="P", bindings={3: _acao("a")})
        self.view.refresh(self.perfil, mode_key=0)
        self.movidas: list[tuple[int, int]] = []
        self.view.key_moved.connect(lambda o, d: self.movidas.append((o, d)))

    def test_soltar_emite_origem_e_destino(self):
        self.view._on_drag_started(3)
        self.view._on_drop(3, 9)
        self.assertEqual(self.movidas, [(3, 9)])

    def test_so_tecla_configurada_pode_ser_arrastada(self):
        caps = self.view._caps
        self.assertTrue(caps[3].can_drag())
        self.assertFalse(caps[4].can_drag())   # vazia
        self.assertFalse(caps[0].can_drag())   # tecla de modo

    def test_tecla_de_modo_e_a_propria_nao_recebem(self):
        caps = self.view._caps
        self.assertTrue(caps[9].accepts_drop_from(caps[3]))
        self.assertFalse(caps[0].accepts_drop_from(caps[3]))
        self.assertFalse(caps[3].accepts_drop_from(caps[3]))

    def test_perfil_trocado_no_meio_do_arrasto_cancela(self):
        # O macropad pode trocar o perfil da tela enquanto o mouse está segurando.
        self.view._on_drag_started(3)
        self.view.refresh(Profile(name="Outro"), mode_key=0)
        self.view._on_drop(3, 9)
        self.assertEqual(self.movidas, [])


if __name__ == "__main__":
    unittest.main()

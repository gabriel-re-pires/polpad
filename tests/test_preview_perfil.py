"""A imagem do display no centro acompanha o perfil clicado."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from polpad.core import display
from polpad.core.controller import Controller
from polpad.core.store import Store
from polpad.ui.main_window import MainWindow

from .apoio import CofreFalso

APP = QApplication.instance() or QApplication([])
AGORA = datetime(2026, 11, 6, 10, 30, 0)


class PreviewDoPerfilTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        self.store.load()
        self.a = self.store.profiles[0]
        self.a.name = "A"
        self.b = self.store.add_profile("B")
        self.b.display.mode = "personalizado"
        self.agendado = []
        self.controller = Controller(
            store=self.store,
            runner=mock.Mock(),
            send=lambda _msg: None,
            schedule=lambda _s, fn: self.agendado.append(fn),
            clock=lambda: AGORA,
        )

    def _janela(self, editando):
        janela = mock.Mock()
        janela._core.controller = self.controller
        janela._core.store = self.store
        janela._editing_profile_id = editando
        return janela

    def _mostrado(self, janela):
        return janela._device.oled.show_frame.call_args[0][0].tobytes()

    def test_perfil_clicado_aparece_no_centro(self):
        janela = self._janela(self.b.id)
        MainWindow._refresh_preview(janela)
        esperado = display.profile_frame(self.b, AGORA).tobytes()
        self.assertEqual(self._mostrado(janela), esperado)
        self.assertNotEqual(esperado, display.profile_frame(self.a, AGORA).tobytes())

    def test_perfil_ativo_continua_espelhando_o_aparelho(self):
        self.a.display.mode = "personalizado"
        self.a.display.icon_splash = True
        self.controller.activate_profile(self.a.id)  # mostra o ícone por 1,5 s
        janela = self._janela(self.a.id)
        MainWindow._refresh_preview(janela)
        self.assertEqual(self._mostrado(janela), display.icon_frame(self.a).tobytes())

    def test_clicar_no_perfil_atualiza_a_imagem(self):
        janela = self._janela(self.a.id)
        MainWindow._on_edit_profile(janela, self.b.id)
        janela._refresh_preview.assert_called_once_with()

    def test_relogio_atualiza_o_perfil_em_edicao(self):
        janela = self._janela(self.b.id)
        janela.isVisible.return_value = True
        MainWindow._on_clock(janela)
        janela._refresh_preview.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

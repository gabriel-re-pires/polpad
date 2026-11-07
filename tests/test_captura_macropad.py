"""'Capturar do macropad' só escolhe a tecla de modo: não executa a ação dela."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from polpad.core.controller import Controller
from polpad.core.models import Action
from polpad.core.store import Store
from polpad.ui import settings_dialog
from polpad.ui.main_window import MainWindow

from .apoio import CofreFalso
from .test_controller import FakeRunner

APP = QApplication.instance() or QApplication([])


class CapturaDaTeclaDeModoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        self.store.load()
        perfil = self.store.profiles[0]
        perfil.bindings[6] = Action(type="hotkey", params={"keys": ["ctrl", "k"]})
        self.runner = FakeRunner()
        self.controller = Controller(
            store=self.store, runner=self.runner, send=lambda _msg: None
        )
        self.pagina = settings_dialog.SettingsPage(
            self.store.settings, self.store.profiles
        )
        self.addCleanup(self.pagina.close)
        self.janela = mock.Mock()
        self.janela._core.controller = self.controller
        self.janela._settings_page = self.pagina
        self.janela._overlay = self.pagina
        self.janela._on_key_captured = lambda key: MainWindow._on_key_captured(
            self.janela, key
        )
        self.janela._cancel_capture = lambda: MainWindow._cancel_capture(self.janela)

    def _apertar(self, key):
        self.controller.handle_message({"t": "key", "k": key, "e": "down"})

    def test_pagina_avisa_quando_a_captura_comeca(self):
        avisos = []
        self.pagina.capture_started.connect(lambda: avisos.append(True))
        self.pagina._capture_button.click()
        self.assertTrue(self.pagina.capturing_mode_key)
        self.assertEqual(avisos, [True])

    def test_tecla_capturada_nao_executa_a_acao(self):
        self.pagina._start_capture()
        MainWindow._start_capture(self.janela)
        self._apertar(6)
        self.assertEqual(self.runner.submitted, [])
        self.assertFalse(self.pagina.capturing_mode_key)
        self.assertEqual(self.pagina._mode_combo.currentData(), 6)
        self.assertIsNone(self.controller.key_capture)

    def test_fechar_as_configuracoes_cancela_a_captura(self):
        self.pagina._start_capture()
        MainWindow._start_capture(self.janela)
        MainWindow._close_overlay(self.janela)
        self.assertIsNone(self.controller.key_capture)
        self._apertar(6)
        self.assertEqual(len(self.runner.submitted), 1)

    def test_esconder_a_janela_cancela_a_captura(self):
        self.pagina._start_capture()
        MainWindow._start_capture(self.janela)
        MainWindow._cancel_capture(self.janela)
        self.assertIsNone(self.controller.key_capture)
        self.assertFalse(self.pagina.capturing_mode_key)
        self.assertTrue(self.pagina._capture_button.isEnabled())


if __name__ == "__main__":
    unittest.main()

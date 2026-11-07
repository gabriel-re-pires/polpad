"""A janela repassa a versão da placa ao aviso de firmware novo."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from polpad.ui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])


class JanelaFirmwareTest(unittest.TestCase):
    def _janela(self):
        janela = mock.Mock()
        janela._device_version = None
        janela._connected_port = None
        return janela

    def test_hello_repassa_a_versao(self):
        janela = self._janela()
        MainWindow._on_device_message(janela, {"t": "hello", "fw": "2.0.2"})
        janela._updates.device_firmware.assert_called_once_with("2.0.2")

    def test_hello_repetido_nao_repassa_de_novo(self):
        janela = self._janela()
        MainWindow._on_device_message(janela, {"t": "hello", "fw": "2.0.2"})
        MainWindow._on_device_message(janela, {"t": "hello", "fw": "2.0.2"})
        janela._updates.device_firmware.assert_called_once_with("2.0.2")

    def test_versao_ja_conhecida_vai_ao_controlador(self):
        # A placa pode responder antes de o controlador de atualização existir.
        janela = self._janela()
        janela._device_version = "2.0.2"
        controlador = mock.Mock()
        MainWindow.set_update_controller(janela, controlador)
        controlador.device_firmware.assert_called_once_with("2.0.2")
        controlador.flash_requested.connect.assert_called_once()

    def test_gravar_do_aviso_abre_a_pagina(self):
        janela = self._janela()
        MainWindow._open_flash_from_notice(janela)
        janela.present.assert_called_once_with()
        janela._open_flash_page.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

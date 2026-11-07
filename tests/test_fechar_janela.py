"""Fechar a janela só esconde o Polpad, sem aviso na bandeja."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from polpad.ui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])


class FecharJanelaTest(unittest.TestCase):
    def test_fechar_esconde_sem_aviso_de_segundo_plano(self):
        janela = mock.Mock(_quitting=False)
        janela._tray.isVisible.return_value = True
        for _ in range(2):
            evento = QCloseEvent()
            MainWindow.closeEvent(janela, evento)
            self.assertFalse(evento.isAccepted())
        self.assertEqual(janela.hide.call_count, 2)
        janela._tray.showMessage.assert_not_called()


if __name__ == "__main__":
    unittest.main()

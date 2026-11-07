""""Versão e atualizações" e "Gravar firmware" abrem como páginas, igual às
Configurações: no lugar das colunas, com "Voltar"."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QWidget

from polpad.ui import flash_dialog, version_dialog
from polpad.ui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])


class PaginaDeVersaoTest(unittest.TestCase):
    def test_e_pagina_com_voltar(self):
        pagina = version_dialog.VersionPage()
        self.addCleanup(pagina.deleteLater)
        self.assertNotIsInstance(pagina, QDialog)
        fechou = []
        pagina.closed.connect(lambda: fechou.append(True))
        pagina.back_button.click()
        self.assertEqual(fechou, [True])


class PaginaDeFirmwareTest(unittest.TestCase):
    def setUp(self):
        self.core = mock.Mock()
        self.core.pause_link.return_value = True
        patches = (
            mock.patch.object(
                flash_dialog, "available_ports", return_value=[("COM5", "Macropad")]
            ),
            mock.patch.object(flash_dialog.FlashPage, "_check_release"),
            mock.patch.object(flash_dialog.QMessageBox, "warning"),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.pagina = flash_dialog.FlashPage(self.core, current_port="COM5")
        self.addCleanup(self.pagina.deleteLater)

    def _gravando(self):
        self.pagina._link_paused = True
        self.pagina._job = mock.Mock()
        self.pagina._job.isRunning.return_value = True

    def test_e_pagina_com_voltar(self):
        self.assertNotIsInstance(self.pagina, QDialog)
        fechou = []
        self.pagina.closed.connect(lambda: fechou.append(True))
        self.pagina.back_button.click()
        self.assertEqual(fechou, [True])

    def test_nao_sai_no_meio_da_gravacao(self):
        self._gravando()
        self.assertFalse(self.pagina.leave())
        flash_dialog.QMessageBox.warning.assert_called_once()
        self.core.resume_link.assert_not_called()

    def test_sair_parado_devolve_a_porta(self):
        self.pagina._link_paused = True
        self.assertTrue(self.pagina.leave())
        self.core.resume_link.assert_called_once_with()

    def test_avisa_quando_a_gravacao_comeca_e_termina(self):
        avisos = []
        self.pagina.running_changed.connect(avisos.append)
        self._gravando()
        self.pagina._set_running(True)
        self.pagina._job = None
        self.pagina._on_finished()
        self.assertEqual(avisos, [True, False])


class TrocaDePaginaTest(unittest.TestCase):
    """A janela não abandona uma página que não pode ser deixada agora."""

    def _janela(self, atual):
        janela = mock.Mock()
        janela._overlay = atual
        janela._settings_page = None
        janela._can_leave = lambda pagina: MainWindow._can_leave(janela, pagina)
        janela._close_overlay = lambda: MainWindow._close_overlay(janela)
        return janela

    def test_nao_troca_durante_a_gravacao(self):
        atual = mock.Mock()
        atual.leave.return_value = False
        janela = self._janela(atual)
        nova = QWidget()
        self.addCleanup(nova.deleteLater)
        self.assertFalse(MainWindow._show_overlay(janela, nova))
        self.assertIs(janela._overlay, atual)
        janela._pages.addWidget.assert_not_called()

    def test_voltar_durante_a_gravacao_fica_na_pagina(self):
        atual = mock.Mock()
        atual.leave.return_value = False
        janela = self._janela(atual)
        self.assertFalse(MainWindow._close_overlay(janela))
        self.assertIs(janela._overlay, atual)
        janela._pages.removeWidget.assert_not_called()

    def test_reabrir_a_mesma_pagina_nao_apaga(self):
        atual = QWidget()
        self.addCleanup(atual.deleteLater)
        janela = self._janela(atual)
        self.assertTrue(MainWindow._show_overlay(janela, atual))
        janela._pages.removeWidget.assert_not_called()
        janela._pages.setCurrentWidget.assert_called_with(atual)


if __name__ == "__main__":
    unittest.main()

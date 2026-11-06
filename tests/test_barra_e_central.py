"""Versão no centro da barra inferior e aviso na central de notificações."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar

from polpad.ui import notification_center
from polpad.ui.status_version import StatusVersion

APP = QApplication.instance() or QApplication([])


class VersaoNaBarraTest(unittest.TestCase):
    def setUp(self):
        self.janela = QMainWindow()
        self.addCleanup(self.janela.close)
        self.barra = QStatusBar()
        self.janela.setStatusBar(self.barra)
        self.rotulo = StatusVersion("Polpad 0.6.1", self.barra)
        self.janela.resize(1000, 600)
        self.janela.show()
        APP.processEvents()

    def test_texto_e_centro(self):
        self.assertEqual(self.rotulo.text(), "Polpad 0.6.1")
        self.assertLessEqual(
            abs(self.rotulo.geometry().center().x() - self.barra.width() // 2), 1
        )

    def test_continua_no_centro_ao_redimensionar(self):
        self.janela.resize(700, 600)
        APP.processEvents()
        self.assertLessEqual(
            abs(self.rotulo.geometry().center().x() - self.barra.width() // 2), 1
        )

    def test_mensagem_curta_nao_esconde(self):
        self.barra.showMessage("Perfil ativo: A")
        self.assertTrue(self.rotulo.isVisible())

    def test_mensagem_longa_esconde_e_volta(self):
        self.barra.showMessage("x" * 300)
        self.assertFalse(self.rotulo.isVisible())
        self.barra.clearMessage()
        self.assertTrue(self.rotulo.isVisible())


class CentralTest(unittest.TestCase):
    def test_xml_escapa_o_texto(self):
        xml = notification_center.toast_xml("A <b> & C", 'diz "oi"')
        self.assertIn("A &lt;b&gt; &amp; C", xml)
        self.assertIn("diz &quot;oi&quot;", xml)
        self.assertTrue(xml.startswith("<toast"))

    def test_sem_texto_secundario(self):
        xml = notification_center.toast_xml("Título", "")
        self.assertEqual(xml.count("<text>"), 1)

    def test_fora_do_windows_nao_faz_nada(self):
        with mock.patch.object(notification_center.sys, "platform", "linux"):
            self.assertFalse(notification_center.post("t", "x"))
            self.assertFalse(notification_center.clear())


if __name__ == "__main__":
    unittest.main()

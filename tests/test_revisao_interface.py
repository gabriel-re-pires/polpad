"""Regressões da revisão geral na interface (26/11/2026)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from polpad.ui.hotkey_capture import _CaptureField
from polpad.ui.port_combo import PortCombo

_app = QApplication.instance() or QApplication([])


class AtalhoDaJanelaNaGravacaoTest(unittest.TestCase):
    """Gravando um atalho, F5 recarregava as portas e Ctrl+, abria as
    Configurações (descartando o editor): o campo não pedia a tecla."""

    def _override(self, tecla):
        sem_mod = Qt.KeyboardModifier.NoModifier
        return QKeyEvent(QEvent.Type.ShortcutOverride, tecla, sem_mod)

    def test_gravando_o_campo_fica_com_a_tecla(self):
        campo = _CaptureField()
        campo.start()
        evento = self._override(Qt.Key.Key_F5)
        evento.ignore()
        self.assertTrue(campo.event(evento))
        self.assertTrue(evento.isAccepted())

    def test_fora_da_gravacao_o_atalho_da_janela_vale(self):
        campo = _CaptureField()
        evento = self._override(Qt.Key.Key_F5)
        evento.ignore()
        campo.event(evento)
        self.assertFalse(evento.isAccepted())


class PortaQueSumiuTest(unittest.TestCase):
    """Se a porta escolhida sumia (reinício após gravar), a lista mostrava
    "Busca automática" enquanto o enlace seguia tentando a porta antiga."""

    def test_porta_escolhida_continua_na_lista(self):
        combo = PortCombo("Busca automática")
        combo.set_ports([("COM7", "USB")], "COM5")
        self.assertEqual(combo.currentData(), "COM5")
        self.assertIn("não encontrada", combo.currentText())

    def test_porta_presente_nao_e_duplicada(self):
        combo = PortCombo("Busca automática")
        combo.set_ports([("COM5", "USB")], "COM5")
        self.assertEqual(combo.count(), 2)

    def test_busca_automatica(self):
        combo = PortCombo("Busca automática")
        combo.set_ports([("COM5", "USB")], None)
        self.assertIsNone(combo.currentData())


if __name__ == "__main__":
    unittest.main()

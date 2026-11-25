"""Gravar um atalho soma ao que já está no campo; só o Limpar apaga.

Com a tecla Win quebrada, o usuário monta Win + V pelo teclado virtual. O
Windows engole o Win + V (abre o histórico da área de transferência) e tira
o foco do campo antes de o Win ser solto: a gravação se perdia, e a seguinte
apagava a anterior.
"""

import unittest

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtWidgets import QApplication

from polpad.ui.hotkey_capture import HotkeyCapture, _CaptureField, merge_keys

_app = QApplication.instance() or QApplication([])

# Códigos virtuais do Windows; o Linux cai no Qt.Key, que dá o mesmo nome.
_VK = {Qt.Key.Key_V: 0x56, Qt.Key.Key_C: 0x43, Qt.Key.Key_S: 0x53}


def _apertar(campo, tecla, mods=Qt.KeyboardModifier.NoModifier):
    evento = QKeyEvent(
        QEvent.Type.KeyPress, tecla, mods, 0, _VK.get(tecla, 0), 0, ""
    )
    campo.event(evento)


def _soltar(campo, tecla, mods=Qt.KeyboardModifier.NoModifier):
    campo.event(QKeyEvent(QEvent.Type.KeyRelease, tecla, mods))


def _perder_foco(campo):
    campo.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))


class SomaTest(unittest.TestCase):
    def test_nova_gravacao_mantem_a_anterior(self):
        campo = _CaptureField()
        campo.start()
        _apertar(campo, Qt.Key.Key_Meta, Qt.KeyboardModifier.MetaModifier)
        _soltar(campo, Qt.Key.Key_Meta)
        self.assertEqual(campo.keys(), ["win"])
        _perder_foco(campo)
        campo.start()
        _apertar(campo, Qt.Key.Key_V)
        self.assertEqual(campo.keys(), ["win", "v"])

    def test_win_v_que_tira_o_foco_grava_o_win(self):
        campo = _CaptureField()
        campo.start()
        _apertar(campo, Qt.Key.Key_Meta, Qt.KeyboardModifier.MetaModifier)
        # O V nem chega: o Windows abre o painel e o campo perde o foco.
        _perder_foco(campo)
        self.assertFalse(campo._listening)
        self.assertEqual(campo.keys(), ["win"])

    def test_perder_foco_sem_tecla_nao_muda_nada(self):
        campo = _CaptureField()
        campo.set_keys(["ctrl", "s"])
        campo.start()
        _perder_foco(campo)
        self.assertEqual(campo.keys(), ["ctrl", "s"])

    def test_esc_cancela_sem_apagar(self):
        campo = _CaptureField()
        campo.set_keys(["ctrl", "s"])
        campo.start()
        _apertar(campo, Qt.Key.Key_Escape)
        self.assertFalse(campo._listening)
        self.assertEqual(campo.keys(), ["ctrl", "s"])

    def test_modificador_novo_vai_para_a_frente(self):
        campo = _CaptureField()
        campo.set_keys(["c"])
        campo.start()
        _apertar(campo, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(campo.keys(), ["ctrl", "c"])

    def test_merge_sem_repetir_e_com_apelidos(self):
        self.assertEqual(merge_keys(["control", "c"], ["ctrl", "c"]), ["ctrl", "c"])
        self.assertEqual(merge_keys(["v"], ["windows"]), ["win", "v"])
        self.assertEqual(
            merge_keys(["shift", "p"], ["ctrl"]), ["ctrl", "shift", "p"]
        )

    def test_desenha_durante_a_gravacao(self):
        campo = _CaptureField()
        campo.set_keys(["win"])
        campo.resize(280, 46)
        campo.start()
        self.assertFalse(campo.grab().isNull())


class LimparTest(unittest.TestCase):
    def test_menu_soma_e_limpar_apaga(self):
        captura = HotkeyCapture()
        emitidos = []
        captura.changed.connect(emitidos.append)
        self.assertFalse(captura.clear_button.isEnabled())

        captura._pick("win")
        self.assertTrue(captura.clear_button.isEnabled())
        captura.field.start()
        _apertar(captura.field, Qt.Key.Key_V)
        self.assertEqual(captura.keys(), ["win", "v"])

        captura.clear_button.click()
        self.assertEqual(captura.keys(), [])
        self.assertFalse(captura.clear_button.isEnabled())
        self.assertEqual(emitidos, [["win"], ["win", "v"], []])

    def test_carregar_atalho_habilita_limpar(self):
        captura = HotkeyCapture()
        captura.set_keys(["ctrl", "c"])
        self.assertTrue(captura.clear_button.isEnabled())


if __name__ == "__main__":
    unittest.main()

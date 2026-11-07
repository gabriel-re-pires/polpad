"""Captura de atalho com as teclas próprias do ABNT2 (Ç e acentos).

O Ç e as teclas mortas não são letra nem número: a captura não as
reconhecia e ignorava a tecla sem avisar.
"""

import sys
import unittest
from unittest import mock

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from polpad.actions import builtin, keys
from polpad.ui.hotkey_capture import _CaptureField

_app = QApplication.instance() or QApplication([])

CTRL = Qt.KeyboardModifier.ControlModifier.value
CCEDILHA = Qt.Key.Key_Ccedilla.value
AGUDO = Qt.Key.Key_Dead_Acute.value
TIL = Qt.Key.Key_Dead_Tilde.value


class NomesAbnt2Test(unittest.TestCase):
    def test_ctrl_c_cedilha_no_windows(self):
        self.assertEqual(
            keys.names_from_event(CCEDILHA, CTRL, 0xBA, xkb=False), ["ctrl", "ç"]
        )

    def test_ctrl_c_cedilha_no_linux(self):
        # keysym "ccedilla" (0xE7); código X 47 = tecla do Ç no ABNT2.
        self.assertEqual(
            keys.names_from_event(CCEDILHA, CTRL, 0xE7, 47, xkb=True), ["ctrl", "ç"]
        )

    def test_teclas_mortas_no_windows(self):
        self.assertEqual(keys.names_from_event(AGUDO, 0, 0xDB, xkb=False), ["´"])
        self.assertEqual(keys.names_from_event(TIL, 0, 0xDE, xkb=False), ["~"])

    def test_teclas_mortas_no_linux(self):
        self.assertEqual(keys.names_from_event(AGUDO, 0, 0xFE51, 34, xkb=True), ["´"])
        self.assertEqual(keys.names_from_event(TIL, 0, 0xFE53, 48, xkb=True), ["~"])

    def test_nomes_sao_aceitos_pelo_executor(self):
        for nome in ("ç", "´", "~"):
            self.assertTrue(keys.is_valid(nome), nome)
        self.assertEqual(keys.pretty(["ctrl", "ç"]), "Ctrl + Ç")


@unittest.skipUnless(sys.platform == "win32", "SendInput só existe no Windows")
class AtalhoCapturadoExecutaTest(unittest.TestCase):
    def test_ctrl_c_cedilha_capturado_vai_como_tecla(self):
        import pynput.keyboard._win32 as w

        from tests.test_atalhos import _Gravador

        nomes = keys.names_from_event(CCEDILHA, CTRL, 0xBA, xkb=False)
        gravador = _Gravador()
        # VkKeyScanW("ç") no ABNT2: tecla 0xBA, sem modificador.
        with (
            mock.patch.object(w, "SendInput", gravador),
            mock.patch.object(keys, "_vk_key_scan", return_value=0x00BA),
        ):
            builtin.run_hotkey({"keys": nomes}, None)
        self.assertFalse([e for e in gravador.eventos if e["unicode"]])
        self.assertIn(0xBA, [e["vk"] for e in gravador.eventos])


class AvisoNaCapturaTest(unittest.TestCase):
    def _apertar(self, campo, tecla, mods=Qt.KeyboardModifier.NoModifier):
        evento = QKeyEvent(QEvent.Type.KeyPress, tecla, mods)
        campo.event(evento)

    def test_tecla_desconhecida_avisa_e_continua_gravando(self):
        campo = _CaptureField()
        campo.set_keys(["ctrl", "k"])
        campo.start()
        self._apertar(campo, Qt.Key.Key_Dead_Ogonek)
        self.assertTrue(campo.warning())
        self.assertTrue(campo._listening)
        self.assertEqual(campo.keys(), ["ctrl", "k"])
        self.assertFalse(campo.grab().isNull())  # desenha o aviso sem erro

    def test_aviso_some_ao_gravar_uma_tecla_valida(self):
        campo = _CaptureField()
        campo.start()
        self._apertar(campo, Qt.Key.Key_Dead_Ogonek)
        self._apertar(campo, Qt.Key.Key_F5)
        self.assertEqual(campo.keys(), ["f5"])
        self.assertEqual(campo.warning(), "")

    def test_c_cedilha_e_gravado(self):
        campo = _CaptureField()
        campo.start()
        self._apertar(campo, Qt.Key.Key_Ccedilla, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(campo.keys(), ["ctrl", "ç"])
        self.assertEqual(campo.warning(), "")


if __name__ == "__main__":
    unittest.main()

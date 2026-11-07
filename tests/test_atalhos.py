"""Testes do envio de atalhos de teclado (ação "hotkey").

Nenhuma tecla de verdade é enviada: o ``SendInput`` do pynput é trocado
por um gravador que só anota os eventos.
"""

import sys
import unittest
from unittest import mock

from pynput.keyboard import KeyCode

from polpad.actions import builtin, keys

WINDOWS = sys.platform == "win32"


class _Gravador:
    """Faz o papel do ``SendInput`` do Windows e anota cada evento."""

    def __init__(self):
        self.eventos = []

    def __call__(self, n, ptr, size):
        import ctypes

        from pynput._util.win32 import INPUT, KEYBDINPUT

        arr = ctypes.cast(ptr, ctypes.POINTER(INPUT))
        for i in range(n):
            ki = arr[i].value.ki
            self.eventos.append(
                {
                    "vk": ki.wVk,
                    "unicode": bool(ki.dwFlags & KEYBDINPUT.UNICODE),
                    "solta": bool(ki.dwFlags & KEYBDINPUT.KEYUP),
                }
            )
        return n


@unittest.skipUnless(WINDOWS, "SendInput só existe no Windows")
class AtalhoComShiftTest(unittest.TestCase):
    """Com Shift pressionado, o pynput trocava "p" por "P" e o mandava como
    caractere Unicode, sem código de tecla: o programa em foco não via
    Ctrl+Shift+P."""

    def _executar(self, nomes):
        import pynput.keyboard._win32 as w

        gravador = _Gravador()
        with mock.patch.object(w, "SendInput", gravador):
            builtin.run_hotkey({"keys": nomes}, None)
        return gravador.eventos

    def test_ctrl_shift_p_vai_como_tecla(self):
        eventos = self._executar(["ctrl", "shift", "p"])
        self.assertFalse([e for e in eventos if e["unicode"]])
        self.assertIn(0x50, [e["vk"] for e in eventos if not e["solta"]])

    def test_win_shift_s_vai_como_tecla(self):
        eventos = self._executar(["win", "shift", "s"])
        self.assertFalse([e for e in eventos if e["unicode"]])
        self.assertIn(0x53, [e["vk"] for e in eventos if not e["solta"]])

    def test_ctrl_shift_numero_vai_como_tecla(self):
        eventos = self._executar(["ctrl", "shift", "1"])
        self.assertFalse([e for e in eventos if e["unicode"]])
        self.assertIn(0x31, [e["vk"] for e in eventos if not e["solta"]])

    def test_ctrl_shift_c_cedilha_usa_a_tecla_do_layout(self):
        # 0xBA é a tecla do Ç no ABNT2 (VkKeyScanW("ç") sem modificador).
        with mock.patch.object(keys, "_vk_key_scan", return_value=0x00BA):
            eventos = self._executar(["ctrl", "shift", "ç"])
        self.assertFalse([e for e in eventos if e["unicode"]])
        self.assertIn(0xBA, [e["vk"] for e in eventos if not e["solta"]])

    def test_digitar_texto_continua_unicode(self):
        import pynput.keyboard._win32 as w

        gravador = _Gravador()
        with mock.patch.object(w, "SendInput", gravador):
            builtin.run_text({"text": "Ç"}, None)
        self.assertTrue(gravador.eventos)
        self.assertTrue(all(e["unicode"] for e in gravador.eventos))


class ResolveTest(unittest.TestCase):
    """No Windows, letras, números e símbolos viram código virtual; o
    pynput só os manda como Unicode se receber o caractere."""

    def test_windows_letras_e_numeros_viram_vk(self):
        with mock.patch.object(keys.sys, "platform", "win32"):
            self.assertEqual(keys.resolve("p"), KeyCode.from_vk(0x50))
            self.assertEqual(keys.resolve("P"), KeyCode.from_vk(0x50))
            self.assertEqual(keys.resolve("7"), KeyCode.from_vk(0x37))

    def test_windows_simbolo_usa_vkkeyscan(self):
        with (
            mock.patch.object(keys.sys, "platform", "win32"),
            mock.patch.object(keys, "_vk_key_scan", return_value=0x00BA),
        ):
            self.assertEqual(keys.resolve("ç"), KeyCode.from_vk(0xBA))

    def test_windows_sem_vk_mantem_o_caractere(self):
        # -1: o layout não tem a tecla; 0x0131: só sai com Shift ("!").
        for retorno in (-1, 0xFFFF, 0x0131):
            with (
                mock.patch.object(keys.sys, "platform", "win32"),
                mock.patch.object(keys, "_vk_key_scan", return_value=retorno),
            ):
                self.assertEqual(keys.resolve("!"), KeyCode.from_char("!"), retorno)

    def test_linux_mantem_o_caractere(self):
        with mock.patch.object(keys.sys, "platform", "linux"):
            self.assertEqual(keys.resolve("p"), KeyCode.from_char("p"))
            self.assertEqual(keys.resolve("ç"), KeyCode.from_char("ç"))


if __name__ == "__main__":
    unittest.main()

"""A janela cabe num notebook 1366×768 com escala de 125%.

A área útil lógica fica em 1093×576 (a barra de tarefas toma 48 px): o
mínimo de 1040×620 da janela não cabia, e o rodapé ia para baixo da barra.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from polpad.ui import main_window
from polpad.ui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])
MOLDURA = 40  # barra de título, fora do resize()


def _janela(area: QRect) -> mock.Mock:
    janela = mock.Mock()
    janela.screen.return_value.availableGeometry.return_value = area
    janela.width.return_value, janela.height.return_value = 1280, 760
    janela.minimumWidth.return_value, janela.minimumHeight.return_value = 1040, 620
    return janela


class TelaPequenaTest(unittest.TestCase):
    def test_cabe_em_1366x768_com_125_por_cento(self):
        janela = _janela(QRect(0, 0, 1093, 576))
        MainWindow._fit_to_screen(janela)
        largura, altura = janela.resize.call_args.args
        self.assertLessEqual(altura + MOLDURA, 576)
        self.assertLessEqual(largura, 1093)
        # O mínimo desce junto, senão o Qt devolveria a janela aos 620 px.
        _min_l, min_a = janela.setMinimumSize.call_args.args
        self.assertLessEqual(min_a, altura)

    def test_tela_grande_mantem_o_minimo(self):
        janela = _janela(QRect(0, 0, 1920, 1040))
        MainWindow._fit_to_screen(janela)
        self.assertEqual(janela.resize.call_args.args, (1280, 760))
        janela.setMinimumSize.assert_not_called()

    def test_geometria_salva_tambem_cabe_na_tela(self):
        # Na segunda abertura a geometria salva é restaurada; o mínimo
        # fixo de 620 px faria a janela voltar a passar da área útil.
        janela = _janela(QRect(0, 0, 1093, 576))
        janela.isMaximized.return_value = False
        salvos = {"janela/geometria": b"geometria", "janela/colunas": None}
        with mock.patch.object(main_window, "QSettings") as qsettings:
            qsettings.return_value.value.side_effect = lambda k, d=None: salvos.get(k, d)
            MainWindow._restore_layout(janela)
        janela.restoreGeometry.assert_called_once_with(b"geometria")
        janela._fit_to_screen.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

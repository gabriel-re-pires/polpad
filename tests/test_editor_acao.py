"""Botão "Testar" do editor de ações."""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

import polpad.actions.builtin  # noqa: F401  (registra os tipos de ação)
from polpad.core.models import Action
from polpad.ui.action_editor import ActionEditorDialog
from polpad.ui.action_page import ActionEditorPage

APP = QApplication.instance() or QApplication([])


class RunnerFalso:
    def __init__(self) -> None:
        self.enviadas: list[Action] = []

    def submit(self, action: Action) -> None:
        self.enviadas.append(action)


def _esperar(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class TestarAcaoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.erros: list[str] = []
        anterior = sys.excepthook
        sys.excepthook = lambda t, v, tb: self.erros.append(f"{t.__name__}: {v}")
        self.addCleanup(setattr, sys, "excepthook", anterior)
        self.runner = RunnerFalso()

    def _pagina(self) -> ActionEditorPage:
        acao = Action(type="text", params={"text": "oi"}, label="Oi")
        return ActionEditorPage(3, acao, "Perfil", self.runner)

    def test_sair_antes_do_disparo_cancela_o_teste(self):
        pagina = self._pagina()
        pagina.editor._test()
        pagina.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        _esperar(ActionEditorDialog._TEST_DELAY_MS + 300)
        self.assertEqual(self.runner.enviadas, [])
        self.assertEqual(self.erros, [])

    def test_disparo_envia_a_acao(self):
        pagina = self._pagina()
        self.addCleanup(pagina.deleteLater)
        editor = pagina.editor
        editor._TEST_DELAY_MS = 20
        editor._test()
        _esperar(200)
        self.assertEqual(len(self.runner.enviadas), 1)
        self.assertEqual(self.runner.enviadas[0].params["text"], "oi")
        self.assertTrue(editor._test_button.isEnabled())
        self.assertEqual(self.erros, [])


if __name__ == "__main__":
    unittest.main()

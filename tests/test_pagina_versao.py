"""Testes da página de versão e atualizações."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from polpad.ui import version_dialog
from polpad.update.backup import Backup
from polpad.update.releases import AppRelease

APP = QApplication.instance() or QApplication([])


def _rel(versao: str, instalavel: bool = True, notas: str = "") -> AppRelease:
    return AppRelease(
        version=versao,
        tag=f"v{versao}",
        name=f"Polpad {versao}",
        notes=notas,
        published_at="2026-11-06T12:00:00Z",
        html_url=f"https://github.com/gabriel-re-pires/polpad/releases/tag/v{versao}",
        asset_name="Polpad-Setup.exe",
        asset_url="https://x/a" if instalavel else None,
        asset_size=1,
        sums_url="https://x/s" if instalavel else None,
    )


def _view(**mudancas) -> version_dialog.VersionView:
    base = {
        "current": "0.5.1",
        "kind": "windows",
        "last_check": datetime(2026, 11, 6, 14, 2),
        "update": None,
        "releases": [_rel("0.5.1"), _rel("0.5.0"), _rel("0.4.1", instalavel=False)],
        "backups": [Backup(Path("b"), datetime(2026, 11, 6, 9, 0), "0.5.0", "0.5.1")],
        "notify": True,
        "auto": False,
    }
    base.update(mudancas)
    return version_dialog.VersionView(**base)


class PaginaTest(unittest.TestCase):
    def setUp(self):
        self.pagina = version_dialog.VersionPage()
        self.addCleanup(self.pagina.close)
        self.eventos: list[tuple] = []
        for nome in ("update_requested", "install_requested", "restore_requested"):
            getattr(self.pagina, nome).connect(
                lambda valor, n=nome: self.eventos.append((n, valor))
            )
        for nome in ("notify_changed", "auto_changed"):
            getattr(self.pagina, nome).connect(
                lambda valor, n=nome: self.eventos.append((n, valor))
            )
        self.pagina.check_requested.connect(lambda: self.eventos.append(("check",)))

    def test_atualizado(self):
        self.pagina.set_view(_view())
        self.assertEqual(
            self.pagina.status_label.text(), "Você está na versão mais recente"
        )
        self.assertTrue(self.pagina.update_button.isHidden())
        self.assertIn("Polpad 0.5.1", self.pagina.version_label.text())

    def test_versao_nova(self):
        self.pagina.set_view(_view(current="0.5.0", update=_rel("0.5.1", notas="Novo X")))
        self.assertEqual(self.pagina.status_label.text(), "Nova versão 0.5.1 disponível")
        self.assertFalse(self.pagina.update_button.isHidden())
        self.assertIn("Novo X", self.pagina.notes.toPlainText())
        self.pagina.update_button.click()
        self.assertEqual(self.eventos[-1][0], "update_requested")
        self.assertEqual(self.eventos[-1][1].version, "0.5.1")

    def test_desenvolvimento_sem_acoes(self):
        self.pagina.set_view(_view(kind="desenvolvimento", update=_rel("0.5.2")))
        self.assertEqual(
            self.pagina.kind_label.text(),
            "Instalação de desenvolvimento: atualize com git pull",
        )
        self.assertFalse(self.pagina.update_button.isEnabled())
        self.assertFalse(self.pagina.check_button.isEnabled())
        self.assertFalse(
            any(b.isEnabled() for b in self.pagina.release_buttons().values())
        )

    def test_anterior_ao_instalador(self):
        self.pagina.set_view(_view())
        self.assertNotIn("0.4.1", self.pagina.release_buttons())
        self.assertIn("anterior ao instalador", self.pagina.release_texts()["0.4.1"])

    def test_versao_atual_sem_botao(self):
        self.pagina.set_view(_view())
        self.assertNotIn("0.5.1", self.pagina.release_buttons())

    def test_voltar_desliga_automatico(self):
        self.pagina.set_view(_view(auto=True))
        perguntas: list[str] = []
        self.pagina._confirm = lambda texto: perguntas.append(texto) or True
        self.pagina.release_buttons()["0.5.0"].click()
        self.assertIn("Voltar para a 0.5.0?", perguntas[0])
        self.assertIn("atualização automática será desligada", perguntas[0])
        self.assertEqual(
            [e[0] for e in self.eventos], ["auto_changed", "install_requested"]
        )
        self.assertIs(self.eventos[0][1], False)
        self.assertEqual(self.eventos[1][1].version, "0.5.0")

    def test_voltar_cancelado_nao_faz_nada(self):
        self.pagina.set_view(_view(auto=True))
        self.pagina._confirm = lambda texto: False
        self.pagina.release_buttons()["0.5.0"].click()
        self.assertEqual(self.eventos, [])

    def test_opcoes_emitem_so_quando_o_usuario_muda(self):
        self.pagina.set_view(_view(notify=True, auto=False))
        self.pagina.set_view(_view(notify=False, auto=True))
        self.assertEqual(self.eventos, [])
        self.pagina.notify_box.click()
        self.assertEqual(self.eventos, [("notify_changed", True)])

    def test_restaurar_backup(self):
        self.pagina.set_view(_view())
        self.pagina._confirm = lambda texto: True
        self.pagina.backup_buttons()[0].click()
        self.assertEqual(self.eventos[-1][0], "restore_requested")
        self.assertEqual(self.eventos[-1][1].label, "0.5.0 → 0.5.1")

    def test_erro_aparece(self):
        self.pagina.set_view(_view(error="Sem internet"))
        self.assertEqual(self.pagina.error_label.text(), "Sem internet")
        self.assertFalse(self.pagina.error_label.isHidden())

    def test_botoes_linux_so_no_linux(self):
        with mock.patch.object(sys, "platform", "win32"):
            pagina = version_dialog.VersionPage()
        self.addCleanup(pagina.close)
        self.assertIsNone(pagina.linux_install_button)
        with mock.patch.object(sys, "platform", "linux"):
            pagina_linux = version_dialog.VersionPage()
        self.addCleanup(pagina_linux.close)
        self.assertIsNotNone(pagina_linux.linux_install_button)


if __name__ == "__main__":
    unittest.main()

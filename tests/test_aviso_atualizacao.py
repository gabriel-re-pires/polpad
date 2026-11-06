"""Testes do aviso de atualização no canto da tela e das configurações novas."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QApplication

from polpad.core.models import Settings
from polpad.ui import update_toast

APP = QApplication.instance() or QApplication([])


class PosicaoTest(unittest.TestCase):
    def test_posicao_no_canto_da_area_util(self):
        self.assertEqual(
            update_toast.toast_position(QRect(0, 0, 1920, 1040), QSize(360, 120)),
            QPoint(1544, 904),
        )

    def test_tela_secundaria_com_deslocamento(self):
        self.assertEqual(
            update_toast.toast_position(QRect(1920, 0, 1280, 984), QSize(360, 120)),
            QPoint(1920 + 1280 - 16 - 360, 984 - 16 - 120),
        )


class AvisoTest(unittest.TestCase):
    def setUp(self):
        self.aviso = update_toast.UpdateToast()
        self.addCleanup(self.aviso.close)
        self.sinais: list[str] = []
        for nome in (
            "update_clicked",
            "install_now_clicked",
            "details_clicked",
            "retry_clicked",
            "dismissed",
        ):
            getattr(self.aviso, nome).connect(lambda n=nome: self.sinais.append(n))

    def test_x_emite_dismissed_e_esconde(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        self.assertTrue(self.aviso.isVisible())
        self.aviso.close_button.click()
        self.assertEqual(self.sinais, ["dismissed"])
        self.assertFalse(self.aviso.isVisible())

    def test_textos_da_versao_nova(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        self.assertEqual(self.aviso.title.text(), "Nova versão do Polpad: 0.5.1")
        self.assertEqual(self.aviso.detail.text(), "Você está na 0.5.0")

    def test_atualizar_emite_sinal(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        self.aviso.action_button.click()
        self.assertEqual(self.sinais, ["update_clicked"])

    def test_pendente_mostra_instalar_agora(self):
        self.aviso.show_pending("0.5.1")
        self.assertEqual(self.aviso.action_button.text(), "Instalar agora")
        self.assertEqual(
            self.aviso.title.text(), "O Polpad 0.5.1 será instalado quando você sair"
        )
        self.aviso.action_button.click()
        self.assertEqual(self.sinais, ["install_now_clicked"])

    def test_falha_oferece_tentar_de_novo(self):
        self.aviso.show_failed("0.5.1", Path("instalacao.log"))
        self.assertEqual(
            self.aviso.title.text(), "A atualização para 0.5.1 não foi concluída"
        )
        self.assertEqual(self.aviso.action_button.text(), "Tentar de novo")
        self.aviso.action_button.click()
        self.assertEqual(self.sinais, ["retry_clicked"])

    def test_atualizado_sem_botao_de_acao(self):
        self.aviso.show_updated("0.5.1")
        self.assertEqual(self.aviso.title.text(), "Polpad atualizado para 0.5.1")
        self.assertTrue(self.aviso.action_button.isHidden())

    def test_progresso_esconde_os_botoes(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        self.aviso.show_progress("Baixando… 45%")
        self.assertEqual(self.aviso.detail.text(), "Baixando… 45%")
        self.assertTrue(self.aviso.action_button.isHidden())

    def test_ver_novidades(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        self.aviso.details_link.linkActivated.emit("novidades")
        self.assertEqual(self.sinais, ["details_clicked"])


class ConfiguracoesTest(unittest.TestCase):
    def test_settings_novos_campos(self):
        padrao = Settings.from_dict({})
        self.assertTrue(padrao.update_notify)
        self.assertFalse(padrao.update_auto)
        self.assertTrue(padrao.linux_install_prompt)
        trocado = Settings(
            update_notify=False, update_auto=True, linux_install_prompt=False
        )
        volta = Settings.from_dict(trocado.to_dict())
        self.assertFalse(volta.update_notify)
        self.assertTrue(volta.update_auto)
        self.assertFalse(volta.linux_install_prompt)


if __name__ == "__main__":
    unittest.main()

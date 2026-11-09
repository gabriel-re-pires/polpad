"""Testes do aviso de atualização no canto da tela e das configurações novas."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shiboken6
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from polpad.core.models import Settings
from polpad.ui import style, update_toast

APP = QApplication.instance() or QApplication([])


def _apagar(aviso: update_toast.UpdateToast) -> None:
    """Fecha e destrói o aviso já: uma janela sem dono destruída depois do
    ``QApplication`` derruba o processo ao sair."""
    aviso.close()
    shiboken6.delete(aviso)


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
        self.addCleanup(_apagar, self.aviso)
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


class VisualTest(unittest.TestCase):
    def setUp(self):
        self.aviso = update_toast.UpdateToast()
        self.addCleanup(_apagar, self.aviso)

    def test_sem_fundo_atras_do_cartao(self):
        self.assertTrue(self.aviso.testAttribute(Qt.WA_TranslucentBackground))

    def test_x_vermelho_sem_bloco(self):
        self.assertEqual(self.aviso.close_button.objectName(), "toastClose")
        qss = style.build_stylesheet()
        regra = qss.split("QToolButton#toastClose {", 1)[1].split("}", 1)[0]
        self.assertIn(f"color: {style.DANGER}", regra)
        self.assertIn("border: none", regra)
        self.assertIn("background: transparent", regra)

    def test_atualizar_na_linha_do_ver_novidades_a_direita(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        link = self.aviso.details_link.geometry()
        botao = self.aviso.action_button.geometry()
        self.assertIs(self.aviso.details_link.parent(), self.aviso.action_button.parent())
        self.assertTrue(link.top() <= botao.center().y() <= link.bottom() + 8)
        self.assertGreater(botao.left(), link.right())
        coluna = self.aviso.title.geometry()
        self.assertEqual(botao.right(), coluna.right())

    def test_ver_novidades_na_cor_do_botao_em_todos_os_avisos(self):
        for mostrar in (
            lambda: self.aviso.show_available("0.5.1", "0.5.0"),
            lambda: self.aviso.show_updated("0.5.1"),
        ):
            mostrar()
            self.assertIn(style.ACCENT_HOVER, self.aviso.details_link.text())


class TempoNaTelaTest(unittest.TestCase):
    def setUp(self):
        self.avisos: list[tuple[str, str]] = []
        self.aviso = update_toast.UpdateToast(
            notify=lambda titulo, texto: self.avisos.append((titulo, texto))
        )
        self.addCleanup(_apagar, self.aviso)

    def test_some_sozinho_depois_de_5_segundos(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        self.assertEqual(self.aviso.hide_timer.interval(), 5000)
        self.assertTrue(self.aviso.hide_timer.isActive())
        self.aviso.hide_timer.timeout.emit()
        self.assertFalse(self.aviso.isVisible())

    def test_avisos_vao_para_a_central_de_notificacoes(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        self.aviso.show_updated("0.5.2")
        self.assertEqual(
            self.avisos,
            [
                ("Nova versão do Polpad: 0.5.1", "Você está na 0.5.0"),
                ("Polpad atualizado para 0.5.2", ""),
            ],
        )

    def test_progresso_e_erro_ficam_na_tela(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        self.aviso.show_progress("Baixando… 10%")
        self.assertFalse(self.aviso.hide_timer.isActive())
        self.aviso.show_error("Sem internet")
        self.assertFalse(self.aviso.hide_timer.isActive())
        self.assertEqual(len(self.avisos), 1)

    def test_mouse_em_cima_segura_o_aviso(self):
        self.aviso.show_available("0.5.1", "0.5.0")
        QApplication.sendEvent(self.aviso, QEnterEvent(QPointF(), QPointF(), QPointF()))
        self.assertFalse(self.aviso.hide_timer.isActive())
        QApplication.sendEvent(self.aviso, QEvent(QEvent.Leave))
        self.assertTrue(self.aviso.hide_timer.isActive())

    def test_mouse_em_cima_do_progresso_nao_religa_o_tempo(self):
        self.aviso.show_progress("Baixando… 10%")
        QApplication.sendEvent(self.aviso, QEvent(QEvent.Leave))
        self.assertFalse(self.aviso.hide_timer.isActive())


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

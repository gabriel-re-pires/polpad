"""Testes da Zona de risco: restaurar padrões, apagar perfis e desinstalar."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from polpad.core import reset
from polpad.core.models import Action, Profile, Settings
from polpad.core.store import Store
from polpad.ui import settings_dialog, update_controller
from polpad.update import backup

from .apoio import CofreFalso

APP = QApplication.instance() or QApplication([])
AGORA = datetime(2026, 11, 6, 12, 0, 0)


class Dados(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dados = Path(self._tmp.name)

    def _store(self) -> Store:
        store = Store(self.dados, vault=CofreFalso())
        store.load()
        return store


class RestaurarPadroesTest(Dados):
    def test_volta_ao_padrao_mantendo_os_perfis(self):
        store = self._store()
        store.settings.auto_switch_enabled = True
        store.settings.obs_host = "estudio"
        store.add_profile("Jogos")
        store.save()

        copia = reset.reset_settings(store, "0.6.0", now=AGORA)

        self.assertEqual(store.settings, Settings())
        self.assertEqual([p.name for p in store.profiles], ["Sistema", "Jogos"])
        salvo = json.loads((self.dados / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(salvo["settings"]["obs_host"], "localhost")
        # A cópia guarda o que havia antes e aparece na página de versão.
        self.assertEqual(copia.label, "0.6.0 → configurações padrão")
        antes = json.loads((copia.path / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(antes["settings"]["obs_host"], "estudio")
        self.assertEqual(backup.list_backups(self.dados)[0].path, copia.path)

    def test_escolhas_de_atualizacao_ficam(self):
        store = self._store()
        store.settings.update_notify = False
        store.settings.update_auto = True
        store.settings.start_with_windows = True
        reset.reset_settings(store, "0.6.0", now=AGORA)
        self.assertFalse(store.settings.update_notify)
        self.assertTrue(store.settings.update_auto)
        self.assertFalse(store.settings.start_with_windows)


class ApagarPerfisTest(Dados):
    def test_fica_so_o_perfil_inicial_e_os_icones_saem(self):
        store = self._store()
        jogos = store.add_profile("Jogos")
        jogos.bindings[3] = Action(type="hotkey", params={"keys": ["f5"]})
        store.active_profile_id = jogos.id
        store.icons_dir.mkdir(parents=True)
        (store.icons_dir / f"{jogos.id}.png").write_bytes(b"png")
        store.settings.obs_host = "estudio"
        store.save()

        copia = reset.reset_profiles(store, "0.6.0", now=AGORA)

        self.assertEqual([p.name for p in store.profiles], ["Sistema"])
        self.assertEqual(store.active_profile_id, store.profiles[0].id)
        self.assertFalse(store.icons_dir.exists())
        self.assertEqual(store.settings.obs_host, "estudio")
        salvo = json.loads((self.dados / "config.json").read_text(encoding="utf-8"))
        self.assertEqual([p["name"] for p in salvo["profiles"]], ["Sistema"])
        # A cópia tem os perfis e os ícones de antes.
        self.assertEqual(copia.label, "0.6.0 → perfis apagados")
        self.assertTrue((copia.path / "icons" / f"{jogos.id}.png").is_file())


class PaginaTest(unittest.TestCase):
    def _pagina(self, desinstalar=(True, "Abre o desinstalador do Windows.")):
        pagina = settings_dialog.SettingsPage(
            Settings(), [Profile(name="Sistema")], uninstall=desinstalar
        )
        self.addCleanup(pagina.close)
        self.eventos: list[str] = []
        pagina.reset_settings_requested.connect(lambda: self.eventos.append("padrao"))
        pagina.reset_profiles_requested.connect(lambda: self.eventos.append("perfis"))
        pagina.uninstall_requested.connect(lambda: self.eventos.append("desinstalar"))
        return pagina

    def test_zona_de_risco_fica_no_fim_da_pagina(self):
        pagina = self._pagina()
        self.assertEqual(pagina.danger_zone.objectName(), "dangerCard")
        coluna = pagina.danger_zone.parentWidget().layout()
        ultimo = coluna.itemAt(coluna.count() - 1).widget()
        self.assertIs(ultimo, pagina.danger_zone)

    def test_restaurar_so_com_confirmacao(self):
        pagina = self._pagina()
        with mock.patch.object(pagina, "_confirm", return_value=False):
            pagina.reset_settings_button.click()
            pagina.reset_profiles_button.click()
        self.assertEqual(self.eventos, [])
        with mock.patch.object(pagina, "_confirm", return_value=True):
            pagina.reset_settings_button.click()
            pagina.reset_profiles_button.click()
        self.assertEqual(self.eventos, ["padrao", "perfis"])

    def test_desinstalar_pede_ao_controlador(self):
        pagina = self._pagina()
        self.assertTrue(pagina.uninstall_button.isEnabled())
        pagina.uninstall_button.click()
        self.assertEqual(self.eventos, ["desinstalar"])

    def test_desinstalar_desativado_explica_o_motivo(self):
        pagina = self._pagina((False, "Versão de desenvolvimento."))
        self.assertFalse(pagina.uninstall_button.isEnabled())
        self.assertEqual(pagina.uninstall_hint.text(), "Versão de desenvolvimento.")


class DesinstalarTest(Dados):
    def setUp(self):
        super().setUp()
        self.processos: list[list[str]] = []
        self.saidas: list[str] = []
        self.pasta_app = self.dados / "Programs" / "Polpad"
        self.pasta_app.mkdir(parents=True)

    def _controlador(self, tipo="windows", plataforma="win32"):
        store = self._store()
        self.janela = QWidget()
        self.addCleanup(self.janela.close)
        executavel = self.pasta_app / ("Polpad.exe" if tipo == "windows" else "polpad")
        controlador = update_controller.UpdateController(
            store,
            self.janela,
            now=lambda: AGORA,
            current="0.6.0",
            platform=plataforma,
            executable=str(executavel),
            launcher=self.processos.append,
            quit_app=lambda: self.saidas.append("sair"),
            kind=lambda: tipo,
        )
        self.addCleanup(controlador.shutdown)
        return controlador

    def test_windows_abre_o_desinstalador_do_inno(self):
        (self.pasta_app / "unins000.exe").write_bytes(b"")
        controlador = self._controlador()
        self.assertTrue(controlador.uninstall_support()[0])
        controlador.uninstall()
        self.assertEqual(self.processos, [[str(self.pasta_app / "unins000.exe")]])
        # Quem fecha o Polpad é o desinstalador, só se a pessoa confirmar.
        self.assertEqual(self.saidas, [])

    def test_windows_sem_desinstalador(self):
        controlador = self._controlador()
        disponivel, motivo = controlador.uninstall_support()
        self.assertFalse(disponivel)
        self.assertIn("Aplicativos", motivo)
        controlador.uninstall()
        self.assertEqual(self.processos, [])

    def test_sem_instalacao_nao_desinstala(self):
        for tipo in ("desenvolvimento", "nao_instalado"):
            with self.subTest(tipo=tipo):
                controlador = self._controlador(tipo=tipo)
                disponivel, motivo = controlador.uninstall_support()
                self.assertFalse(disponivel)
                self.assertTrue(motivo)
                controlador.uninstall()
                self.assertEqual(self.processos, [])
                self.assertEqual(self.saidas, [])

    def test_linux_cancelado_nao_faz_nada(self):
        controlador = self._controlador("linux_menu", "linux")
        with (
            mock.patch.object(controlador, "_ask_linux_uninstall", return_value=None),
            mock.patch.object(update_controller.linux_install, "uninstall") as remover,
        ):
            controlador.uninstall()
        remover.assert_not_called()
        self.assertEqual(self.saidas, [])

    def test_linux_remove_do_menu_e_sai(self):
        controlador = self._controlador("linux_menu", "linux")
        with (
            mock.patch.object(controlador, "_ask_linux_uninstall", return_value=False),
            mock.patch.object(update_controller.linux_install, "uninstall") as remover,
            mock.patch.object(update_controller.QMessageBox, "information"),
        ):
            controlador.uninstall()
        remover.assert_called_once_with()
        self.assertEqual(self.processos, [])
        self.assertEqual(self.saidas, ["sair"])

    def test_linux_com_perfis_apaga_a_pasta_depois_de_sair(self):
        """A pasta só pode sair depois do Polpad fechar: ao sair ele ainda
        grava a configuração, que voltaria a existir."""
        controlador = self._controlador("linux_menu", "linux")
        with (
            mock.patch.object(controlador, "_ask_linux_uninstall", return_value=True),
            mock.patch.object(update_controller.linux_install, "uninstall"),
            mock.patch.object(update_controller.QMessageBox, "information"),
        ):
            controlador.uninstall()
        self.assertEqual(len(self.processos), 1)
        argv = self.processos[0]
        self.assertEqual(argv[:2], ["/bin/sh", "-c"])
        self.assertEqual(argv[-2:], [str(os.getpid()), str(self.dados)])
        self.assertTrue(self.dados.exists())
        self.assertEqual(self.saidas, ["sair"])


if __name__ == "__main__":
    unittest.main()

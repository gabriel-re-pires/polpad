"""Testes do controlador de atualizações (rede, processos e relógio falsos)."""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import requests
import shiboken6
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from polpad.core.store import Store
from polpad.device import firmware_release
from polpad.device.firmware_release import FirmwareRelease
from polpad.ui import update_controller, version_dialog
from polpad.update import backup, github, state

from .apoio import ClienteFalso, CofreFalso, RespostaFalsa

APP = QApplication.instance() or QApplication([])
AGORA = datetime(2026, 11, 6, 12, 0, 0)
CONTEUDO = b"instalador 0.5.1"


def _payload() -> list[dict]:
    base = "https://github.com/gabriel-re-pires/polpad/releases/download/v0.5.1"
    return [
        {
            "tag_name": "v0.5.1",
            "name": "Polpad 0.5.1",
            "body": "Novidades",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-11-06T10:00:00Z",
            "html_url": "https://github.com/gabriel-re-pires/polpad/releases/tag/v0.5.1",
            "assets": [
                {
                    "name": "Polpad-Setup.exe",
                    "size": len(CONTEUDO),
                    "browser_download_url": f"{base}/Polpad-Setup.exe",
                },
                {
                    "name": "SHA256SUMS.txt",
                    "size": 1,
                    "browser_download_url": f"{base}/SHA256SUMS.txt",
                },
            ],
        }
    ]


def _cliente() -> ClienteFalso:
    base = "https://github.com/gabriel-re-pires/polpad/releases/download/v0.5.1"
    soma = hashlib.sha256(CONTEUDO).hexdigest()
    return ClienteFalso(
        {
            github.RELEASES_URL: RespostaFalsa(payload=_payload()),
            f"{base}/Polpad-Setup.exe": RespostaFalsa(conteudo=CONTEUDO),
            f"{base}/SHA256SUMS.txt": RespostaFalsa(
                conteudo=f"{soma}  Polpad-Setup.exe\n".encode()
            ),
        }
    )


def _sincrono(funcao, ao_terminar, ao_falhar):
    try:
        resultado = funcao()
    except Exception as exc:
        ao_falhar(str(exc))
    else:
        ao_terminar(resultado)


class Adiado:
    """Executor que guarda as tarefas para o teste rodar quando quiser."""

    def __init__(self):
        self.fila = []

    def __call__(self, funcao, ao_terminar, ao_falhar):
        self.fila.append((funcao, ao_terminar, ao_falhar))

    def rodar(self):
        funcao, ao_terminar, ao_falhar = self.fila.pop(0)
        _sincrono(funcao, ao_terminar, ao_falhar)


ASSET_051 = (
    "https://github.com/gabriel-re-pires/polpad/releases/download/v0.5.1/Polpad-Setup.exe"
)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dados = Path(self._tmp.name)
        (self.dados / "config.json").write_text("{}", encoding="utf-8")
        self.processos: list[list[str]] = []
        self.saidas: list[str] = []

    def _controlador(
        self,
        cliente=None,
        atual="0.5.0",
        auto=False,
        runner=None,
        tipo="windows",
        plataforma="win32",
        central=None,
        firmware=None,
    ):
        store = Store(self.dados, vault=CofreFalso())
        store.settings.update_auto = auto
        self.janela = QWidget()
        self.addCleanup(self.janela.close)
        controlador = update_controller.UpdateController(
            store,
            self.janela,
            session=cliente or _cliente(),
            now=lambda: AGORA,
            current=atual,
            platform=plataforma,
            executable=str(self.dados / "Polpad.exe"),
            launcher=self.processos.append,
            quit_app=lambda: self.saidas.append("sair"),
            runner=runner or _sincrono,
            kind=lambda: tipo,
            center=central,
            **({"firmware_check": firmware} if firmware is not None else {}),
        )
        self.addCleanup(controlador.shutdown)
        return controlador

    def _estado(self) -> state.UpdateState:
        return state.UpdateState.load(state.state_path(self.dados))


class StartupTest(Base):
    def _pendente(self, versao: str, existe: bool = True) -> Path:
        arquivo = self.dados / "updates" / f"v{versao}" / "Polpad-Setup.exe"
        if existe:
            arquivo.parent.mkdir(parents=True)
            arquivo.write_bytes(CONTEUDO)
        soma = hashlib.sha256(CONTEUDO).hexdigest()
        state.UpdateState(pending=state.Pending(versao, str(arquivo), soma)).save(
            state.state_path(self.dados)
        )
        return arquivo

    def _startup(self, atual: str) -> update_controller.StartupResult:
        return update_controller.startup(
            self.dados,
            atual,
            frozen=True,
            platform="win32",
            executable=str(self.dados / "Polpad.exe"),
            launcher=self.processos.append,
            now=lambda: AGORA,
        )

    def test_startup_instala_pendente(self):
        arquivo = self._pendente("0.5.1")
        resultado = self._startup("0.5.0")
        self.assertEqual(resultado.action, "exit")
        self.assertEqual(len(backup.list_backups(self.dados)), 1)
        estado = self._estado()
        self.assertEqual(estado.switch.to_version, "0.5.1")
        self.assertIsNone(estado.pending)
        self.assertEqual(self.processos[0][0], str(arquivo))
        self.assertIn("/ATUALIZACAO", self.processos[0])

    def test_pendente_alterada_no_disco_nao_e_executada(self):
        arquivo = self._pendente("0.5.1")
        arquivo.write_bytes(b"outro programa")
        resultado = self._startup("0.5.0")
        self.assertEqual(resultado.action, "continue")
        self.assertEqual(self.processos, [])
        self.assertIsNone(self._estado().pending)
        self.assertIsNone(self._estado().switch)

    def test_pendente_linux_danificada_nao_deixa_troca_marcada(self):
        alvo = self.dados / "bin" / "polpad"
        alvo.parent.mkdir()
        alvo.write_bytes(b"\x7fELF velho")
        executavel = b"\x7fELF" + os.urandom(256 * 1024)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            info = tarfile.TarInfo("Polpad-Linux/Polpad")
            info.size = len(executavel)
            tar.addfile(info, io.BytesIO(executavel))
        # Cortado ao meio, mas com a soma conferida: o release já veio assim.
        cortado = buffer.getvalue()[: len(buffer.getvalue()) // 2]
        arquivo = self.dados / "updates" / "v0.5.1" / "Polpad-linux-x86_64.tar.gz"
        arquivo.parent.mkdir(parents=True)
        arquivo.write_bytes(cortado)
        soma = hashlib.sha256(cortado).hexdigest()
        state.UpdateState(pending=state.Pending("0.5.1", str(arquivo), soma)).save(
            state.state_path(self.dados)
        )
        resultado = update_controller.startup(
            self.dados,
            "0.5.0",
            frozen=True,
            platform="linux",
            executable=str(alvo),
            launcher=self.processos.append,
            now=lambda: AGORA,
        )
        self.assertEqual(resultado.action, "continue")
        self.assertEqual(self.processos, [])
        self.assertEqual(alvo.read_bytes(), b"\x7fELF velho")
        estado = self._estado()
        self.assertIsNone(estado.switch)
        self.assertIsNone(estado.pending)
        self.assertFalse(arquivo.exists())

    def test_startup_descarta_pendente_velha(self):
        arquivo = self._pendente("0.5.0")
        resultado = self._startup("0.5.1")
        self.assertEqual(resultado.action, "continue")
        self.assertFalse(arquivo.exists())
        self.assertIsNone(self._estado().pending)
        self.assertEqual(self.processos, [])

    def test_startup_resultado_da_troca(self):
        sobra = self.dados / "updates" / "v0.5.1" / "Polpad-Setup.exe"
        sobra.parent.mkdir(parents=True)
        sobra.write_bytes(b"x")
        marca = state.Switch("0.5.0", "0.5.1", AGORA.isoformat())
        state.UpdateState(switch=marca).save(state.state_path(self.dados))
        resultado = self._startup("0.5.1")
        self.assertEqual((resultado.outcome, resultado.version), ("ok", "0.5.1"))
        self.assertIsNone(self._estado().switch)
        self.assertFalse(sobra.exists())
        self.assertTrue(state.state_path(self.dados).exists())

    def test_startup_troca_que_falhou(self):
        marca = state.Switch("0.5.0", "0.5.1", AGORA.isoformat())
        state.UpdateState(switch=marca).save(state.state_path(self.dados))
        resultado = self._startup("0.5.0")
        self.assertEqual((resultado.outcome, resultado.version), ("failed", "0.5.1"))

    def test_desenvolvimento_ignora_pendente(self):
        self._pendente("0.5.1")
        resultado = update_controller.startup(
            self.dados, "0.5.0", frozen=False, launcher=self.processos.append
        )
        self.assertEqual(resultado.action, "continue")
        self.assertEqual(self.processos, [])


class VerificacaoTest(Base):
    def test_verificacao_automatica_silenciosa(self):
        controlador = self._controlador(ClienteFalso(requests.ConnectionError("x")))
        controlador.check_now(user=False)
        self.assertFalse(controlador.toast.isVisible())
        self.assertIsNone(self._estado().last_check)
        self.assertEqual(controlador.error, "")

    def test_verificacao_do_usuario_mostra_o_erro(self):
        controlador = self._controlador(ClienteFalso(requests.ConnectionError("x")))
        controlador.check_now(user=True)
        self.assertIn("internet", controlador.error)

    def test_aviso_de_versao_nova(self):
        controlador = self._controlador()
        controlador.check_now(user=False)
        self.assertTrue(controlador.toast.isVisible())
        self.assertEqual(controlador.toast.title.text(), "Nova versão do Polpad: 0.5.1")
        self.assertEqual(self._estado().last_check, AGORA.isoformat())

    def test_aviso_respeita_x(self):
        controlador = self._controlador()
        controlador.check_now(user=False)
        controlador.toast.close_button.click()
        controlador.check_now(user=False)
        self.assertFalse(controlador.toast.isVisible())
        controlador.scheduled_check()
        self.assertTrue(controlador.toast.isVisible())

    def test_aviso_aparece_a_cada_inicio(self):
        # Verificou há 2 h, mas o Polpad acabou de abrir: avisa de novo.
        state.UpdateState(last_check=(AGORA - timedelta(hours=2)).isoformat()).save(
            state.state_path(self.dados)
        )
        controlador = self._controlador()
        with mock.patch.object(
            update_controller.QTimer, "singleShot", lambda _ms, fn: fn()
        ):
            controlador.start()
        self.assertTrue(controlador.toast.isVisible())

    def test_atualizar_limpa_a_central_de_notificacoes(self):
        central = mock.Mock()
        controlador = self._controlador(central=central)
        controlador.check_now(user=False)
        central.post.assert_called_once_with(
            "Nova versão do Polpad: 0.5.1", "Você está na 0.5.0"
        )
        controlador.toast.action_button.click()
        central.clear.assert_called()

    def test_aviso_desligado(self):
        controlador = self._controlador()
        controlador.store.settings.update_notify = False
        controlador.check_now(user=False)
        self.assertFalse(controlador.toast.isVisible())
        self.assertEqual(controlador.update.version, "0.5.1")

    def test_verificacao_agendada_respeita_24h(self):
        state.UpdateState(last_check=(AGORA - timedelta(hours=2)).isoformat()).save(
            state.state_path(self.dados)
        )
        cliente = _cliente()
        controlador = self._controlador(cliente)
        controlador.tick()
        self.assertEqual(cliente.chamadas, [])


class EncerramentoTest(Base):
    def test_shutdown_apaga_o_aviso_antes_do_qapplication(self):
        """Uma janela sem dono destruída depois do QApplication derruba o
        processo ao sair (access violation no encerramento do Python)."""
        controlador = self._controlador()
        controlador.check_now(user=False)
        aviso = controlador.toast
        controlador.shutdown()
        self.assertFalse(shiboken6.isValid(aviso))
        controlador.shutdown()  # idempotente


class AtualizacaoTest(Base):
    def test_automatico_baixa_e_deixa_pendente(self):
        controlador = self._controlador(auto=True)
        controlador.check_now(user=False)
        pendente = self._estado().pending
        self.assertEqual(pendente.version, "0.5.1")
        self.assertEqual(Path(pendente.path).read_bytes(), CONTEUDO)
        self.assertEqual(
            controlador.toast.title.text(),
            "O Polpad 0.5.1 será instalado quando você sair",
        )
        self.assertEqual(self.processos, [])

    def test_sair_nao_executa_pendente_alterada(self):
        controlador = self._controlador(auto=True)
        controlador.check_now(user=False)
        Path(self._estado().pending.path).write_bytes(b"outro programa")
        controlador.before_quit()
        self.assertEqual(self.processos, [])

    def test_sair_instala_a_pendente_sem_reabrir(self):
        controlador = self._controlador(auto=True)
        controlador.check_now(user=False)
        controlador.before_quit()
        self.assertEqual(len(self.processos), 1)
        self.assertNotIn("/ATUALIZACAO", self.processos[0])
        self.assertEqual(self._estado().switch.to_version, "0.5.1")

    def test_atualizar_baixa_instala_e_sai(self):
        controlador = self._controlador()
        controlador.check_now(user=False)
        controlador.toast.action_button.click()
        self.assertIn("/ATUALIZACAO", self.processos[0])
        self.assertEqual(self.saidas, ["sair"])
        self.assertEqual(len(backup.list_backups(self.dados)), 1)

    def test_falha_no_download_mostra_tentar_de_novo(self):
        cliente = _cliente()
        base = "https://github.com/gabriel-re-pires/polpad/releases/download/v0.5.1"
        cliente._resposta[f"{base}/Polpad-Setup.exe"] = requests.ConnectionError("x")
        controlador = self._controlador(cliente)
        controlador.check_now(user=False)
        controlador.toast.action_button.click()
        self.assertEqual(self.processos, [])
        self.assertEqual(controlador.toast.action_button.text(), "Tentar de novo")
        self.assertEqual(self.saidas, [])

    def test_ligar_automatico_salva(self):
        controlador = self._controlador()
        controlador.set_auto(True)
        recarregado = Store(self.dados, vault=CofreFalso())
        recarregado.load()
        self.assertTrue(recarregado.settings.update_auto)


class StartupRobustoTest(Base):
    def test_log_preso_pelo_instalador_nao_impede_a_abertura(self):
        log = self.dados / "updates" / "instalacao.log"
        log.parent.mkdir(parents=True)
        log.write_text("x", encoding="utf-8")
        marca = state.Switch("0.5.0", "0.5.1", AGORA.isoformat())
        state.UpdateState(switch=marca).save(state.state_path(self.dados))
        original = Path.unlink

        def unlink(caminho, missing_ok=False):
            if caminho.name == "instalacao.log":
                raise PermissionError(32, "em uso")
            return original(caminho, missing_ok=missing_ok)

        with mock.patch.object(Path, "unlink", unlink):
            resultado = update_controller.startup(
                self.dados, "0.5.1", frozen=True, launcher=self.processos.append
            )
        self.assertEqual(resultado.outcome, "ok")

    def test_safe_startup_nunca_impede_a_abertura(self):
        with mock.patch.object(
            update_controller, "startup", side_effect=OSError("disco cheio")
        ):
            resultado = update_controller.safe_startup(self.dados, "0.5.0", True)
        self.assertEqual(resultado.action, "continue")


class DesenvolvimentoTest(Base):
    def test_desenvolvimento_nao_mostra_aviso_nem_instala(self):
        controlador = self._controlador(tipo="desenvolvimento")
        controlador.check_now(user=True)
        self.assertEqual(controlador.update.version, "0.5.1")
        self.assertFalse(controlador.toast.isVisible())
        controlador.begin_update(controlador.update)
        self.assertEqual(self.processos, [])
        self.assertEqual(self.saidas, [])


class AutomaticoTest(Base):
    def test_desligar_automatico_descarta_a_pendente(self):
        controlador = self._controlador(auto=True)
        controlador.check_now(user=False)
        arquivo = Path(self._estado().pending.path)
        controlador.set_auto(False)
        self.assertIsNone(self._estado().pending)
        self.assertFalse(arquivo.exists())
        self.assertFalse(controlador.toast.isVisible())

    def test_download_que_termina_depois_de_desligar_nao_fica_pendente(self):
        adiado = Adiado()
        controlador = self._controlador(auto=True, runner=adiado)
        controlador.check_now(user=False)
        adiado.rodar()  # consulta
        controlador.set_auto(False)
        adiado.rodar()  # download automático
        self.assertIsNone(self._estado().pending)

    def test_download_automatico_nao_se_repete(self):
        cliente = _cliente()
        controlador = self._controlador(cliente, auto=True)
        controlador.check_now(user=False)
        controlador.scheduled_check()
        controlador.set_auto(True)
        self.assertEqual(cliente.chamadas.count(ASSET_051), 1)

    def test_um_download_automatico_por_vez(self):
        adiado = Adiado()
        controlador = self._controlador(auto=True, runner=adiado)
        controlador.check_now(user=False)
        adiado.rodar()  # consulta → agenda o download
        controlador.check_now(user=False)
        adiado.rodar()  # segunda consulta: não agenda outro download
        self.assertEqual(len(adiado.fila), 1)

    def test_atualizar_durante_download_automatico_usa_o_mesmo(self):
        adiado = Adiado()
        controlador = self._controlador(auto=True, runner=adiado)
        controlador.check_now(user=False)
        adiado.rodar()  # consulta → agenda o download automático
        controlador.begin_update(controlador.update)
        self.assertEqual(len(adiado.fila), 1)
        adiado.rodar()  # o download automático termina
        self.assertIn("/ATUALIZACAO", self.processos[0])
        self.assertEqual(self.saidas, ["sair"])

    def test_verificacao_nao_libera_atualizacao_em_andamento(self):
        adiado = Adiado()
        controlador = self._controlador(runner=adiado)
        controlador.check_now(user=False)
        adiado.rodar()
        controlador.begin_update(controlador.update)
        controlador.check_now(user=True)
        adiado.rodar()  # download do usuário (primeiro da fila)
        adiado.rodar()  # consulta
        controlador.begin_update(controlador.update)
        self.assertEqual(adiado.fila, [])
        self.assertEqual(len(self.processos), 1)


class EncerramentoDuranteDownloadTest(Base):
    def test_shutdown_cancela_o_download_em_andamento(self):
        adiado = Adiado()
        controlador = self._controlador(auto=True, runner=adiado)
        controlador.check_now(user=False)
        adiado.rodar()
        controlador.shutdown()
        adiado.rodar()
        self.assertIsNone(self._estado().pending)
        self.assertEqual(list((self.dados / "updates").rglob("*.exe")), [])


class RestaurarTest(Base):
    def test_restaurar_recarrega_os_perfis_antes_de_sair(self):
        import json

        controlador = self._controlador()
        copia = backup.create(self.dados, "0.5.0", "0.5.1", now=AGORA)
        (copia.path / "config.json").write_text(
            json.dumps({"settings": {"update_notify": False}, "profiles": []}),
            encoding="utf-8",
        )
        controlador._restore(copia)
        self.assertFalse(controlador.store.settings.update_notify)
        self.assertEqual(self.saidas, ["sair"])


class PlataformaTest(Base):
    def test_lista_usa_a_plataforma_do_controlador(self):
        """A plataforma injetada vale também para escolher o arquivo do
        release; com a do sistema, os testes de Windows falhavam no Linux."""
        base = "https://x/v0.5.1"
        payload = _payload()
        payload[0]["assets"] = [
            {
                "name": "Polpad-linux-x86_64.tar.gz",
                "size": 1,
                "browser_download_url": f"{base}/Polpad-linux-x86_64.tar.gz",
            },
            {"name": "SHA256SUMS.txt", "size": 1, "browser_download_url": f"{base}/s"},
        ]
        cliente = ClienteFalso({github.RELEASES_URL: RespostaFalsa(payload=payload)})
        controlador = self._controlador(cliente, plataforma="linux")
        controlador.store.settings.update_notify = False
        controlador.check_now(user=False)
        self.assertIsNotNone(controlador.update)
        self.assertEqual(controlador.update.asset_name, "Polpad-linux-x86_64.tar.gz")


class PaginaDeVersaoTest(Base):
    """"Versão e atualizações" abre como página dentro da janela."""

    def _com_paginas(self):
        controlador = self._controlador()
        self.mostradas = []
        controlador.show_page = self.mostradas.append
        return controlador

    def test_abre_como_pagina(self):
        controlador = self._com_paginas()
        controlador.open_page()
        self.assertEqual(len(self.mostradas), 1)
        self.assertIsInstance(self.mostradas[0], version_dialog.VersionPage)
        self.assertNotIsInstance(self.mostradas[0], QDialog)

    def test_ver_novidades_abre_a_pagina(self):
        controlador = self._com_paginas()
        controlador.toast.details_clicked.emit()
        self.assertIsInstance(self.mostradas[0], version_dialog.VersionPage)

    def test_abrir_de_novo_reaproveita_a_pagina(self):
        controlador = self._com_paginas()
        controlador.open_page()
        controlador.open_page()
        self.assertIs(self.mostradas[0], self.mostradas[1])

    def test_pagina_fechada_e_recriada(self):
        controlador = self._com_paginas()
        controlador.open_page()
        shiboken6.delete(self.mostradas[0])
        controlador.check_now(user=True)  # atualizar o estado não pode quebrar
        controlador.open_page()
        self.assertTrue(shiboken6.isValid(self.mostradas[1]))
        self.assertEqual(
            self.mostradas[1].version_label.text(), f"Polpad {controlador.current}"
        )


def _firmware(versao: str = "2.1.0") -> FirmwareRelease:
    return FirmwareRelease(
        tag="v0.7.2",
        version=versao,
        asset_name=f"firmware-{versao}.bin",
        url=f"https://x/firmware-{versao}.bin",
        size=1,
    )


class AvisoDeFirmwareTest(Base):
    """Placa com firmware antigo: o Polpad avisa que há um mais novo."""

    def _com_firmware(self, versao="2.1.0", central=None):
        self.consultas = 0

        def consultar():
            self.consultas += 1
            return _firmware(versao)

        return self._controlador(firmware=consultar, central=central)

    def test_firmware_novo_avisa(self):
        central = mock.Mock()
        controlador = self._com_firmware(central=central)
        controlador.device_firmware("2.0.2")
        self.assertTrue(controlador.toast.isVisible())
        self.assertEqual(
            controlador.toast.title.text(), "Firmware 2.1.0 disponível para o macropad"
        )
        self.assertEqual(controlador.toast.current_action, "flash")
        central.post.assert_called_once_with(
            "Firmware 2.1.0 disponível para o macropad",
            "O seu está com o 2.0.2",
            tag="firmware",
        )

    def test_firmware_em_dia_nao_avisa(self):
        controlador = self._com_firmware("2.0.2")
        controlador.device_firmware("2.0.2")
        self.assertFalse(controlador.toast.isVisible())

    def test_firmware_mais_novo_que_o_release_nao_avisa(self):
        controlador = self._com_firmware("2.0.2")
        controlador.device_firmware("2.1.0")
        self.assertFalse(controlador.toast.isVisible())

    def test_aviso_desligado_nem_consulta(self):
        controlador = self._com_firmware()
        controlador.store.settings.update_notify = False
        controlador.device_firmware("2.0.2")
        self.assertEqual(self.consultas, 0)
        self.assertFalse(controlador.toast.isVisible())

    def test_consulta_uma_vez_por_sessao(self):
        controlador = self._com_firmware()
        controlador.device_firmware("2.0.2")
        controlador.toast.hide()
        controlador.device_firmware("2.0.2")  # a placa reconectou
        self.assertEqual(self.consultas, 1)

    def test_gravar_abre_a_pagina_de_firmware(self):
        controlador = self._com_firmware()
        pedidos = []
        controlador.flash_requested.connect(lambda: pedidos.append(True))
        controlador.device_firmware("2.0.2")
        controlador.toast.action_button.click()
        self.assertEqual(pedidos, [True])
        self.assertFalse(controlador.toast.isVisible())

    def test_fechar_nao_avisa_de_novo_nesta_sessao(self):
        controlador = self._com_firmware()
        controlador.device_firmware("2.0.2")
        controlador.toast.close_button.click()
        controlador.device_firmware("2.0.2")
        self.assertFalse(controlador.toast.isVisible())
        # O X do firmware não cala o aviso de versão nova do programa.
        controlador.check_now(user=False)
        self.assertEqual(controlador.toast.title.text(), "Nova versão do Polpad: 0.5.1")

    def test_nao_atropela_o_aviso_do_programa(self):
        controlador = self._com_firmware()
        controlador.check_now(user=False)
        adiados = []
        with mock.patch.object(
            update_controller.QTimer, "singleShot", lambda _ms, fn: adiados.append(fn)
        ):
            controlador.device_firmware("2.0.2")
        self.assertEqual(controlador.toast.title.text(), "Nova versão do Polpad: 0.5.1")
        controlador.toast.hide()
        adiados[0]()
        self.assertEqual(
            controlador.toast.title.text(), "Firmware 2.1.0 disponível para o macropad"
        )

    def test_falha_na_consulta_nao_avisa(self):
        def falhar():
            raise firmware_release.ReleaseError("sem internet")

        controlador = self._controlador(firmware=falhar)
        controlador.device_firmware("2.0.2")
        self.assertFalse(controlador.toast.isVisible())


if __name__ == "__main__":
    unittest.main()

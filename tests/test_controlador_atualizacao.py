"""Testes do controlador de atualizações (rede, processos e relógio falsos)."""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import requests
from PySide6.QtWidgets import QApplication, QWidget

from polpad.core.store import Store
from polpad.ui import update_controller
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


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dados = Path(self._tmp.name)
        (self.dados / "config.json").write_text("{}", encoding="utf-8")
        self.processos: list[list[str]] = []
        self.saidas: list[str] = []

    def _controlador(self, cliente=None, atual="0.5.0", auto=False):
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
            platform="win32",
            executable=str(self.dados / "Polpad.exe"),
            launcher=self.processos.append,
            quit_app=lambda: self.saidas.append("sair"),
            runner=_sincrono,
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
        import shiboken6

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


if __name__ == "__main__":
    unittest.main()

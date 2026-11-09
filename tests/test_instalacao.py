"""Testes do download conferido e da troca de versão."""

from __future__ import annotations

import hashlib
import io
import os
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

from polpad import single_instance
from polpad.update import installer
from polpad.update.releases import AppRelease

from .apoio import ClienteFalso, RespostaFalsa

CONTEUDO = b"instalador de mentira"
ARQUIVO_URL = "https://x/Polpad-Setup.exe"
SOMAS_URL = "https://x/SHA256SUMS.txt"


def _release() -> AppRelease:
    return AppRelease(
        version="0.5.1",
        tag="v0.5.1",
        name="Polpad 0.5.1",
        notes="",
        published_at="",
        html_url="",
        asset_name="Polpad-Setup.exe",
        asset_url=ARQUIVO_URL,
        asset_size=len(CONTEUDO),
        sums_url=SOMAS_URL,
    )


def _cliente(soma: str) -> ClienteFalso:
    return ClienteFalso(
        {
            ARQUIVO_URL: RespostaFalsa(conteudo=CONTEUDO),
            SOMAS_URL: RespostaFalsa(conteudo=f"{soma}  Polpad-Setup.exe\n".encode()),
        }
    )


class PrepareTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dados = Path(self._tmp.name)

    def test_prepare_confere_a_soma(self):
        soma = hashlib.sha256(CONTEUDO).hexdigest()
        caminho, sha = installer.prepare(_release(), self.dados, session=_cliente(soma))
        self.assertEqual(caminho, self.dados / "updates" / "v0.5.1" / "Polpad-Setup.exe")
        self.assertEqual(caminho.read_bytes(), CONTEUDO)
        self.assertEqual(sha, soma)

    def test_soma_errada_apaga_e_recusa(self):
        with self.assertRaises(installer.InstallError) as caso:
            installer.prepare(_release(), self.dados, session=_cliente("0" * 64))
        self.assertIn("corrompido", str(caso.exception))
        self.assertFalse(
            (self.dados / "updates" / "v0.5.1" / "Polpad-Setup.exe").exists()
        )


class LinhaDeComandoTest(unittest.TestCase):
    def test_linha_de_comando_windows(self):
        log = Path("C:/Users/João Silva/AppData/Roaming/Polpad/updates/instalacao.log")
        argv = installer.windows_command(Path("C:/x/Polpad-Setup.exe"), log, True)
        # /SILENT mostra o progresso, para ninguém achar que o Polpad sumiu.
        self.assertEqual(
            argv[1:5],
            ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        )
        self.assertEqual(argv[-1], "/ATUALIZACAO")
        logs = [a for a in argv if a.startswith("/LOG=")]
        self.assertEqual(len(logs), 1)
        self.assertIn("João Silva", logs[0])

    def test_sem_reabrir(self):
        argv = installer.windows_command(Path("a.exe"), Path("b.log"), False)
        self.assertNotIn("/ATUALIZACAO", argv)
        # Ao sair pela bandeja a pessoa quis fechar: nada de janela.
        self.assertIn("/VERYSILENT", argv)


def _pacote(pasta: Path, conteudo: bytes, membro: str = "Polpad") -> Path:
    caminho = pasta / "Polpad-linux-x86_64.tar.gz"
    with tarfile.open(caminho, "w:gz") as tar:
        info = tarfile.TarInfo(membro)
        info.size = len(conteudo)
        tar.addfile(info, io.BytesIO(conteudo))
    return caminho


class TrocaLinuxTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pasta = Path(self._tmp.name)
        self.alvo = self.pasta / "bin" / "polpad"
        self.alvo.parent.mkdir()
        self.alvo.write_bytes(b"\x7fELF velho")

    def test_troca_linux(self):
        installer.swap_linux(_pacote(self.pasta, b"\x7fELF novo"), self.alvo)
        self.assertEqual(self.alvo.read_bytes(), b"\x7fELF novo")
        self.assertFalse((self.alvo.parent / ".polpad.novo").exists())
        if sys.platform != "win32":
            self.assertEqual(self.alvo.stat().st_mode & 0o777, 0o755)

    def test_troca_linux_com_a_pasta_polpad_linux(self):
        pacote = _pacote(self.pasta, b"\x7fELF novo", "Polpad-Linux/Polpad")
        installer.swap_linux(pacote, self.alvo)
        self.assertEqual(self.alvo.read_bytes(), b"\x7fELF novo")

    def test_troca_linux_recusa_nao_elf(self):
        with self.assertRaises(installer.InstallError):
            installer.swap_linux(_pacote(self.pasta, b"#!/bin/sh\n"), self.alvo)
        self.assertEqual(self.alvo.read_bytes(), b"\x7fELF velho")
        self.assertFalse((self.alvo.parent / ".polpad.novo").exists())

    def test_pacote_cortado_vira_install_error(self):
        # Conteúdo aleatório não comprime: o corte cai no meio do executável.
        executavel = b"\x7fELF" + os.urandom(2 * 1024 * 1024)
        inteiro = _pacote(self.pasta, executavel, "Polpad-Linux/Polpad").read_bytes()
        for fracao in (0.5, 0.9, 0.999):
            with self.subTest(fracao=fracao):
                cortado = self.pasta / f"cortado-{fracao}.tar.gz"
                cortado.write_bytes(inteiro[: int(len(inteiro) * fracao)])
                with self.assertRaises(installer.InstallError) as ctx:
                    installer.swap_linux(cortado, self.alvo)
                self.assertIn("danificado", str(ctx.exception))
                self.assertEqual(self.alvo.read_bytes(), b"\x7fELF velho")
                self.assertFalse((self.alvo.parent / ".polpad.novo").exists())


class TipoDeInstalacaoTest(unittest.TestCase):
    def test_desenvolvimento(self):
        self.assertFalse(getattr(sys, "frozen", False))
        self.assertEqual(installer.install_kind(), "desenvolvimento")

    def test_windows_instalado(self):
        local = Path(tempfile.gettempdir()) / "local"
        exe = local / "Programs" / "Polpad" / "Polpad.exe"
        with (
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(sys, "executable", str(exe)),
            mock.patch.object(sys, "platform", "win32"),
            mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local)}),
        ):
            self.assertEqual(installer.install_kind(), "windows")


class InstanciaUnicaTest(unittest.TestCase):
    def test_instancia_espera_a_antiga(self):
        app = QApplication.instance() or QApplication([])
        nome = f"polpad-teste-{os.getpid()}-{time.time_ns()}"
        with mock.patch.object(single_instance, "SERVER_NAME", nome):
            antiga = QLocalServer()
            self.assertTrue(antiga.listen(nome))
            QTimer.singleShot(500, antiga.close)
            nova = single_instance.SingleInstance()
            self.assertTrue(nova.try_acquire(wait_s=5))
            nova.release()
        del app

    def test_sem_espera_respeita_a_antiga(self):
        app = QApplication.instance() or QApplication([])
        nome = f"polpad-teste-{os.getpid()}-{time.time_ns()}"
        with mock.patch.object(single_instance, "SERVER_NAME", nome):
            antiga = QLocalServer()
            self.assertTrue(antiga.listen(nome))
            self.assertFalse(single_instance.SingleInstance().try_acquire())
            antiga.close()
        del app


class LancamentoTest(unittest.TestCase):
    def test_processo_novo_nao_herda_o_ambiente_do_pyinstaller(self):
        """O Polpad reaberto por si mesmo precisa desempacotar a própria
        versão, não reusar a pasta temporária da instância que vai sair."""
        with mock.patch.object(installer.subprocess, "Popen") as popen:
            installer.launch_detached(["/opt/polpad", "--apos-atualizacao"])
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        self.assertEqual(env.get("PATH"), os.environ.get("PATH"))


if __name__ == "__main__":
    unittest.main()

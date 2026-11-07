"""Testes da integração com o OBS (obs-websocket)."""

import logging
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from polpad.core import logs
from polpad.integrations import obs


def _porta_fechada() -> int:
    """Porta livre em que nada escuta: a conexão é recusada na hora."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SenhaNoLogTest(unittest.TestCase):
    """O obsws_python registra em INFO os parâmetros de conexão, senha
    inclusive; com o log raiz em INFO ela ia parar no polpad.log."""

    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.pasta, True)
        raiz = logging.getLogger()
        self.addCleanup(raiz.setLevel, raiz.level)
        self.addCleanup(setattr, raiz, "handlers", list(raiz.handlers))
        self.addCleanup(setattr, sys, "excepthook", sys.excepthook)
        obsws = logging.getLogger("obsws_python")
        self.addCleanup(obsws.setLevel, obsws.level)

    def test_senha_nao_vai_para_o_arquivo_de_log(self):
        # Sem stderr: só o arquivo, e nada de log no console dos testes.
        with (
            mock.patch.object(logs, "log_dir", return_value=self.pasta),
            mock.patch.object(logs.sys, "stderr", None),
        ):
            caminho = logs.setup()
        self.assertIsNotNone(caminho)
        novos = [
            h for h in logging.getLogger().handlers
            if getattr(h, "baseFilename", None) == str(caminho)
        ]
        self.addCleanup(lambda: [h.close() for h in novos])

        with self.assertRaises(obs.ActionError):
            obs._connect("127.0.0.1", _porta_fechada(), "X-segredo")
        for h in novos:
            h.flush()

        texto = caminho.read_text(encoding="utf-8")
        self.assertNotIn("X-segredo", texto)


if __name__ == "__main__":
    unittest.main()

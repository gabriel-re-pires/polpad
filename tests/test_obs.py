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


class ClienteFalso:
    """Cliente obs-websocket que registra os pedidos que "chegaram ao OBS"
    e depois lança o erro configurado (nas primeiras ``falhas`` vezes)."""

    def __init__(self, recebidos, erro, falhas=1):
        self.recebidos = recebidos
        self.erro = erro
        self.falhas = falhas

    def send(self, request, data=None):
        self.recebidos.append(request)
        if len(self.recebidos) <= self.falhas:
            raise self.erro

    def disconnect(self):
        pass


class ReenvioTest(unittest.TestCase):
    """Só vale reenviar quando a conexão caiu antes de o pedido chegar. Se
    o OBS demorou a responder ou recusou o pedido, ele já o recebeu: um
    reenvio liga e desliga a gravação."""

    def setUp(self):
        obs._reset_client()
        self.addCleanup(obs._reset_client)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def _enviar(self, erro):
        recebidos = []
        cliente = ClienteFalso(recebidos, erro)
        with mock.patch.object(obs, "_connect", return_value=cliente):
            try:
                obs.send("localhost", 4455, "", "toggle_record", {})
            except obs.ActionError as exc:
                return recebidos, exc
        return recebidos, None

    def test_timeout_nao_reenvia(self):
        from obsws_python.error import OBSSDKTimeoutError

        recebidos, erro = self._enviar(OBSSDKTimeoutError("timeout"))
        self.assertEqual(recebidos.count("ToggleRecord"), 1)
        self.assertIsInstance(erro, obs.ActionError)

    def test_pedido_recusado_nao_reenvia(self):
        from obsws_python.error import OBSSDKRequestError

        recebidos, erro = self._enviar(OBSSDKRequestError("ToggleRecord", 500, None))
        self.assertEqual(recebidos.count("ToggleRecord"), 1)
        self.assertIsInstance(erro, obs.ActionError)

    def test_conexao_caida_reenvia_uma_vez(self):
        recebidos, erro = self._enviar(ConnectionResetError("caiu"))
        self.assertEqual(recebidos.count("ToggleRecord"), 2)
        self.assertIsNone(erro)

    def test_conexao_fechada_pelo_websocket_reenvia(self):
        from websocket import WebSocketConnectionClosedException

        recebidos, erro = self._enviar(WebSocketConnectionClosedException("fechada"))
        self.assertEqual(recebidos.count("ToggleRecord"), 2)
        self.assertIsNone(erro)

    def test_obs_fechado_normalmente_reenvia(self):
        # OBS fechado e reaberto: o quadro de fechamento faz o recv devolver
        # "" e o obsws_python falha ao ler o JSON da resposta.
        import json

        recebidos, erro = self._enviar(json.JSONDecodeError("vazio", "", 0))
        self.assertEqual(recebidos.count("ToggleRecord"), 2)
        self.assertIsNone(erro)


if __name__ == "__main__":
    unittest.main()

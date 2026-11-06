"""Testes do acesso ao GitHub compartilhado pelo firmware e pelo atualizador."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from polpad.update import github

from .apoio import ClienteFalso, RespostaFalsa


def _rel(tag: str, **extra: object) -> dict:
    return {"tag_name": tag, "draft": False, "prerelease": False, "assets": [], **extra}


class ReleasesPublicadosTest(unittest.TestCase):
    def test_releases_publicados_sem_rascunho_nem_previa(self):
        payload = [
            _rel("v0.5.0"),
            _rel("v0.6.0", draft=True),
            _rel("v0.5.1", prerelease=True),
            _rel("v0.4.1"),
        ]
        releases = github.published_releases(ClienteFalso(RespostaFalsa(payload=payload)))
        self.assertEqual([r["tag_name"] for r in releases], ["v0.5.0", "v0.4.1"])

    def test_tag_ilegivel_vai_para_o_fim(self):
        payload = [_rel("teste"), _rel("v0.5.0")]
        releases = github.published_releases(ClienteFalso(RespostaFalsa(payload=payload)))
        self.assertEqual(releases[0]["tag_name"], "v0.5.0")

    def test_url_de_teste_pela_variavel(self):
        url = "http://localhost:8000/releases.json"
        cliente = ClienteFalso(RespostaFalsa(payload=[]))
        with mock.patch.dict(os.environ, {"POLPAD_RELEASES_URL": url}):
            self.assertEqual(github.releases_url(), url)
            github.published_releases(cliente)
        self.assertEqual(cliente.chamadas, [url])

    def test_resposta_que_nao_e_lista_vira_github_error(self):
        cliente = ClienteFalso(RespostaFalsa(payload={"message": "Not Found"}))
        with self.assertRaises(github.GitHubError):
            github.published_releases(cliente)

    def test_falha_de_rede_vira_github_error(self):
        cliente = ClienteFalso(requests.ConnectionError("sem rota"))
        with self.assertRaises(github.GitHubError):
            github.published_releases(cliente)


class DownloadTest(unittest.TestCase):
    def test_download_interrompido_nao_deixa_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "arquivo.bin"
            cliente = ClienteFalso(RespostaFalsa(conteudo=b"1234"))
            with self.assertRaises(github.GitHubError):
                github.download("https://x/a", destino, expected_size=10, session=cliente)
            self.assertFalse(destino.exists())
            self.assertFalse(destino.with_name("arquivo.bin.part").exists())

    def test_download_completo(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "sub" / "arquivo.bin"
            cliente = ClienteFalso(RespostaFalsa(conteudo=b"1234"))
            progresso: list[int] = []
            github.download(
                "https://x/a", destino, 4, on_progress=progresso.append, session=cliente
            )
            self.assertEqual(destino.read_bytes(), b"1234")
            self.assertEqual(progresso[-1], 100)


class VersaoTest(unittest.TestCase):
    def test_chave_de_versao(self):
        self.assertEqual(github.version_key("0.5.10"), (0, 5, 10))
        self.assertGreater(github.version_key("0.5.10"), github.version_key("0.5.9"))
        self.assertEqual(github.version_key("teste"), ())

    def test_compara(self):
        self.assertTrue(github.is_newer("0.5.1", "0.5.0"))
        self.assertFalse(github.is_newer("0.5.0", "0.5.0"))


if __name__ == "__main__":
    unittest.main()

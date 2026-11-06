"""Testes da lista de versões do aplicativo publicadas no GitHub."""

from __future__ import annotations

import unittest

from polpad.update import github, releases

from .apoio import ClienteFalso, RespostaFalsa

SOMAS_URL = "https://x/v0.5.0/SHA256SUMS.txt"


def _anexo(nome: str, tamanho: int = 10) -> dict:
    return {"name": nome, "size": tamanho, "browser_download_url": f"https://x/{nome}"}


def _release(tag: str, *anexos: dict) -> dict:
    return {
        "tag_name": tag,
        "name": f"Polpad {tag[1:]}",
        "body": "notas",
        "published_at": "2026-11-06T12:00:00Z",
        "html_url": f"https://github.com/gabriel-re-pires/polpad/releases/tag/{tag}",
        "draft": False,
        "prerelease": False,
        "assets": list(anexos),
    }


def _completa(tag: str = "v0.5.0") -> dict:
    somas = {"name": "SHA256SUMS.txt", "size": 1, "browser_download_url": SOMAS_URL}
    return _release(
        tag, _anexo("Polpad-Setup.exe"), _anexo("Polpad-linux-x86_64.tar.gz"), somas
    )


def _listar(payload: list, plataforma: str) -> list[releases.AppRelease]:
    cliente = ClienteFalso(RespostaFalsa(payload=payload))
    return releases.list_releases(cliente, platform=plataforma)


class ListaTest(unittest.TestCase):
    def test_arquivo_certo_por_sistema(self):
        windows = _listar([_completa()], "win32")[0]
        self.assertEqual(windows.asset_name, "Polpad-Setup.exe")
        self.assertEqual(
            _listar([_completa()], "linux")[0].asset_name, "Polpad-linux-x86_64.tar.gz"
        )

    def test_nomes_com_o_sistema(self):
        somas = {"name": "SHA256SUMS.txt", "size": 1, "browser_download_url": SOMAS_URL}
        nova = _release(
            "v0.6.0",
            _anexo("Polpad-Windows-Instalador.exe"),
            _anexo("Polpad-Linux-Instalador.tar.gz"),
            # Cópias com os nomes antigos, para a 0.5.0 se atualizar.
            _anexo("Polpad-Setup.exe"),
            _anexo("Polpad-linux-x86_64.tar.gz"),
            somas,
        )
        windows = _listar([nova], "win32")[0]
        self.assertEqual(windows.asset_name, "Polpad-Windows-Instalador.exe")
        self.assertEqual(windows.asset_url, "https://x/Polpad-Windows-Instalador.exe")
        linux = _listar([nova], "linux")[0]
        self.assertEqual(linux.asset_name, "Polpad-Linux-Instalador.tar.gz")

    def test_nomes_novos_nao_colidem_com_os_antigos(self):
        """O GitHub não distingue maiúsculas nos anexos: um nome novo igual
        a um antigo, a menos da caixa, derruba o envio do release."""
        novos = {releases.WINDOWS_ASSET, releases.LINUX_ASSET}
        antigos = set(releases.LEGACY_ASSETS.values())
        self.assertFalse({n.lower() for n in novos} & {n.lower() for n in antigos})

    def test_041_nao_e_instalavel(self):
        antiga = _release(
            "v0.4.1", _anexo("Polpad.exe"), _anexo("Polpad-linux-x86_64.tar.gz")
        )
        for plataforma in ("win32", "linux"):
            self.assertFalse(_listar([antiga], plataforma)[0].installable)

    def test_instalavel_com_arquivo_e_somas(self):
        release = _listar([_completa()], "win32")[0]
        self.assertTrue(release.installable)
        self.assertEqual(release.version, "0.5.0")
        self.assertEqual(release.sums_url, SOMAS_URL)
        self.assertEqual(release.asset_size, 10)

    def test_mais_nova_primeiro(self):
        lista = _listar([_completa("v0.5.0"), _completa("v0.5.1")], "linux")
        self.assertEqual([r.version for r in lista], ["0.5.1", "0.5.0"])


class SomasTest(unittest.TestCase):
    def test_parse_sums(self):
        texto = "ABC123  Polpad-Setup.exe\ndef456 *Polpad-linux-x86_64.tar.gz\n"
        self.assertEqual(
            releases.parse_sums(texto),
            {"Polpad-Setup.exe": "abc123", "Polpad-linux-x86_64.tar.gz": "def456"},
        )

    def test_soma_do_arquivo(self):
        release = _listar([_completa()], "win32")[0]
        cliente = ClienteFalso(RespostaFalsa(conteudo=b"abc123  Polpad-Setup.exe\n"))
        self.assertEqual(releases.expected_sha256(release, cliente), "abc123")

    def test_soma_ausente_para_o_arquivo(self):
        release = _listar([_completa()], "linux")[0]
        cliente = ClienteFalso(RespostaFalsa(conteudo=b"abc123  Polpad-Setup.exe\n"))
        with self.assertRaises(github.GitHubError):
            releases.expected_sha256(release, cliente)


if __name__ == "__main__":
    unittest.main()

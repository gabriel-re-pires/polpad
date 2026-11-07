"""Testes de regressão de dados, perfis e cópias.

Cada classe descreve, no comentário inicial, o defeito real que a motivou.
"""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from polpad.core import secrets
from polpad.core.store import Store

from .apoio import CofreFalso


class KeyringFalso:
    """Imita o módulo ``keyring``; ``falhas_de_leitura`` leituras dão erro."""

    def __init__(self) -> None:
        self.dados: dict[str, str] = {}
        self.falhas_de_leitura = 0

    def set_password(self, servico: str, nome: str, valor: str) -> None:
        self.dados[nome] = valor

    def get_password(self, servico: str, nome: str) -> str | None:
        if self.falhas_de_leitura:
            self.falhas_de_leitura -= 1
            raise RuntimeError("cofre bloqueado")
        return self.dados.get(nome)

    def delete_password(self, servico: str, nome: str) -> None:
        self.dados.pop(nome, None)


class CofreQueFalhaTest(unittest.TestCase):
    """``secrets.load`` devolvia ``""`` tanto para "não existe" quanto para
    "deu erro". Com o cofre bloqueado por um instante na abertura, o token
    ficava vazio em memória e o ``save()`` seguinte (qualquer troca de
    perfil) o apagava do cofre de vez.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.keyring = KeyringFalso()
        # Nunca toca o cofre real do usuário.
        patcher = mock.patch.object(secrets, "_keyring", lambda: self.keyring)
        patcher.start()
        self.addCleanup(patcher.stop)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def _store(self) -> Store:
        store = Store(data_dir=self.dir, vault=secrets)
        store.load()
        return store

    def test_leitura_com_erro_e_diferente_de_vazio(self):
        self.keyring.falhas_de_leitura = 1
        self.assertIsNone(secrets.load("ha_token"))
        self.assertEqual(secrets.load("ha_token"), "")

    def test_falha_de_leitura_nao_apaga_o_token(self):
        store = self._store()
        store.settings.ha_token = "TOKEN-HA"
        store.save()

        self.keyring.falhas_de_leitura = 1
        reaberto = self._store()
        reaberto.save()  # qualquer troca de perfil grava

        self.assertEqual(self.keyring.dados.get("ha_token"), "TOKEN-HA")
        # Na próxima abertura, com o cofre de volta, o token reaparece.
        self.assertEqual(self._store().settings.ha_token, "TOKEN-HA")

    def test_token_novo_ainda_e_gravado(self):
        store = self._store()
        store.settings.ha_token = "TOKEN-HA"
        store.save()

        self.keyring.falhas_de_leitura = 1
        reaberto = self._store()
        reaberto.settings.ha_token = "TOKEN-NOVO"
        reaberto.save()

        self.assertEqual(self.keyring.dados.get("ha_token"), "TOKEN-NOVO")

    def test_config_ilegivel_nao_apaga_o_token(self):
        store = self._store()
        store.settings.ha_token = "TOKEN-HA"
        store.save()
        (self.dir / "config.json").write_text("{", encoding="utf-8")

        reaberto = self._store()

        self.assertEqual(self.keyring.dados.get("ha_token"), "TOKEN-HA")
        self.assertEqual(reaberto.settings.ha_token, "TOKEN-HA")


CONFIG_SIMPLES = {
    "settings": {},
    "active_profile_id": "p1",
    "profiles": [{"id": "p1", "name": "Meu perfil", "bindings": {}}],
}


class CodificacaoDaConfigTest(unittest.TestCase):
    """Um ``config.json`` salvo pelo Bloco de Notas ganha BOM e era tratado
    como corrompido: os perfis sumiam. Fora de UTF-8 (Latin-1 com "ç") o
    ``UnicodeDecodeError`` escapava e o Polpad nem abria.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def _carregar(self, bruto: bytes) -> Store:
        (self.dir / "config.json").write_bytes(bruto)
        store = Store(data_dir=self.dir, vault=CofreFalso())
        store.load()
        return store

    def test_config_com_bom_mantem_os_perfis(self):
        store = self._carregar(b"\xef\xbb\xbf" + json.dumps(CONFIG_SIMPLES).encode())

        self.assertEqual([p.name for p in store.profiles], ["Meu perfil"])
        self.assertFalse((self.dir / "config.json.bak").exists())

    def test_config_em_latin1_nao_impede_de_abrir(self):
        cfg = {**CONFIG_SIMPLES, "profiles": [{"id": "p1", "name": "Ação"}]}
        bruto = json.dumps(cfg, ensure_ascii=False).encode("latin-1")

        store = self._carregar(bruto)

        self.assertGreaterEqual(len(store.profiles), 1)
        self.assertTrue((self.dir / "config.json.bak").exists())
        self.assertEqual((self.dir / "config.json.bak").read_bytes(), bruto)


if __name__ == "__main__":
    unittest.main()

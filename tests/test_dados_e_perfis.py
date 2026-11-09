"""Regressões de dados, perfis e cópias; cada classe diz o defeito que a motivou."""

from __future__ import annotations

import base64
import json
import logging
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

from polpad.core import profile_io, reset, secrets
from polpad.core.models import Action, Profile
from polpad.core.store import Store
from polpad.update import backup

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
    "deu erro": com o cofre bloqueado na abertura, o ``save()`` seguinte
    apagava o token do cofre.
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


def _documento(perfil: dict[str, Any], **extra: Any) -> str:
    return json.dumps(
        {"format": profile_io.FORMAT, "version": 1, "profile": perfil, **extra}
    )


class ImportarPerfilTest(unittest.TestCase):
    """Perfis de terceiros: nome ``null`` quebrava o display; macro com
    ``command`` e ``webhook`` passavam sem aviso; o sufixo do ícone vinha
    sem filtro (um ``.exe`` ia para a pasta de dados); BOM ou texto fora
    de UTF-8 não viravam arquivo inválido.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def test_nome_invalido_e_recusado(self):
        for nome in (None, 123, ["a"], "", "   "):
            with self.subTest(nome=nome), self.assertRaises(
                profile_io.ProfileFileError
            ):
                profile_io.from_json(_documento({"name": nome}))

    def test_passo_de_macro_que_executa_e_sinalizado(self):
        perfil = Profile(name="X")
        perfil.bindings[0] = Action(
            type="macro",
            params={
                "steps": [
                    {"type": "hotkey", "params": {"keys": ["ctrl", "c"]}},
                    {"type": "command", "params": {"command": "del /q arquivo"}},
                ]
            },
        )
        importado = profile_io.from_json(profile_io.to_json(perfil))

        self.assertEqual(len(importado.sensitive), 1)
        tecla, alvo = importado.sensitive[0]
        self.assertEqual(tecla, 0)
        self.assertIn("del /q arquivo", alvo)

    def test_webhook_e_sinalizado(self):
        perfil = Profile(name="X")
        perfil.bindings[1] = Action(
            type="webhook", params={"url": "http://exemplo.invalid/?k=1"}
        )
        importado = profile_io.from_json(profile_io.to_json(perfil))

        self.assertEqual(importado.sensitive, [(1, "http://exemplo.invalid/?k=1")])

    def test_macro_malformada_nao_quebra_a_verificacao(self):
        perfil = Profile(name="X")
        perfil.bindings[0] = Action(type="macro", params={"steps": "nao e lista"})
        perfil.bindings[1] = Action(type="macro", params={"steps": [42, None]})
        importado = profile_io.from_json(profile_io.to_json(perfil))
        self.assertEqual(importado.sensitive, [])

    def test_sufixo_de_icone_fora_da_lista_nao_e_usado(self):
        dados = base64.b64encode(b"MZ" + bytes(50)).decode()
        documento = _documento({"name": "Y"}, icon={"suffix": ".exe", "data": dados})
        importado = profile_io.from_json(documento)
        self.assertIn(importado.icon_suffix, Store.ICON_SUFFIXES)

        store = Store(data_dir=self.dir, vault=CofreFalso())
        store.load()
        novo = store.add_imported_profile(importado)
        self.assertEqual(list(self.dir.rglob("*.exe")), [])
        if novo.icon_path:
            self.assertIn(Path(novo.icon_path).suffix, Store.ICON_SUFFIXES)

    def test_sufixo_em_maiusculas_e_aceito(self):
        dados = base64.b64encode(b"png").decode()
        documento = _documento({"name": "Y"}, icon={"suffix": ".PNG", "data": dados})
        importado = profile_io.from_json(documento)
        self.assertEqual(importado.icon_bytes, b"png")
        self.assertEqual(importado.icon_suffix, ".png")

    def test_arquivo_com_bom_e_aceito(self):
        bruto = b"\xef\xbb\xbf" + _documento({"name": "Com BOM"}).encode("utf-8")

        self.assertEqual(profile_io.from_json(bruto).profile.name, "Com BOM")
        # Lido como texto UTF-8 comum, o BOM vira o caractere U+FEFF.
        self.assertEqual(
            profile_io.from_json(bruto.decode("utf-8")).profile.name, "Com BOM"
        )

    def test_binario_vira_erro_de_arquivo(self):
        with self.assertRaises(profile_io.ProfileFileError):
            profile_io.from_json(b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x80" * 10)


class RestaurarConfiguracoesTest(unittest.TestCase):
    """"Restaurar configurações" trocava o objeto ``store.settings``, mas o
    contexto das ações guardava o antigo: as teclas do Home Assistant
    seguiam com a URL e o token de antes até reiniciar o Polpad.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def test_acoes_enxergam_as_configuracoes_restauradas(self):
        from PySide6.QtWidgets import QApplication

        import polpad.app as papp

        QApplication.instance() or QApplication([])
        with mock.patch.object(
            papp, "Store", lambda: Store(data_dir=self.dir, vault=CofreFalso())
        ):
            core = papp.MacropadApp()
        self.addCleanup(core.shutdown)
        core.store.settings.ha_url = "http://velho:8123"
        core.store.settings.ha_token = "TOK-VELHO"
        core.store.save()

        reset.reset_settings(core.store, "0.7.2")
        core.store.settings.ha_url = "http://novo:8123"
        core.store.settings.ha_token = "TOK-NOVO"

        contexto = core.runner._context.settings
        self.assertEqual(contexto.ha_url, "http://novo:8123")
        self.assertEqual(contexto.ha_token, "TOK-NOVO")


class CopiaDeAtualizacaoTest(unittest.TestCase):
    """As cópias da Zona de risco e as de atualização dividiam o mesmo
    limite de cinco: seis cliques em "Apagar perfis" levavam embora a
    cópia feita antes de atualizar, a única com os perfis de verdade.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def test_zona_de_risco_nao_apaga_a_copia_da_atualizacao(self):
        store = Store(data_dir=self.dir, vault=CofreFalso())
        store.load()
        store.add_profile("Meu perfil importante")
        agora = datetime(2026, 11, 7, 10, 0)
        atualizacao = backup.create(self.dir, "0.7.1", "0.7.2", agora)

        for i in range(1, 7):
            reset.reset_profiles(store, "0.7.2", agora + timedelta(minutes=i))

        caminhos = [b.path for b in backup.list_backups(self.dir)]
        self.assertIn(atualizacao.path, caminhos)

    def test_so_a_atualizacao_mais_recente_e_poupada(self):
        agora = datetime(2026, 11, 7, 10, 0)
        backup.create(self.dir, "0.7.0", "0.7.1", agora)
        recente = backup.create(self.dir, "0.7.1", "0.7.2", agora + timedelta(1))
        store = Store(data_dir=self.dir, vault=CofreFalso())
        store.load()
        for i in range(1, 7):
            reset.reset_profiles(store, "0.7.2", agora + timedelta(2, minutes=i))

        lista = backup.list_backups(self.dir)
        self.assertEqual([b for b in lista if b.path == recente.path], [lista[-1]])
        self.assertEqual(len(lista), backup.KEEP + 1)

    def test_copias_antigas_sem_tipo(self):
        # Feitas antes do campo "kind": o destino diz o que eram.
        for nome, destino in (("a", "0.7.2"), ("b", "perfis apagados")):
            pasta = backup.backups_dir(self.dir) / nome
            pasta.mkdir(parents=True)
            meta = {"created": "2026-11-07T10:00:00", "from": "0.7.1", "to": destino}
            (pasta / backup.META).write_text(json.dumps(meta), encoding="utf-8")

        tipos = {b.path.name: b.kind for b in backup.list_backups(self.dir)}
        self.assertEqual(tipos, {"a": backup.UPDATE, "b": backup.RISK})


if __name__ == "__main__":
    unittest.main()

"""Testes do estado do atualizador e das decisões puras sobre ele."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from polpad.update import policy, state
from polpad.update.releases import AppRelease

AGORA = datetime(2026, 11, 6, 12, 0, 0)


def _rel(versao: str, instalavel: bool = True) -> AppRelease:
    return AppRelease(
        version=versao,
        tag=f"v{versao}",
        name=f"Polpad {versao}",
        notes="",
        published_at="",
        html_url="",
        asset_name="Polpad-Setup.exe",
        asset_url="https://x/a" if instalavel else None,
        asset_size=1,
        sums_url="https://x/s" if instalavel else None,
    )


class VerificacaoTest(unittest.TestCase):
    def test_verifica_sem_registro_e_apos_24h(self):
        self.assertTrue(policy.should_check(None, AGORA))
        self.assertFalse(policy.should_check(AGORA - timedelta(hours=23), AGORA))
        self.assertTrue(policy.should_check(AGORA - timedelta(hours=25), AGORA))

    def test_relogio_voltou(self):
        self.assertTrue(policy.should_check(AGORA + timedelta(hours=2), AGORA))


class AtualizacaoDisponivelTest(unittest.TestCase):
    def test_atualizacao_disponivel_ignora_nao_instalaveis(self):
        lista = [_rel("0.6.0", instalavel=False), _rel("0.5.1"), _rel("0.4.1", False)]
        self.assertEqual(policy.available_update(lista, "0.5.0").version, "0.5.1")
        self.assertIsNone(policy.available_update(lista, "0.5.1"))

    def test_aviso(self):
        upd = _rel("0.5.1")
        self.assertTrue(policy.should_notify(upd, True, False))
        self.assertFalse(policy.should_notify(upd, False, False))
        self.assertFalse(policy.should_notify(upd, True, True))
        self.assertFalse(policy.should_notify(None, True, False))

    def test_voltar_de_versao(self):
        self.assertTrue(policy.is_downgrade("0.5.0", "0.5.1"))
        self.assertFalse(policy.is_downgrade("0.5.1", "0.5.0"))


class PendenteEMarcaTest(unittest.TestCase):
    def test_pendente(self):
        pend = state.Pending("0.5.1", "x", "abc")
        self.assertEqual(policy.pending_action(pend, "0.5.0", True), "install")
        self.assertEqual(policy.pending_action(pend, "0.5.1", True), "discard")
        self.assertEqual(policy.pending_action(pend, "0.5.0", False), "discard")
        self.assertEqual(policy.pending_action(None, "0.5.0", True), "none")

    def test_marca_de_troca(self):
        marca = state.Switch("0.5.0", "0.5.1", AGORA.isoformat())
        self.assertEqual(policy.switch_outcome(marca, "0.5.1"), "ok")
        self.assertEqual(policy.switch_outcome(marca, "0.5.0"), "failed")
        self.assertEqual(policy.switch_outcome(None, "0.5.0"), "none")


class EstadoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.caminho = state.state_path(Path(self._tmp.name))

    def test_caminho(self):
        self.assertEqual(self.caminho.parent.name, "updates")
        self.assertEqual(self.caminho.name, "estado.json")

    def test_estado_corrompido_vira_vazio(self):
        self.caminho.parent.mkdir(parents=True)
        self.caminho.write_text("não é json", encoding="utf-8")
        self.assertEqual(state.UpdateState.load(self.caminho), state.UpdateState())

    def test_estado_ausente_vira_vazio(self):
        self.assertEqual(state.UpdateState.load(self.caminho), state.UpdateState())

    def test_ida_e_volta(self):
        original = state.UpdateState(
            last_check=AGORA.isoformat(),
            pending=state.Pending("0.5.1", "C:/x/Polpad-Setup.exe", "abc"),
            switch=state.Switch("0.5.0", "0.5.1", AGORA.isoformat()),
        )
        original.save(self.caminho)
        self.assertEqual(state.UpdateState.load(self.caminho), original)


if __name__ == "__main__":
    unittest.main()

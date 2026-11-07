"""Testes do controlador (tecla -> ação, tecla de modo -> troca de perfil)."""

import base64
import tempfile
import unittest
from pathlib import Path

from polpad.core import display, icons
from polpad.core.controller import Controller
from polpad.core.models import Action
from polpad.core.store import Store

from .apoio import CofreFalso


class FakeRunner:
    def __init__(self):
        self.submitted = []

    def submit(self, action):
        self.submitted.append(action)


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        self.store.load()
        self.store.settings.mode_key = 17

        profile_a = self.store.profiles[0]
        profile_a.name = "A"
        profile_a.bindings[0] = Action(type="text", params={"text": "olá"}, label="Oi")
        self.profile_b = self.store.add_profile("B")

        self.runner = FakeRunner()
        self.sent = []
        self.changed = []
        self.scheduled = []
        self.controller = Controller(
            store=self.store,
            runner=self.runner,
            send=self.sent.append,
            on_profile_changed=self.changed.append,
            schedule=lambda seconds, fn: self.scheduled.append((seconds, fn)),
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _press(self, key):
        self.controller.handle_message({"t": "key", "k": key, "e": "down"})

    def _last_frame(self):
        """Quadro 1 bpp da última mensagem ``img`` enviada ao dispositivo."""
        message = self.sent[-1]
        self.assertEqual(message["t"], "img")
        return icons.unpack_bits(base64.b64decode(message["d"]))

    def _expected(self, name):
        profile = next(p for p in self.store.profiles if p.name == name)
        return display.profile_frame(profile)

    def test_key_down_dispatches_bound_action(self):
        self._press(0)
        self.assertEqual(len(self.runner.submitted), 1)
        self.assertEqual(self.runner.submitted[0].params["text"], "olá")

    def test_captura_recebe_a_tecla_e_nao_executa_a_acao(self):
        capturadas = []
        self.controller.key_capture = capturadas.append
        self._press(0)
        self.assertEqual(capturadas, [0])
        self.assertEqual(self.runner.submitted, [])
        # A captura vale para uma tecla só: a seguinte volta a executar.
        self.assertIsNone(self.controller.key_capture)
        self._press(0)
        self.assertEqual(capturadas, [0])
        self.assertEqual(len(self.runner.submitted), 1)

    def test_captura_da_tecla_de_modo_nao_troca_o_perfil(self):
        capturadas = []
        self.controller.key_capture = capturadas.append
        self._press(17)
        self.assertEqual(capturadas, [17])
        self.assertEqual(self.store.active_profile.name, "A")

    def test_key_up_and_unbound_keys_are_ignored(self):
        self.controller.handle_message({"t": "key", "k": 0, "e": "up"})
        self._press(3)  # sem ação
        self.assertEqual(self.runner.submitted, [])

    def test_mode_key_switches_profile_and_updates_display(self):
        self.assertEqual(self.store.active_profile.name, "A")
        self._press(17)
        self.assertEqual(self.store.active_profile.name, "B")
        self.assertEqual(self.changed[-1].name, "B")
        # O display recebe a tela do novo perfil.
        self.assertEqual(self._last_frame().tobytes(), self._expected("B").tobytes())
        # A tecla de modo nunca dispara ações.
        self.assertEqual(self.runner.submitted, [])

    def test_hello_pushes_current_display(self):
        self.controller.handle_message({"t": "hello", "keys": 18})
        self.assertEqual(self._last_frame().tobytes(), self._expected("A").tobytes())

    def test_hello_forces_resend_even_if_unchanged(self):
        # O dispositivo pode ter reiniciado: após "hello" o quadro vai de novo.
        self.controller.handle_message({"t": "hello"})
        self.controller.handle_message({"t": "hello"})
        self.assertEqual(len(self.sent), 2)

    def test_identical_frame_is_not_resent(self):
        self.controller.push_display()
        self.controller.push_display()
        self.assertEqual(len(self.sent), 1)

    def test_activate_profile_from_ui(self):
        self.controller.activate_profile(self.profile_b.id)
        self.assertEqual(self.store.active_profile_id, self.profile_b.id)
        self.assertEqual(self._last_frame().tobytes(), self._expected("B").tobytes())

    def test_key_press_does_not_touch_the_display(self):
        # O mapa de teclas saiu do display: tecla comum não gera quadro.
        self._press(0)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.scheduled, [])

    def test_icon_mode_without_icon_shows_profile_name(self):
        self.store.active_profile.display.mode = "icone"
        self.controller.push_display()
        from polpad.core import oled_render

        expected = oled_render.render_text_lines(["A"])
        self.assertEqual(self._last_frame().tobytes(), expected.tobytes())


class RelogioTest(unittest.TestCase):
    """Tela personalizada: a hora vem do relógio injetado."""

    def setUp(self):
        from datetime import datetime

        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        self.store.load()
        self.store.active_profile.display.mode = "personalizado"
        self.agora = datetime(2026, 11, 3, 14, 5, 0)
        self.sent = []
        self.controller = Controller(
            store=self.store,
            runner=FakeRunner(),
            send=self.sent.append,
            clock=lambda: self.agora,
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_tick_so_reenvia_quando_o_minuto_muda(self):
        from datetime import timedelta

        self.controller.tick()
        self.controller.tick()
        self.assertEqual(len(self.sent), 1)
        self.agora += timedelta(seconds=30)
        self.controller.tick()
        self.assertEqual(len(self.sent), 1)
        self.agora += timedelta(seconds=30)
        self.controller.tick()
        self.assertEqual(len(self.sent), 2)

    def test_tick_nao_faz_nada_no_modo_icone(self):
        self.store.active_profile.display.mode = "icone"
        self.controller.tick()
        self.assertEqual(self.sent, [])


class TrocaDePerfilEmCicloTest(unittest.TestCase):
    """"Alternar perfil" numa tecla de um perfil só criava um beco sem saída:
    no perfil seguinte a tecla não tinha ação e não dava para voltar."""

    def _store_com_acao_em_um_perfil(self, tecla=2):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Store(data_dir=Path(tmp.name), vault=CofreFalso())
        store.load()
        store.profiles[0].name = "Teste"
        store.profiles[0].bindings[tecla] = Action("mode_switch", {}, "Troca Perfil")
        store.add_profile("Teste2")
        store.save()
        # Recarrega como o aplicativo faz ao abrir.
        novo = Store(data_dir=Path(tmp.name), vault=CofreFalso())
        novo.load()
        return novo

    def test_configuracao_antiga_vira_tecla_de_modo(self):
        store = self._store_com_acao_em_um_perfil()
        self.assertEqual(store.settings.mode_key, 2)
        self.assertNotIn(2, store.profiles[0].bindings)

    def test_tecla_da_a_volta_na_lista(self):
        store = self._store_com_acao_em_um_perfil()
        controller = Controller(store=store, runner=FakeRunner(), send=lambda m: None)
        nomes = []
        for _ in range(3):
            controller.handle_message({"t": "key", "k": 2, "e": "down"})
            nomes.append(store.active_profile.name)
        self.assertEqual(nomes, ["Teste2", "Teste", "Teste2"])

    def test_teclas_diferentes_nao_sao_migradas(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Store(data_dir=Path(tmp.name), vault=CofreFalso())
        store.load()
        store.profiles[0].bindings[1] = Action("mode_switch", {})
        store.add_profile("B").bindings[4] = Action("mode_switch", {})
        store.save()
        novo = Store(data_dir=Path(tmp.name), vault=CofreFalso())
        novo.load()
        self.assertIsNone(novo.settings.mode_key)


if __name__ == "__main__":
    unittest.main()

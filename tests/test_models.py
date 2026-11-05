"""Testes de serialização dos modelos e da persistência."""

import tempfile
import unittest
from pathlib import Path

from polpad.core.models import Action, Profile, Settings
from polpad.core.store import Store

from .apoio import CofreFalso


class ModelsTest(unittest.TestCase):
    def test_action_roundtrip(self):
        action = Action(type="hotkey", params={"keys": ["ctrl", "c"]}, label="Copiar")
        self.assertEqual(Action.from_dict(action.to_dict()), action)

    def test_profile_roundtrip_preserves_int_keys(self):
        profile = Profile(name="VS Code")
        profile.bindings[5] = Action(type="text", params={"text": "npm run dev"})
        restored = Profile.from_dict(profile.to_dict())
        self.assertIn(5, restored.bindings)
        self.assertEqual(restored.bindings[5].params["text"], "npm run dev")

    def test_settings_roundtrip(self):
        settings = Settings(mode_key=17, ha_url="http://ha:8123", ha_token="x")
        self.assertEqual(Settings.from_dict(settings.to_dict()), settings)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        self.store.load()

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_default_profile(self):
        self.assertGreaterEqual(len(self.store.profiles), 1)
        self.assertIsNotNone(self.store.active_profile)

    def test_save_and_reload(self):
        profile = self.store.add_profile("Streaming")
        profile.bindings[0] = Action(type="media", params={"control": "volume_up"})
        self.store.save()

        reloaded = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        reloaded.load()
        names = [p.name for p in reloaded.profiles]
        self.assertIn("Streaming", names)
        restored = next(p for p in reloaded.profiles if p.name == "Streaming")
        self.assertEqual(restored.bindings[0].params["control"], "volume_up")

    def test_next_profile_cycles_in_order(self):
        self.store.add_profile("B")
        self.store.add_profile("C")
        first = self.store.profiles[0]
        self.store.active_profile_id = first.id
        seen = [self.store.next_profile().name for _ in range(len(self.store.profiles))]
        self.assertEqual(seen[-1], first.name)  # deu a volta completa

    def test_corrupted_config_recovers(self):
        config = Path(self._tmp.name) / "config.json"
        config.write_text("{quebrado", encoding="utf-8")
        store = Store(data_dir=Path(self._tmp.name), vault=CofreFalso())
        store.load()  # não deve lançar exceção
        self.assertGreaterEqual(len(store.profiles), 1)


if __name__ == "__main__":
    unittest.main()

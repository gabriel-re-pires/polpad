"""Testes das funcionalidades adicionais (troca automática, webhooks, novos modelos)."""

import unittest

import polpad.actions.builtin  # noqa: F401  (registra os tipos de ação)
from polpad.actions.base import ActionContext, ActionError, get
from polpad.core.models import Profile, Settings
from polpad.integrations.foreground import match_profile


class AutoSwitchTest(unittest.TestCase):
    def test_match_profile_by_exe(self):
        vscode = Profile(name="VS Code", auto_apps=["code.exe"])
        obs = Profile(name="Streaming", auto_apps=["obs64.exe", "obs32.exe"])
        profiles = [vscode, obs]
        self.assertIs(match_profile(profiles, "code.exe"), vscode)
        self.assertIs(match_profile(profiles, "OBS64.EXE"), obs)
        self.assertIsNone(match_profile(profiles, "notepad.exe"))
        self.assertIsNone(match_profile(profiles, None))

    def test_auto_apps_survive_serialization(self):
        profile = Profile(name="X", auto_apps=["Code.EXE"])
        restored = Profile.from_dict(profile.to_dict())
        # Nomes são normalizados para minúsculo ao carregar.
        self.assertEqual(restored.auto_apps, ["code.exe"])

    def test_settings_new_fields_roundtrip(self):
        settings = Settings(
            auto_switch_enabled=True,
            start_with_windows=True,
            obs_host="10.0.0.5",
            obs_port=4456,
            obs_password="s3nha",
        )
        restored = Settings.from_dict(settings.to_dict())
        self.assertEqual(restored, settings)

    def test_old_config_without_new_fields_loads(self):
        settings = Settings.from_dict({"mode_key": 3, "ha_url": "http://x"})
        self.assertFalse(settings.auto_switch_enabled)
        self.assertEqual(settings.obs_port, 4455)


class NewActionsTest(unittest.TestCase):
    def test_new_action_types_are_registered(self):
        for name in ("webhook", "obs", "home_assistant"):
            self.assertIsNotNone(get(name), name)

    def test_webhook_requires_valid_url(self):
        handler = get("webhook").handler
        with self.assertRaises(ActionError):
            handler({"url": ""}, ActionContext())
        with self.assertRaises(ActionError):
            handler({"url": "ftp://x"}, ActionContext())

    def test_obs_requires_settings(self):
        handler = get("obs").handler
        with self.assertRaises(ActionError):
            handler({"operation": "toggle_record"}, ActionContext(settings=None))


class TextNormalizationTest(unittest.TestCase):
    def test_msg_text_strips_accents_for_firmware_font(self):
        from polpad.device import protocol

        message = protocol.msg_text(["Edição", "Vídeo & Áudio"])
        self.assertEqual(message["lines"], ["Edicao", "Video & Audio"])


if __name__ == "__main__":
    unittest.main()

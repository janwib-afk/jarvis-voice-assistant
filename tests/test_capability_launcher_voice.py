"""Slice 7 — Launcher-Sprachsteuerung (Amendment 2 §A2.2).

`APP_OPEN`, `PROFILE_ACTIVATE`, `APP_AUTOSTART_ON`, `APP_AUTOSTART_OFF`, `APP_PLACE`.

Zwei Besonderheiten:

* `APP_AUTOSTART_ON` und `APP_AUTOSTART_OFF` teilen **denselben** semantischen Vertrag
  `launcher.app.autostart.set` und unterscheiden sich nur im booleschen Eingabewert.
  Es werden ausdruecklich **nicht** 22 verschiedene Capability-Namen erzwungen.
* Mutationen laufen ausschliesslich ueber den **semantischen** Launcher-Port
  (`configuration`-Intent), nie ueber einen vorberechneten Voll-Block (RFC-0003).

Kontrollierte Grenzen: ``app_launcher`` (Prozessstart) und der Mutationsport.
"""
import asyncio
import unittest
from unittest import mock

import tests  # noqa: F401

import actions
import app_launcher
import capability as cap
import configuration


class _Action:
    def __init__(self, type_, payload=""):
        self.type = type_
        self.payload = payload


def _coord():
    return cap.Coordinator(cap.build_registry(cap.CapabilityDeps()),
                           cap.ACTIVE_RULES, audit=lambda *a, **k: None)


class _RecordingLauncher:
    """Faengt die semantische Absicht ab — kein Voll-Block, keine Datei."""

    def __init__(self, errors=()):
        self.intents = []
        self._errors = list(errors)

    async def __call__(self, intent, kind):
        self.intents.append((intent, kind))
        return list(self._errors)


def _run(action, mutate=None):
    return asyncio.run(cap.run_migrated(
        _coord(), action, actions.ActionContext(mutate_launcher=mutate)))


class LauncherFixture(unittest.TestCase):
    def setUp(self):
        self._saved = (app_launcher.APPS, app_launcher.PROFILES,
                       app_launcher.ACTIVE_PROFILE)
        app_launcher.APPS = [
            {"id": "obsidian", "name": "Obsidian", "type": "exe",
             "path": "C:/x/o.exe"},
        ]
        app_launcher.PROFILES = [
            {"id": "default", "name": "Standard", "apps": {}},
            {"id": "writing", "name": "Schreiben", "apps": {}},
        ]
        app_launcher.ACTIVE_PROFILE = "default"

    def tearDown(self):
        (app_launcher.APPS, app_launcher.PROFILES,
         app_launcher.ACTIVE_PROFILE) = self._saved


class CanonicalMappingTests(LauncherFixture):
    def test_launcher_voice_actions_are_mapped(self):
        self.assertEqual("launcher.app.open", cap.MIGRATED_ACTIONS["APP_OPEN"])
        self.assertEqual("launcher.profile.activate",
                         cap.MIGRATED_ACTIONS["PROFILE_ACTIVATE"])
        self.assertEqual("launcher.app.placement.set",
                         cap.MIGRATED_ACTIONS["APP_PLACE"])

    def test_both_autostart_actions_share_one_contract(self):
        """§A2.2: derselbe semantische Vertrag, nur ein anderer Eingabewert."""
        self.assertEqual("launcher.app.autostart.set",
                         cap.MIGRATED_ACTIONS["APP_AUTOSTART_ON"])
        self.assertEqual("launcher.app.autostart.set",
                         cap.MIGRATED_ACTIONS["APP_AUTOSTART_OFF"])

    def test_the_shared_contract_takes_a_boolean(self):
        contract = cap.build_registry(cap.CapabilityDeps()).get(
            "launcher.app.autostart.set")
        self.assertIn("enabled", contract.inputs.names)


class ByteIdenticalLauncherTests(LauncherFixture):
    def test_app_open_is_byte_identical(self):
        with mock.patch("app_launcher.launch",
                        lambda q: {"ok": True, "message": "Obsidian ist offen."}):
            legacy = asyncio.run(actions.spec_for("APP_OPEN").execute(
                "obsidian", actions.ActionContext()))
            migrated = _run(_Action("APP_OPEN", "obsidian"))
        self.assertEqual(legacy, migrated.text)

    def test_profile_activate_is_byte_identical(self):
        mutate = _RecordingLauncher()
        legacy_mutate = _RecordingLauncher()
        legacy = asyncio.run(actions.spec_for("PROFILE_ACTIVATE").execute(
            "Schreiben", actions.ActionContext(mutate_launcher=legacy_mutate)))
        migrated = _run(_Action("PROFILE_ACTIVATE", "Schreiben"), mutate)
        self.assertEqual(legacy, migrated.text)
        self.assertEqual("Schreiben ist jetzt aktiv.", migrated.text)

    def test_unknown_profile_wording_is_preserved(self):
        migrated = _run(_Action("PROFILE_ACTIVATE", "gibtsnicht"),
                        _RecordingLauncher())
        self.assertIn("kenne ich nicht", migrated.text)

    def test_autostart_on_and_off_produce_the_existing_wordings(self):
        on = _run(_Action("APP_AUTOSTART_ON", "obsidian"), _RecordingLauncher())
        off = _run(_Action("APP_AUTOSTART_OFF", "obsidian"), _RecordingLauncher())
        self.assertEqual("Obsidian startet beim nächsten Clap mit.", on.text)
        self.assertEqual("Obsidian ist aus dem Clap-Start raus.", off.text)

    def test_app_place_is_byte_identical(self):
        payload = "Obsidian | left | right_half"
        mutate = _RecordingLauncher()
        legacy = asyncio.run(actions.spec_for("APP_PLACE").execute(
            payload, actions.ActionContext(mutate_launcher=_RecordingLauncher())))
        migrated = _run(_Action("APP_PLACE", payload), mutate)
        self.assertEqual(legacy, migrated.text)


class SemanticMutationOnlyTests(LauncherFixture):
    """RFC-0003: eine Aenderungsabsicht, kein vorberechneter Voll-Block."""

    def test_autostart_passes_a_semantic_intent(self):
        mutate = _RecordingLauncher()
        _run(_Action("APP_AUTOSTART_ON", "obsidian"), mutate)
        self.assertEqual(1, len(mutate.intents))
        intent, kind = mutate.intents[0]
        self.assertIsInstance(intent, configuration.SetAutostart)
        self.assertEqual("autostart", kind)
        self.assertTrue(intent.enabled)

    def test_autostart_off_flips_only_the_boolean(self):
        mutate = _RecordingLauncher()
        _run(_Action("APP_AUTOSTART_OFF", "obsidian"), mutate)
        intent, _ = mutate.intents[0]
        self.assertIsInstance(intent, configuration.SetAutostart)
        self.assertFalse(intent.enabled)

    def test_profile_activate_passes_a_semantic_intent(self):
        mutate = _RecordingLauncher()
        _run(_Action("PROFILE_ACTIVATE", "Schreiben"), mutate)
        intent, kind = mutate.intents[0]
        self.assertIsInstance(intent, configuration.ActivateProfile)
        self.assertEqual("profile", kind)

    def test_placement_passes_a_semantic_intent(self):
        mutate = _RecordingLauncher()
        _run(_Action("APP_PLACE", "Obsidian | left | right_half"), mutate)
        intent, kind = mutate.intents[0]
        self.assertIsInstance(intent, configuration.SetPlacement)
        self.assertEqual("placement", kind)

    def test_persist_errors_surface_as_the_existing_wording(self):
        mutate = _RecordingLauncher(errors=["Platte voll"])
        result = _run(_Action("APP_AUTOSTART_ON", "obsidian"), mutate)
        self.assertIn("konnte ich nicht speichern", result.text)

    def test_missing_port_yields_the_existing_wording(self):
        result = _run(_Action("APP_AUTOSTART_ON", "obsidian"), None)
        self.assertIn("gerade nicht möglich", result.text)


class LauncherEffectCensusTests(LauncherFixture):
    def _view(self, name):
        return cap.build_registry(cap.CapabilityDeps()).inspect(name)

    def test_app_open_declares_local_execute(self):
        view = self._view("launcher.app.open")
        self.assertIn(cap.EffectClass.LOCAL_EXECUTE, view.effects)
        self.assertIn(cap.Scope.APPS, view.scopes)

    def test_mutating_launcher_paths_declare_local_write(self):
        for name in ("launcher.profile.activate", "launcher.app.autostart.set",
                     "launcher.app.placement.set"):
            with self.subTest(name=name):
                view = self._view(name)
                self.assertIn(cap.EffectClass.LOCAL_WRITE, view.effects)
                self.assertIn(cap.DataClass.LOCAL, view.writes)
                self.assertIn(cap.Scope.CONFIG_LAUNCHER, view.scopes)

    def test_all_launcher_voice_paths_declare_the_tts_network_effect(self):
        """Alle fuenf haben ``speaks_result=True`` — das Ergebnis geht als TTS hinaus."""
        for name in ("launcher.app.open", "launcher.profile.activate",
                     "launcher.app.autostart.set", "launcher.app.placement.set"):
            with self.subTest(name=name):
                self.assertIn(cap.EffectClass.NETWORK_READ, self._view(name).effects)

    def test_timeouts_match_the_action_specs(self):
        registry = cap.build_registry(cap.CapabilityDeps())
        for action_type in ("APP_OPEN", "PROFILE_ACTIVATE", "APP_AUTOSTART_ON",
                            "APP_AUTOSTART_OFF", "APP_PLACE"):
            with self.subTest(action_type=action_type):
                name = cap.MIGRATED_ACTIONS[action_type]
                self.assertEqual(actions.spec_for(action_type).timeout,
                                 registry.get(name).timeout_s)


if __name__ == "__main__":
    unittest.main()

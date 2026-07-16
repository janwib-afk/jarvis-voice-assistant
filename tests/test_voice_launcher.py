"""
Tests fuer die Launcher-Sprachaktionen (Phase 5): PROFILE_ACTIVATE,
PROFILE_STATUS, APP_AUTOSTART_ON/OFF, APP_PLACE.

Seit RFC-0001 ueber die oeffentliche Action-Seam (spec.execute); die Persistenz
laeuft ueber ``ctx.persist_launcher`` — hier gestubbt (sammelt Aufrufe, schreibt
nichts). Der echte Persist-Pfad wird in tests/test_launcher_api.py integrativ
getestet.

    python -m unittest discover -s tests
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

import actions
import app_launcher

try:
    import server  # verdrahtet assistant_core (configure/init_clients/PERSIST_LAUNCHER)
    import assistant_core
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    assistant_core = None
    _IMPORT_ERROR = e

_APPS = [
    {"id": "obsidian", "name": "Obsidian", "command": "obsidian://open", "type": "url"},
    {"id": "vscode", "name": "VS Code", "command": "code", "type": "process"},
]
_LAUNCHER = {"active_profile": "coding", "profiles": [
    {"id": "coding", "name": "Coding", "apps": {"vscode": {"autostart": True}}},
    {"id": "deep-work", "name": "Deep Work", "apps": {}},
]}


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class VoiceLauncherTests(unittest.TestCase):
    def setUp(self):
        self._saved = (app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE)
        app_launcher.configure(_APPS, _LAUNCHER)

        self.persist_calls = []

        async def _stub(new_launcher, kind):
            self.persist_calls.append((new_launcher, kind))
            return []

        self.ctx = actions.ActionContext(persist_launcher=_stub)

    def tearDown(self):
        app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE = self._saved

    def _run(self, action_type, payload=""):
        return asyncio.run(actions.spec_for(action_type).execute(payload, self.ctx))

    @staticmethod
    def _profile(launcher, pid):
        return next(p for p in launcher["profiles"] if p["id"] == pid)

    # ── PROFILE_ACTIVATE ─────────────────────────────────────────────────────
    def test_activate_by_name(self):
        result = self._run("PROFILE_ACTIVATE", "Deep Work")
        self.assertEqual(result, "Deep Work ist jetzt aktiv.")
        launcher, kind = self.persist_calls[0]
        self.assertEqual(kind, "profile")
        self.assertEqual(launcher["active_profile"], "deep-work")

    def test_activate_by_id_case_insensitive(self):
        result = self._run("PROFILE_ACTIVATE", "DEEP-WORK")
        self.assertEqual(result, "Deep Work ist jetzt aktiv.")

    def test_activate_unknown_profile_no_persist(self):
        result = self._run("PROFILE_ACTIVATE", "Gaming")
        self.assertIn("kenne ich nicht", result)
        self.assertIn("Coding", result)  # nennt Verfuegbares statt zu raten
        self.assertEqual(self.persist_calls, [])

    def test_activate_already_active_no_persist(self):
        result = self._run("PROFILE_ACTIVATE", "Coding")
        self.assertEqual(result, "Coding ist bereits aktiv.")
        self.assertEqual(self.persist_calls, [])

    # ── PROFILE_STATUS ───────────────────────────────────────────────────────
    def test_status_active_profile(self):
        result = self._run("PROFILE_STATUS")
        self.assertIn("Aktiv ist 'Coding'", result)
        # vscode explizit an, obsidian nicht gelistet -> Default an.
        self.assertIn("Obsidian", result)
        self.assertIn("VS Code", result)

    def test_status_named_profile(self):
        result = self._run("PROFILE_STATUS", "Deep Work")
        self.assertIn("Im Profil 'Deep Work'", result)
        self.assertEqual(self.persist_calls, [])  # Status persistiert nie

    def test_status_unknown_profile(self):
        result = self._run("PROFILE_STATUS", "Gaming")
        self.assertIn("kenne ich nicht", result)

    def test_status_nothing_enabled(self):
        app_launcher.configure(_APPS, {"active_profile": "leer", "profiles": [
            {"id": "leer", "name": "Leer", "apps": {
                "obsidian": {"autostart": False}, "vscode": {"autostart": False}}},
        ]})
        result = self._run("PROFILE_STATUS")
        self.assertIn("startet nichts automatisch", result)

    # ── APP_AUTOSTART_ON / OFF ───────────────────────────────────────────────
    def test_autostart_off(self):
        result = self._run("APP_AUTOSTART_OFF", "vs code")
        self.assertEqual(result, "VS Code ist aus dem Clap-Start raus.")
        launcher, kind = self.persist_calls[0]
        self.assertEqual(kind, "autostart")
        self.assertFalse(self._profile(launcher, "coding")["apps"]["vscode"]["autostart"])
        # Anderes Profil unberuehrt.
        self.assertNotIn("vscode", self._profile(launcher, "deep-work")["apps"])

    def test_autostart_on(self):
        result = self._run("APP_AUTOSTART_ON", "Obsidian")
        self.assertEqual(result, "Obsidian startet beim nächsten Clap mit.")
        launcher, _ = self.persist_calls[0]
        self.assertTrue(self._profile(launcher, "coding")["apps"]["obsidian"]["autostart"])

    def test_autostart_unknown_app_no_persist(self):
        result = self._run("APP_AUTOSTART_ON", "Photoshop")
        self.assertIn("nicht konfiguriert", result)
        self.assertIn("Verfügbar", result)
        self.assertEqual(self.persist_calls, [])

    # ── APP_PLACE ────────────────────────────────────────────────────────────
    def test_place_canonical(self):
        result = self._run("APP_PLACE", "VS Code | left | left_half")
        self.assertEqual(result, "VS Code liegt jetzt in der linken Hälfte auf dem linken Monitor.")
        launcher, kind = self.persist_calls[0]
        self.assertEqual(kind, "placement")
        self.assertEqual(
            self._profile(launcher, "coding")["apps"]["vscode"]["placement"],
            {"monitor": "left", "zone": "left_half"},
        )

    def test_place_german_aliases(self):
        result = self._run("APP_PLACE", "Obsidian | links | rechte Hälfte")
        self.assertEqual(result, "Obsidian liegt jetzt in der rechten Hälfte auf dem linken Monitor.")

    def test_place_parse_error_no_persist(self):
        result = self._run("APP_PLACE", "Obsidian | left")
        self.assertIn("app | monitor | zone", result)
        self.assertEqual(self.persist_calls, [])
        result = self._run("APP_PLACE", "Obsidian | left | diagonal")
        self.assertIn("Zone kenne ich nicht", result)

    def test_place_unknown_app_no_persist(self):
        result = self._run("APP_PLACE", "Photoshop | left | center")
        self.assertIn("nicht konfiguriert", result)
        self.assertEqual(self.persist_calls, [])

    # ── Persist-Fehlerpfade ──────────────────────────────────────────────────
    def test_persist_error_is_spoken(self):
        async def _failing(new_launcher, kind):
            return ["Datei gesperrt."]
        self.ctx = actions.ActionContext(persist_launcher=_failing)
        result = self._run("APP_AUTOSTART_OFF", "VS Code")
        self.assertTrue(result.startswith("Das konnte ich nicht speichern"))

    def test_persist_missing_is_graceful(self):
        # Kein Hook im Kontext (Standalone/Tests ohne Server).
        self.ctx = actions.ActionContext()
        result = self._run("PROFILE_ACTIVATE", "Deep Work")
        self.assertEqual(result, "Profil-Änderungen sind gerade nicht möglich.")


class FindProfileTests(unittest.TestCase):
    def setUp(self):
        self._saved = (app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE)
        app_launcher.configure(_APPS, _LAUNCHER)

    def tearDown(self):
        app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE = self._saved

    def test_find_by_id_and_name(self):
        self.assertEqual(app_launcher.find_profile("coding")["id"], "coding")
        self.assertEqual(app_launcher.find_profile("deep work")["id"], "deep-work")
        self.assertEqual(app_launcher.find_profile("  DEEP WORK  ")["id"], "deep-work")

    def test_slugged_input_matches_id(self):
        self.assertEqual(app_launcher.find_profile("Deep Work!")["id"], "deep-work")

    def test_unknown_returns_none(self):
        self.assertIsNone(app_launcher.find_profile("Gaming"))
        self.assertIsNone(app_launcher.find_profile(""))
        self.assertIsNone(app_launcher.find_profile(None))


if __name__ == "__main__":
    unittest.main()

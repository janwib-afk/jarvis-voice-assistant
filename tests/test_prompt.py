"""
Tests fuer build_system_prompt(): Persona kommt aus der Config, nicht aus
hartcodierten Literalen (Regression fuer den frueheren "Jan"/"Sir"-Hardcode).

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

try:
    import server  # verdrahtet assistant_core (configure/init_clients)
    import app_launcher
    import assistant_core
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    app_launcher = None
    assistant_core = None
    _IMPORT_ERROR = e


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class SystemPromptTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            name: getattr(assistant_core, name)
            for name in ("USER_NAME", "USER_ADDRESS", "USER_ROLE")
        }

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(assistant_core, name, value)

    def test_persona_uses_config_values(self):
        assistant_core.USER_NAME = "Unit-Tester"
        assistant_core.USER_ADDRESS = "Mylady"
        assistant_core.USER_ROLE = "Qualitätssicherung"
        prompt = assistant_core.build_system_prompt()
        self.assertIn("der persönliche KI-Assistent von Unit-Tester, Qualitätssicherung.", prompt)
        self.assertIn('mit "Mylady" angesprochen', prompt)
        self.assertIn('WENN Unit-Tester "Jarvis activate" sagt', prompt)

    def test_no_hardcoded_persona_remains(self):
        assistant_core.USER_NAME = "Unit-Tester"
        assistant_core.USER_ADDRESS = "Mylady"
        assistant_core.USER_ROLE = ""
        prompt = assistant_core.build_system_prompt()
        self.assertNotIn("Dienstherr ist Jan", prompt)
        self.assertNotIn('"Sir"', prompt)
        self.assertNotIn("Softwareentwickler", prompt)

    def test_empty_role_renders_cleanly(self):
        assistant_core.USER_NAME = "Unit-Tester"
        assistant_core.USER_ROLE = ""
        prompt = assistant_core.build_system_prompt()
        self.assertIn("der persönliche KI-Assistent von Unit-Tester.", prompt)

    def test_app_open_listed_when_apps_configured(self):
        saved_apps = app_launcher.APPS
        self.addCleanup(lambda: setattr(app_launcher, "APPS", saved_apps))
        app_launcher.configure([{"name": "Obsidian", "command": "obsidian://open"}])
        prompt = assistant_core.build_system_prompt()
        self.assertIn("[ACTION:APP_OPEN]", prompt)
        self.assertIn("Verfügbare Apps: Obsidian", prompt)

    def test_app_open_absent_without_apps(self):
        saved_apps = app_launcher.APPS
        self.addCleanup(lambda: setattr(app_launcher, "APPS", saved_apps))
        app_launcher.configure([])
        prompt = assistant_core.build_system_prompt()
        self.assertNotIn("[ACTION:APP_OPEN]", prompt)

    def _save_launcher_state(self):
        saved = (app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE)
        self.addCleanup(lambda: (
            setattr(app_launcher, "APPS", saved[0]),
            setattr(app_launcher, "PROFILES", saved[1]),
            setattr(app_launcher, "ACTIVE_PROFILE", saved[2]),
        ))

    def test_launcher_actions_listed_with_profiles(self):
        self._save_launcher_state()
        app_launcher.configure(
            [{"name": "Obsidian", "command": "obsidian://open"}],
            {"active_profile": "coding", "profiles": [
                {"id": "coding", "name": "Coding", "apps": {}},
                {"id": "writing", "name": "Writing", "apps": {}},
            ]},
        )
        prompt = assistant_core.build_system_prompt()
        for tag in ("[ACTION:PROFILE_ACTIVATE]", "[ACTION:PROFILE_STATUS]",
                    "[ACTION:APP_AUTOSTART_ON]", "[ACTION:APP_AUTOSTART_OFF]",
                    "[ACTION:APP_PLACE]"):
            self.assertIn(tag, prompt)
        self.assertIn("Verfügbare Profile: Coding, Writing", prompt)
        self.assertIn("[ACTION:APP_PLACE] Obsidian | left | right_half", prompt)
        self.assertIn("frag nach statt zu raten", prompt)

    def test_launcher_actions_absent_without_apps(self):
        self._save_launcher_state()
        app_launcher.configure([])
        prompt = assistant_core.build_system_prompt()
        self.assertNotIn("[ACTION:PROFILE_ACTIVATE]", prompt)
        self.assertNotIn("[ACTION:APP_PLACE]", prompt)


if __name__ == "__main__":
    unittest.main()

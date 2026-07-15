"""
Tests fuer die Settings-API (GET/POST /settings) gegen die echte App.

WICHTIG: ``server.CONFIG_PATH`` wird auf eine Temp-Kopie gepatcht und
``assistant_core.refresh_data`` auf einen No-Op — die Tests duerfen NIEMALS
die echte config.json beschreiben oder Netzaufrufe (wttr.in) ausloesen.

    python -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

try:
    import server
    import app_launcher
    import assistant_core
    import config_loader
    import memory
    from fastapi.testclient import TestClient
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    app_launcher = None
    assistant_core = None
    TestClient = None
    _IMPORT_ERROR = e

_TEST_CONFIG = {
    "anthropic_api_key": "sk-ant-test-secret-111",
    "elevenlabs_api_key": "el-test-secret-222",
    "elevenlabs_voice_id": "voice-alt",
    "user_name": "TestUser",
    "user_address": "Sir",
    "user_role": "Tester",
    "city": "Hamburg",
    # Nicht UI-editierbar — muss ein POST unangetastet lassen:
    "workspace_path": "C:\\test-workspace",
    "apps": ["obsidian://open"],
}

# Globals, die apply_settings veraendert — werden pro Test gesichert.
# Persona/City/Voice und refresh_data leben in assistant_core, die
# Obsidian-Pfade in memory; server behaelt config/Warnings/CONFIG_PATH.
_SERVER_GLOBALS = ("config", "STARTUP_WARNINGS", "CONFIG_PATH")
_CORE_GLOBALS = (
    "USER_NAME", "USER_ADDRESS", "USER_ROLE", "CITY",
    "ELEVENLABS_VOICE_ID", "refresh_data",
)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.headers = {"X-Jarvis-Token": server.SESSION_TOKEN}

        # Temp-Config anlegen und CONFIG_PATH umbiegen.
        fd, self.cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(_TEST_CONFIG, f, ensure_ascii=False)

        self._saved = {name: getattr(server, name) for name in _SERVER_GLOBALS}
        self._saved_core = {name: getattr(assistant_core, name) for name in _CORE_GLOBALS}
        self._saved_memory = (memory.VAULT_PATH, memory.INBOX_PATH)
        self._saved_apps = (app_launcher.APPS, app_launcher.PROFILES,
                            app_launcher.ACTIVE_PROFILE)
        server.CONFIG_PATH = self.cfg_path
        assistant_core.refresh_data = lambda: None  # kein wttr.in/Vault-Scan im Test
        server.config = dict(_TEST_CONFIG)
        assistant_core.CITY = _TEST_CONFIG["city"]
        assistant_core.USER_NAME = _TEST_CONFIG["user_name"]
        memory.configure(vault_path="", inbox_path="")

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(server, name, value)
        for name, value in self._saved_core.items():
            setattr(assistant_core, name, value)
        memory.configure(*self._saved_memory)
        app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE = \
            self._saved_apps
        if os.path.exists(self.cfg_path):
            os.remove(self.cfg_path)

    # ── Auth ────────────────────────────────────────────────────────────────
    def test_get_requires_token(self):
        self.assertEqual(self.client.get("/settings").status_code, 403)
        resp = self.client.get("/settings", headers={"X-Jarvis-Token": "falsch"})
        self.assertEqual(resp.status_code, 403)

    def test_post_requires_token(self):
        resp = self.client.post("/settings", json={"city": "Berlin"})
        self.assertEqual(resp.status_code, 403)

    # ── Secrets ─────────────────────────────────────────────────────────────
    def test_get_never_contains_secrets(self):
        resp = self.client.get("/settings", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.text
        self.assertNotIn("sk-ant-test-secret-111", body)
        self.assertNotIn("el-test-secret-222", body)
        self.assertNotIn("anthropic_api_key", body)
        self.assertNotIn("elevenlabs_api_key", body)

    def test_post_protected_key_rejected(self):
        resp = self.client.post(
            "/settings", headers=self.headers, json={"anthropic_api_key": "sk-neu"}
        )
        self.assertEqual(resp.status_code, 400)
        # Datei unveraendert
        with open(self.cfg_path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["anthropic_api_key"], "sk-ant-test-secret-111")

    # ── Roundtrip + Live-Apply ──────────────────────────────────────────────
    def test_post_updates_file_and_get_reflects(self):
        resp = self.client.post(
            "/settings", headers=self.headers, json={"city": "Berlin", "user_name": "Neu"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(resp.json()["applied"], ["city", "user_name"])

        got = self.client.get("/settings", headers=self.headers).json()["settings"]
        self.assertEqual(got["city"], "Berlin")
        self.assertEqual(got["user_name"], "Neu")

        with open(self.cfg_path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["city"], "Berlin")
        # Secrets + nicht-editierbare Felder bleiben erhalten
        self.assertEqual(on_disk["anthropic_api_key"], "sk-ant-test-secret-111")
        self.assertEqual(on_disk["workspace_path"], "C:\\test-workspace")

    def test_post_applies_globals_without_restart(self):
        self.client.post(
            "/settings", headers=self.headers,
            json={"city": "Berlin", "user_address": "Madame", "elevenlabs_voice_id": "voice-neu"},
        )
        self.assertEqual(assistant_core.CITY, "Berlin")
        self.assertEqual(assistant_core.USER_ADDRESS, "Madame")
        self.assertEqual(assistant_core.ELEVENLABS_VOICE_ID, "voice-neu")

    def test_post_apps_objects_reconfigures_launcher(self):
        resp = self.client.post(
            "/settings", headers=self.headers,
            json={"apps": [{"name": "Notepad", "command": "notepad", "type": "process"}]},
        )
        self.assertEqual(resp.status_code, 200)
        # Live-Apply: der Launcher kennt die neue App sofort, per Name findbar.
        app = app_launcher.find_app("notepad")
        self.assertIsNotNone(app)
        self.assertEqual(app["command"], "notepad")

    def test_post_apps_preserves_vscode_entry_roundtrip(self):
        # Der VS-Code-Eintrag (id/name/command/process_name) darf beim Speichern
        # NICHT verworfen oder verstuemmelt werden — 'command' bleibt woertlich 'code'.
        vscode = {"id": "vscode", "name": "VS Code", "command": "code",
                  "type": "process", "process_name": "Code"}
        resp = self.client.post(
            "/settings", headers=self.headers,
            json={"apps": [{"id": "obsidian", "name": "Obsidian",
                            "command": "obsidian://open", "type": "url"}, vscode]},
        )
        self.assertEqual(resp.status_code, 200)
        with open(self.cfg_path, encoding="utf-8") as f:
            on_disk_apps = json.load(f)["apps"]
        saved = next(a for a in on_disk_apps if a.get("id") == "vscode")
        self.assertEqual(saved["command"], "code")
        self.assertEqual(saved["name"], "VS Code")
        self.assertEqual(saved["process_name"], "Code")
        # Live-Apply: per Name UND ID findbar, command unveraendert.
        self.assertEqual(app_launcher.find_app("VS Code")["id"], "vscode")
        self.assertEqual(app_launcher.find_app("vscode")["command"], "code")

    def test_music_fields_roundtrip_without_secrets(self):
        resp = self.client.post(
            "/settings", headers=self.headers,
            json={"music_folder": "C:\\Musik\\jarvis", "selected_music_file": "song.mp3"},
        )
        self.assertEqual(resp.status_code, 200)
        got = self.client.get("/settings", headers=self.headers)
        # Musikfelder werden publiziert, Secrets weiterhin nie.
        self.assertNotIn("sk-ant-test-secret-111", got.text)
        self.assertNotIn("el-test-secret-222", got.text)
        settings = got.json()["settings"]
        self.assertEqual(settings["music_folder"], "C:\\Musik\\jarvis")
        self.assertEqual(settings["selected_music_file"], "song.mp3")

    def test_music_file_with_path_rejected(self):
        resp = self.client.post(
            "/settings", headers=self.headers,
            json={"selected_music_file": "C:\\Musik\\song.mp3"},
        )
        self.assertEqual(resp.status_code, 400)

    # ── Validierung ─────────────────────────────────────────────────────────
    def test_post_unknown_key_400(self):
        resp = self.client.post(
            "/settings", headers=self.headers, json={"gibt_es_nicht": "x"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(resp.json()["errors"])

    def test_post_bad_type_400(self):
        resp = self.client.post(
            "/settings", headers=self.headers, json={"apps": "kein-array"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_non_object_400(self):
        resp = self.client.post("/settings", headers=self.headers, json=["liste"])
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()

"""
Tests fuer die Settings-API (GET/POST /settings) gegen die echte App.

WICHTIG: ``server.CONFIG_PATH`` wird auf eine Temp-Kopie gepatcht und
``server.refresh_data`` auf einen No-Op — die Tests duerfen NIEMALS die echte
config.json beschreiben oder Netzaufrufe (wttr.in) ausloesen.

    python -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import server
    import config_loader
    import memory
    from fastapi.testclient import TestClient
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
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
    "browser_url": "https://alt.example",
    "apps": ["obsidian://open"],
}

# Server-Globals, die apply_settings veraendert — werden pro Test gesichert.
# (Die Obsidian-Pfade leben inzwischen als Modul-State in memory.py.)
_PATCHED_GLOBALS = (
    "config", "USER_NAME", "USER_ADDRESS", "USER_ROLE", "CITY",
    "ELEVENLABS_VOICE_ID", "STARTUP_WARNINGS",
    "CONFIG_PATH", "refresh_data",
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

        self._saved = {name: getattr(server, name) for name in _PATCHED_GLOBALS}
        self._saved_memory = (memory.VAULT_PATH, memory.INBOX_PATH)
        server.CONFIG_PATH = self.cfg_path
        server.refresh_data = lambda: None  # kein wttr.in/Vault-Scan im Test
        server.config = dict(_TEST_CONFIG)
        server.CITY = _TEST_CONFIG["city"]
        server.USER_NAME = _TEST_CONFIG["user_name"]
        memory.configure(vault_path="", inbox_path="")

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(server, name, value)
        memory.configure(*self._saved_memory)
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
        self.assertEqual(on_disk["browser_url"], "https://alt.example")

    def test_post_applies_globals_without_restart(self):
        self.client.post(
            "/settings", headers=self.headers,
            json={"city": "Berlin", "user_address": "Madame", "elevenlabs_voice_id": "voice-neu"},
        )
        self.assertEqual(server.CITY, "Berlin")
        self.assertEqual(server.USER_ADDRESS, "Madame")
        self.assertEqual(server.ELEVENLABS_VOICE_ID, "voice-neu")

    # ── Validierung ─────────────────────────────────────────────────────────
    def test_post_unknown_key_400(self):
        resp = self.client.post(
            "/settings", headers=self.headers, json={"browser_url": "https://x.de"}
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

"""
Tests fuer die Settings-API (GET/POST /settings) gegen die echte App.

Seam (RFC-0003): ``server.create_app(Runtime(...))`` mit EIGENER Temp-Config pro
Runtime und lifespan-fahrendem TestClient — **keine** Patches von
``server.CONFIG_PATH``/``server.config``. Die echte config.json wird nie gelesen
oder geschrieben; ``assistant_core.refresh_data`` ist ein No-Op (kein wttr.in).

    python -m unittest discover -s tests
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config vor 'import server'

try:
    import server
    import app_launcher
    import assistant_core
    import config_loader
    import memory
    import runtime as runtime_mod
    from fastapi.testclient import TestClient
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit abfangen
    server = None
    _IMPORT_ERROR = e

_TEST_CONFIG = {
    "schema_version": 1,
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

_CORE_GLOBALS = ("USER_NAME", "USER_ADDRESS", "USER_ROLE", "CITY",
                 "ELEVENLABS_VOICE_ID", "refresh_data")


class _FakeAI:
    """Injizierter LLM-Fake (BORROWED) — es geht nie ein Providercall raus."""


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class _SettingsSeamTestCase(unittest.TestCase):
    """Jede Probe: eigene Runtime + eigene Temp-Config + eigener TestClient."""

    CONFIG = _TEST_CONFIG

    def setUp(self):
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"
        self.tmp = tempfile.mkdtemp(prefix="jarvis-settings-")
        self.cfg_path = os.path.join(self.tmp, "config.json")
        self.write_config(self.CONFIG)

        self._saved_core = {n: getattr(assistant_core, n) for n in _CORE_GLOBALS}
        self._saved_memory = (memory.VAULT_PATH, memory.INBOX_PATH)
        self._saved_apps = (app_launcher.APPS, app_launcher.PROFILES,
                            app_launcher.ACTIVE_PROFILE)
        assistant_core.refresh_data = lambda: None

        self.runtime = runtime_mod.Runtime.for_production(
            config_path=self.cfg_path, environ={}, ai=_FakeAI(), http=object())
        self.app = server.create_app(self.runtime)
        self._client_cm = TestClient(self.app)
        self.client = self._client_cm.__enter__()   # faehrt den Lifespan
        self.headers = {"X-Jarvis-Token": self.runtime.session_token}

    def tearDown(self):
        self._client_cm.__exit__(None, None, None)
        for n, v in self._saved_core.items():
            setattr(assistant_core, n, v)
        memory.configure(*self._saved_memory)
        (app_launcher.APPS, app_launcher.PROFILES,
         app_launcher.ACTIVE_PROFILE) = self._saved_apps
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_config(self, doc, path=None):
        with open(path or self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)

    def read_config(self):
        with open(self.cfg_path, encoding="utf-8") as f:
            return json.load(f)

    def read_raw(self):
        with open(self.cfg_path, encoding="utf-8") as f:
            return f.read()

    def revision(self):
        return self.client.get("/settings", headers=self.headers).json()["revision"]


class SettingsApiTests(_SettingsSeamTestCase):
    # ── Auth ────────────────────────────────────────────────────────────────
    def test_get_requires_token(self):
        self.assertEqual(self.client.get("/settings").status_code, 403)
        self.assertEqual(
            self.client.get("/settings", headers={"X-Jarvis-Token": "falsch"}).status_code,
            403)

    def test_post_requires_token(self):
        self.assertEqual(
            self.client.post("/settings", json={"city": "Berlin"}).status_code, 403)

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
        resp = self.client.post("/settings", headers=self.headers,
                                json={"anthropic_api_key": "sk-neu"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.read_config()["anthropic_api_key"], "sk-ant-test-secret-111")

    # ── Roundtrip + Live-Apply ──────────────────────────────────────────────
    def test_post_updates_file_and_get_reflects(self):
        resp = self.client.post("/settings", headers=self.headers,
                                json={"city": "Berlin", "user_name": "Neu"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(resp.json()["applied"], ["city", "user_name"])
        on_disk = self.read_config()
        self.assertEqual(on_disk["city"], "Berlin")
        self.assertEqual(on_disk["user_name"], "Neu")
        view = self.client.get("/settings", headers=self.headers).json()["settings"]
        self.assertEqual(view["city"], "Berlin")

    def test_post_preserves_secrets_and_unknown_fields(self):
        self.client.post("/settings", headers=self.headers, json={"city": "Berlin"})
        on_disk = self.read_config()
        self.assertEqual(on_disk["anthropic_api_key"], "sk-ant-test-secret-111")
        self.assertEqual(on_disk["workspace_path"], "C:\\test-workspace")
        self.assertEqual(on_disk["schema_version"], 1)

    def test_post_applies_globals_without_restart(self):
        self.client.post("/settings", headers=self.headers,
                         json={"city": "Berlin", "user_name": "Neu"})
        self.assertEqual(assistant_core.CITY, "Berlin")
        self.assertEqual(assistant_core.USER_NAME, "Neu")

    def test_post_apps_objects_reconfigures_launcher(self):
        apps = [{"id": "obsidian", "name": "Obsidian", "command": "obsidian://open",
                 "type": "url"}]
        resp = self.client.post("/settings", headers=self.headers, json={"apps": apps})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(a["id"] == "obsidian" for a in app_launcher.APPS))

    def test_post_apps_preserves_vscode_entry_roundtrip(self):
        apps = [{"id": "vscode", "name": "VS Code", "command": "code.exe",
                 "type": "process", "process_name": "Code.exe"}]
        self.client.post("/settings", headers=self.headers, json={"apps": apps})
        self.assertEqual(self.read_config()["apps"], apps)

    def test_music_fields_roundtrip_without_secrets(self):
        resp = self.client.post("/settings", headers=self.headers,
                                json={"music_folder": self.tmp, "music_volume": 0.5})
        self.assertEqual(resp.status_code, 200)
        on_disk = self.read_config()
        self.assertEqual(on_disk["music_folder"], self.tmp)
        self.assertEqual(on_disk["music_volume"], 0.5)

    def test_music_file_with_path_rejected(self):
        resp = self.client.post("/settings", headers=self.headers,
                                json={"selected_music_file": "..\\evil.mp3"})
        self.assertEqual(resp.status_code, 400)

    # ── Validierung ─────────────────────────────────────────────────────────
    def test_post_unknown_key_400(self):
        resp = self.client.post("/settings", headers=self.headers, json={"quatsch": "x"})
        self.assertEqual(resp.status_code, 400)

    def test_post_bad_type_400(self):
        resp = self.client.post("/settings", headers=self.headers, json={"city": 42})
        self.assertEqual(resp.status_code, 400)

    def test_post_non_object_400(self):
        resp = self.client.post("/settings", headers=self.headers, json=["nope"])
        self.assertEqual(resp.status_code, 400)


class SettingsRevisionConflictTests(_SettingsSeamTestCase):
    """Revision + If-Match: eine veraltete UI-Basis darf nie ueberschreiben (D6)."""

    def test_get_returns_revision_additively(self):
        body = self.client.get("/settings", headers=self.headers).json()
        self.assertTrue(body["ok"])
        self.assertIn("settings", body)
        self.assertIn("warnings", body)          # Bestandsfelder bleiben
        self.assertTrue(body["revision"])        # additiv

    def test_post_with_matching_if_match_succeeds(self):
        rev = self.revision()
        resp = self.client.post("/settings", headers={**self.headers, "If-Match": rev},
                                json={"city": "Berlin"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.read_config()["city"], "Berlin")

    def test_post_with_stale_if_match_conflicts(self):
        stale = self.revision()
        self.client.post("/settings", headers=self.headers, json={"city": "Berlin"})
        before = self.read_raw()
        resp = self.client.post("/settings", headers={**self.headers, "If-Match": stale},
                                json={"city": "Kiel"})
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(resp.json()["ok"])
        self.assertTrue(resp.json()["errors"])
        self.assertEqual(self.read_raw(), before, "Konflikt darf nichts schreiben")

    def test_conflict_does_not_apply_live(self):
        stale = self.revision()
        self.client.post("/settings", headers=self.headers, json={"city": "Berlin"})
        self.assertEqual(assistant_core.CITY, "Berlin")
        self.client.post("/settings", headers={**self.headers, "If-Match": stale},
                         json={"city": "Kiel"})
        self.assertEqual(assistant_core.CITY, "Berlin",
                         "Konflikt darf kein Live-Apply ausloesen")

    def test_conflict_message_has_no_secrets(self):
        stale = self.revision()
        self.client.post("/settings", headers=self.headers, json={"city": "Berlin"})
        resp = self.client.post("/settings", headers={**self.headers, "If-Match": stale},
                                json={"city": "Kiel"})
        flat = resp.text
        self.assertNotIn("sk-ant-test-secret-111", flat)
        self.assertNotIn("el-test-secret-222", flat)

    def test_post_without_if_match_still_allowed(self):
        """Kompatibilitaet: ohne Header wird gegen die frische Basis gearbeitet."""
        resp = self.client.post("/settings", headers=self.headers, json={"city": "Kiel"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.read_config()["city"], "Kiel")

    def test_revision_changes_after_write(self):
        first = self.revision()
        self.client.post("/settings", headers=self.headers, json={"city": "Berlin"})
        self.assertNotEqual(self.revision(), first)

    def test_manual_change_before_post_is_new_base(self):
        manual = self.read_config()
        manual["user_role"] = "haendisch"
        self.write_config(manual)
        resp = self.client.post("/settings", headers=self.headers, json={"city": "Berlin"})
        self.assertEqual(resp.status_code, 200)
        on_disk = self.read_config()
        self.assertEqual(on_disk["user_role"], "haendisch")
        self.assertEqual(on_disk["city"], "Berlin")

    def test_corrupt_file_before_post_is_not_overwritten(self):
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            f.write('{"kaputt": ')
        before = self.read_raw()
        resp = self.client.post("/settings", headers=self.headers, json={"city": "Berlin"})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(self.read_raw(), before)


class SettingsBroadcastTests(_SettingsSeamTestCase):
    """Post-Commit-Effekt: nach einem Save gehen frische Warnings an alle
    WS-Clients (Regression — der Broadcast schlug wegen eines falschen
    Variablennamens still fehl und wurde nur als Degraded geloggt)."""

    def test_save_broadcasts_health_to_ws_clients(self):
        sent = []

        class _FakeWS:
            async def send_json(self, payload):
                sent.append(payload)

        self.runtime.ws_clients.add(_FakeWS())
        resp = self.client.post("/settings", headers=self.headers, json={"city": "Berlin"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(p.get("type") == "health" for p in sent),
                        "nach dem Save muss ein health-Frame gebroadcastet werden")
        # Kein stiller Degraded-Zustand bei erfolgreichem Broadcast.
        self.assertNotIn("degraded", resp.json())


class SettingsIsolationTests(unittest.TestCase):
    """Zwei Runtimes mit zwei Config-Pfaden schreiben nie in die jeweils andere
    Datei (Regression fuer den frueheren globalen CONFIG_PATH — Befund B)."""

    def setUp(self):
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"
        self.tmp = tempfile.mkdtemp(prefix="jarvis-iso-")
        self._saved_core = {n: getattr(assistant_core, n) for n in _CORE_GLOBALS}
        self._saved_apps = (app_launcher.APPS, app_launcher.PROFILES,
                            app_launcher.ACTIVE_PROFILE)
        assistant_core.refresh_data = lambda: None

    def tearDown(self):
        for n, v in self._saved_core.items():
            setattr(assistant_core, n, v)
        (app_launcher.APPS, app_launcher.PROFILES,
         app_launcher.ACTIVE_PROFILE) = self._saved_apps
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, name, city):
        path = os.path.join(self.tmp, name)
        doc = dict(_TEST_CONFIG, city=city)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        rt = runtime_mod.Runtime.for_production(config_path=path, environ={},
                                               ai=_FakeAI(), http=object())
        return path, rt, server.create_app(rt)

    def test_request_to_app_a_never_writes_file_b(self):
        pa, rta, appa = self._make("a.json", "Hamburg")
        pb, rtb, appb = self._make("b.json", "Hamburg")
        with TestClient(appa) as ca, TestClient(appb) as cb:
            resp = ca.post("/settings", headers={"X-Jarvis-Token": rta.session_token},
                           json={"city": "Bremen"})
            self.assertEqual(resp.status_code, 200)
        with open(pa, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["city"], "Bremen")
        with open(pb, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["city"], "Hamburg",
                             "Request an App A darf Datei B nie veraendern")


if __name__ == "__main__":
    unittest.main()

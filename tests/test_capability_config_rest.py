"""Slice 9 — uebrige sichere REST-Mutationen (Amendment 2 §A2.3).

Settings speichern, Musikauswahl speichern, Profil erstellen, Profil duplizieren.

Diese vier tragen die empfindlichsten Vertraege des Servers: If-Match/Revision,
`409 Conflict`, `403`, `404`, ungueltige JSON-/Body-Antworten, Broadcast und
Correlation — und die Regel, dass ein **gueltig persistierter** Commit wegen eines
spaeteren Refresh-/Broadcast-Fehlers **nie** zurueckgerollt wird.

Seam (RFC-0003): eigene Runtime + Temp-Config + lifespan-fahrender TestClient.
"""
import json
import os
import tempfile
import unittest

import tests  # noqa: F401
from tests.env_guard import guard_env
from fastapi.testclient import TestClient

import app_launcher
import assistant_core
import capability as cap
import memory
import runtime as runtime_mod
import server

_CONFIG = {
    "anthropic_api_key": "test-key", "elevenlabs_api_key": "test-key",
    "user_name": "Test", "user_role": "Dev", "user_address": "du",
    "city": "Hamburg",
    "apps": [{"id": "obsidian", "name": "Obsidian", "type": "process",
              "command": "obsidian", "process_name": "Obsidian"}],
    "launcher": {
        "active_profile": "default",
        "profiles": [{"id": "default", "name": "Standard", "apps": []}],
    },
}


class ConfigRestBase(unittest.TestCase):
    def setUp(self):
        guard_env(self, "JARVIS_SKIP_STARTUP_REFRESH")
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"
        fd, self.cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(dict(_CONFIG, schema_version=1), f, ensure_ascii=False)
        self._saved_launcher = (app_launcher.APPS, app_launcher.PROFILES,
                                app_launcher.ACTIVE_PROFILE)
        self._saved_refresh = assistant_core.refresh_data
        assistant_core.refresh_data = lambda: None
        memory.configure(vault_path="", inbox_path="")
        self._saved_session_token = server.SESSION_TOKEN
        self.runtime = runtime_mod.Runtime.for_production(
            config_path=self.cfg_path, environ={}, ai=object(), http=object())
        self.app = server.create_app(self.runtime)
        self._cm = TestClient(self.app)
        self.client = self._cm.__enter__()
        self.headers = {"X-Jarvis-Token": self.runtime.session_token}

    def tearDown(self):
        self._cm.__exit__(None, None, None)
        server.SESSION_TOKEN = self._saved_session_token
        assistant_core.refresh_data = self._saved_refresh
        (app_launcher.APPS, app_launcher.PROFILES,
         app_launcher.ACTIVE_PROFILE) = self._saved_launcher
        os.unlink(self.cfg_path)


class SettingsRouteTests(ConfigRestBase):
    def test_success_body_and_revision(self):
        r = self.client.post("/settings", json={"city": "Bremen"},
                             headers=self.headers)
        self.assertEqual(200, r.status_code)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(["city"], body["applied"])
        self.assertIn("revision", body)
        self.assertEqual("Bremen", assistant_core.CITY)

    def test_stale_if_match_stays_409(self):
        r = self.client.post("/settings", json={"city": "Bremen"},
                             headers=dict(self.headers, **{"If-Match": "veraltet"}))
        self.assertEqual(409, r.status_code)
        self.assertTrue(r.json()["conflict"])

    def test_fresh_if_match_succeeds(self):
        rev = self.runtime.configuration.snapshot().revision
        r = self.client.post("/settings", json={"city": "Bremen"},
                             headers=dict(self.headers, **{"If-Match": rev}))
        self.assertEqual(200, r.status_code)

    def test_unauthorised_stays_403(self):
        self.assertEqual(403, self.client.post("/settings",
                                               json={"city": "X"}).status_code)

    def test_invalid_json_stays_400(self):
        r = self.client.post("/settings", content=b"{nope", headers=self.headers)
        self.assertEqual(400, r.status_code)

    def test_unknown_key_stays_400(self):
        r = self.client.post("/settings", json={"nicht_erlaubt": "x"},
                             headers=self.headers)
        self.assertEqual(400, r.status_code)

    def test_runs_through_the_coordinator(self):
        seen = []
        real = self.runtime.capabilities.attempt

        async def _spy(request, evidence=None, **kw):
            seen.append(request.capability)
            return await real(request, evidence, **kw)

        self.runtime.capabilities.attempt = _spy
        try:
            self.client.post("/settings", json={"city": "Bremen"},
                             headers=self.headers)
        finally:
            self.runtime.capabilities.attempt = real
        self.assertIn("settings.update", seen)

    def test_a_valid_commit_is_never_rolled_back_by_a_later_failure(self):
        """§A2.3: ein gueltig persistierter Commit ueberlebt einen Post-Commit-Fehler."""
        real = server.broadcast_health

        async def _boom(rt):
            raise RuntimeError("Broadcast kaputt")

        server.broadcast_health = _boom
        try:
            r = self.client.post("/settings", json={"city": "Bremen"},
                                 headers=self.headers)
        finally:
            server.broadcast_health = real
        self.assertEqual(200, r.status_code)
        self.assertEqual("Bremen", assistant_core.CITY)
        with open(self.cfg_path, encoding="utf-8") as f:
            self.assertEqual("Bremen", json.load(f)["city"])


class MusicRouteTests(ConfigRestBase):
    def test_deselect_succeeds(self):
        r = self.client.post("/music/selection", json={"file": ""},
                             headers=self.headers)
        self.assertEqual(200, r.status_code)

    def test_invalid_json_stays_400(self):
        r = self.client.post("/music/selection", content=b"{nope",
                             headers=self.headers)
        self.assertEqual(400, r.status_code)

    def test_missing_field_stays_400(self):
        r = self.client.post("/music/selection", json={}, headers=self.headers)
        self.assertEqual(400, r.status_code)

    def test_bad_filename_stays_400(self):
        r = self.client.post("/music/selection", json={"file": "../evil.mp3"},
                             headers=self.headers)
        self.assertEqual(400, r.status_code)

    def test_unauthorised_stays_403(self):
        self.assertEqual(403, self.client.post("/music/selection",
                                               json={"file": ""}).status_code)

    def test_runs_through_the_coordinator(self):
        seen = []
        real = self.runtime.capabilities.attempt

        async def _spy(request, evidence=None, **kw):
            seen.append(request.capability)
            return await real(request, evidence, **kw)

        self.runtime.capabilities.attempt = _spy
        try:
            self.client.post("/music/selection", json={"file": ""},
                             headers=self.headers)
        finally:
            self.runtime.capabilities.attempt = real
        self.assertIn("music.selection.set", seen)


class ProfileCreateAndDuplicateTests(ConfigRestBase):
    def test_create_succeeds(self):
        r = self.client.post("/launcher/profiles", json={"name": "Fokus"},
                             headers=self.headers)
        self.assertEqual(200, r.status_code)
        names = [p["name"] for p in r.json()["profiles"]]
        self.assertIn("Fokus", names)

    def test_create_does_not_activate(self):
        self.client.post("/launcher/profiles", json={"name": "Fokus"},
                         headers=self.headers)
        self.assertEqual("default", app_launcher.ACTIVE_PROFILE)

    def test_create_duplicate_id_stays_400(self):
        r = self.client.post("/launcher/profiles",
                             json={"id": "default", "name": "Nochmal"},
                             headers=self.headers)
        self.assertEqual(400, r.status_code)

    def test_create_missing_name_stays_400(self):
        r = self.client.post("/launcher/profiles", json={}, headers=self.headers)
        self.assertEqual(400, r.status_code)

    def test_duplicate_succeeds(self):
        r = self.client.post("/launcher/profiles/default/duplicate",
                             json={"name": "Kopie"}, headers=self.headers)
        self.assertEqual(200, r.status_code)
        names = [p["name"] for p in r.json()["profiles"]]
        self.assertIn("Kopie", names)

    def test_duplicate_unknown_stays_404(self):
        r = self.client.post("/launcher/profiles/gibtsnicht/duplicate",
                             json={"name": "K"}, headers=self.headers)
        self.assertEqual(404, r.status_code)

    def test_both_run_through_the_coordinator(self):
        seen = []
        real = self.runtime.capabilities.attempt

        async def _spy(request, evidence=None, **kw):
            seen.append(request.capability)
            return await real(request, evidence, **kw)

        self.runtime.capabilities.attempt = _spy
        try:
            self.client.post("/launcher/profiles", json={"name": "Fokus"},
                             headers=self.headers)
            self.client.post("/launcher/profiles/default/duplicate",
                             json={"name": "Kopie"}, headers=self.headers)
        finally:
            self.runtime.capabilities.attempt = real
        self.assertIn("launcher.profile.create", seen)
        self.assertIn("launcher.profile.duplicate", seen)


class ConfigCapabilityCensusTests(ConfigRestBase):
    def _view(self, name):
        return self.runtime.capabilities.inspect(name)

    def test_settings_uses_its_own_scope(self):
        view = self._view("settings.update")
        self.assertIn(cap.Scope.CONFIG_SETTINGS, view.scopes)
        self.assertNotIn(cap.Scope.CONFIG_LAUNCHER, view.scopes)

    def test_music_uses_its_own_scope(self):
        view = self._view("music.selection.set")
        self.assertIn(cap.Scope.CONFIG_MUSIC, view.scopes)
        self.assertNotIn(cap.Scope.CONFIG_LAUNCHER, view.scopes)

    def test_all_four_declare_local_write(self):
        for name in ("settings.update", "music.selection.set",
                     "launcher.profile.create", "launcher.profile.duplicate"):
            with self.subTest(name=name):
                self.assertIn(cap.EffectClass.LOCAL_WRITE, self._view(name).effects)

    def test_no_config_capability_is_destructive(self):
        for name in ("settings.update", "music.selection.set",
                     "launcher.profile.create", "launcher.profile.duplicate"):
            with self.subTest(name=name):
                self.assertNotIn(cap.EffectClass.DESTRUCTIVE,
                                 self._view(name).effects)


if __name__ == "__main__":
    unittest.main()

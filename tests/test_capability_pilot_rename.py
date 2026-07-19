"""Slice 8 — REST-Pilot launcher.profile.rename (RFC-0007 Amendment 1 §A1.4).

Die Rename-Route laeuft ueber DENSELBEN Coordinator; Provenance ist ``operator``;
Configuration bleibt der einzige Writer; Statuscode, Response-Body und Broadcast bleiben
unveraendert. ``launcher.profile.delete`` bleibt unveraendert — die dokumentierte
destructive Luecke.

Seam (RFC-0003): eigene Runtime + Temp-Config + lifespan-fahrender TestClient.
"""
import json
import os
import tempfile
import unittest

import tests  # noqa: F401
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
    "apps": [{"id": "obsidian", "name": "Obsidian", "path": "C:/x/obsidian.exe"}],
    "launcher": {
        "active_profile": "default",
        "profiles": [
            {"id": "default", "name": "Standard", "apps": []},
            {"id": "writing", "name": "Schreiben", "apps": []},
        ],
    },
}


class ProfileRenamePilotTests(unittest.TestCase):
    def setUp(self):
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
        # RFC-0002 A3: der Lifespan setzt das Kompat-Alias ``server.SESSION_TOKEN`` auf
        # die aktive Runtime. Bei einer Test-Runtime muss es danach wiederhergestellt
        # werden, sonst sehen nachfolgende Tests, die ``server.SESSION_TOKEN`` +
        # ``server.app`` (Modul-Runtime) nutzen, einen Fremdtoken (403).
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
        app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE = \
            self._saved_launcher
        if os.path.exists(self.cfg_path):
            os.remove(self.cfg_path)

    def _read_cfg(self):
        with open(self.cfg_path, encoding="utf-8") as f:
            return json.load(f)

    # ── Zensus ───────────────────────────────────────────────────────────────

    def test_rename_capability_in_registry(self):
        view = self.runtime.capabilities.inspect("launcher.profile.rename")
        self.assertEqual(view.effects, frozenset({cap.EffectClass.LOCAL_WRITE}))
        self.assertEqual(view.writes, frozenset({cap.DataClass.LOCAL}))
        self.assertIs(view.tier, cap.Tier.GOVERNED)

    # ── Vertrag ──────────────────────────────────────────────────────────────

    def test_rename_succeeds_and_persists_via_configuration(self):
        resp = self.client.post("/launcher/profiles/writing/rename",
                                headers=self.headers, json={"name": "Prosa"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        # Configuration ist der einzige Writer: die Temp-Datei traegt den neuen Namen.
        profiles = self._read_cfg()["launcher"]["profiles"]
        self.assertEqual(next(p for p in profiles if p["id"] == "writing")["name"], "Prosa")

    def test_rename_unknown_profile_still_404(self):
        resp = self.client.post("/launcher/profiles/nope/rename",
                                headers=self.headers, json={"name": "X"})
        self.assertEqual(resp.status_code, 404)

    def test_rename_requires_token(self):
        resp = self.client.post("/launcher/profiles/writing/rename", json={"name": "X"})
        self.assertEqual(resp.status_code, 403)

    def test_rename_dispatches_through_the_coordinator(self):
        events = []
        orig = self.runtime.capabilities._audit
        self.runtime.capabilities._audit = lambda name, **f: events.append((name, f))
        try:
            self.client.post("/launcher/profiles/writing/rename",
                             headers=self.headers, json={"name": "Prosa"})
        finally:
            self.runtime.capabilities._audit = orig
        attempted = [f for n, f in events if n == "capability.attempted"]
        self.assertTrue(any(f.get("capability") == "launcher.profile.rename"
                            for f in attempted),
                        "Rename lief nicht ueber den Coordinator")

    def test_rename_uses_operator_provenance(self):
        seen = {}
        real = cap.Coordinator.attempt

        async def _spy(self_c, request, evidence=None, *, meta=None):
            if request.capability == "launcher.profile.rename":
                seen["provenance"] = request.provenance
            return await real(self_c, request, evidence, meta=meta)

        cap.Coordinator.attempt = _spy
        try:
            self.client.post("/launcher/profiles/writing/rename",
                             headers=self.headers, json={"name": "Prosa"})
        finally:
            cap.Coordinator.attempt = real
        self.assertIs(seen.get("provenance"), cap.Provenance.OPERATOR)

    # ── Delete bleibt die offene Luecke ──────────────────────────────────────

    def test_delete_is_unchanged_and_not_routed_through_the_coordinator(self):
        events = []
        orig = self.runtime.capabilities._audit
        self.runtime.capabilities._audit = lambda name, **f: events.append((name, f))
        try:
            resp = self.client.delete("/launcher/profiles/writing",
                                      headers=self.headers)
        finally:
            self.runtime.capabilities._audit = orig
        self.assertEqual(resp.status_code, 200)
        # Delete ist NICHT migriert: keine capability.attempted mit profile.delete.
        self.assertFalse(any(f.get("capability", "").endswith("delete")
                             for n, f in events if n == "capability.attempted"))
        # Und das Profil ist tatsaechlich weg (Verhalten unveraendert).
        profiles = self._read_cfg()["launcher"]["profiles"]
        self.assertNotIn("writing", [p["id"] for p in profiles])


if __name__ == "__main__":
    unittest.main()

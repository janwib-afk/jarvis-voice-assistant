"""Slice 8 — gemeinsame Launcher-REST-Adapter (Amendment 2 §A2.3).

Voice und REST benutzen bei derselben fachlichen Operation **denselben** Vertrag.
Es entsteht keine transportabhaengige zweite Wahrheit: eine Ausfuehrung, zwei
Projektionen (sprechbarer Text fuer die Stimme, Fehlerliste fuer HTTP).

Status, Body, Broadcast und Correlation bleiben unveraendert.

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
    "apps": [{"id": "obsidian", "name": "Obsidian", "type": "process",
              "command": "obsidian", "process_name": "Obsidian"}],
    "launcher": {
        "active_profile": "default",
        "profiles": [
            {"id": "default", "name": "Standard", "apps": []},
            {"id": "writing", "name": "Schreiben", "apps": []},
        ],
    },
}


class LauncherRestBase(unittest.TestCase):
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
        # RFC-0002 A3: der Lifespan setzt server.SESSION_TOKEN auf die aktive
        # Runtime. Ohne Wiederherstellung sehen spaetere Tests einen Fremdtoken.
        self._saved_session_token = server.SESSION_TOKEN
        self.runtime = runtime_mod.Runtime.for_production(
            config_path=self.cfg_path, environ={}, ai=object(), http=object())
        self.app = server.create_app(self.runtime)
        self._cm = TestClient(self.app)
        self.client = self._cm.__enter__()
        self.token = self.runtime.session_token

    def tearDown(self):
        self._cm.__exit__(None, None, None)
        server.SESSION_TOKEN = self._saved_session_token
        assistant_core.refresh_data = self._saved_refresh
        (app_launcher.APPS, app_launcher.PROFILES,
         app_launcher.ACTIVE_PROFILE) = self._saved_launcher
        os.unlink(self.cfg_path)

    def _headers(self):
        return {"X-Jarvis-Token": self.token}


class SharedContractTests(LauncherRestBase):
    """Dieselbe Operation, derselbe Vertrag — unabhaengig vom Transport."""

    def test_voice_and_rest_share_the_same_contracts(self):
        names = {v.name for v in self.runtime.capabilities.inspect()}
        for action_type in ("APP_AUTOSTART_ON", "APP_PLACE", "PROFILE_ACTIVATE",
                            "APP_OPEN"):
            with self.subTest(action_type=action_type):
                shared = cap.MIGRATED_ACTIONS[action_type]
                self.assertIn(shared, names)

    def test_no_transport_specific_duplicate_contracts_exist(self):
        """Kein ``…​.rest``-Zwilling neben dem Voice-Vertrag."""
        names = [v.name for v in self.runtime.capabilities.inspect()]
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertFalse(name.endswith(".rest"), name)
            self.assertFalse(name.endswith(".voice"), name)


class AutostartRouteTests(LauncherRestBase):
    def test_success_body_and_status_unchanged(self):
        r = self.client.post("/launcher/apps/obsidian/toggle",
                             json={"autostart": False}, headers=self._headers())
        self.assertEqual(200, r.status_code)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertIn("apps", body)
        by_id = {a["id"]: a for a in body["apps"]}
        self.assertFalse(by_id["obsidian"]["autostart"])

    def test_unauthorised_stays_403(self):
        r = self.client.post("/launcher/apps/obsidian/toggle",
                             json={"autostart": True})
        self.assertEqual(403, r.status_code)

    def test_persist_failure_stays_500_and_carries_the_errors(self):
        """Ein fehlgeschlagener Speichervorgang darf nie als 200 durchgehen.

        Die Fehlerliste entsteht im Capability-Execute und muss die Route
        erreichen — sonst meldete sie Erfolg, obwohl nichts gespeichert wurde.
        """
        real = server.persist_launcher_intent

        async def _failing(rt, intent, kind, correlation_id=None):
            return ["Platte voll."]

        server.persist_launcher_intent = _failing
        try:
            r = self.client.post("/launcher/apps/obsidian/toggle",
                                 json={"autostart": True}, headers=self._headers())
        finally:
            server.persist_launcher_intent = real
        self.assertEqual(500, r.status_code)
        self.assertIn("Platte voll.", r.json()["errors"])

    def test_invalid_json_stays_400(self):
        r = self.client.post("/launcher/apps/obsidian/toggle",
                             content=b"{nope", headers=self._headers())
        self.assertEqual(400, r.status_code)

    def test_wrong_type_stays_400(self):
        r = self.client.post("/launcher/apps/obsidian/toggle",
                             json={"autostart": "ja"}, headers=self._headers())
        self.assertEqual(400, r.status_code)
        self.assertIn("true oder false", " ".join(r.json()["errors"]))

    def test_unknown_app_stays_404(self):
        r = self.client.post("/launcher/apps/gibtsnicht/toggle",
                             json={"autostart": True}, headers=self._headers())
        self.assertEqual(404, r.status_code)


class PlacementRouteTests(LauncherRestBase):
    def test_success_status_unchanged(self):
        r = self.client.post("/launcher/apps/obsidian/placement",
                             json={"monitor": "left", "zone": "right_half"},
                             headers=self._headers())
        self.assertEqual(200, r.status_code)
        self.assertTrue(r.json()["ok"])

    def test_missing_field_stays_400(self):
        r = self.client.post("/launcher/apps/obsidian/placement",
                             json={"monitor": "left"}, headers=self._headers())
        self.assertEqual(400, r.status_code)

    def test_unknown_app_stays_404(self):
        r = self.client.post("/launcher/apps/gibtsnicht/placement",
                             json={"monitor": "left", "zone": "right_half"},
                             headers=self._headers())
        self.assertEqual(404, r.status_code)


class ProfileActivateRouteTests(LauncherRestBase):
    def test_success_status_unchanged(self):
        r = self.client.post("/launcher/profiles/writing/activate",
                             headers=self._headers())
        self.assertEqual(200, r.status_code)
        self.assertTrue(r.json()["ok"])
        self.assertEqual("writing", app_launcher.ACTIVE_PROFILE)

    def test_reactivating_the_active_profile_still_persists_and_broadcasts(self):
        """Der belegte Transportunterschied (Amendment 2 §A2.3).

        Die Stimme bricht bei einem bereits aktiven Profil ab; die Route hat
        immer persistiert und ``launcher_changed`` gebroadcastet. Der Unterschied
        steht als typisiertes ``force``-Feld im Vertrag — nicht als zweite
        Wahrheit im Transport. ``default`` ist hier bereits aktiv.
        """
        seen = []
        real = self.runtime.capabilities.attempt

        async def _spy(request, evidence=None, **kw):
            seen.append(dict(request.payload))
            return await real(request, evidence, **kw)

        self.runtime.capabilities.attempt = _spy
        try:
            r = self.client.post("/launcher/profiles/default/activate",
                                 headers=self._headers())
        finally:
            self.runtime.capabilities.attempt = real
        self.assertEqual(200, r.status_code)
        self.assertTrue(seen[0]["force"])

    def test_voice_does_not_force(self):
        self.assertFalse(
            cap._legacy._PAYLOAD_BUILDERS["PROFILE_ACTIVATE"](
                type("A", (), {"payload": "default"})())["force"])

    def test_unknown_profile_stays_404(self):
        r = self.client.post("/launcher/profiles/gibtsnicht/activate",
                             headers=self._headers())
        self.assertEqual(404, r.status_code)

    def test_unauthorised_stays_403(self):
        r = self.client.post("/launcher/profiles/writing/activate")
        self.assertEqual(403, r.status_code)


class AppOpenRouteTests(LauncherRestBase):
    def test_success_body_shape_unchanged(self):
        import app_launcher as al
        real = al.launch
        al.launch = lambda q: {"ok": True, "app": "obsidian", "name": "Obsidian",
                               "message": "Obsidian ist offen."}
        try:
            r = self.client.post("/commands/app/open", json={"app": "obsidian"},
                                 headers=self._headers())
        finally:
            al.launch = real
        self.assertEqual(200, r.status_code)
        body = r.json()
        self.assertEqual({"ok", "app", "name", "message"}, set(body))
        self.assertEqual("Obsidian ist offen.", body["message"])

    def test_unknown_app_stays_404(self):
        import app_launcher as al
        real = al.launch
        al.launch = lambda q: {"ok": False, "app": None, "name": None,
                               "message": "Unbekannte App."}
        try:
            r = self.client.post("/commands/app/open", json={"app": "x"},
                                 headers=self._headers())
        finally:
            al.launch = real
        self.assertEqual(404, r.status_code)

    def test_missing_field_stays_400(self):
        r = self.client.post("/commands/app/open", json={},
                             headers=self._headers())
        self.assertEqual(400, r.status_code)

    def test_unauthorised_stays_403(self):
        r = self.client.post("/commands/app/open", json={"app": "obsidian"})
        self.assertEqual(403, r.status_code)


class CoordinatorIsTheOnlyPathTests(LauncherRestBase):
    """Die Routen umgehen den Coordinator nicht."""

    def test_autostart_route_runs_through_the_coordinator(self):
        seen = []
        real = self.runtime.capabilities.attempt

        async def _spy(request, evidence=None, **kw):
            seen.append(request.capability)
            return await real(request, evidence, **kw)

        self.runtime.capabilities.attempt = _spy
        try:
            self.client.post("/launcher/apps/obsidian/toggle",
                             json={"autostart": True}, headers=self._headers())
        finally:
            self.runtime.capabilities.attempt = real
        self.assertIn("launcher.app.autostart.set", seen)

    def test_rest_uses_operator_provenance(self):
        seen = []
        real = self.runtime.capabilities.attempt

        async def _spy(request, evidence=None, **kw):
            seen.append(request.provenance)
            return await real(request, evidence, **kw)

        self.runtime.capabilities.attempt = _spy
        try:
            self.client.post("/launcher/profiles/writing/activate",
                             headers=self._headers())
        finally:
            self.runtime.capabilities.attempt = real
        self.assertEqual([cap.Provenance.OPERATOR], seen)


if __name__ == "__main__":
    unittest.main()

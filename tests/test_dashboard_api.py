"""
Tests fuer die Dashboard-/Command-API (GET /dashboard/state, POST /commands/app/open).

Muster wie test_settings_api.py: echte App via TestClient, Token-Header,
gesicherte Modul-Globals. ``_start_url``/``_start_process`` werden gepatcht —
es wird niemals eine echte App gestartet.

    python -m unittest discover -s tests
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

try:
    import server
    import app_launcher
    import assistant_core
    from fastapi.testclient import TestClient
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    app_launcher = None
    assistant_core = None
    TestClient = None
    _IMPORT_ERROR = e

VALID_ORIGIN = "http://127.0.0.1:8340"

_APPS = [
    {"id": "obsidian", "name": "Obsidian", "command": "obsidian://open", "type": "url"},
    {"id": "vscode", "name": "VS Code", "command": "code", "type": "process"},
]

_CORE_GLOBALS = ("TASKS_INFO", "TODAY_INBOX", "VAULT_SUMMARY", "DATA_LOADED", "LAST_REFRESH")


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class DashboardApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.headers = {"X-Jarvis-Token": server.SESSION_TOKEN}

        self._saved_apps = (app_launcher.APPS, app_launcher.PROFILES,
                            app_launcher.ACTIVE_PROFILE)
        self._saved_core = {name: getattr(assistant_core, name) for name in _CORE_GLOBALS}
        app_launcher.configure(_APPS)
        assistant_core.TASKS_INFO = ["Steuern machen", "Zahnarzt anrufen"]
        assistant_core.TODAY_INBOX = "- [Idee] Testeintrag"
        assistant_core.VAULT_SUMMARY = {"total": 3, "by_folder": {"Inbox": 3}, "recent": ["Notiz A"]}
        assistant_core.DATA_LOADED = True
        assistant_core.LAST_REFRESH = 1700000000.0

    def tearDown(self):
        app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE = \
            self._saved_apps
        for name, value in self._saved_core.items():
            setattr(assistant_core, name, value)

    # ── Auth ────────────────────────────────────────────────────────────────
    def test_state_requires_token(self):
        self.assertEqual(self.client.get("/dashboard/state").status_code, 403)
        resp = self.client.get("/dashboard/state", headers={"X-Jarvis-Token": "falsch"})
        self.assertEqual(resp.status_code, 403)

    def test_open_requires_token(self):
        resp = self.client.post("/commands/app/open", json={"app": "obsidian"})
        self.assertEqual(resp.status_code, 403)

    # ── Dashboard-State ─────────────────────────────────────────────────────
    def test_state_shape(self):
        resp = self.client.get("/dashboard/state", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(
            set(body),
            {"ok", "health", "tasks", "today_inbox", "vault", "apps",
             "data_loaded", "last_refresh"},
        )
        self.assertEqual(body["tasks"], ["Steuern machen", "Zahnarzt anrufen"])
        self.assertEqual(body["today_inbox"], "- [Idee] Testeintrag")
        self.assertEqual(body["vault"]["recent"], ["Notiz A"])
        self.assertTrue(body["data_loaded"])
        # health hat dieselbe Service-Struktur wie /health (siehe test_ws).
        self.assertEqual(
            set(body["health"]["services"]), {"config", "llm", "tts", "browser", "vault"}
        )

    def test_state_apps_expose_no_command(self):
        body = self.client.get("/dashboard/state", headers=self.headers).json()
        self.assertEqual(len(body["apps"]), 2)
        for app in body["apps"]:
            self.assertNotIn("command", app)
            self.assertNotIn("process_name", app)
            self.assertEqual(set(app), {"id", "name", "type", "autostart", "placement"})

    # ── Command: App oeffnen ────────────────────────────────────────────────
    def test_open_known_app(self):
        with mock.patch.object(app_launcher, "_start_url") as start_url:
            resp = self.client.post(
                "/commands/app/open", headers=self.headers, json={"app": "obsidian"}
            )
        start_url.assert_called_once_with("obsidian://open")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["app"], "obsidian")
        self.assertIn("Obsidian", body["message"])

    def test_open_unknown_app_404(self):
        with mock.patch.object(app_launcher, "_start_url"), \
             mock.patch.object(app_launcher, "_start_process"):
            resp = self.client.post(
                "/commands/app/open", headers=self.headers, json={"app": "photoshop"}
            )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()["ok"])

    def test_open_missing_field_400(self):
        resp = self.client.post("/commands/app/open", headers=self.headers, json={})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/commands/app/open", headers=self.headers, json={"app": 7})
        self.assertEqual(resp.status_code, 400)

    def test_open_launch_failure_500(self):
        with mock.patch.object(app_launcher, "_start_url", side_effect=OSError("kaputt")):
            resp = self.client.post(
                "/commands/app/open", headers=self.headers, json={"app": "obsidian"}
            )
        self.assertEqual(resp.status_code, 500)
        self.assertFalse(resp.json()["ok"])

    def test_open_broadcasts_app_event(self):
        with self.client.websocket_connect(
            f"/ws?token={server.SESSION_TOKEN}", headers={"origin": VALID_ORIGIN}
        ) as websocket:
            # Der Server schickt direkt nach dem Accept einen health-Frame.
            self.assertEqual(websocket.receive_json()["type"], "health")
            with mock.patch.object(app_launcher, "_start_url"):
                resp = self.client.post(
                    "/commands/app/open", headers=self.headers, json={"app": "obsidian"}
                )
            self.assertEqual(resp.status_code, 200)
            event = websocket.receive_json()
            self.assertEqual(event["type"], "app_event")
            self.assertTrue(event["ok"])
            self.assertEqual(event["app"], "obsidian")
            self.assertIn("ts", event)


if __name__ == "__main__":
    unittest.main()

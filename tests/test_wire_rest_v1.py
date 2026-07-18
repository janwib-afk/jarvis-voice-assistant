"""Slice 7 (RFC-0005/Phase 4H) — SEAM-REST: REST-V1-Presentation nach Routenfamilien.

Eigene Runtime + Temp-Config (Fixture unberührt), lifespan-fahrender TestClient. Legacy
(ohne V1-Accept) bleibt byte-/shape-exakt; V1 (`Accept: application/vnd.jarvis.v1+json`)
liefert die Envelope + Correlation-Header. HTTP-Status bleibt maßgeblich.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401

try:
    import server
    import assistant_core
    import memory
    import app_launcher
    import runtime as runtime_mod
    from fastapi.testclient import TestClient
    _IMPORT_ERROR = None
except BaseException as e:
    server = assistant_core = memory = app_launcher = runtime_mod = TestClient = None
    _IMPORT_ERROR = e

VALID_ORIGIN = "http://127.0.0.1:8340"
V1 = {"Accept": "application/vnd.jarvis.v1+json"}
_UUID = "123e4567-e89b-42d3-a456-426614174000"


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class RestV1Tests(unittest.TestCase):
    def setUp(self):
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"
        with open(os.path.join(os.path.dirname(__file__), "fixtures", "config.test.json"),
                  encoding="utf-8") as f:
            base = json.loads(f.read())
        base.setdefault("apps", [])
        self.music_dir = tempfile.mkdtemp(prefix="jarvis-restv1-music-")
        with open(os.path.join(self.music_dir, "song.mp3"), "w", encoding="utf-8") as f:
            f.write("x")
        base["music_folder"] = self.music_dir
        fd, self.cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(base, f, ensure_ascii=False)

        self._saved_core = {n: getattr(assistant_core, n)
                            for n in ("DATA_LOADED", "LAST_REFRESH", "refresh_data")}
        self._saved_mem = (memory.VAULT_PATH, memory.INBOX_PATH)
        self._saved_apps = (app_launcher.APPS, app_launcher.PROFILES,
                            app_launcher.ACTIVE_PROFILE)
        assistant_core.refresh_data = lambda: None
        memory.configure(vault_path="", inbox_path="")

        self.runtime = runtime_mod.Runtime.for_production(
            config_path=self.cfg_path, environ={}, ai=object(), http=object())
        self.app = server.create_app(self.runtime)
        self._cm = TestClient(self.app)
        self.client = self._cm.__enter__()
        self.token = {"X-Jarvis-Token": self.runtime.session_token}

    def tearDown(self):
        self._cm.__exit__(None, None, None)
        for n, v in self._saved_core.items():
            setattr(assistant_core, n, v)
        memory.configure(*self._saved_mem)
        (app_launcher.APPS, app_launcher.PROFILES,
         app_launcher.ACTIVE_PROFILE) = self._saved_apps
        if os.path.exists(self.cfg_path):
            os.remove(self.cfg_path)
        shutil.rmtree(self.music_dir, ignore_errors=True)
        os.environ.pop("JARVIS_SKIP_STARTUP_REFRESH", None)

    # ── Health ───────────────────────────────────────────────────────────────
    def test_health_legacy_unchanged(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json().keys()), {"ok", "warnings", "services", "startup"})
        self.assertNotIn("vnd.jarvis", r.headers.get("content-type", ""))

    def test_health_v1_envelope_redacts_paths(self):
        r = self.client.get("/health", headers=V1)
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/vnd.jarvis.v1+json", r.headers.get("content-type", ""))
        env = r.json()
        self.assertEqual(env["protocol_version"], 1)
        self.assertEqual(env["type"], "health")
        self.assertEqual(env["sensitivity"], "public")
        self.assertIsNone(env["session_id"])          # REST erfindet keine session_id
        p = env["payload"]
        self.assertEqual(p["warnings"], [])            # keine rohen (pfadhaltigen) Warnungen
        self.assertIn("warnings_count", p)
        self.assertNotIn(self.music_dir, r.text)       # kein lokaler Pfad im Body

    def test_health_v1_correlation_mirrored_in_body_and_header(self):
        r = self.client.get("/health", headers={**V1, "X-Jarvis-Correlation-ID": _UUID})
        self.assertEqual(r.json()["correlation_id"], _UUID)
        self.assertEqual(r.headers.get("x-jarvis-correlation-id"), _UUID)

    def test_unsupported_vendor_version_is_406(self):
        r = self.client.get("/health", headers={"Accept": "application/vnd.jarvis.v2+json"})
        self.assertEqual(r.status_code, 406)
        self.assertEqual(r.json()["payload"]["code"], "not_acceptable")

    # ── Settings / Dashboard / Launcher (Legacy exakt + V1-Envelope) ─────────
    def test_settings_legacy_unchanged(self):
        r = self.client.get("/settings", headers=self.token)
        self.assertEqual(set(r.json().keys()), {"ok", "settings", "warnings", "revision"})

    def test_settings_v1_envelope(self):
        r = self.client.get("/settings", headers={**self.token, **V1})
        env = r.json()
        self.assertEqual(env["type"], "settings")
        self.assertEqual(env["sensitivity"], "personal")
        self.assertIn("settings", env["payload"])
        self.assertIn("revision", env["payload"])

    def test_launcher_apps_v1_envelope(self):
        r = self.client.get("/launcher/apps", headers={**self.token, **V1})
        self.assertEqual(r.json()["type"], "launcher")
        self.assertIn("apps", r.json()["payload"])

    def test_protected_route_still_403_without_token(self):
        r = self.client.get("/settings", headers=V1)  # V1 angefragt, aber kein Token
        self.assertEqual(r.status_code, 403)  # Auth bleibt maßgeblich

    # ── REST-Broadcast teilt die Request-Correlation ─────────────────────────
    def test_app_open_broadcast_shares_request_correlation(self):
        events = []

        async def record(payload):
            events.append(payload)

        self.runtime.connections.register(record, ["jarvis.v1"])  # V1-Empfänger
        r = self.client.post("/commands/app/open", json={"app": "unbekannt"},
                             headers={**self.token, **V1, "X-Jarvis-Correlation-ID": _UUID})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["correlation_id"], _UUID)  # REST-Response
        app_events = [e for e in events if e.get("type") == "app_event"]
        self.assertEqual(len(app_events), 1)
        self.assertEqual(app_events[0]["correlation_id"], _UUID)  # Broadcast = gleiche Correlation


if __name__ == "__main__":
    unittest.main()

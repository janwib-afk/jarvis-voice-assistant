"""Slice 5 (RFC-0005/Phase 4H) — SEAM-MIXED-WIRE: gemischte Legacy-/V1-Clients + Broadcasts.

Echte parallele FastAPI-TestClient-WebSockets gegen EINE App (eigene Runtime + Temp-Config;
die eingecheckte Fixture bleibt unberührt). Ein REST-getriggerter Broadcast erreicht alle
Clients: Legacy-Empfänger byte-/shape-exakt, V1-Empfänger als Envelope; ein semantischer
Broadcast teilt Event-ID und Correlation, je Empfänger aber die eigene Session-ID.
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


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class MixedBroadcastTests(unittest.TestCase):
    def setUp(self):
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"
        with open(os.path.join(os.path.dirname(__file__), "fixtures", "config.test.json"),
                  encoding="utf-8") as f:
            base = json.loads(f.read())
        base.setdefault("apps", [])
        self.tmp = tempfile.mkdtemp(prefix="jarvis-mixed-")
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
        self.headers = {"X-Jarvis-Token": self.runtime.session_token}

    def tearDown(self):
        self._cm.__exit__(None, None, None)
        for n, v in self._saved_core.items():
            setattr(assistant_core, n, v)
        memory.configure(*self._saved_mem)
        (app_launcher.APPS, app_launcher.PROFILES,
         app_launcher.ACTIVE_PROFILE) = self._saved_apps
        if os.path.exists(self.cfg_path):
            os.remove(self.cfg_path)
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.pop("JARVIS_SKIP_STARTUP_REFRESH", None)

    def _conn(self, subprotocols=None):
        return self.client.websocket_connect(
            f"/ws?token={self.runtime.session_token}", headers={"origin": VALID_ORIGIN},
            subprotocols=subprotocols)

    def _trigger_app_event(self):
        # /commands/app/open broadcastet IMMER ein app_event (auch bei unbekannter App).
        r = self.client.post("/commands/app/open", json={"app": "kein-solches"},
                             headers=self.headers)
        self.assertEqual(r.status_code, 404)

    @staticmethod
    def _recv_app_event(sock, limit=5):
        for _ in range(limit):
            f = sock.receive_json()
            t = f.get("type") if "type" in f else f.get("type")
            if t == "app_event":
                return f
        raise AssertionError("app_event nicht empfangen")

    def test_legacy_and_v1_client_both_receive(self):
        with self._conn() as legacy, self._conn(["jarvis.v1"]) as v1:
            legacy.receive_json()  # legacy health
            v1.receive_json()      # v1 health envelope
            self._trigger_app_event()
            lf = self._recv_app_event(legacy)
            vf = self._recv_app_event(v1)
        # Legacy-Empfänger: exakte Legacy-Shape.
        self.assertEqual(set(lf.keys()), {"type", "ok", "app", "name", "message", "ts"})
        self.assertNotIn("protocol_version", lf)
        # V1-Empfänger: Envelope.
        self.assertEqual(vf["protocol_version"], 1)
        self.assertEqual(vf["type"], "app_event")
        self.assertEqual(vf["payload"]["ok"], False)

    def test_two_v1_clients_share_event_id_distinct_session(self):
        with self._conn(["jarvis.v1"]) as a, self._conn(["jarvis.v1"]) as b:
            a.receive_json()
            b.receive_json()
            self._trigger_app_event()
            ea = self._recv_app_event(a)
            eb = self._recv_app_event(b)
        self.assertEqual(ea["event_id"], eb["event_id"])           # gemeinsame Event-ID
        self.assertEqual(ea["correlation_id"], eb["correlation_id"])  # gemeinsame Correlation
        self.assertNotEqual(ea["session_id"], eb["session_id"])    # eigene Session-ID

    def test_dead_connection_removed_others_still_receive(self):
        with self._conn(["jarvis.v1"]) as a:
            a.receive_json()
            with self._conn(["jarvis.v1"]) as b:
                b.receive_json()
            # b ist geschlossen; ein Broadcast erreicht a weiterhin, ohne Fehler.
            self._trigger_app_event()
            ea = self._recv_app_event(a)
        self.assertEqual(ea["type"], "app_event")


if __name__ == "__main__":
    unittest.main()

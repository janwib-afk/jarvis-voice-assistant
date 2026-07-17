"""Slice 1 (RFC-0005 / Phase 4H) — GOLDEN-Charakterisierung der Legacy-Wire-Contracts.

Diese Tests fixieren den HEUTIGEN, untypisierten Legacy-Vertrag über die ÖFFENTLICHEN
Seams (echter WS-Dialog, echte REST-Routen), damit der Codec-Refactor (Slice 2/3) ihn
byte-/shape-exakt bewahren kann. Charakterisierungstests — sie sind erwartungsgemäß
bereits grün (kein vorgetäuschtes TDD-RED).

Erwartete Shapes stammen aus docs/contracts/WEBSOCKET_PROTOCOL.md und
docs/contracts/REST_CONTRACTS.md, nicht aus der Implementierung nachgebaut. Es werden
NUR externe Providergrenzen ersetzt (ai/synthesize_speech); keine internen Module gemockt,
kein send_json/broadcast_json gepatcht. Die eingecheckte Fixture wird NICHT verändert
(mutierende Routen laufen gegen eine eigene Temp-Config).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  — synthetische Fixture vor 'import server'

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


class _FakeMessages:
    def __init__(self, replies):
        self._replies = list(replies)

    async def create(self, **kwargs):
        item = self._replies.pop(0)
        if isinstance(item, BaseException):
            raise item
        return SimpleNamespace(content=[SimpleNamespace(text=item)])


class _FakeAI:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


# ── WS-Frames (SEAM-CONVERSATION auf server.app; keine Config-Mutation) ───────

@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class LegacyWsFrameGoldenTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        # Token autoritativ aus DERSELBEN App (server.SESSION_TOKEN kann durch andere
        # Testklassen mit eigener Runtime-Lifespan veralten).
        self.token = server.app.state.runtime.session_token
        self.spoken = []

        async def fake_synth(text):
            self.spoken.append(text)
            return b"", None

        self._synth = mock.patch.object(assistant_core, "synthesize_speech", fake_synth)
        self._synth.start()
        self.tmp = tempfile.mkdtemp(prefix="jarvis-golden-")
        self._saved_mem = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path=self.tmp, inbox_path=self.tmp)

    def tearDown(self):
        self._synth.stop()
        memory.configure(*self._saved_mem)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _use_ai(self, replies):
        p = mock.patch.object(assistant_core, "ai", _FakeAI(replies))
        p.start()
        self.addCleanup(p.stop)

    def _connect(self):
        return self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN})

    def test_health_frame_is_exact_shape(self):
        with self._connect() as sock:
            frame = sock.receive_json()
        self.assertEqual(set(frame.keys()), {"type", "warnings"})
        self.assertEqual(frame["type"], "health")
        self.assertIsInstance(frame["warnings"], list)

    def test_response_frame_is_exact_shape(self):
        self._use_ai(["Klar, erledigt."])
        with self._connect() as sock:
            sock.receive_json()  # health
            sock.send_json({"text": "sag bescheid"})
            frame = sock.receive_json()
        self.assertEqual(set(frame.keys()), {"type", "text", "audio"})
        self.assertEqual(frame["type"], "response")
        self.assertEqual(frame["text"], "Klar, erledigt.")
        self.assertIsInstance(frame["audio"], str)

    def test_action_frame_shape_and_epoch_ts(self):
        self._use_ai(["[ACTION:MEMORY_READ]", "Nichts gemerkt."])
        with self._connect() as sock:
            sock.receive_json()  # health
            sock.send_json({"text": "was hast du gemerkt?"})
            frame = sock.receive_json()  # action start
        self.assertEqual(set(frame.keys()),
                         {"type", "phase", "action", "label", "detail", "ts"})
        self.assertEqual(frame["type"], "action")
        self.assertEqual(frame["phase"], "start")
        self.assertEqual(frame["action"], "MEMORY_READ")
        # Legacy-ts ist ein Epoch-Float (KEIN RFC3339-String).
        self.assertIsInstance(frame["ts"], float)
        self.assertGreater(frame["ts"], 1_000_000_000)

    def test_error_frame_is_exact_shape(self):
        self._use_ai([RuntimeError("provider kaputt")])
        with self._connect() as sock:
            sock.receive_json()  # health
            sock.send_json({"text": "hallo"})
            frame = sock.receive_json()
        self.assertEqual(set(frame.keys()), {"type", "component", "text", "hint"})
        self.assertEqual(frame["type"], "error")
        self.assertEqual(frame["component"], "llm")

    def test_stop_frame_is_exact_shape_without_active_task(self):
        with self._connect() as sock:
            sock.receive_json()  # health
            sock.send_json({"type": "stop"})
            frame = sock.receive_json()
        self.assertEqual(frame, {"type": "stop"})


# ── Broadcasts + mutierende REST (eigene Runtime + Temp-Config) ───────────────

@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class LegacyBroadcastAndRestGoldenTests(unittest.TestCase):
    """Eigene Runtime mit Temp-Config (Fixture bleibt unberührt). Ein WS-Client
    beobachtet die drei REST-getriggerten Broadcast-Frames."""

    def setUp(self):
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"
        self.music_dir = tempfile.mkdtemp(prefix="jarvis-golden-music-")
        with open(os.path.join(self.music_dir, "song.mp3"), "w", encoding="utf-8") as f:
            f.write("x")
        with open(os.path.join(os.path.dirname(__file__), "fixtures", "config.test.json"),
                  encoding="utf-8") as _f:
            base = json.loads(_f.read())
        base["music_folder"] = self.music_dir
        base.setdefault("apps", [])
        if not base["apps"]:
            base["apps"] = [{"id": "editor", "name": "Editor", "type": "url",
                             "command": "https://example.com"}]
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
        shutil.rmtree(self.music_dir, ignore_errors=True)
        os.environ.pop("JARVIS_SKIP_STARTUP_REFRESH", None)

    def _ws(self):
        return self.client.websocket_connect(
            f"/ws?token={self.runtime.session_token}", headers={"origin": VALID_ORIGIN})

    @staticmethod
    def _recv_until(sock, frame_type, limit=6):
        """Zwischengeschaltete health-Re-Broadcasts überspringen und den Ziel-Frame liefern."""
        for _ in range(limit):
            frame = sock.receive_json()
            if frame.get("type") == frame_type:
                return frame
        raise AssertionError(f"Frame '{frame_type}' nicht empfangen")

    def test_music_changed_broadcast_shape(self):
        with self._ws() as sock:
            sock.receive_json()  # health
            r = self.client.post("/music/selection", json={"file": "song.mp3"},
                                 headers=self.headers)
            self.assertEqual(r.status_code, 200)
            frame = self._recv_until(sock, "music_changed")
        self.assertEqual(set(frame.keys()), {"type", "selected", "ts"})
        self.assertEqual(frame["type"], "music_changed")
        self.assertEqual(frame["selected"], "song.mp3")
        self.assertIsInstance(frame["ts"], float)

    def test_app_event_broadcast_shape(self):
        with self._ws() as sock:
            sock.receive_json()  # health
            r = self.client.post("/commands/app/open", json={"app": "kein-solches-app"},
                                 headers=self.headers)
            self.assertEqual(r.status_code, 404)
            frame = self._recv_until(sock, "app_event")
        self.assertEqual(set(frame.keys()), {"type", "ok", "app", "name", "message", "ts"})
        self.assertEqual(frame["type"], "app_event")
        self.assertFalse(frame["ok"])
        self.assertIsNone(frame["app"])
        self.assertIsInstance(frame["ts"], float)

    def test_launcher_changed_broadcast_shape(self):
        with self._ws() as sock:
            sock.receive_json()  # health
            r = self.client.post("/launcher/profiles/default/activate", headers=self.headers)
            self.assertEqual(r.status_code, 200)
            frame = self._recv_until(sock, "launcher_changed")
        self.assertEqual(set(frame.keys()), {"type", "kind", "active_profile", "ts"})
        self.assertEqual(frame["type"], "launcher_changed")
        self.assertIsInstance(frame["ts"], float)

    # ── REST-Kernverträge ────────────────────────────────────────────────────
    def test_health_is_public_and_shape_locked(self):
        r = self.client.get("/health")  # ohne Token
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(set(body.keys()), {"ok", "warnings", "services", "startup"})
        self.assertEqual(set(body["services"].keys()),
                         {"config", "llm", "tts", "browser", "vault"})

    def test_settings_get_carries_revision(self):
        r = self.client.get("/settings", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(set(body.keys()), {"ok", "settings", "warnings", "revision"})
        self.assertTrue(body["revision"])

    def test_settings_post_stale_ifmatch_conflicts_409(self):
        rev = self.client.get("/settings", headers=self.headers).json()["revision"]
        # erste Änderung zieht die Revision weiter
        self.client.post("/settings", json={"city": "Bremen"}, headers=self.headers)
        # zweite mit veralteter Revision -> 409 conflict
        h = dict(self.headers); h["If-Match"] = rev
        r = self.client.post("/settings", json={"city": "Kiel"}, headers=h)
        self.assertEqual(r.status_code, 409)
        body = r.json()
        self.assertFalse(body["ok"])
        self.assertTrue(body.get("conflict"))

    def test_protected_routes_reject_without_token_403(self):
        for method, path in [("get", "/settings"), ("get", "/dashboard/state"),
                             ("get", "/launcher/apps"), ("get", "/launcher/profiles"),
                             ("post", "/commands/app/open")]:
            r = getattr(self.client, method)(path)
            self.assertEqual(r.status_code, 403, f"{method} {path}")
            self.assertEqual(r.json(), {"ok": False, "errors": ["Nicht autorisiert."]})


if __name__ == "__main__":
    unittest.main()

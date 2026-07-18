"""Slice 4 (RFC-0005/Phase 4H) — SEAM-WS/SEAM-CONVERSATION: versionierter WS-Transport.

Echter FastAPI-TestClient-Handshake mit `Sec-WebSocket-Protocol: jarvis.v1`; nur die
externen Providergrenzen (ai/synthesize_speech) werden ersetzt. Beobachtet werden die
vollständig serialisierten V1-Envelopes bzw. der Legacy-Fallback.
"""
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401

try:
    import server
    import assistant_core
    import memory
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    _IMPORT_ERROR = None
except BaseException as e:
    server = assistant_core = memory = TestClient = None
    WebSocketDisconnect = Exception
    _IMPORT_ERROR = e

VALID_ORIGIN = "http://127.0.0.1:8340"
_UUID = "123e4567-e89b-42d3-a456-426614174000"


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


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class V1WebSocketTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.token = server.app.state.runtime.session_token
        self.spoken = []

        async def fake_synth(text):
            self.spoken.append(text)
            return b"", None

        self._synth = mock.patch.object(assistant_core, "synthesize_speech", fake_synth)
        self._synth.start()
        self.tmp = tempfile.mkdtemp(prefix="jarvis-v1-")
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

    def _v1(self):
        return self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN},
            subprotocols=["jarvis.v1"])

    def _legacy(self):
        return self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN})

    # ── Aushandlung ──────────────────────────────────────────────────────────
    def test_v1_immediate_health_is_envelope(self):
        with self._v1() as sock:
            env = sock.receive_json()
        self.assertEqual(env["protocol_version"], 1)
        self.assertEqual(env["type"], "health")
        self.assertEqual(env["sensitivity"], "public")  # redigierte oeffentliche Projektion
        self.assertIn("event_id", env)
        self.assertIn("session_id", env)
        self.assertIn("timestamp", env)
        self.assertIn("warnings_count", env["payload"])  # keine rohen (pfadhaltigen) Warnungen
        self.assertNotIn("warnings", env["payload"])

    def test_no_subprotocol_is_legacy_health(self):
        with self._legacy() as sock:
            frame = sock.receive_json()
        self.assertEqual(set(frame.keys()), {"type", "warnings"})  # exakt Legacy
        self.assertEqual(frame["type"], "health")

    def test_unsupported_only_version_is_rejected(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(
                    f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN},
                    subprotocols=["jarvis.v2"]):
                pass

    # ── Command-Decode + Correlation ─────────────────────────────────────────
    def test_v1_say_text_correlation_mirrored(self):
        self._use_ai(["Klar, erledigt."])
        with self._v1() as sock:
            sock.receive_json()  # health
            sock.send_json({"protocol_version": 1, "type": "say_text",
                            "correlation_id": _UUID, "payload": {"text": "sag bescheid"}})
            env = sock.receive_json()
        self.assertEqual(env["type"], "response")
        self.assertEqual(env["correlation_id"], _UUID)  # gültige Client-ID gespiegelt
        self.assertEqual(env["payload"]["text"], "Klar, erledigt.")
        self.assertEqual(env["sensitivity"], "personal")

    def test_v1_stop_yields_stopack_envelope(self):
        with self._v1() as sock:
            sock.receive_json()  # health
            sock.send_json({"protocol_version": 1, "type": "stop", "payload": {}})
            env = sock.receive_json()
        self.assertEqual(env["type"], "stop")
        self.assertEqual(env["protocol_version"], 1)

    def test_v1_action_correlation_across_all_events(self):
        # Alle Events eines Commands teilen die Correlation-ID.
        self._use_ai(["[ACTION:MEMORY_READ]", "Nichts gemerkt."])
        with self._v1() as sock:
            sock.receive_json()  # health
            sock.send_json({"protocol_version": 1, "type": "say_text",
                            "correlation_id": _UUID, "payload": {"text": "was gemerkt?"}})
            a1 = sock.receive_json()  # action start
            a2 = sock.receive_json()  # action done
            r = sock.receive_json()   # response summary
        for env in (a1, a2, r):
            self.assertEqual(env["correlation_id"], _UUID)
        self.assertEqual((a1["type"], a1["payload"]["phase"]), ("action", "start"))
        self.assertEqual((a2["type"], a2["payload"]["phase"]), ("action", "done"))

    # ── Session-Semantik ─────────────────────────────────────────────────────
    def test_session_id_stable_within_connection(self):
        self._use_ai(["Antwort."])
        with self._v1() as sock:
            h = sock.receive_json()
            sock.send_json({"protocol_version": 1, "type": "say_text",
                            "payload": {"text": "hi"}})
            r = sock.receive_json()
        self.assertEqual(h["session_id"], r["session_id"])
        self.assertTrue(h["session_id"])

    def test_two_connections_have_distinct_session_ids(self):
        with self._v1() as s1:
            e1 = s1.receive_json()
            with self._v1() as s2:
                e2 = s2.receive_json()
        self.assertNotEqual(e1["session_id"], e2["session_id"])

    # ── Spoofing wird abgelehnt ──────────────────────────────────────────────
    def test_client_cannot_spoof_server_fields(self):
        with self._v1() as sock:
            sock.receive_json()  # health
            sock.send_json({"protocol_version": 1, "type": "say_text",
                            "event_id": "geklaut", "session_id": "geklaut",
                            "payload": {"text": "hi"}})
            env = sock.receive_json()
        self.assertEqual(env["type"], "error")
        self.assertEqual(env["payload"]["code"], "reserved_field")

    def test_unknown_major_version_closes_1002(self):
        with self._v1() as sock:
            sock.receive_json()  # health
            sock.send_json({"protocol_version": 2, "type": "say_text",
                            "payload": {"text": "hi"}})
            env = sock.receive_json()
            self.assertEqual(env["payload"]["code"], "unsupported_version")
            with self.assertRaises(WebSocketDisconnect):
                sock.receive_json()  # Verbindung wird geschlossen (1002)


if __name__ == "__main__":
    unittest.main()

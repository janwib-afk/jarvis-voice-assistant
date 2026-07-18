"""Slice 9 (RFC-0005/Phase 4H) — Fault-/Size-Matrix über die echten Transporte.

WS-Frame-Größen-/Malformed-Vertrag (A1.C) und REST-Body-Limit. Nur externe
Providergrenzen ersetzt; echte Handshakes/Routen.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401

try:
    import server
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    _IMPORT_ERROR = None
except BaseException as e:
    server = TestClient = None
    WebSocketDisconnect = Exception
    _IMPORT_ERROR = e

VALID_ORIGIN = "http://127.0.0.1:8340"


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class WsFaultTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.token = server.app.state.runtime.session_token

    def _v1(self):
        return self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN},
            subprotocols=["jarvis.v1"])

    def test_malformed_json_closes_1007_with_error(self):
        with self._v1() as sock:
            sock.receive_json()  # health
            sock.send_text("{ das ist kein JSON")
            env = sock.receive_json()
            self.assertEqual(env["payload"]["code"], "malformed_json")
            with self.assertRaises(WebSocketDisconnect) as ctx:
                sock.receive_json()
        self.assertEqual(ctx.exception.code, 1007)

    def test_oversize_frame_closes_1009(self):
        with self._v1() as sock:
            sock.receive_json()  # health
            sock.send_text("x" * (64 * 1024 + 1))
            env = sock.receive_json()
            self.assertEqual(env["payload"]["code"], "too_large")
            with self.assertRaises(WebSocketDisconnect) as ctx:
                sock.receive_json()
        self.assertEqual(ctx.exception.code, 1009)

    def test_oversize_say_text_is_rejected(self):
        with self._v1() as sock:
            sock.receive_json()  # health
            sock.send_json({"protocol_version": 1, "type": "say_text",
                            "payload": {"text": "a" * (16 * 1024 + 1)}})
            env = sock.receive_json()
            self.assertEqual(env["payload"]["code"], "too_large")

    def test_unknown_command_stays_open_with_error(self):
        with self._v1() as sock:
            sock.receive_json()  # health
            sock.send_json({"protocol_version": 1, "type": "fliegen", "payload": {}})
            env = sock.receive_json()
            self.assertEqual(env["payload"]["code"], "unknown_command")
            # Verbindung bleibt offen -> ein gültiger Stop kommt noch durch.
            sock.send_json({"protocol_version": 1, "type": "stop", "payload": {}})
            self.assertEqual(sock.receive_json()["type"], "stop")


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class RestFaultTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.headers = {"X-Jarvis-Token": server.app.state.runtime.session_token,
                        "Accept": "application/vnd.jarvis.v1+json"}

    def test_oversize_v1_body_is_413(self):
        big = {"app": "x" * (1024 * 1024 + 100)}
        r = self.client.post("/commands/app/open", json=big, headers=self.headers)
        self.assertEqual(r.status_code, 413)
        self.assertEqual(r.json()["payload"]["code"], "too_large")


if __name__ == "__main__":
    unittest.main()

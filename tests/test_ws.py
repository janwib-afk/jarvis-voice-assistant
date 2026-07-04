"""
Praktischer WebSocket-Handshake-Test gegen die echte App (Starlette TestClient).

Prueft nur das Auth-Gate (Origin + Token) — es wird **keine** Nachricht gesendet,
also kein LLM-/TTS-Aufruf ausgeloest. Falls die Umgebung den Import von ``server``
nicht erlaubt (z.B. fehlende/ungueltige config.json), wird der Test sauber
uebersprungen statt fehlzuschlagen.

Hinweis: Der Server sendet direkt nach dem Accept einen ``health``-Frame.
Tests, die eine Antwort auf ``{text}`` lesen wollen, muessen diesen Frame
zuerst abholen.

    python -m unittest discover -s tests
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import server
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    TestClient = None
    WebSocketDisconnect = Exception
    _IMPORT_ERROR = e

VALID_ORIGIN = "http://127.0.0.1:8340"


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class WebSocketHandshakeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.token = server.SESSION_TOKEN

    def test_foreign_origin_rejected(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(
                f"/ws?token={self.token}", headers={"origin": "http://evil.example.com"}
            ):
                pass

    def test_bad_token_rejected(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(
                "/ws?token=wrong-token", headers={"origin": VALID_ORIGIN}
            ):
                pass

    def test_missing_token_rejected(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws", headers={"origin": VALID_ORIGIN}):
                pass

    def test_valid_origin_and_token_accepted(self):
        # Verbindung wird akzeptiert; sofort schliessen, keine Nachricht senden.
        with self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN}
        ):
            pass

    def test_null_origin_with_token_accepted(self):
        # pywebview/WebView2-Randfall: 'null' wird mit gueltigem Token akzeptiert.
        with self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": "null"}
        ):
            pass

    def test_null_origin_without_token_rejected(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws?token=wrong", headers={"origin": "null"}):
                pass

    def test_health_frame_sent_on_connect(self):
        with self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN}
        ) as websocket:
            data = websocket.receive_json()
            self.assertEqual(data["type"], "health")
            self.assertIsInstance(data["warnings"], list)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class HealthEndpointTests(unittest.TestCase):
    def test_health_endpoint(self):
        client = TestClient(server.app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertIsInstance(body["warnings"], list)

    def test_health_reports_services_and_startup(self):
        client = TestClient(server.app)
        body = client.get("/health").json()
        self.assertEqual(
            set(body["services"]), {"config", "llm", "tts", "browser", "vault"}
        )
        for name, svc in body["services"].items():
            self.assertIsInstance(svc["ok"], bool, f"services.{name}.ok")
        self.assertIsInstance(body["startup"]["data_loaded"], bool)
        # last_refresh ist None bis zum ersten refresh_data-Lauf, danach float.
        self.assertIn("last_refresh", body["startup"])


class _StubWS:
    """Faengt send_json-Frames ab, ohne eine echte WS-Verbindung zu brauchen."""

    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class FrameShapeTests(unittest.TestCase):
    def test_send_error_shape(self):
        stub = _StubWS()
        asyncio.run(server.send_error(stub, "tts", "Sprachausgabe fehlgeschlagen.", "Status 401"))
        self.assertEqual(stub.sent, [{
            "type": "error",
            "component": "tts",
            "text": "Sprachausgabe fehlgeschlagen.",
            "hint": "Status 401",
        }])

    def test_send_action_event_shape(self):
        stub = _StubWS()
        asyncio.run(server.send_action_event(stub, "start", "SEARCH", "wetter hamburg"))
        (frame,) = stub.sent
        self.assertEqual(frame["type"], "action")
        self.assertEqual(frame["phase"], "start")
        self.assertEqual(frame["action"], "SEARCH")
        self.assertEqual(frame["label"], "Websuche")
        self.assertEqual(frame["detail"], "wetter hamburg")
        self.assertIsInstance(frame["ts"], float)


if __name__ == "__main__":
    unittest.main()

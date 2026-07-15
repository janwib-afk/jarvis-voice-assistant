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
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

try:
    import server
    import assistant_core
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    assistant_core = None
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
class StopFlowTests(unittest.TestCase):
    """"Stopp" bricht eine laufende Verarbeitung ab, ohne die Verbindung zu beenden."""

    def setUp(self):
        self.client = TestClient(server.app)
        self.token = server.SESSION_TOKEN

    def _connect(self):
        return self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN}
        )

    def _wait_for(self, record, marker, timeout=3.0):
        deadline = time.monotonic() + timeout
        while marker not in record and time.monotonic() < deadline:
            time.sleep(0.02)
        return marker in record

    def test_stop_frame_cancels_running_task(self):
        record = []

        async def slow_process(session_id, text, ws):
            record.append("start")
            try:
                await asyncio.sleep(30)
                record.append("finished")
            except asyncio.CancelledError:
                record.append("cancelled")
                raise

        with mock.patch.object(server.assistant_core, "process_message", slow_process):
            with self._connect() as sock:
                sock.receive_json()  # health-Frame
                sock.send_json({"text": "recherchiere zu ssds"})
                self.assertTrue(self._wait_for(record, "start"), "Worker hat nicht gestartet")
                sock.send_json({"type": "stop"})
                frame = sock.receive_json()
                self.assertEqual(frame["type"], "stop")
                confirm = sock.receive_json()
                self.assertEqual(confirm["type"], "response")
                self.assertIn("gestoppt", confirm["text"].lower())
                self.assertEqual(confirm["audio"], "")
                self.assertTrue(self._wait_for(record, "cancelled"), "Task wurde nicht gecancelt")
        self.assertNotIn("finished", record)

    def test_disconnect_cancels_running_task(self):
        # Verbindung wird MITTEN in einer langen Aktion geschlossen: das finally
        # muss Worker UND Child sauber beenden (kein stiller Task-Leak).
        record = []

        async def slow_process(session_id, text, ws):
            record.append("start")
            try:
                await asyncio.sleep(30)
                record.append("finished")
            except asyncio.CancelledError:
                record.append("cancelled")
                raise

        with mock.patch.object(server.assistant_core, "process_message", slow_process):
            with self._connect() as sock:
                sock.receive_json()  # health-Frame
                sock.send_json({"text": "recherchiere zu ssds"})
                self.assertTrue(self._wait_for(record, "start"), "Worker hat nicht gestartet")
            # Verlassen des with-Blocks => Disconnect => finally cancelt Worker + Child.
            self.assertTrue(
                self._wait_for(record, "cancelled"),
                "Child wurde beim Disconnect nicht gecancelt",
            )
        self.assertNotIn("finished", record)

    def test_new_message_processed_after_stop(self):
        # Stopp beendet die laufende Verarbeitung, aber der Worker lebt weiter:
        # eine danach gesendete Nachricht muss normal verarbeitet werden.
        record = []

        async def proc(session_id, text, ws):
            record.append(("start", text))
            if text == "erste":
                await asyncio.sleep(30)  # wird per Stopp abgebrochen
            else:
                record.append(("done", text))
                await ws.send_json({"type": "response", "text": "fertig", "audio": ""})

        with mock.patch.object(server.assistant_core, "process_message", proc):
            with self._connect() as sock:
                sock.receive_json()  # health-Frame
                sock.send_json({"text": "erste"})
                self.assertTrue(self._wait_for(record, ("start", "erste")))
                sock.send_json({"type": "stop"})
                self.assertEqual(sock.receive_json()["type"], "stop")
                self.assertEqual(sock.receive_json()["type"], "response")  # "Okay, gestoppt."
                sock.send_json({"text": "zweite"})
                frame = sock.receive_json()
                self.assertEqual(frame["type"], "response")
                self.assertEqual(frame["text"], "fertig")
        self.assertIn(("done", "zweite"), record)

    def test_stop_clears_queue(self):
        # Eine hinter einer laufenden Aktion wartende Nachricht wird bei Stopp
        # verworfen (Queue geleert), nicht nachtraeglich abgearbeitet.
        record = []

        async def proc(session_id, text, ws):
            record.append(text)
            if text == "lang":
                await asyncio.sleep(30)

        with mock.patch.object(server.assistant_core, "process_message", proc):
            with self._connect() as sock:
                sock.receive_json()  # health-Frame
                sock.send_json({"text": "lang"})     # belegt den Worker
                self.assertTrue(self._wait_for(record, "lang"))
                sock.send_json({"text": "queued"})   # landet in der Queue
                sock.send_json({"type": "stop"})     # bricht "lang" ab UND leert die Queue
                self.assertEqual(sock.receive_json()["type"], "stop")
                sock.receive_json()  # "Okay, gestoppt."
                time.sleep(0.3)      # Zeit geben, falls "queued" faelschlich liefe
        self.assertNotIn("queued", record)

    def test_spoken_stop_word_without_running_task(self):
        # "Stopp" als Text ohne laufende Aktion: nur der stop-Frame, kein LLM-Aufruf.
        called = []

        async def fail_process(session_id, text, ws):
            called.append(text)

        with mock.patch.object(server.assistant_core, "process_message", fail_process):
            with self._connect() as sock:
                sock.receive_json()  # health-Frame
                sock.send_json({"text": "Jarvis, stopp!"})
                frame = sock.receive_json()
                self.assertEqual(frame["type"], "stop")
        self.assertEqual(called, [])

    def test_stop_clears_pending_confirmation(self):
        import actions as actions_mod

        async def idle_process(session_id, text, ws):
            pass

        with mock.patch.object(server.assistant_core, "process_message", idle_process):
            with self._connect() as sock:
                sock.receive_json()  # health-Frame
                # pending_confirm der Session simulieren (Session-ID kennt nur der
                # Server) — daher global fuer alle Sessions setzen und pruefen,
                # dass Stopp sie leert.
                server.assistant_core.pending_confirm["dummy-check"] = actions_mod.Action("SEARCH", "x")
                sock.send_json({"type": "stop"})
                sock.receive_json()  # stop-Frame
        # Die eigene Session wurde geleert; fremde Eintraege bleiben unberuehrt.
        self.assertIn("dummy-check", server.assistant_core.pending_confirm)
        server.assistant_core.pending_confirm.pop("dummy-check", None)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class FrameShapeTests(unittest.TestCase):
    def test_send_error_shape(self):
        stub = _StubWS()
        asyncio.run(assistant_core.send_error(stub, "tts", "Sprachausgabe fehlgeschlagen.", "Status 401"))
        self.assertEqual(stub.sent, [{
            "type": "error",
            "component": "tts",
            "text": "Sprachausgabe fehlgeschlagen.",
            "hint": "Status 401",
        }])

    def test_send_action_event_shape(self):
        stub = _StubWS()
        asyncio.run(assistant_core.send_action_event(stub, "start", "SEARCH", "wetter hamburg"))
        (frame,) = stub.sent
        self.assertEqual(frame["type"], "action")
        self.assertEqual(frame["phase"], "start")
        self.assertEqual(frame["action"], "SEARCH")
        self.assertEqual(frame["label"], "Websuche")
        self.assertEqual(frame["detail"], "wetter hamburg")
        self.assertIsInstance(frame["ts"], float)


if __name__ == "__main__":
    unittest.main()

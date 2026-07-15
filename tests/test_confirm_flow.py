"""
Tests fuer den Bestaetigungs-Flow riskanter Aktionen (process_message +
pending_confirm in assistant_core). Ausfuehrung und Sprachausgabe werden
gestubbt — kein LLM-/TTS-/Browser-Aufruf.

    python -m unittest discover -s tests
"""
import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

try:
    import server  # verdrahtet assistant_core (configure/init_clients)
    import assistant_core
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    assistant_core = None
    _IMPORT_ERROR = e

import actions


class _StubWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


class _FailingAI:
    """Stellt sicher, dass kein echter LLM-Call rausgeht."""

    class messages:
        @staticmethod
        async def create(**kwargs):
            raise RuntimeError("LLM-Call im Test nicht erlaubt")


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class ConfirmFlowTests(unittest.TestCase):
    SID = "confirm-test-session"

    def setUp(self):
        self.ws = _StubWS()
        self.pending = actions.Action("SEARCH", "riskanter test")
        assistant_core.conversations[self.SID] = []
        assistant_core.pending_confirm[self.SID] = self.pending
        self.spoken = []
        self.executed = []

        async def fake_spoken(ws, text, display_text=None):
            self.spoken.append(text)

        async def fake_run(session_id, action, ws):
            self.executed.append(action)

        self._patches = [
            mock.patch.object(assistant_core, "send_spoken_response", fake_spoken),
            mock.patch.object(assistant_core, "run_action_and_respond", fake_run),
            mock.patch.object(assistant_core, "ai", _FailingAI()),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        assistant_core.end_session(self.SID)

    def test_yes_executes_pending_action(self):
        asyncio.run(assistant_core.process_message(self.SID, "Ja bitte", self.ws))
        self.assertEqual(self.executed, [self.pending])
        self.assertNotIn(self.SID, assistant_core.pending_confirm)

    def test_no_discards_pending_action(self):
        asyncio.run(assistant_core.process_message(self.SID, "Nein, lieber nicht", self.ws))
        self.assertEqual(self.executed, [])
        self.assertNotIn(self.SID, assistant_core.pending_confirm)
        self.assertTrue(any("lasse es bleiben" in t for t in self.spoken))

    def test_unrelated_text_discards_pending_and_processes_normally(self):
        # Weder Ja noch Nein: Aktion verfaellt, die Nachricht geht den normalen
        # Weg (hier: der gestubbte LLM-Call schlaegt fehl => error-Frame).
        asyncio.run(assistant_core.process_message(self.SID, "Wie ist das Wetter morgen in Hamburg?", self.ws))
        self.assertEqual(self.executed, [])
        self.assertNotIn(self.SID, assistant_core.pending_confirm)
        self.assertTrue(any(f.get("type") == "error" for f in self.ws.sent))


if __name__ == "__main__":
    unittest.main()

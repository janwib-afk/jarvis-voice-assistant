"""
Slice 1 (RFC-0006 / Phase 4J) — CHARAKTERISIERUNG des Ist-Verhaltens.

Diese Tests halten das HEUTIGE beobachtbare Verhalten fest, BEVOR der
Conversation-Zustand in ein explizites Session-/Turn-Modell wandert. Sie sind
charakterisierend und daher erwartungsgemaess von Anfang an gruen — es gibt hier
kein vorgetaeuschtes RED.

Beobachtet wird ausschliesslich ueber den echten ``/ws``-Dialog (SEAM-CONVERSATION):
kein internes Modul gemockt, kein ``conversations``/``pending_confirm``-Global
gesetzt, keine private Funktion gepatcht. Ersetzt werden nur externe Grenzen:
``ai`` (Anthropic), ``synthesize_speech`` (ElevenLabs) und ``browser_tools``
(Websuche) — 0 echte Provider-/Netzaufrufe.

Der wichtigste festgehaltene Vertrag ist die **Framefolge bei Action-Cancellation**
(Prompt-17 Praezisierung 7): bestehende Frames duerfen bei der Migration weder
still entfallen noch umsortiert werden.

    python -m unittest discover -s tests
"""
import asyncio
import os
import shutil
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt die synthetische Test-Config vor 'import server'

try:
    import server
    import assistant_core
    import browser_tools
    import memory
    from fastapi.testclient import TestClient
    _IMPORT_ERROR = None
except BaseException as e:
    server = assistant_core = browser_tools = memory = TestClient = None
    _IMPORT_ERROR = e

VALID_ORIGIN = "http://127.0.0.1:8340"


class _FakeMessages:
    def __init__(self, replies):
        self._replies = list(replies)

    async def create(self, **kwargs):
        if not self._replies:
            raise AssertionError("unerwarteter zusaetzlicher LLM-Call im Test")
        item = self._replies.pop(0)
        if isinstance(item, BaseException):
            raise item
        return SimpleNamespace(content=[SimpleNamespace(text=item)])


class _FakeAI:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class ConversationCharacterizationTests(unittest.TestCase):
    """Haelt Stop-, Queue-, Confirmation- und Cancellation-Vertraege fest."""

    def setUp(self):
        self.client = TestClient(server.app)
        self.token = server.app.state.runtime.session_token

        async def fake_synth(text):
            return b"", None

        p = mock.patch.object(assistant_core, "synthesize_speech", fake_synth)
        p.start()
        self.addCleanup(p.stop)

        self.tmp = tempfile.mkdtemp(prefix="jarvis-char-")
        saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path=self.tmp, inbox_path=self.tmp)
        self.addCleanup(lambda: memory.configure(*saved))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _use_ai(self, replies):
        p = mock.patch.object(assistant_core, "ai", _FakeAI(replies))
        p.start()
        self.addCleanup(p.stop)

    def _connect(self):
        return self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN})

    def _slow_search(self, started):
        """Ersetzt die externe Websuche durch eine kontrolliert langsame Variante."""
        async def _search(query, *a, **kw):
            started.append(query)
            await asyncio.sleep(30)      # wird vom Stop/Disconnect abgebrochen
            return "nie erreicht"
        return mock.patch.object(browser_tools, "search_and_read", _search)

    @staticmethod
    def _wait(pred, timeout=3.0):
        deadline = time.monotonic() + timeout
        while not pred() and time.monotonic() < deadline:
            time.sleep(0.02)
        return pred()

    # ── Cancellation-Framefolge (Praezisierung 7) ───────────────────────────
    def test_stop_during_action_frame_sequence(self):
        """IST-Vertrag (empirisch ermittelt, NICHT angenommen): Stop waehrend einer
        laufenden Action erzeugt genau diese Reihenfolge:

            1. action(start)
            2. stop
            3. action(error, detail='abgebrochen')
            4. response('Okay, gestoppt.')

        Der Abbruch-Frame der Action liegt ZWISCHEN Stop-Bestaetigung und
        'Okay, gestoppt.', weil ``await emit(StopAck)`` ein Yield-Punkt ist, an dem
        der gecancelte Task seinen Abbruchpfad ausfuehrt. Diese Reihenfolge darf die
        Migration weder umsortieren noch Frames entfernen (Praezisierung 7)."""
        self._use_ai(["[ACTION:SEARCH] ssd preise"])
        started = []
        with self._slow_search(started):
            with self._connect() as sock:
                self.assertEqual(sock.receive_json()["type"], "health")
                sock.send_json({"text": "suche ssd preise"})

                f_start = sock.receive_json()
                self.assertTrue(self._wait(lambda: bool(started)), "Action lief nicht an")
                sock.send_json({"type": "stop"})
                f_stop = sock.receive_json()
                f_err = sock.receive_json()
                f_resp = sock.receive_json()

        self.assertEqual((f_start["type"], f_start["phase"]), ("action", "start"))
        self.assertEqual(f_stop["type"], "stop")
        self.assertEqual((f_err["type"], f_err["phase"]), ("action", "error"))
        self.assertEqual(f_err["action"], "SEARCH")
        self.assertEqual(f_err["detail"], "abgebrochen")
        self.assertEqual(f_resp["type"], "response")
        self.assertIn("gestoppt", f_resp["text"].lower())
        self.assertEqual(f_resp["audio"], "")

    def test_disconnect_during_action_emits_no_further_frames(self):
        """IST-Vertrag: ein Disconnect waehrend der Action bricht sie ab, ohne dass
        der Client noch Frames sieht (Verbindung ist weg) — und ohne Task-Leak."""
        self._use_ai(["[ACTION:SEARCH] ssd preise"])
        started = []
        with self._slow_search(started):
            with self._connect() as sock:
                self.assertEqual(sock.receive_json()["type"], "health")
                sock.send_json({"text": "suche ssd preise"})
                self.assertEqual(sock.receive_json()["phase"], "start")
                self.assertTrue(self._wait(lambda: bool(started)))
            # Verlassen des with-Blocks = Disconnect.
        # Eine neue Verbindung ist danach sofort wieder voll nutzbar.
        self._use_ai(["Alles klar."])
        with self._connect() as sock2:
            self.assertEqual(sock2.receive_json()["type"], "health")
            sock2.send_json({"text": "geht es noch?"})
            self.assertEqual(sock2.receive_json()["text"], "Alles klar.")

    # ── Stop-Semantik ───────────────────────────────────────────────────────
    def test_stop_while_idle_is_ack_only(self):
        """IST-Vertrag: Stop ohne laufende Verarbeitung bestaetigt nur (stop-Frame)
        und sendet KEIN 'Okay, gestoppt.' — wiederholter Stop ist idempotent."""
        with self._connect() as sock:
            self.assertEqual(sock.receive_json()["type"], "health")
            sock.send_json({"type": "stop"})
            self.assertEqual(sock.receive_json()["type"], "stop")
            sock.send_json({"type": "stop"})
            self.assertEqual(sock.receive_json()["type"], "stop")
            # Kein weiterer Frame: die naechste echte Nachricht wird normal beantwortet.
            self._use_ai(["Bereit."])
            sock.send_json({"text": "hallo"})
            frame = sock.receive_json()
        self.assertEqual(frame["type"], "response")
        self.assertEqual(frame["text"], "Bereit.")

    def test_stop_drops_queued_message(self):
        """IST-Vertrag: eine hinter der laufenden Action wartende Nachricht wird
        beim Stop verworfen und NICHT nachtraeglich verarbeitet."""
        self._use_ai(["[ACTION:SEARCH] ssd preise", "Zweite Antwort."])
        started = []
        with self._slow_search(started):
            with self._connect() as sock:
                self.assertEqual(sock.receive_json()["type"], "health")
                sock.send_json({"text": "suche ssd preise"})
                self.assertEqual(sock.receive_json()["phase"], "start")
                self.assertTrue(self._wait(lambda: bool(started)))
                sock.send_json({"text": "diese nachricht wartet"})
                sock.send_json({"type": "stop"})
                self.assertEqual(sock.receive_json()["type"], "stop")
                self.assertEqual(sock.receive_json()["phase"], "error")      # abgebrochen
                self.assertEqual(sock.receive_json()["type"], "response")    # "Okay, gestoppt."
                # Die wartende Nachricht wurde verworfen: eine NEUE Nachricht wird
                # mit der naechsten LLM-Antwort beantwortet.
                sock.send_json({"text": "neu"})
                frame = sock.receive_json()
        self.assertEqual(frame["text"], "Zweite Antwort.")

    # ── Confirmation ────────────────────────────────────────────────────────
    def test_normal_message_lets_confirmation_expire_silently(self):
        """IST-Vertrag: eine normale Nachricht statt Ja/Nein laesst die offene
        Bestaetigung STILL verfallen — keine Absage, keine Ausfuehrung."""
        memory.append_memory("Projekt Zeta ist geheim.")
        mem_path = memory.memory_file_path()
        self._use_ai(["[ACTION:MEMORY_FORGET] Projekt Zeta", "Das Wetter ist gut."])
        with self._connect() as sock:
            self.assertEqual(sock.receive_json()["type"], "health")
            sock.send_json({"text": "vergiss Projekt Zeta"})
            self.assertIn("Ja oder Nein", sock.receive_json()["text"])
            sock.send_json({"text": "wie ist das wetter?"})
            frame = sock.receive_json()
        self.assertEqual(frame["type"], "response")
        self.assertEqual(frame["text"], "Das Wetter ist gut.")
        with open(mem_path, encoding="utf-8") as f:
            self.assertIn("Projekt Zeta", f.read())   # NICHT geloescht

    def test_stop_discards_open_confirmation(self):
        """IST-Vertrag: Stop verwirft die offene Bestaetigung — ein spaeteres 'Ja'
        fuehrt die Aktion NICHT mehr aus."""
        memory.append_memory("Projekt Zeta ist geheim.")
        mem_path = memory.memory_file_path()
        self._use_ai(["[ACTION:MEMORY_FORGET] Projekt Zeta", "Alles klar."])
        with self._connect() as sock:
            self.assertEqual(sock.receive_json()["type"], "health")
            sock.send_json({"text": "vergiss Projekt Zeta"})
            self.assertIn("Ja oder Nein", sock.receive_json()["text"])
            sock.send_json({"type": "stop"})
            self.assertEqual(sock.receive_json()["type"], "stop")
            sock.send_json({"text": "Ja"})
            frame = sock.receive_json()
        self.assertEqual(frame["type"], "response")
        self.assertEqual(frame["text"], "Alles klar.")
        with open(mem_path, encoding="utf-8") as f:
            self.assertIn("Projekt Zeta", f.read())   # NICHT geloescht

    # ── Reihenfolge ─────────────────────────────────────────────────────────
    def test_two_messages_are_processed_sequentially(self):
        """IST-Vertrag: zwei schnell aufeinanderfolgende Nachrichten werden strikt
        nacheinander beantwortet (genau ein Worker je Session)."""
        self._use_ai(["Antwort eins.", "Antwort zwei."])
        with self._connect() as sock:
            self.assertEqual(sock.receive_json()["type"], "health")
            sock.send_json({"text": "eins"})
            sock.send_json({"text": "zwei"})
            f1 = sock.receive_json()
            f2 = sock.receive_json()
        self.assertEqual(f1["text"], "Antwort eins.")
        self.assertEqual(f2["text"], "Antwort zwei.")


if __name__ == "__main__":
    unittest.main()

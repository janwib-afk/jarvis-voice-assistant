"""
SEAM-CONVERSATION — Integrationstests ueber den ECHTEN WebSocket-Dialog.

Diese Tests fahren den kompletten Gespraechsfluss ueber die reale ``/ws``-
Transportschicht (Starlette ``TestClient``) und beobachten AUSSCHLIESSLICH die
ausgehenden Frames. Es wird KEIN internes Modul gemockt, KEIN ``conversations``/
``pending_confirm``-Global gesetzt und KEINE interne Funktion gepatcht — nur die
externen Provider-Grenzen ``ai`` (Anthropic) und ``synthesize_speech``
(ElevenLabs) werden kontrolliert ersetzt. So gehen 0 echte API-/Netz-/
Provideraufrufe raus.

Vertraege: docs/contracts/WEBSOCKET_PROTOCOL.md, docs/contracts/
LEGACY_ACTION_PROTOCOL.md. Erwartete Werte stammen aus diesen Vertraegen
(response.text == gesprochener Teil; action-Frames start/done; error-Frame mit
component; Confirm vor Ausfuehrung), nicht aus der Implementierung nachgebaut.

Sensitivitaet: siehe Klassendocstring der einzelnen Tests — jeder Test enthaelt
einen kontrollierten Gegenbeweis (z.B. Vorher/Nachher-Zustand des Gedaechtnisses,
Fehler- vs. Antwort-Frame). Zusaetzlich wurde die Sensitivitaet einmalig mit einer
vollstaendig rueckgaengig gemachten Produktionsmutation belegt (dokumentiert in
docs/quality/TEST_SEAMS.md-Historie / Prompt-6-Bericht).

    python -m unittest discover -s tests
"""
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

try:
    import server  # verdrahtet assistant_core (configure/init_clients)
    import assistant_core
    import memory
    from fastapi.testclient import TestClient
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    assistant_core = None
    memory = None
    TestClient = None
    _IMPORT_ERROR = e

VALID_ORIGIN = "http://127.0.0.1:8340"


class _FakeMessages:
    """Liefert vordefinierte LLM-Antworten der Reihe nach; ein Eintrag, der eine
    Exception IST, wird beim Aufruf geworfen (Provider-Fehler simulieren)."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
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
class ConversationWsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.token = server.SESSION_TOKEN

        # TTS-Grenze ersetzen: kein echter ElevenLabs-Aufruf, deterministisch.
        self.spoken = []

        async def fake_synth(text):
            self.spoken.append(text)
            return b"", None  # audio="" -> kein Netz, deterministisch

        self._synth_patch = mock.patch.object(assistant_core, "synthesize_speech", fake_synth)
        self._synth_patch.start()

        # Isoliertes Gedaechtnis/Inbox im Tempdir — keine echten Vault-/Memory-Daten.
        self.tmp = tempfile.mkdtemp(prefix="jarvis-convo-")
        self._saved_mem = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path=self.tmp, inbox_path=self.tmp)

    def tearDown(self):
        self._synth_patch.stop()
        memory.configure(*self._saved_mem)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _use_ai(self, replies):
        """Provider-Grenze ``ai`` fuer diesen Test ersetzen (LIFO-Cleanup)."""
        patch = mock.patch.object(assistant_core, "ai", _FakeAI(replies))
        patch.start()
        self.addCleanup(patch.stop)

    def _connect(self):
        return self.client.websocket_connect(
            f"/ws?token={self.token}", headers={"origin": VALID_ORIGIN}
        )

    # ── Slice 4a: gesprochene Antwort als response-Frame ────────────────────
    def test_plain_reply_yields_response_frame(self):
        # Vertrag: LLM-Text ohne [ACTION] -> genau ein response-Frame, dessen
        # ``text`` der gesprochene Teil ist; ``audio``-Feld ist vorhanden.
        self._use_ai(["Klar, ich kuemmere mich darum."])
        with self._connect() as sock:
            self.assertEqual(sock.receive_json()["type"], "health")
            sock.send_json({"text": "Sag mir kurz Bescheid"})
            frame = sock.receive_json()
        self.assertEqual(frame["type"], "response")
        self.assertEqual(frame["text"], "Klar, ich kuemmere mich darum.")
        self.assertIn("audio", frame)  # Feld existiert (im Test leer)
        # Gegenbeweis: der gesprochene Teil lief durch die TTS-Grenze.
        self.assertIn("Klar, ich kuemmere mich darum.", self.spoken)

    # ── Slice 4b: Aktions-Lebenszyklus (start/done) + Zusammenfassung ────────
    def test_action_lifecycle_emits_start_done_and_summary(self):
        # Vertrag: [ACTION:MEMORY_READ] ohne Text davor -> kein erster response,
        # dann action(start) -> action(done) -> response(Zusammenfassung).
        self._use_ai(["[ACTION:MEMORY_READ]", "Ich habe dir noch nichts gemerkt."])
        with self._connect() as sock:
            self.assertEqual(sock.receive_json()["type"], "health")
            sock.send_json({"text": "Was hast du dir gemerkt?"})
            f1 = sock.receive_json()
            f2 = sock.receive_json()
            f3 = sock.receive_json()
        self.assertEqual((f1["type"], f1["phase"], f1["action"]), ("action", "start", "MEMORY_READ"))
        self.assertEqual((f2["type"], f2["phase"], f2["action"]), ("action", "done", "MEMORY_READ"))
        self.assertEqual(f3["type"], "response")
        self.assertEqual(f3["text"], "Ich habe dir noch nichts gemerkt.")

    # ── Slice 6: riskante Aktion erst nach muendlichem "Ja" ausfuehren ───────
    def test_forget_requires_confirmation_before_executing(self):
        # Vertrag (SI-7): MEMORY_FORGET (risk=confirm) wird NICHT ausgefuehrt,
        # bevor der Nutzer bestaetigt. Kontrollierter Gegenbeweis: das Gedaechtnis
        # bleibt vor dem "Ja" unveraendert und ist erst danach geloescht.
        memory.append_memory("Projekt Zeta ist streng geheim.")
        mem_path = memory.memory_file_path()
        self._use_ai(["[ACTION:MEMORY_FORGET] Projekt Zeta", "Erledigt, ich habe es vergessen."])
        with self._connect() as sock:
            self.assertEqual(sock.receive_json()["type"], "health")
            sock.send_json({"text": "vergiss Projekt Zeta"})
            question = sock.receive_json()
            self.assertEqual(question["type"], "response")
            self.assertIn("Ja oder Nein", question["text"])
            # NEGATIV: vor dem "Ja" ist nichts geloescht.
            with open(mem_path, encoding="utf-8") as f:
                self.assertIn("Projekt Zeta", f.read())

            sock.send_json({"text": "Ja, bitte"})
            frames = [sock.receive_json() for _ in range(3)]
        phases = [(f.get("type"), f.get("phase")) for f in frames]
        self.assertIn(("action", "start"), phases)
        self.assertIn(("action", "done"), phases)
        self.assertEqual(frames[-1]["type"], "response")
        # POSITIV: nach dem "Ja" ist der Eintrag hart geloescht.
        with open(mem_path, encoding="utf-8") as f:
            self.assertNotIn("Projekt Zeta", f.read())

    # ── Slice 10: Provider-Fehler -> error-Frame, Verbindung bleibt nutzbar ──
    def test_llm_failure_emits_error_frame_and_keeps_connection(self):
        # Vertrag: schlaegt der LLM-Call fehl, kommt ein strukturierter error-Frame
        # (component=llm) OHNE Roh-Exception; die Verbindung bleibt nutzbar (eine
        # zweite Nachricht wird normal beantwortet). Gegenbeweis: erste Nachricht =
        # error, zweite = response.
        self._use_ai([RuntimeError("interne-details-nicht-leaken"), "Zweite Antwort, alles gut."])
        with self._connect() as sock:
            self.assertEqual(sock.receive_json()["type"], "health")
            sock.send_json({"text": "Erste Frage"})
            err = sock.receive_json()
            self.assertEqual(err["type"], "error")
            self.assertEqual(err["component"], "llm")
            # Kein Roh-Exception-Text im Frame (keine internen Details leaken).
            blob = f"{err.get('text', '')} {err.get('hint', '')}"
            self.assertNotIn("interne-details-nicht-leaken", blob)

            sock.send_json({"text": "Zweite Frage"})
            ok = sock.receive_json()
            self.assertEqual(ok["type"], "response")
            self.assertEqual(ok["text"], "Zweite Antwort, alles gut.")


if __name__ == "__main__":
    unittest.main()

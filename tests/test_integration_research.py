"""
Integrationstest fuer den kompletten RESEARCH-Flow — ohne echte APIs.

Deckt den Weg ab, den eine echte Nutzernachricht nimmt:
  process_message -> LLM liefert [ACTION:RESEARCH] -> Quellen suchen/lesen ->
  Zusammenfassen -> Quellen anzeigen (aber nicht vorlesen) -> Autosave.

LLM, TTS und Browser sind vollstaendig gemockt; es geht kein Netz-/API-Aufruf
raus. Der Autosave landet in einem Tempdir und wird real geprueft.

    python -m unittest discover -s tests
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

import memory

try:
    import server  # verdrahtet assistant_core (configure/init_clients)
    import assistant_core
    import browser_tools
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    assistant_core = None
    browser_tools = None
    _IMPORT_ERROR = e


class _StubWS:
    """Faengt send_json-Frames ab, ohne echte WS-Verbindung."""

    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


class _FakeMessages:
    """Liefert vordefinierte LLM-Antworten der Reihe nach zurueck."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self._replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class _FakeAI:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


_SOURCES = [
    {"title": "EV-Studie 2026", "url": "https://example.com/ev-studie"},
    {"title": "Reichweite heute", "url": "https://example.org/reichweite"},
    {"title": "Akku-Preise", "url": "https://example.net/akkus"},
]


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class ResearchFlowIntegrationTests(unittest.IsolatedAsyncioTestCase):
    SID = "integration-research-session"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-integration-")
        self._saved_mem = (memory.VAULT_PATH, memory.INBOX_PATH)
        # Vault leer (isoliertes Memory), Inbox = Tempdir (Autosave real pruefbar).
        memory.configure(vault_path="", inbox_path=self.tmp)

        self.spoken = []  # alles, was tatsaechlich vertont werden sollte

        async def fake_synth(text):
            self.spoken.append(text)
            return b"FAKEAUDIO", None

        async def fake_search_links(query, limit=4):
            self.search_query = query
            return [dict(s) for s in _SOURCES]

        async def fake_visit(url, max_chars=5000):
            return {"title": f"Titel {url}", "url": url,
                    "content": f"Inhalt zu {url} rund um Elektroautos und Reichweite."}

        self.ai = _FakeAI([
            "Ich recherchiere das fuer dich. [ACTION:RESEARCH] Elektroautos",
            "Moderne Elektroautos sind alltagstauglicher und die Reichweite waechst stetig.",
        ])

        self._patches = [
            mock.patch.object(assistant_core, "ai", self.ai),
            mock.patch.object(assistant_core, "synthesize_speech", fake_synth),
            mock.patch.object(browser_tools, "search_links", fake_search_links),
            mock.patch.object(browser_tools, "visit", fake_visit),
        ]
        for p in self._patches:
            p.start()
        assistant_core.conversations[self.SID] = []

    def tearDown(self):
        for p in self._patches:
            p.stop()
        assistant_core.end_session(self.SID)
        memory.configure(*self._saved_mem)
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_full_research_flow(self):
        ws = _StubWS()
        await assistant_core.process_message(self.SID, "Recherchiere Elektroautos", ws)

        # Genau zwei LLM-Calls: die Hauptantwort + die Zusammenfassung (kein Dedup,
        # da der Recherche-Autosave dedup=False nutzt).
        self.assertEqual(len(self.ai.messages.calls), 2)

        # Der Anzeige-Text der finalen Antwort enthaelt die Quellenliste inkl. URLs.
        responses = [f for f in ws.sent if f.get("type") == "response"]
        self.assertTrue(responses, "keine response-Frames gesendet")
        display = responses[-1]["text"]
        self.assertIn("Quellen:", display)
        for src in _SOURCES:
            self.assertIn(src["url"], display)

        # Der GESPROCHENE Text enthaelt keine URLs (nur der Anzeige-Text hat sie).
        for spoken in self.spoken:
            self.assertNotIn("http", spoken.lower())

        # Autosave: die Recherche wurde real in die heutige Inbox-Datei geschrieben.
        inbox_file = os.path.join(self.tmp, f"{time.strftime('%Y-%m-%d')} Brain Dump.md")
        self.assertTrue(os.path.exists(inbox_file), "Autosave-Datei fehlt")
        with open(inbox_file, "r", encoding="utf-8") as f:
            saved = f.read()
        self.assertIn("Elektroautos", saved)
        self.assertIn("Quellen:", saved)


if __name__ == "__main__":
    unittest.main()

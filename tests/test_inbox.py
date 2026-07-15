"""
Tests fuer die Inbox-Helfer in memory.py: kategorisierte Eintraege,
Tages-Inbox lesen, Recherche-Nachbereitung und Sitzungsprotokoll.

Alle Tests arbeiten mit einem Temp-Ordner als Inbox — kein LLM-/TTS-Aufruf
(``dedup=False`` bzw. leere Bestandsdatei ueberspringen den Dedup-Check).

    python -m unittest discover -s tests
"""
import asyncio
import os
import shutil
import sys
import tempfile
import time
import unittest

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
import memory


class WriteInboxEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-inbox-")
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path="", inbox_path=self.tmp)

    def tearDown(self):
        memory.configure(*self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _today_file(self):
        return os.path.join(self.tmp, f"{time.strftime('%Y-%m-%d')} Brain Dump.md")

    def test_entry_has_category_heading_and_tag(self):
        result = asyncio.run(memory.write_inbox_entry("Zahnarzt Dienstag 9 Uhr", "Termin", dedup=False))
        self.assertIn("Eintrag gespeichert", result)
        with open(self._today_file(), "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("· Termin", content)
        self.assertIn("#termin", content)
        self.assertIn("Zahnarzt Dienstag 9 Uhr", content)

    def test_first_entry_with_dedup_skips_llm(self):
        # Leere Bestandsdatei => kein Dedup-Call, auch mit dedup=True (ai=None).
        result = asyncio.run(memory.write_inbox_entry("Milch kaufen", "Aufgabe"))
        self.assertIn("Eintrag gespeichert", result)
        self.assertIn("Kategorie: Aufgabe", result)

    def test_read_today_inbox_roundtrip(self):
        asyncio.run(memory.write_inbox_entry("Podcast starten", "Idee", dedup=False))
        content = memory.read_today_inbox_sync()
        self.assertIsNotNone(content)
        self.assertIn("Podcast starten", content)

    def test_read_today_inbox_none_when_empty(self):
        self.assertIsNone(memory.read_today_inbox_sync())

    def test_unconfigured_inbox_returns_message(self):
        memory.configure(vault_path="", inbox_path="")
        result = asyncio.run(memory.write_inbox_entry("x", "Notiz", dedup=False))
        self.assertIn("nicht konfiguriert", result)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class FinishResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-research-")
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path="", inbox_path=self.tmp)

    def tearDown(self):
        memory.configure(*self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sources_appended_and_autosaved(self):
        action_result = (
            "Recherche zu: ssd\n\n"
            "QUELLE: Test-Seite — https://example.com/a\nInhalt A\n\n"
            "QUELLE: Andere Seite — https://example.org/b\nInhalt B"
        )
        display = asyncio.run(assistant_core._finish_research("Kurzes Fazit.", action_result))
        self.assertIn("Kurzes Fazit.", display)
        self.assertIn("Quellen:", display)
        self.assertIn("- Test-Seite — https://example.com/a", display)
        # Autosave im Brain Dump mit Kategorie Recherche
        today_file = os.path.join(self.tmp, f"{time.strftime('%Y-%m-%d')} Brain Dump.md")
        with open(today_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("· Recherche", content)
        self.assertIn("https://example.org/b", content)

    def test_no_sources_returns_none(self):
        self.assertIsNone(asyncio.run(assistant_core._finish_research("Fazit.", "kein quellenformat")))


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class RunResearchThinSourcesTests(unittest.TestCase):
    """Duenne Quellenlage wird ehrlich an den Summary-Schritt gemeldet.

    Seit RFC-0001 ueber die oeffentliche Action-Seam (spec.execute) statt ueber
    den fruaeheren assistant_core.run_research-Helfer — gleiche Abdeckung.
    """

    def setUp(self):
        import browser_tools
        self._orig = (browser_tools.search_links, browser_tools.visit)
        self.browser_tools = browser_tools

    def tearDown(self):
        self.browser_tools.search_links, self.browser_tools.visit = self._orig

    def _stub(self, links, readable_urls):
        async def fake_search_links(query, limit=4):
            return links

        async def fake_visit(url, max_chars=1500):
            if url in readable_urls:
                return {"title": f"Titel {url}", "url": url, "content": "Inhalt"}
            return {"error": "timeout", "url": url}

        self.browser_tools.search_links = fake_search_links
        self.browser_tools.visit = fake_visit

    def test_single_readable_source_adds_hint(self):
        self._stub(
            links=[{"title": "A", "url": "https://a.example"}, {"title": "B", "url": "https://b.example"}],
            readable_urls={"https://a.example"},
        )
        result = asyncio.run(actions.spec_for("RESEARCH").execute("ssd", actions.ActionContext()))
        self.assertIn("QUELLE: ", result)
        self.assertIn("Nur 1 Quelle(n)", result)
        self.assertIn("dünn", result)

    def test_three_sources_no_hint(self):
        links = [{"title": t, "url": f"https://{t}.example"} for t in ("a", "b", "c")]
        self._stub(links=links, readable_urls={l["url"] for l in links})
        result = asyncio.run(actions.spec_for("RESEARCH").execute("ssd", actions.ActionContext()))
        self.assertEqual(result.count("QUELLE: "), 3)
        self.assertNotIn("HINWEIS AN JARVIS", result)

    def test_no_readable_sources_fails_honestly(self):
        self._stub(
            links=[{"title": "A", "url": "https://a.example"}],
            readable_urls=set(),
        )
        result = asyncio.run(actions.spec_for("RESEARCH").execute("ssd", actions.ActionContext()))
        self.assertIn("keine der Quellen war lesbar", result)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class SessionSummaryActionTests(unittest.TestCase):
    def test_session_protocol_from_history(self):
        sid = "test-session-summary"
        assistant_core.conversations[sid] = [
            {"role": "user", "content": "Recherchiere zu SSDs"},
            {"role": "assistant", "content": "Erledigt, Sir."},
        ]
        try:
            result = asyncio.run(assistant_core.execute_action(actions.Action("SESSION_SUMMARY"), sid))
        finally:
            assistant_core.conversations.pop(sid, None)
        self.assertIn("Sitzungsprotokoll:", result)
        self.assertIn("Du: Recherchiere zu SSDs", result)
        self.assertIn("Jarvis: Erledigt, Sir.", result)

    def test_empty_session(self):
        result = asyncio.run(assistant_core.execute_action(actions.Action("SESSION_SUMMARY"), "unbekannt"))
        self.assertIn("keinen nennenswerten Verlauf", result)


class RecentNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-vault-")
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path=self.tmp, inbox_path="")

    def tearDown(self):
        memory.configure(*self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reads_recent_notes_with_names(self):
        sub = os.path.join(self.tmp, "Projekte")
        os.makedirs(sub)
        with open(os.path.join(sub, "Alpha.md"), "w", encoding="utf-8") as f:
            f.write("Inhalt Alpha")
        with open(os.path.join(self.tmp, "Beta.md"), "w", encoding="utf-8") as f:
            f.write("Inhalt Beta")
        result = memory.read_recent_notes_sync(n=5)
        self.assertIn("Notiz: Alpha", result)
        self.assertIn("Inhalt Beta", result)

    def test_empty_vault_returns_empty(self):
        memory.configure(vault_path="", inbox_path="")
        self.assertEqual(memory.read_recent_notes_sync(), "")


if __name__ == "__main__":
    unittest.main()

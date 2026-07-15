"""Contract-Tests der Action-Seam (RFC-0001: Action als deep module).

Getestet wird ausschliesslich das oeffentliche Action-Interface:

    spec = actions.spec_for(TYP)
    result = await spec.execute(payload, ctx)     # Ausfuehrung
    text   = spec.describe(prompt_ctx)            # Selbstbeschreibung

Kein Patchen von Modul-Globals (``ai``/``conversations``), keine internen
Call-Counts, keine echten Provider/Apps/Screens/Clipboards. Erwartete Werte
stammen aus der Spezifikation (docs/contracts/LEGACY_ACTION_PROTOCOL.md), nicht
aus einer Neuberechnung durch den Produktionscode.
"""
import asyncio
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import tests  # noqa: F401  — synthetische Config-Fixture (JARVIS_CONFIG_PATH)

import actions
import browser_tools
import memory


def run(coro):
    """Coroutine synchron ausfuehren (unittest ohne IsolatedAsyncioTestCase)."""
    return asyncio.run(coro)


def ctx(**kwargs) -> "actions.ActionContext":
    """Request-scoped Ausfuehrungskontext mit Test-Defaults."""
    return actions.ActionContext(**kwargs)


def execute(action_type: str, payload: str = "", **ctx_kwargs) -> str:
    """Die Action ueber ihr oeffentliches Interface ausfuehren."""
    return run(actions.spec_for(action_type).execute(payload, ctx(**ctx_kwargs)))


def fake_async(return_value):
    """Async-Fake fuer eine externe Grenze (Browser/Screen/Clipboard)."""
    async def _fake(*args, **kwargs):
        return return_value
    return _fake


class SessionSummaryActionTests(unittest.TestCase):
    """SESSION_SUMMARY ist rein: liest den Verlauf ausschliesslich aus ctx.history."""

    def test_renders_session_log_from_context_history(self):
        result = run(actions.spec_for("SESSION_SUMMARY").execute("", ctx(history=(
            {"role": "user", "content": "Wie ist das Wetter?"},
            {"role": "assistant", "content": "Sonnig, 20 Grad."},
        ))))
        self.assertEqual(
            result,
            "Sitzungsprotokoll:\nDu: Wie ist das Wetter?\nJarvis: Sonnig, 20 Grad.",
        )

    def test_empty_history_reports_no_session_content(self):
        result = run(actions.spec_for("SESSION_SUMMARY").execute("", ctx(history=())))
        self.assertEqual(result, "Diese Sitzung hat noch keinen nennenswerten Verlauf.")


class SearchActionTests(unittest.TestCase):
    """SEARCH liest den ersten Treffer — Browser ist eine gefakte externe Grenze."""

    def test_reads_first_hit_and_returns_page_block(self):
        page = {"title": "Wetter Hamburg", "url": "https://example.invalid/w",
                "content": "Heute sonnig."}
        with mock.patch.object(browser_tools, "search_and_read", fake_async(page)):
            result = execute("SEARCH", "Wetter Hamburg")
        self.assertEqual(
            result,
            "Seite: Wetter Hamburg\nURL: https://example.invalid/w\n\nHeute sonnig.",
        )

    def test_browser_error_becomes_spoken_failure(self):
        with mock.patch.object(browser_tools, "search_and_read",
                               fake_async({"error": "Timeout"})):
            result = execute("SEARCH", "irgendwas")
        self.assertEqual(result, "Suche fehlgeschlagen: Timeout")


class BrowseActionTests(unittest.TestCase):
    """BROWSE liest eine bereits validierte URL (parse_action normalisiert sie)."""

    def test_returns_page_block_without_url_line(self):
        page = {"title": "Beispiel", "content": "Inhalt der Seite."}
        with mock.patch.object(browser_tools, "visit", fake_async(page)):
            result = execute("BROWSE", "https://example.invalid/a")
        self.assertEqual(result, "Seite: Beispiel\n\nInhalt der Seite.")

    def test_unreachable_page_becomes_spoken_failure(self):
        with mock.patch.object(browser_tools, "visit", fake_async({"error": "404"})):
            result = execute("BROWSE", "https://example.invalid/x")
        self.assertEqual(result, "Seite nicht erreichbar: 404")


class OpenActionTests(unittest.TestCase):
    """OPEN oeffnet die URL und meldet sie zurueck (kein Zusammenfassungs-LLM)."""

    def test_confirms_opened_url(self):
        opened = []

        async def _fake_open(url):
            opened.append(url)

        with mock.patch.object(browser_tools, "open_url", _fake_open):
            result = execute("OPEN", "https://example.invalid/seite")
        self.assertEqual(result, "Geöffnet: https://example.invalid/seite")
        self.assertEqual(opened, ["https://example.invalid/seite"])


class NewsActionTests(unittest.TestCase):
    """NEWS reicht das Ergebnis der Browser-Grenze unveraendert durch."""

    def test_returns_news_result_verbatim(self):
        with mock.patch.object(browser_tools, "fetch_news",
                               fake_async("Schlagzeile A\nSchlagzeile B")):
            result = execute("NEWS", "")
        self.assertEqual(result, "Schlagzeile A\nSchlagzeile B")


class ResearchActionTests(unittest.TestCase):
    """RESEARCH liest mehrere Quellen; der QUELLE:-Prefix gehoert zur Action."""

    def test_reads_sources_and_marks_them_with_source_prefix(self):
        links = [{"url": f"https://example.invalid/{i}", "title": f"T{i}"}
                 for i in range(1, 6)]
        pages = {f"https://example.invalid/{i}": {"title": f"T{i}", "content": f"C{i}"}
                 for i in range(1, 6)}

        async def _fake_search_links(topic, limit=5):
            return links

        async def _fake_visit(url, max_chars=1500):
            return pages[url]

        with mock.patch.object(browser_tools, "search_links", _fake_search_links), \
                mock.patch.object(browser_tools, "visit", _fake_visit):
            result = execute("RESEARCH", "Thema X")

        self.assertTrue(result.startswith("Recherche zu: Thema X"))
        # Genau 4 Quellen werden gelesen (gelesen >= 4 bricht ab).
        self.assertEqual(result.count(actions.RESEARCH_SOURCE_PREFIX), 4)
        self.assertIn(f"{actions.RESEARCH_SOURCE_PREFIX}T1 — https://example.invalid/1\nC1",
                      result)
        self.assertNotIn("HINWEIS AN JARVIS", result)

    def test_no_search_results_reports_failure(self):
        async def _no_links(topic, limit=5):
            return []

        with mock.patch.object(browser_tools, "search_links", _no_links):
            result = execute("RESEARCH", "Thema")
        self.assertEqual(result, "Recherche fehlgeschlagen: keine Suchergebnisse gefunden.")

    def test_thin_source_coverage_is_flagged_honestly(self):
        async def _one_link(topic, limit=5):
            return [{"url": "https://example.invalid/1", "title": "T1"}]

        async def _fake_visit(url, max_chars=1500):
            return {"title": "T1", "content": "C1"}

        with mock.patch.object(browser_tools, "search_links", _one_link), \
                mock.patch.object(browser_tools, "visit", _fake_visit):
            result = execute("RESEARCH", "Thema")
        self.assertIn("HINWEIS AN JARVIS: Nur 1 Quelle(n) waren lesbar", result)

    def test_all_sources_unreadable_reports_failure(self):
        async def _links(topic, limit=5):
            return [{"url": "https://example.invalid/1", "title": "T1"}]

        with mock.patch.object(browser_tools, "search_links", _links), \
                mock.patch.object(browser_tools, "visit", fake_async({"error": "boom"})):
            result = execute("RESEARCH", "Thema")
        self.assertEqual(result, "Recherche fehlgeschlagen: keine der Quellen war lesbar.")


class _TempVaultTestCase(unittest.TestCase):
    """Basis fuer Vault-/Inbox-Actions: ausschliesslich temporaere Verzeichnisse.

    Der echte persoenliche Vault wird nie beruehrt; memory.configure wird nach
    jedem Test auf den vorherigen Stand zurueckgesetzt.
    """

    def setUp(self):
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        self.tmp = tempfile.mkdtemp(prefix="jarvis-action-test-")
        self.vault = os.path.join(self.tmp, "vault")
        self.inbox = os.path.join(self.tmp, "inbox")
        os.makedirs(self.vault, exist_ok=True)
        os.makedirs(self.inbox, exist_ok=True)
        memory.configure(vault_path=self.vault, inbox_path=self.inbox)

    def tearDown(self):
        memory.configure(vault_path=self._saved[0], inbox_path=self._saved[1])
        shutil.rmtree(self.tmp, ignore_errors=True)

    def unconfigure(self):
        memory.configure(vault_path="", inbox_path="")


class InboxReadActionTests(_TempVaultTestCase):
    def test_unconfigured_inbox_reports_missing_folder(self):
        self.unconfigure()
        self.assertEqual(execute("INBOX_READ"),
                         "Inbox-Ordner nicht konfiguriert oder nicht gefunden.")

    def test_no_entries_today_names_the_date(self):
        heute = time.strftime("%Y-%m-%d")
        self.assertEqual(execute("INBOX_READ"),
                         f"Noch keine Einträge für heute ({heute}).")

    def test_returns_todays_entries(self):
        datei = os.path.join(self.inbox, time.strftime("%Y-%m-%d") + " Brain Dump.md")
        with open(datei, "w", encoding="utf-8") as f:
            f.write("- [Idee] Solarzellen prüfen")
        self.assertIn("Solarzellen prüfen", execute("INBOX_READ"))


class InboxWriteActionTests(_TempVaultTestCase):
    def test_writes_entry_with_parsed_category(self):
        result = execute("INBOX_WRITE", "[Termin] Zahnarzt Dienstag 9 Uhr")
        datei = os.path.join(self.inbox, time.strftime("%Y-%m-%d") + " Brain Dump.md")
        inhalt = open(datei, encoding="utf-8").read()
        self.assertIn("Termin", inhalt)
        self.assertIn("Zahnarzt Dienstag 9 Uhr", inhalt)
        self.assertNotIn("[Termin] Zahnarzt", inhalt)  # Kategorie wurde abgetrennt
        self.assertTrue(result)

    def test_unknown_category_falls_back_to_notiz_without_losing_text(self):
        execute("INBOX_WRITE", "[Quatsch] Wichtiger Text")
        datei = os.path.join(self.inbox, time.strftime("%Y-%m-%d") + " Brain Dump.md")
        inhalt = open(datei, encoding="utf-8").read()
        self.assertIn("Notiz", inhalt)
        self.assertIn("[Quatsch] Wichtiger Text", inhalt)


class MemoryReadActionTests(_TempVaultTestCase):
    def test_empty_memory_is_reported_honestly(self):
        self.assertEqual(execute("MEMORY_READ"),
                         "Ich habe mir dauerhaft noch nichts gemerkt.")

    def test_returns_memory_with_prefix(self):
        with open(os.path.join(self.vault, memory.MEMORY_FILENAME), "w",
                  encoding="utf-8") as f:
            f.write("- Trinkt Kaffee schwarz")
        result = execute("MEMORY_READ")
        self.assertTrue(result.startswith("Langzeit-Gedächtnis (dauerhaft gespeichert):\n"))
        self.assertIn("Trinkt Kaffee schwarz", result)


class MemoryWriteForgetActionTests(_TempVaultTestCase):
    def test_write_then_read_roundtrip(self):
        execute("MEMORY_WRITE", "Arbeitet an Projekt Nordlicht")
        self.assertIn("Projekt Nordlicht", execute("MEMORY_READ"))

    def test_forget_removes_matching_entry(self):
        execute("MEMORY_WRITE", "Arbeitet an Projekt Nordlicht")
        execute("MEMORY_FORGET", "Nordlicht")
        self.assertNotIn("Nordlicht", execute("MEMORY_READ"))


class NotesRecentActionTests(_TempVaultTestCase):
    def test_empty_vault_reports_no_notes(self):
        self.assertEqual(execute("NOTES_RECENT"),
                         "Keine Notizen gefunden — Vault nicht konfiguriert oder leer.")

    def test_returns_recent_note_names(self):
        with open(os.path.join(self.vault, "Nordlicht.md"), "w", encoding="utf-8") as f:
            f.write("# Nordlicht\nStand: Prototyp laeuft.")
        self.assertIn("Nordlicht", execute("NOTES_RECENT"))


class ProjectContextActionTests(_TempVaultTestCase):
    def test_unconfigured_vault_asks_for_vault_path(self):
        self.unconfigure()
        self.assertEqual(
            execute("PROJECT_CONTEXT", "Nordlicht"),
            "Kein Obsidian-Vault konfiguriert — bitte den Vault-Pfad in den "
            "Einstellungen hinterlegen.",
        )

    def test_no_match_is_reported_honestly(self):
        self.assertEqual(execute("PROJECT_CONTEXT", "Nordlicht"),
                         'Im Vault habe ich zu "Nordlicht" nichts Passendes gefunden.')

    def test_match_returns_question_and_context(self):
        with open(os.path.join(self.vault, "Nordlicht.md"), "w", encoding="utf-8") as f:
            f.write("# Nordlicht\nDer Prototyp laeuft seit Mai.")
        result = execute("PROJECT_CONTEXT", "Nordlicht")
        self.assertTrue(result.startswith('Frage: "Nordlicht"\n\n'))
        self.assertIn("Prototyp", result)

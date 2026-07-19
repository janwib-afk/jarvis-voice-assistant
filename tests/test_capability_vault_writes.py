"""Slice 5 — Vault-/Memory-Writes (Amendment 2 §A2.5).

Der Kern dieses Slices ist die **Korrektur einer Fehlklassifikation**. `INBOX_WRITE`
und `CLIPBOARD_NOTE` sahen bisher aus wie reine lokale Schreibvorgaenge. Tatsaechlich
liest ``memory.write_inbox_entry`` beim Dedup **vorhandene persoenliche Inbox-Inhalte**
und schickt bis zu 2000 Zeichen davon an das LLM. Beide sind damit:

``read-sensitive`` + ``local-write`` + ``network-read``.

Dieser Pfad wird hier nicht behauptet, sondern **belegt**: ein Fake-LLM-Client zaehlt
die Aufrufe und faengt ab, was tatsaechlich uebertragen wird.

Kontrollierte Grenzen: ``memory.*`` (Dateisystem), ``clipboard_tools`` (Betriebssystem)
und der LLM-Client. Ausschliesslich synthetische Inhalte.
"""
import asyncio
import os
import tempfile
import unittest
from unittest import mock

import tests  # noqa: F401

import actions
import capability as cap
import memory

VORHANDEN = "## 09:00 · Idee\n#idee\nAlter Eintrag zum Projekt Nordwind\n"
NEU = "Neue Notiz zum Projekt Nordwind"


class _Action:
    def __init__(self, type_, payload=""):
        self.type = type_
        self.payload = payload


class _DedupAI:
    """Faengt ab, was beim Dedup tatsaechlich an das LLM geht."""

    def __init__(self, verdict="NEU"):
        self.calls = []
        outer = self

        class _Messages:
            async def create(self, **kw):
                outer.calls.append(kw)

                class _R:
                    content = [type("C", (), {"text": verdict})()]
                return _R()

        self.messages = _Messages()


def _coord():
    return cap.Coordinator(cap.build_registry(cap.CapabilityDeps()),
                           cap.ACTIVE_RULES, audit=lambda *a, **k: None)


def _run(action, ai=None):
    return asyncio.run(cap.run_migrated(
        _coord(), action, actions.ActionContext(ai=ai)))


class _InboxDir:
    """Ein temporaerer Inbox-Ordner — nie der echte Vault des Nutzers."""

    def __enter__(self):
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        self.dir = tempfile.mkdtemp()
        memory.configure(vault_path=self.dir, inbox_path=self.dir)
        return self

    def __exit__(self, *a):
        memory.configure(vault_path=self._saved[0], inbox_path=self._saved[1])

    def seed_today(self, text):
        with open(memory._today_inbox_file(), "w", encoding="utf-8") as f:
            f.write(text)

    def today(self):
        path = memory._today_inbox_file()
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as f:
            return f.read()


class CanonicalMappingTests(unittest.TestCase):
    def test_write_paths_are_mapped(self):
        self.assertEqual("vault.inbox.write", cap.MIGRATED_ACTIONS["INBOX_WRITE"])
        self.assertEqual("memory.write", cap.MIGRATED_ACTIONS["MEMORY_WRITE"])
        self.assertEqual("clipboard.note.create",
                         cap.MIGRATED_ACTIONS["CLIPBOARD_NOTE"])


class DedupPathIsRealTests(unittest.TestCase):
    """Der versteckte Read- und Netzeffekt wird belegt, nicht behauptet."""

    def test_inbox_write_sends_existing_personal_content_to_the_llm(self):
        ai = _DedupAI()
        with _InboxDir() as inbox:
            inbox.seed_today(VORHANDEN)
            _run(_Action("INBOX_WRITE", "Idee: " + NEU), ai=ai)
        self.assertEqual(1, len(ai.calls), "der Dedup-LLM-Aufruf fand nicht statt")
        sent = ai.calls[0]["messages"][0]["content"]
        self.assertIn("Alter Eintrag zum Projekt Nordwind", sent,
                      "vorhandene persoenliche Inhalte gingen NICHT an das LLM — "
                      "dann waere die Klassifikation falsch")

    def test_clipboard_note_also_walks_the_dedup_path(self):
        ai = _DedupAI()
        with _InboxDir() as inbox:
            inbox.seed_today(VORHANDEN)
            with mock.patch("clipboard_tools.get_clipboard_text",
                            lambda: "Zwischenablage-Inhalt Nordwind"):
                _run(_Action("CLIPBOARD_NOTE"), ai=ai)
        self.assertEqual(1, len(ai.calls))
        sent = ai.calls[0]["messages"][0]["content"]
        self.assertIn("Alter Eintrag zum Projekt Nordwind", sent)

    def test_duplicate_verdict_keeps_the_existing_wording(self):
        ai = _DedupAI(verdict="DUPLIKAT: Alter Eintrag")
        with _InboxDir() as inbox:
            inbox.seed_today(VORHANDEN)
            result = _run(_Action("INBOX_WRITE", "Idee: " + NEU), ai=ai)
        self.assertIn("existiert bereits", result.text)


class ByteIdenticalWriteTests(unittest.TestCase):
    def test_memory_write_is_byte_identical(self):
        with mock.patch("memory.append_memory", lambda p: f"Gemerkt: {p}"):
            legacy = asyncio.run(actions.spec_for("MEMORY_WRITE").execute(
                "Nordwind", actions.ActionContext()))
            migrated = _run(_Action("MEMORY_WRITE", "Nordwind"))
        self.assertEqual(legacy, migrated.text)

    def test_clipboard_note_empty_clipboard_wording(self):
        with mock.patch("clipboard_tools.get_clipboard_text", lambda: ""):
            migrated = _run(_Action("CLIPBOARD_NOTE"))
        self.assertEqual("Die Zwischenablage ist leer oder enthält keinen Text.",
                         migrated.text)

    def test_inbox_write_actually_persists(self):
        ai = _DedupAI()
        with _InboxDir() as inbox:
            result = _run(_Action("INBOX_WRITE", "Idee: " + NEU), ai=ai)
            written = inbox.today()
        self.assertIn(NEU, written)
        self.assertTrue(result.ok)


class WriteEffectCensusTests(unittest.TestCase):
    """Die korrigierte Klassifikation aus §A2.5."""

    def _view(self, name):
        return cap.build_registry(cap.CapabilityDeps()).inspect(name)

    def test_inbox_write_declares_all_three_effects(self):
        view = self._view("vault.inbox.write")
        self.assertEqual(
            frozenset({cap.EffectClass.READ_SENSITIVE, cap.EffectClass.LOCAL_WRITE,
                       cap.EffectClass.NETWORK_READ}),
            view.effects)

    def test_clipboard_note_declares_all_three_effects(self):
        view = self._view("clipboard.note.create")
        self.assertEqual(
            frozenset({cap.EffectClass.READ_SENSITIVE, cap.EffectClass.LOCAL_WRITE,
                       cap.EffectClass.NETWORK_READ}),
            view.effects)

    def test_clipboard_note_carries_both_scopes(self):
        view = self._view("clipboard.note.create")
        self.assertIn(cap.Scope.CLIPBOARD, view.scopes)
        self.assertIn(cap.Scope.VAULT, view.scopes)

    def test_write_paths_write_personal_data(self):
        for name in ("vault.inbox.write", "memory.write", "clipboard.note.create"):
            with self.subTest(name=name):
                self.assertIn(cap.DataClass.PERSONAL, self._view(name).writes)

    def test_no_write_path_is_destructive(self):
        """Anhaengen ist kein Loeschen — nur MEMORY_FORGET ist destructive."""
        for name in ("vault.inbox.write", "memory.write", "clipboard.note.create"):
            with self.subTest(name=name):
                self.assertNotIn(cap.EffectClass.DESTRUCTIVE,
                                 self._view(name).effects)


if __name__ == "__main__":
    unittest.main()

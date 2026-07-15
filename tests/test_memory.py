"""
Tests fuer das Langzeit-Gedaechtnis in memory.py: Datei-Roundtrip,
Vault-/Workspace-Fallback, Kappung und Einbindung in den System-Prompt.
Keine LLM-/Netzwerk-Aufrufe.

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

import actions
import memory

try:
    import server  # verdrahtet assistant_core (configure/init_clients)
    import assistant_core
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    assistant_core = None
    _IMPORT_ERROR = e


class MemoryFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-memory-")
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path=self.tmp, inbox_path="")

    def tearDown(self):
        memory.configure(*self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_path_in_vault_when_configured(self):
        self.assertEqual(
            memory.memory_file_path(),
            os.path.join(self.tmp, memory.MEMORY_FILENAME),
        )

    def test_fallback_to_workspace_without_vault(self):
        memory.configure(vault_path="", inbox_path="")
        path = memory.memory_file_path()
        self.assertTrue(path.endswith(memory.FALLBACK_MEMORY_FILENAME))
        # Fallback liegt im Projektordner (neben memory.py).
        self.assertEqual(os.path.dirname(path), os.path.dirname(os.path.abspath(memory.__file__)))

    def test_empty_memory_reads_empty(self):
        self.assertEqual(memory.read_memory_sync(), "")

    def test_append_and_read_roundtrip(self):
        result = memory.append_memory("Jan mag kurze Antworten.")
        self.assertIn("Dauerhaft gemerkt", result)
        content = memory.read_memory_sync()
        self.assertIn("Jan mag kurze Antworten.", content)
        self.assertIn(time.strftime("%Y-%m-%d"), content)
        # Header ist in der Datei (Transparenz), aber nicht im Prompt-Inhalt.
        with open(memory.memory_file_path(), "r", encoding="utf-8") as f:
            raw = f.read()
        self.assertIn("# Jarvis Memory", raw)
        self.assertNotIn("# Jarvis Memory", content)

    def test_multiple_entries_appended(self):
        memory.append_memory("Erster Fakt.")
        memory.append_memory("Zweiter Fakt.")
        content = memory.read_memory_sync()
        self.assertIn("Erster Fakt.", content)
        self.assertIn("Zweiter Fakt.", content)

    def test_empty_text_not_saved(self):
        result = memory.append_memory("   ")
        self.assertIn("Kein Inhalt", result)
        self.assertFalse(os.path.exists(memory.memory_file_path()))

    def test_read_caps_at_max_chars_keeps_newest(self):
        for i in range(100):
            memory.append_memory(f"Eintrag Nummer {i} mit etwas Fuelltext dahinter.")
        content = memory.read_memory_sync(max_chars=500)
        self.assertLessEqual(len(content), 501)  # inkl. Ellipse
        # Die NEUESTEN Eintraege (Ende der Datei) bleiben erhalten.
        self.assertIn("Eintrag Nummer 99", content)
        self.assertNotIn("Eintrag Nummer 0 ", content)

    def test_user_edited_file_without_header_still_readable(self):
        with open(memory.memory_file_path(), "w", encoding="utf-8") as f:
            f.write("- Handgeschriebene Notiz vom Nutzer\n")
        self.assertIn("Handgeschriebene Notiz", memory.read_memory_sync())

    def test_forget_removes_only_matching_lines(self):
        memory.append_memory("Jan trinkt gerne Kaffee.")
        memory.append_memory("Lieblingseditor ist VS Code.")
        result = memory.forget_memory("Kaffee")
        self.assertIn("Vergessen", result)
        content = memory.read_memory_sync()
        self.assertNotIn("Kaffee", content)
        self.assertIn("VS Code", content)

    def test_forget_matches_by_all_significant_words(self):
        memory.append_memory("Projekt Delphin startet im August.")
        memory.append_memory("Projekt Wal ist abgeschlossen.")
        memory.forget_memory("Delphin Projekt")  # Wortreihenfolge egal
        content = memory.read_memory_sync()
        self.assertNotIn("Delphin", content)
        self.assertIn("Wal", content)

    def test_forget_unknown_query_deletes_nothing(self):
        memory.append_memory("Jan trinkt gerne Kaffee.")
        result = memory.forget_memory("Segelboot")
        self.assertIn("nichts", result.lower())
        self.assertIn("Kaffee", memory.read_memory_sync())

    def test_forget_on_empty_memory(self):
        result = memory.forget_memory("irgendwas")
        self.assertIn("noch nichts", result.lower())

    def test_forget_preserves_header_and_freetext(self):
        memory.append_memory("Jan mag Kaffee.")
        # Nutzer ergaenzt eine freie (nicht '- '-praefixierte) Zeile mit "Kaffee".
        with open(memory.memory_file_path(), "a", encoding="utf-8") as f:
            f.write("Freitext ohne Praefix, erwaehnt Kaffee\n")
        memory.forget_memory("Kaffee")
        with open(memory.memory_file_path(), "r", encoding="utf-8") as f:
            raw = f.read()
        self.assertIn("# Jarvis Memory", raw)                 # Header bleibt
        self.assertIn("Freitext ohne Praefix", raw)           # Freitext bleibt
        self.assertNotIn(": Jan mag Kaffee.", raw)            # Eintragszeile ist weg


class VaultSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-vault-")
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path=self.tmp, inbox_path="")

    def tearDown(self):
        memory.configure(*self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_md(self, *parts):
        path = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Notiz\n")

    def test_total_includes_root_level_notes(self):
        # 2 Notizen im Vault-Root, 3 in Unterordnern.
        self._write_md("Root Eins.md")
        self._write_md("Root Zwei.md")
        self._write_md("Projekte", "Alpha.md")
        self._write_md("Projekte", "Beta.md")
        self._write_md("Archiv", "Gamma.md")

        summary = memory.get_vault_summary_sync()
        self.assertIsNotNone(summary)
        # total zaehlt ALLE .md — inkl. der beiden Root-Notizen.
        self.assertEqual(summary["total"], 5)
        # by_folder zaehlt weiterhin nur Unterordner (keine Root-Verfaelschung).
        self.assertEqual(summary["by_folder"].get("Projekte"), 2)
        self.assertEqual(summary["by_folder"].get("Archiv"), 1)
        self.assertEqual(sum(summary["by_folder"].values()), 3)

    def test_empty_vault_totals_zero(self):
        summary = memory.get_vault_summary_sync()
        self.assertIsNotNone(summary)
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["by_folder"], {})


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class MemoryInPromptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-memory-prompt-")
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path=self.tmp, inbox_path="")

    def tearDown(self):
        memory.configure(*self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_prompt_contains_memory_block_when_present(self):
        memory.append_memory("Lieblingseditor ist VS Code.")
        prompt = assistant_core.build_system_prompt()
        self.assertIn("Langzeit-Gedächtnis (aus", prompt)
        self.assertIn("Lieblingseditor ist VS Code.", prompt)

    def test_prompt_without_memory_has_no_block(self):
        # Die MEMORY_WRITE-Anleitung bleibt, aber der Daten-Block fehlt.
        prompt = assistant_core.build_system_prompt()
        self.assertNotIn("Langzeit-Gedächtnis (aus", prompt)

    def test_prompt_documents_memory_write_action(self):
        prompt = assistant_core.build_system_prompt()
        self.assertIn("[ACTION:MEMORY_WRITE]", prompt)


class ProjectContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-vault-")
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path=self.tmp, inbox_path="")

    def tearDown(self):
        memory.configure(*self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_md(self, *parts, content="# Notiz\nEtwas Inhalt.\n"):
        path = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_finds_note_by_filename(self):
        self._write_md("Jarvis Voice Assistant.md", content="Naechster Schritt: Tests.\n")
        self._write_md("Einkaufsliste.md", content="Milch, Brot, Eier.\n")
        result = memory.get_project_context_sync("Jarvis Voice Assistant")
        self.assertIn("Notiz: Jarvis Voice Assistant", result)
        self.assertNotIn("Einkaufsliste", result)

    def test_finds_note_by_heading_and_content(self):
        self._write_md("Wochenlog.md", content="Allgemeines.\n\n## Delphin Fortschritt\nParser ist fertig.\n")
        result = memory.get_project_context_sync("Delphin")
        self.assertIn("Notiz: Wochenlog", result)
        self.assertIn("Delphin Fortschritt", result)

    def test_excerpts_capped_never_whole_file(self):
        self._write_md("Alpha.md", content="alpha Anfang.\n" + "Fuelltext-Zeile.\n" * 800)
        result = memory.get_project_context_sync("alpha", max_chars=500)
        self.assertTrue(result)
        self.assertLessEqual(len(result), 500)

    def test_limit_caps_number_of_hits(self):
        for i in range(8):
            self._write_md(f"Alpha {i}.md", content="Notizen zu alpha.\n")
        result = memory.get_project_context_sync("alpha", limit=2)
        self.assertEqual(result.count("Notiz: "), 2)

    def test_hidden_folder_ignored(self):
        self._write_md(".obsidian", "Workspace Alpha.md", content="alpha alpha alpha\n")
        self.assertEqual(memory.get_project_context_sync("alpha"), "")

    def test_memory_file_excluded(self):
        self._write_md(memory.MEMORY_FILENAME, content="Alles ueber projektdelphin.\n")
        self._write_md("Delphin Plan.md", content="projektdelphin Meilensteine.\n")
        result = memory.get_project_context_sync("projektdelphin")
        self.assertIn("Notiz: Delphin Plan", result)
        self.assertNotIn("Notiz: Jarvis Memory", result)

    def test_secret_file_skipped(self):
        self._write_md("API Keys.md", content="delphin: sk-abc123\n")
        self.assertEqual(memory.get_project_context_sync("delphin"), "")

    def test_secret_lines_skipped_in_excerpt(self):
        self._write_md("Delphin.md", content="Delphin Roadmap steht.\napi_key = sk-geheim12345\nWeiter im Text.\n")
        result = memory.get_project_context_sync("delphin")
        self.assertIn("Roadmap", result)
        self.assertNotIn("sk-geheim", result)

    def test_no_hits_returns_empty(self):
        self._write_md("Einkaufsliste.md", content="Milch, Brot.\n")
        self.assertEqual(memory.get_project_context_sync("Quantencomputer"), "")

    def test_unconfigured_vault_returns_empty(self):
        memory.configure(vault_path="", inbox_path="")
        self.assertEqual(memory.get_project_context_sync("alpha"), "")

    def test_empty_query_returns_empty(self):
        self._write_md("Alpha.md")
        self.assertEqual(memory.get_project_context_sync("   "), "")

    def test_relative_path_uses_forward_slash(self):
        self._write_md("Projekte", "Alpha.md", content="alpha Details.\n")
        result = memory.get_project_context_sync("alpha")
        self.assertIn("Projekte/Alpha.md", result)

    def test_umlaut_query_matches_casefold(self):
        self._write_md("Küchenumbau.md", content="Angebot vom Schreiner liegt vor.\n")
        result = memory.get_project_context_sync("KÜCHENUMBAU")
        self.assertIn("Notiz: Küchenumbau", result)

    def test_stopword_only_query_falls_back_to_raw_words(self):
        # "mein Projekt" besteht nur aus Stopwoertern — Fallback nutzt sie trotzdem.
        self._write_md("Projektliste.md", content="Uebersicht aller Vorhaben.\n")
        result = memory.get_project_context_sync("mein Projekt")
        self.assertIn("Notiz: Projektliste", result)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class ProjectContextActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-vault-")
        self._saved = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path=self.tmp, inbox_path="")

    def tearDown(self):
        memory.configure(*self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, payload):
        # RFC-0001: ueber die oeffentliche Action-Seam, ohne Modul-Globals.
        return asyncio.run(actions.spec_for("PROJECT_CONTEXT").execute(
            payload, actions.ActionContext()))

    def test_returns_context_with_question_prefix(self):
        with open(os.path.join(self.tmp, "Alpha.md"), "w", encoding="utf-8") as f:
            f.write("Naechster Schritt bei alpha: Tests schreiben.\n")
        result = self._run("alpha")
        self.assertIn('Frage: "alpha"', result)
        self.assertIn("Notiz: Alpha", result)

    def test_unconfigured_vault_gives_friendly_message(self):
        memory.configure(vault_path="", inbox_path="")
        self.assertIn("Kein Obsidian-Vault konfiguriert", self._run("alpha"))

    def test_no_hits_gives_friendly_message(self):
        self.assertIn("nichts Passendes", self._run("alpha"))


if __name__ == "__main__":
    unittest.main()

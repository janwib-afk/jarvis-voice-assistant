"""
Tests fuer das Langzeit-Gedaechtnis in memory.py: Datei-Roundtrip,
Vault-/Workspace-Fallback, Kappung und Einbindung in den System-Prompt.
Keine LLM-/Netzwerk-Aufrufe.

    python -m unittest discover -s tests
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        self.assertIn("Langzeit-Gedaechtnis (aus", prompt)
        self.assertIn("Lieblingseditor ist VS Code.", prompt)

    def test_prompt_without_memory_has_no_block(self):
        # Die MEMORY_WRITE-Anleitung bleibt, aber der Daten-Block fehlt.
        prompt = assistant_core.build_system_prompt()
        self.assertNotIn("Langzeit-Gedaechtnis (aus", prompt)

    def test_prompt_documents_memory_write_action(self):
        prompt = assistant_core.build_system_prompt()
        self.assertIn("[ACTION:MEMORY_WRITE]", prompt)


if __name__ == "__main__":
    unittest.main()

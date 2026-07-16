"""Contract-Tests der Configuration-Seam (RFC-0003).

Getestet wird ausschliesslich das oeffentliche Interface:

    configuration.schema_version_of(doc)
    configuration.migrate_document(doc)      # rein, v0 -> v1
    configuration.read_document(path)        # fails-closed, ruehrt die Datei nie an
    Configuration.snapshot() / settings_view() / mutate(intent, expected_revision)

Immer gegen ECHTE temporaere JSON-Dateien — nie gegen die persoenliche config.json.
Keine Tests privater Lock-/Hash-/Temp-/Replace-Helfer. Keine Provider, keine Secrets
in Erwartungen.
"""
import json
import os
import shutil
import tempfile
import unittest

import tests  # noqa: F401  — synthetische Config-Fixture (JARVIS_CONFIG_PATH)

import config_loader
import configuration


def base_document(**over) -> dict:
    """Synthetisches, gueltiges v0-Dokument (versionlos) mit unbekanntem Feld."""
    doc = {
        "anthropic_api_key": "dummy-anthropic",
        "elevenlabs_api_key": "dummy-eleven",
        "elevenlabs_voice_id": "voice",
        "user_name": "Tester",
        "user_address": "Tester",
        "user_role": "",
        "city": "Hamburg",
        "obsidian_inbox_path": "",
        "obsidian_inbox_folder": "",
        "music_folder": "",
        "selected_music_file": "",
        "music_volume": 0.25,
        "_comment": "unbekanntes Feld — muss erhalten bleiben",
        "apps": [],
        "launcher": {"active_profile": "default",
                     "profiles": [{"id": "default", "name": "Default", "apps": {}}]},
    }
    doc.update(over)
    return doc


class _TempConfigTestCase(unittest.TestCase):
    """Basis: jede Probe bekommt ihre eigene Temp-Datei."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-cfg-")
        self.path = os.path.join(self.tmp, "config.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, doc, path=None):
        with open(path or self.path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)

    def write_raw(self, text, path=None):
        with open(path or self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def read_raw(self, path=None):
        with open(path or self.path, encoding="utf-8") as f:
            return f.read()


class SchemaVersionTests(unittest.TestCase):
    """Versionsbestimmung: fehlend = v0 (Legacy)."""

    def test_missing_marker_is_version_zero(self):
        self.assertEqual(configuration.schema_version_of(base_document()), 0)

    def test_explicit_version_is_read(self):
        self.assertEqual(
            configuration.schema_version_of(base_document(schema_version=1)), 1)

    def test_target_version_is_one(self):
        self.assertEqual(configuration.SCHEMA_VERSION, 1)


class MigrationContractTests(unittest.TestCase):
    """v0 -> v1 ergaenzt AUSSCHLIESSLICH den Versionsmarker."""

    def test_v0_gains_only_the_version_marker(self):
        before = base_document()
        after = configuration.migrate_document(before)
        self.assertEqual(after["schema_version"], 1)
        # Exakt ein neuer Schluessel, sonst nichts veraendert.
        self.assertEqual(set(after) - set(before), {"schema_version"})
        for key, value in before.items():
            self.assertEqual(after[key], value, f"Feld '{key}' wurde veraendert")

    def test_v0_migration_is_pure(self):
        before = base_document()
        snapshot = json.dumps(before, sort_keys=True)
        configuration.migrate_document(before)
        self.assertEqual(json.dumps(before, sort_keys=True), snapshot,
                         "migrate_document darf die Eingabe nicht mutieren")

    def test_v1_is_accepted_unchanged(self):
        doc = base_document(schema_version=1)
        self.assertEqual(configuration.migrate_document(doc), doc)

    def test_unknown_fields_survive(self):
        after = configuration.migrate_document(base_document())
        self.assertEqual(after["_comment"], "unbekanntes Feld — muss erhalten bleiben")

    def test_secrets_survive_untouched(self):
        after = configuration.migrate_document(base_document())
        self.assertEqual(after["anthropic_api_key"], "dummy-anthropic")
        self.assertEqual(after["elevenlabs_api_key"], "dummy-eleven")

    def test_legacy_app_strings_are_not_normalized(self):
        doc = base_document(apps=["notepad.exe", {"command": "code.exe"}])
        after = configuration.migrate_document(doc)
        self.assertEqual(after["apps"], ["notepad.exe", {"command": "code.exe"}],
                         "Migration darf Legacy-/Mischformen nicht normalisieren")

    def test_missing_launcher_block_stays_missing(self):
        doc = base_document()
        del doc["launcher"]
        after = configuration.migrate_document(doc)
        self.assertNotIn("launcher", after)

    def test_key_order_is_preserved(self):
        before = base_document()
        after = configuration.migrate_document(before)
        self.assertEqual([k for k in after if k != "schema_version"], list(before))

    def test_future_version_fails_closed(self):
        with self.assertRaises(config_loader.ConfigError) as ctx:
            configuration.migrate_document(base_document(schema_version=99))
        self.assertIn("99", str(ctx.exception))

    def test_future_version_error_names_no_values(self):
        doc = base_document(schema_version=99)
        with self.assertRaises(config_loader.ConfigError) as ctx:
            configuration.migrate_document(doc)
        msg = str(ctx.exception)
        self.assertNotIn("dummy-anthropic", msg)
        self.assertNotIn("dummy-eleven", msg)


class ReadDocumentTests(_TempConfigTestCase):
    """read_document ist fails-closed und ruehrt die Datei nie an."""

    def test_reads_valid_document(self):
        self.write(base_document())
        self.assertEqual(configuration.read_document(self.path)["user_name"], "Tester")

    def test_corrupt_json_raises_and_leaves_file_untouched(self):
        self.write_raw('{"anthropic_api_key": "x", ')  # abgeschnitten
        before = self.read_raw()
        with self.assertRaises(config_loader.ConfigError):
            configuration.read_document(self.path)
        self.assertEqual(self.read_raw(), before, "beschaedigte Datei darf nie veraendert werden")

    def test_missing_file_raises(self):
        with self.assertRaises(config_loader.ConfigError):
            configuration.read_document(os.path.join(self.tmp, "gibt-es-nicht.json"))

    def test_error_message_contains_no_config_values(self):
        self.write_raw('{"anthropic_api_key": "geheim-123", ')
        with self.assertRaises(config_loader.ConfigError) as ctx:
            configuration.read_document(self.path)
        self.assertNotIn("geheim-123", str(ctx.exception))

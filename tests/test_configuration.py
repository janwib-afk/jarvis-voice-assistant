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


class ConfigurationSnapshotTests(_TempConfigTestCase):
    """snapshot()/settings_view(): kanonische Sicht, Projektion, Revision."""

    def open_config(self, doc=None, path=None):
        self.write(doc if doc is not None else base_document(schema_version=1),
                   path or self.path)
        cfg = configuration.Configuration(path or self.path)
        cfg.load()
        return cfg

    def test_snapshot_exposes_document_version_and_revision(self):
        snap = self.open_config().snapshot()
        self.assertEqual(snap.document["user_name"], "Tester")
        self.assertEqual(snap.schema_version, 1)
        self.assertTrue(snap.revision, "Revision muss ein nicht-leeres Token sein")

    def test_snapshot_document_is_not_mutable_by_callers(self):
        cfg = self.open_config()
        snap = cfg.snapshot()
        # snapshot().document ist eine NUR-LESBARE Sicht: Schreibversuche scheitern.
        with self.assertRaises((TypeError, AttributeError)):
            snap.document["user_name"] = "Angreifer"
        with self.assertRaises((TypeError, AttributeError)):
            snap.document["apps"].append("boom.exe")
        self.assertEqual(cfg.snapshot().document["user_name"], "Tester")
        # as_dict() liefert eine veraenderbare Kopie — Aenderungen daran bleiben lokal.
        copy_doc = cfg.snapshot().as_dict()
        copy_doc["user_name"] = "Angreifer"
        copy_doc["apps"].append("boom.exe")
        self.assertEqual(cfg.snapshot().document["user_name"], "Tester",
                         "Aenderung an der Kopie darf den kanonischen Zustand nicht treffen")
        self.assertEqual(cfg.snapshot().as_dict()["apps"], [])

    def test_revision_is_stable_without_changes(self):
        cfg = self.open_config()
        self.assertEqual(cfg.snapshot().revision, cfg.snapshot().revision)

    def test_revision_differs_for_different_content(self):
        a = self.open_config(base_document(schema_version=1, user_name="A"))
        other = os.path.join(self.tmp, "b.json")
        b = self.open_config(base_document(schema_version=1, user_name="B"), path=other)
        self.assertNotEqual(a.snapshot().revision, b.snapshot().revision)

    def test_settings_view_has_only_ui_editable_keys_and_revision(self):
        view = self.open_config().settings_view()
        self.assertEqual(set(view["settings"]), set(config_loader.UI_EDITABLE_KEYS))
        self.assertTrue(view["revision"])

    def test_settings_view_never_exposes_secrets(self):
        view = self.open_config().settings_view()
        flat = json.dumps(view, ensure_ascii=False)
        for secret in config_loader.PROTECTED_KEYS:
            self.assertNotIn(secret, view["settings"])
        self.assertNotIn("dummy-anthropic", flat)
        self.assertNotIn("dummy-eleven", flat)

    def test_settings_view_is_not_mutable_by_callers(self):
        cfg = self.open_config()
        view = cfg.settings_view()
        view["settings"]["user_name"] = "Angreifer"
        self.assertEqual(cfg.settings_view()["settings"]["user_name"], "Tester")


class ConfigurationLoadMigrationTests(_TempConfigTestCase):
    """load(): migriert v0 atomar auf Platte, mit genau einem Pre-Migration-Backup."""

    def test_v0_file_is_migrated_on_disk(self):
        self.write(base_document())  # versionlos
        cfg = configuration.Configuration(self.path)
        cfg.load()
        on_disk = json.load(open(self.path, encoding="utf-8"))
        self.assertEqual(on_disk["schema_version"], 1)
        self.assertEqual(cfg.snapshot().schema_version, 1)

    def test_migration_creates_byte_exact_backup(self):
        original = base_document()
        self.write(original)
        before_bytes = open(self.path, "rb").read()
        cfg = configuration.Configuration(self.path)
        cfg.load()
        backup = cfg.backup_path
        self.assertTrue(os.path.isfile(backup), "Pre-Migration-Backup fehlt")
        self.assertEqual(open(backup, "rb").read(), before_bytes,
                         "Backup muss bytegenau dem Original entsprechen")

    def test_v1_file_needs_no_backup(self):
        self.write(base_document(schema_version=1))
        cfg = configuration.Configuration(self.path)
        cfg.load()
        self.assertFalse(os.path.isfile(cfg.backup_path),
                         "ohne Migration darf kein Backup entstehen")

    def test_migration_preserves_unknown_fields_and_secrets_on_disk(self):
        self.write(base_document(apps=["legacy.exe", {"command": "code.exe"}]))
        configuration.Configuration(self.path).load()
        on_disk = json.load(open(self.path, encoding="utf-8"))
        self.assertEqual(on_disk["_comment"], "unbekanntes Feld — muss erhalten bleiben")
        self.assertEqual(on_disk["anthropic_api_key"], "dummy-anthropic")
        self.assertEqual(on_disk["apps"], ["legacy.exe", {"command": "code.exe"}])

    def test_future_version_file_is_not_overwritten(self):
        self.write(base_document(schema_version=99))
        before = self.read_raw()
        cfg = configuration.Configuration(self.path)
        with self.assertRaises(config_loader.ConfigError):
            cfg.load()
        self.assertEqual(self.read_raw(), before)

    def test_corrupt_file_is_not_overwritten(self):
        self.write_raw('{"anthropic_api_key": "x",')
        before = self.read_raw()
        with self.assertRaises(config_loader.ConfigError):
            configuration.Configuration(self.path).load()
        self.assertEqual(self.read_raw(), before)

    def test_invalid_config_fails_closed(self):
        doc = base_document()
        del doc["anthropic_api_key"]
        self.write(doc)
        with self.assertRaises(config_loader.ConfigError):
            configuration.Configuration(self.path).load()

    def test_load_is_idempotent(self):
        self.write(base_document())
        cfg = configuration.Configuration(self.path)
        cfg.load()
        rev = cfg.snapshot().revision
        cfg.load()
        self.assertEqual(cfg.snapshot().revision, rev)


class RuntimeOwnershipTests(_TempConfigTestCase):
    """Runtime besitzt genau eine Configuration; Migration laeuft im aopen —
    vor Provider-Erzeugung und Wiring. Import bleibt seiteneffektfrei (RFC-0002)."""

    def setUp(self):
        super().setUp()
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"

    def make_runtime(self, doc=None):
        import runtime as runtime_mod
        self.write(doc if doc is not None else base_document(schema_version=1))
        return runtime_mod.Runtime.for_production(
            config_path=self.path, environ={}, ai=object(), http=object())

    def test_runtime_has_unopened_configuration_before_open(self):
        rt = self.make_runtime()
        self.assertIsNotNone(rt.configuration, "Runtime besitzt eine Configuration-Instanz")
        with self.assertRaises(config_loader.ConfigError):
            rt.configuration.snapshot()  # ungeoeffnet: kein Snapshot

    def test_configuration_path_matches_runtime_path(self):
        rt = self.make_runtime()
        self.assertEqual(rt.configuration.path, rt.config_path)

    def test_open_loads_and_publishes_snapshot(self):
        import asyncio as aio
        rt = self.make_runtime()
        aio.run(rt.aopen())
        try:
            self.assertEqual(rt.configuration.snapshot().document["user_name"], "Tester")
            self.assertEqual(rt.configuration.snapshot().schema_version, 1)
        finally:
            aio.run(rt.aclose())

    def test_open_migrates_v0_before_wiring(self):
        import asyncio as aio
        import app_launcher
        rt = self.make_runtime(base_document(
            apps=[{"id": "obsidian", "name": "Obsidian", "command": "o.exe",
                   "type": "process"}]))
        aio.run(rt.aopen())
        try:
            on_disk = json.load(open(self.path, encoding="utf-8"))
            self.assertEqual(on_disk["schema_version"], 1, "aopen muss v0 migrieren")
            # Wiring lief NACH der Migration und sieht die migrierte Config.
            self.assertTrue(any(a["id"] == "obsidian" for a in app_launcher.APPS))
        finally:
            aio.run(rt.aclose())

    def test_open_fails_closed_on_future_version_without_touching_file(self):
        import asyncio as aio
        rt = self.make_runtime(base_document(schema_version=99))
        before = self.read_raw()
        with self.assertRaises(config_loader.ConfigError):
            aio.run(rt.aopen())
        self.assertEqual(self.read_raw(), before)

    def test_two_runtimes_are_isolated(self):
        import asyncio as aio
        import runtime as runtime_mod
        other = os.path.join(self.tmp, "b.json")
        self.write(base_document(schema_version=1, user_name="AAA"), self.path)
        self.write(base_document(schema_version=1, user_name="BBB"), other)
        a = runtime_mod.Runtime.for_production(config_path=self.path, environ={},
                                              ai=object(), http=object())
        b = runtime_mod.Runtime.for_production(config_path=other, environ={},
                                              ai=object(), http=object())
        aio.run(a.aopen()); aio.run(b.aopen())
        try:
            self.assertEqual(a.configuration.snapshot().document["user_name"], "AAA")
            self.assertEqual(b.configuration.snapshot().document["user_name"], "BBB")
            self.assertIsNot(a.configuration, b.configuration)
        finally:
            aio.run(a.aclose()); aio.run(b.aclose())

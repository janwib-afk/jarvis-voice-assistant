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


class MutationCoreTests(_TempConfigTestCase):
    """mutate(): der EINZIGE Schreibweg — Fresh-Read, Konflikt, Validierung,
    atomarer Austausch, Live-Apply, Kompensation."""

    def open_config(self, doc=None):
        self.write(doc if doc is not None else base_document(schema_version=1))
        cfg = configuration.Configuration(self.path)
        cfg.load()
        return cfg

    def mutate(self, cfg, intent, expected_revision=None, apply=None):
        import asyncio as aio
        return aio.run(cfg.mutate(intent, expected_revision=expected_revision,
                                  apply=apply))

    def test_set_settings_writes_and_publishes_new_revision(self):
        cfg = self.open_config()
        old_rev = cfg.snapshot().revision
        result = self.mutate(cfg, configuration.SetSettings({"city": "Bremen"}))
        self.assertEqual(json.load(open(self.path, encoding="utf-8"))["city"], "Bremen")
        self.assertEqual(cfg.snapshot().document["city"], "Bremen")
        self.assertNotEqual(cfg.snapshot().revision, old_rev)
        self.assertEqual(result.snapshot.revision, cfg.snapshot().revision)

    def test_set_settings_keeps_secrets_and_unknown_fields(self):
        cfg = self.open_config()
        self.mutate(cfg, configuration.SetSettings({"city": "Bremen"}))
        on_disk = json.load(open(self.path, encoding="utf-8"))
        self.assertEqual(on_disk["anthropic_api_key"], "dummy-anthropic")
        self.assertEqual(on_disk["_comment"], "unbekanntes Feld — muss erhalten bleiben")
        self.assertEqual(on_disk["schema_version"], 1)

    def test_protected_key_is_rejected_without_writing(self):
        cfg = self.open_config()
        before = self.read_raw()
        with self.assertRaises(config_loader.ConfigError):
            self.mutate(cfg, configuration.SetSettings({"anthropic_api_key": "neu"}))
        self.assertEqual(self.read_raw(), before, "abgelehntes Update darf nichts schreiben")

    def test_stale_revision_conflicts_without_writing_or_applying(self):
        cfg = self.open_config()
        stale = cfg.snapshot().revision
        self.mutate(cfg, configuration.SetSettings({"city": "Bremen"}))  # Revision zieht weiter
        before = self.read_raw()
        applied = []
        with self.assertRaises(configuration.ConfigConflict):
            self.mutate(cfg, configuration.SetSettings({"city": "Kiel"}),
                        expected_revision=stale,
                        apply=lambda doc: applied.append(doc))
        self.assertEqual(self.read_raw(), before, "Konflikt darf nichts schreiben")
        self.assertEqual(applied, [], "Konflikt darf kein Live-Apply ausloesen")

    def test_matching_revision_succeeds(self):
        cfg = self.open_config()
        rev = cfg.snapshot().revision
        self.mutate(cfg, configuration.SetSettings({"city": "Kiel"}), expected_revision=rev)
        self.assertEqual(cfg.snapshot().document["city"], "Kiel")

    def test_manual_change_before_mutation_becomes_new_base(self):
        cfg = self.open_config()
        # Manuelle, gueltige Aenderung direkt in der Datei (RFC-0003 D7).
        manual = json.load(open(self.path, encoding="utf-8"))
        manual["user_role"] = "haendisch gesetzt"
        manual["manual_marker"] = "bleibt"
        self.write(manual)
        self.mutate(cfg, configuration.SetSettings({"city": "Bremen"}))
        on_disk = json.load(open(self.path, encoding="utf-8"))
        self.assertEqual(on_disk["user_role"], "haendisch gesetzt",
                         "manuelle Aenderung muss neue Basis sein")
        self.assertEqual(on_disk["manual_marker"], "bleibt")
        self.assertEqual(on_disk["city"], "Bremen")

    def test_corrupt_file_before_mutation_is_not_overwritten(self):
        cfg = self.open_config()
        self.write_raw('{"kaputt": ')
        before = self.read_raw()
        with self.assertRaises(config_loader.ConfigError):
            self.mutate(cfg, configuration.SetSettings({"city": "Bremen"}))
        self.assertEqual(self.read_raw(), before)

    def test_future_version_before_mutation_is_not_overwritten(self):
        cfg = self.open_config()
        self.write(base_document(schema_version=99))
        before = self.read_raw()
        with self.assertRaises(config_loader.ConfigError):
            self.mutate(cfg, configuration.SetSettings({"city": "Bremen"}))
        self.assertEqual(self.read_raw(), before)

    def test_invalid_value_is_rejected_without_writing(self):
        cfg = self.open_config()
        before = self.read_raw()
        with self.assertRaises(config_loader.ConfigError):
            self.mutate(cfg, configuration.SetSettings({"music_volume": 5}))
        self.assertEqual(self.read_raw(), before)

    def test_live_apply_failure_restores_file_and_snapshot(self):
        cfg = self.open_config()
        before_file = self.read_raw()
        before_rev = cfg.snapshot().revision

        def boom(document):
            raise RuntimeError("Live-Apply kaputt")

        with self.assertRaises(RuntimeError):
            self.mutate(cfg, configuration.SetSettings({"city": "Bremen"}), apply=boom)
        self.assertEqual(self.read_raw(), before_file,
                         "Live-Apply-Fehler muss die alte Datei wiederherstellen")
        self.assertEqual(cfg.snapshot().revision, before_rev,
                         "Live-Apply-Fehler muss den alten Snapshot wiederherstellen")
        self.assertEqual(cfg.snapshot().document["city"], "Hamburg")

    def test_live_apply_receives_the_new_document(self):
        cfg = self.open_config()
        seen = {}
        self.mutate(cfg, configuration.SetSettings({"city": "Bremen"}),
                    apply=lambda doc: seen.update(doc))
        self.assertEqual(seen["city"], "Bremen")

    def test_mutations_are_serialized(self):
        """Zwei gleichzeitige Mutationen laufen nacheinander — keine verliert."""
        import asyncio as aio
        cfg = self.open_config()

        async def both():
            await aio.gather(
                cfg.mutate(configuration.SetSettings({"city": "Bremen"})),
                cfg.mutate(configuration.SetSettings({"user_role": "Rolle"})),
            )
        aio.run(both())
        on_disk = json.load(open(self.path, encoding="utf-8"))
        self.assertEqual(on_disk["city"], "Bremen")
        self.assertEqual(on_disk["user_role"], "Rolle",
                         "beide disjunkten Mutationen muessen erhalten bleiben")


class SelectMusicIntentTests(_TempConfigTestCase):
    """SelectMusic: Dateiname + Existenz gegen den Musikordner DESSELBEN Snapshots."""

    def setUp(self):
        super().setUp()
        self.music = os.path.join(self.tmp, "music")
        os.makedirs(self.music, exist_ok=True)
        open(os.path.join(self.music, "song.mp3"), "wb").close()
        self.write(base_document(schema_version=1, music_folder=self.music))
        self.cfg = configuration.Configuration(self.path)
        self.cfg.load()

    def run_intent(self, file):
        import asyncio as aio
        return aio.run(self.cfg.mutate(configuration.SelectMusic(file)))

    def test_selects_existing_file(self):
        self.run_intent("song.mp3")
        self.assertEqual(json.load(open(self.path, encoding="utf-8"))["selected_music_file"],
                         "song.mp3")

    def test_deselect_with_empty_name(self):
        self.run_intent("song.mp3")
        self.run_intent("")
        self.assertEqual(json.load(open(self.path, encoding="utf-8"))["selected_music_file"], "")

    def test_missing_file_is_rejected_without_writing(self):
        before = self.read_raw()
        with self.assertRaises(config_loader.ConfigError):
            self.run_intent("gibt-es-nicht.mp3")
        self.assertEqual(self.read_raw(), before)

    def test_path_traversal_is_rejected(self):
        for evil in ("..\evil.mp3", "../evil.mp3", "C:\evil.mp3", "sub/song.mp3"):
            with self.assertRaises(config_loader.ConfigError, msg=evil):
                self.run_intent(evil)

    def test_non_mp3_is_rejected(self):
        open(os.path.join(self.music, "doc.txt"), "wb").close()
        with self.assertRaises(config_loader.ConfigError):
            self.run_intent("doc.txt")

    def test_folder_comes_from_the_transaction_snapshot(self):
        """Manuell geaenderter Musikordner wird als frische Basis benutzt."""
        other = os.path.join(self.tmp, "musik2")
        os.makedirs(other, exist_ok=True)
        open(os.path.join(other, "neu.mp3"), "wb").close()
        manual = json.load(open(self.path, encoding="utf-8"))
        manual["music_folder"] = other
        self.write(manual)
        # 'neu.mp3' liegt nur im NEUEN Ordner — die Mutation muss ihn sehen.
        self.run_intent("neu.mp3")
        on_disk = json.load(open(self.path, encoding="utf-8"))
        self.assertEqual(on_disk["selected_music_file"], "neu.mp3")
        self.assertEqual(on_disk["music_folder"], other)

    def test_unconfigured_folder_is_rejected(self):
        self.write(base_document(schema_version=1, music_folder=""))
        cfg = configuration.Configuration(self.path)
        cfg.load()
        import asyncio as aio
        with self.assertRaises(config_loader.ConfigError):
            aio.run(cfg.mutate(configuration.SelectMusic("song.mp3")))

    def test_only_selected_music_file_changes(self):
        before = json.load(open(self.path, encoding="utf-8"))
        self.run_intent("song.mp3")
        after = json.load(open(self.path, encoding="utf-8"))
        changed = {k for k in after if before.get(k) != after[k]}
        self.assertEqual(changed, {"selected_music_file"})

"""
Tests fuer config_loader.py — Validierung + Laden mit klaren Fehlern.

Nutzt ausschliesslich temporaere Dateien — niemals die echte config.json.
    python -m unittest discover -s tests
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config_loader
from config_loader import (
    ConfigError,
    check_obsidian_paths,
    check_playwright_chromium,
    find_chromium_executable,
    load_config,
    validate_config,
    validate_launcher_value,
    validate_placement_value,
    validate_settings_update,
)

_HAS_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None

_VALID = {
    "anthropic_api_key": "sk-ant-abc123",
    "elevenlabs_api_key": "sk_def456",
}


class ValidateConfigTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_config(_VALID), [])

    def test_missing_required_key(self):
        errors = validate_config({"anthropic_api_key": "sk-ant-x"})
        self.assertTrue(any("elevenlabs_api_key" in e for e in errors))

    def test_empty_value(self):
        errors = validate_config({"anthropic_api_key": "  ", "elevenlabs_api_key": "x"})
        self.assertTrue(any("anthropic_api_key" in e for e in errors))

    def test_placeholder_value_detected(self):
        cfg = {"anthropic_api_key": "YOUR_ANTHROPIC_API_KEY", "elevenlabs_api_key": "sk_x"}
        errors = validate_config(cfg)
        self.assertTrue(any("anthropic_api_key" in e for e in errors))

    def test_error_messages_do_not_leak_values(self):
        # Secret-Wert darf nicht in der Fehlermeldung auftauchen.
        cfg = {"anthropic_api_key": "", "elevenlabs_api_key": "super-secret-value-123"}
        errors = validate_config(cfg)
        joined = " ".join(errors)
        self.assertNotIn("super-secret-value-123", joined)

    def test_non_dict(self):
        self.assertTrue(validate_config(["not", "a", "dict"]))


class LoadConfigTests(unittest.TestCase):
    def _write_temp(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_load_valid(self):
        path = self._write_temp(json.dumps(_VALID))
        self.assertEqual(load_config(path), _VALID)

    def test_missing_file_message(self):
        missing = os.path.join(tempfile.gettempdir(), "jarvis_nope_does_not_exist.json")
        with self.assertRaises(ConfigError) as ctx:
            load_config(missing)
        self.assertIn("config.json", str(ctx.exception))

    def test_invalid_json_message(self):
        path = self._write_temp("{ this is not json }")
        with self.assertRaises(ConfigError) as ctx:
            load_config(path)
        self.assertIn("JSON", str(ctx.exception))

    def test_invalid_config_raises(self):
        path = self._write_temp(json.dumps({"anthropic_api_key": "sk-ant-x"}))
        with self.assertRaises(ConfigError):
            load_config(path)


class ObsidianPathTests(unittest.TestCase):
    def _tempdir(self) -> str:
        path = tempfile.mkdtemp()
        self.addCleanup(lambda: os.path.exists(path) and os.rmdir(path))
        return path

    def test_missing_vault_path_warns_with_key_name(self):
        cfg = {"obsidian_inbox_path": os.path.join(tempfile.gettempdir(), "jarvis_nope_vault")}
        warnings = check_obsidian_paths(cfg)
        self.assertTrue(any("obsidian_inbox_path" in w for w in warnings))

    def test_existing_vault_path_no_warning(self):
        cfg = {"obsidian_inbox_path": self._tempdir()}
        self.assertEqual(check_obsidian_paths(cfg), [])

    def test_unset_vault_path_gives_mild_warning(self):
        warnings = check_obsidian_paths({})
        self.assertTrue(any("deaktiviert" in w for w in warnings))

    def test_inbox_folder_with_existing_parent_ok(self):
        # INBOX_WRITE legt den Ordner selbst an — existierender Parent reicht.
        parent = self._tempdir()
        cfg = {
            "obsidian_inbox_path": parent,
            "obsidian_inbox_folder": os.path.join(parent, "01 Inbox"),
        }
        self.assertEqual(check_obsidian_paths(cfg), [])

    def test_inbox_folder_without_parent_warns(self):
        vault = self._tempdir()
        cfg = {
            "obsidian_inbox_path": vault,
            "obsidian_inbox_folder": os.path.join(
                tempfile.gettempdir(), "jarvis_nope_parent", "01 Inbox"
            ),
        }
        warnings = check_obsidian_paths(cfg)
        self.assertTrue(any("obsidian_inbox_folder" in w for w in warnings))


class PlaywrightCheckTests(unittest.TestCase):
    def _tempdir(self) -> str:
        path = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_find_chromium_missing(self):
        self.assertIsNone(find_chromium_executable(browsers_dir=self._tempdir()))

    def test_find_chromium_found(self):
        root = self._tempdir()
        exe_dir = os.path.join(root, "chromium-1234", "chrome-win64")
        os.makedirs(exe_dir)
        exe = os.path.join(exe_dir, "chrome.exe")
        with open(exe, "w"):
            pass
        self.assertEqual(find_chromium_executable(browsers_dir=root), exe)

    def test_check_missing_chromium_warns(self):
        warnings = check_playwright_chromium(browsers_dir=self._tempdir())
        self.assertEqual(len(warnings), 1)
        # Je nach Umgebung fehlt das Paket oder nur Chromium — beides nennt den Fix.
        self.assertIn("nstallier", warnings[0])

    @unittest.skipIf(not _HAS_PLAYWRIGHT, "playwright-Paket nicht installiert")
    def test_check_missing_chromium_names_install_command(self):
        warnings = check_playwright_chromium(browsers_dir=self._tempdir())
        self.assertTrue(any("playwright install" in w for w in warnings))

    @unittest.skipIf(not _HAS_PLAYWRIGHT, "playwright-Paket nicht installiert")
    def test_check_found_chromium_no_warning(self):
        root = self._tempdir()
        exe_dir = os.path.join(root, "chromium-1234", "chrome-win")
        os.makedirs(exe_dir)
        with open(os.path.join(exe_dir, "chrome.exe"), "w"):
            pass
        self.assertEqual(check_playwright_chromium(browsers_dir=root), [])


class ValidateSettingsUpdateTests(unittest.TestCase):
    def test_valid_update(self):
        self.assertEqual(validate_settings_update({"city": "Berlin", "apps": ["a://b"]}), [])

    def test_protected_key_rejected(self):
        errors = validate_settings_update({"anthropic_api_key": "sk-neu"})
        self.assertTrue(any("anthropic_api_key" in e for e in errors))

    def test_unknown_key_rejected(self):
        errors = validate_settings_update({"gibt_es_nicht": "x"})
        self.assertTrue(any("gibt_es_nicht" in e for e in errors))

    def test_apps_must_be_list(self):
        self.assertTrue(validate_settings_update({"apps": "obsidian://open"}))
        self.assertTrue(validate_settings_update({"apps": [1, 2]}))

    def test_apps_accepts_legacy_strings(self):
        # Regressions-Guard: einfache String-Listen bleiben dauerhaft gueltig.
        self.assertEqual(validate_settings_update({"apps": ["obsidian://open", "code"]}), [])

    def test_apps_accepts_objects(self):
        apps = [
            {"id": "obsidian", "name": "Obsidian", "command": "obsidian://open",
             "type": "url", "autostart": True},
            {"command": "code"},
        ]
        self.assertEqual(validate_settings_update({"apps": apps}), [])

    def test_apps_mixed_list_ok(self):
        apps = ["obsidian://open", {"name": "VS Code", "command": "code"}]
        self.assertEqual(validate_settings_update({"apps": apps}), [])

    def test_apps_object_without_command_rejected(self):
        errors = validate_settings_update({"apps": [{"name": "Ohne Befehl"}]})
        self.assertTrue(any("command" in e for e in errors))

    def test_apps_bad_type_value_rejected(self):
        errors = validate_settings_update({"apps": [{"command": "x", "type": "shell"}]})
        self.assertTrue(any("type" in e for e in errors))

    def test_apps_unknown_key_rejected(self):
        errors = validate_settings_update({"apps": [{"command": "x", "shell": True}]})
        self.assertTrue(any("shell" in e for e in errors))

    def test_apps_non_bool_autostart_rejected(self):
        errors = validate_settings_update({"apps": [{"command": "x", "autostart": "ja"}]})
        self.assertTrue(any("autostart" in e for e in errors))

    def test_apps_empty_string_entry_rejected(self):
        self.assertTrue(validate_settings_update({"apps": ["  "]}))

    def test_apps_duplicate_explicit_id_rejected(self):
        apps = [
            {"id": "obsidian", "command": "obsidian://open"},
            {"id": "obsidian", "command": "code"},
        ]
        errors = validate_settings_update({"apps": apps})
        self.assertTrue(any("'id'" in e and "Eintrag 1" in e for e in errors))

    def test_apps_duplicate_id_case_insensitive_rejected(self):
        apps = [
            {"id": "Obsidian", "command": "obsidian://open"},
            {"id": "obsidian", "command": "code"},
        ]
        self.assertTrue(validate_settings_update({"apps": apps}))

    def test_apps_unique_ids_and_idless_entries_ok(self):
        # Legacy-Strings und Objekte ohne id zaehlen nie als Duplikat.
        apps = [
            "obsidian://open",
            {"command": "notepad"},
            {"id": "vscode", "command": "code"},
            {"id": "kalender", "command": "https://calendar.google.com"},
        ]
        self.assertEqual(validate_settings_update({"apps": apps}), [])

    # ── placement + process_name ────────────────────────────────────────────
    def test_apps_placement_valid(self):
        apps = [{"command": "code", "placement": {"monitor": "left", "zone": "left_half"}}]
        self.assertEqual(validate_settings_update({"apps": apps}), [])

    def test_apps_placement_partial_ok(self):
        # monitor/zone sind optional — Defaults setzt die Normalisierung.
        for placement in ({"monitor": "left"}, {"zone": "center"}, {}):
            apps = [{"command": "code", "placement": placement}]
            self.assertEqual(validate_settings_update({"apps": apps}), [], placement)

    def test_apps_placement_invalid_monitor_rejected(self):
        apps = [{"command": "code", "placement": {"monitor": "mars", "zone": "center"}}]
        errors = validate_settings_update({"apps": apps})
        self.assertTrue(any("'placement.monitor'" in e and "Eintrag 0" in e for e in errors))
        # Wert-frei: der fehlerhafte Wert taucht nicht in der Meldung auf.
        self.assertNotIn("mars", " ".join(errors))

    def test_apps_placement_invalid_zone_rejected(self):
        apps = [{"command": "code", "placement": {"zone": "diagonal"}}]
        errors = validate_settings_update({"apps": apps})
        self.assertTrue(any("'placement.zone'" in e for e in errors))
        self.assertNotIn("diagonal", " ".join(errors))

    def test_apps_placement_not_dict_rejected(self):
        for bad in ("left", ["left"], 5):
            apps = [{"command": "code", "placement": bad}]
            self.assertTrue(validate_settings_update({"apps": apps}), repr(bad))

    def test_apps_placement_unknown_key_rejected(self):
        apps = [{"command": "code", "placement": {"monitor": "left", "x": 10}}]
        errors = validate_settings_update({"apps": apps})
        self.assertTrue(any("unbekanntes Feld 'x'" in e for e in errors))

    def test_apps_process_name_valid_and_invalid(self):
        ok = [{"command": "https://calendar.google.com", "process_name": "chrome"}]
        self.assertEqual(validate_settings_update({"apps": ok}), [])
        for bad in (5, "", "   "):
            apps = [{"command": "code", "process_name": bad}]
            errors = validate_settings_update({"apps": apps})
            self.assertTrue(any("process_name" in e for e in errors), repr(bad))


class ValidatePlacementValueTests(unittest.TestCase):
    """Direkter Helfer-Test — server.py nutzt validate_placement_value standalone
    fuer den Body von POST /launcher/apps/{id}/placement."""

    def test_valid_and_partial(self):
        self.assertEqual(validate_placement_value({"monitor": "rightmost", "zone": "top_left"}), [])
        self.assertEqual(validate_placement_value({}), [])
        self.assertEqual(validate_placement_value({"zone": "fullscreen"}), [])

    def test_non_dict(self):
        self.assertTrue(validate_placement_value("left"))
        self.assertTrue(validate_placement_value(None))

    def test_unknown_key(self):
        errors = validate_placement_value({"monitor": "left", "profil": "arbeit"})
        self.assertTrue(any("unbekanntes Feld 'profil'" in e for e in errors))

    def test_bad_values_listed_allowed(self):
        errors = validate_placement_value({"monitor": "mitte", "zone": "ecke"})
        self.assertEqual(len(errors), 2)
        # Meldungen nennen die erlaubten Werte, nie den fehlerhaften.
        self.assertTrue(any("primary" in e for e in errors))
        self.assertTrue(any("fullscreen" in e for e in errors))
        self.assertNotIn("mitte", " ".join(errors))
        self.assertNotIn("ecke", " ".join(errors))


class ValidateLauncherValueTests(unittest.TestCase):
    """Session-Profile: launcher-Block-Validierung (Phase 4)."""

    _VALID = {
        "active_profile": "coding",
        "profiles": [
            {"id": "coding", "name": "Coding", "apps": {
                "vscode": {"autostart": True,
                           "placement": {"monitor": "left", "zone": "left_half"}}}},
            {"id": "writing", "name": "Writing", "apps": {}},
        ],
    }

    def test_valid_launcher(self):
        self.assertEqual(validate_launcher_value(self._VALID), [])

    def test_non_dict_and_unknown_key(self):
        self.assertTrue(validate_launcher_value("coding"))
        errors = validate_launcher_value({**self._VALID, "extra": 1})
        self.assertTrue(any("unbekanntes Feld 'extra'" in e for e in errors))

    def test_empty_profiles_rejected(self):
        for profiles in ([], None):
            errors = validate_launcher_value({"active_profile": "x", "profiles": profiles})
            self.assertTrue(any("mindestens einem Profil" in e for e in errors))

    def test_profile_requires_id_and_name(self):
        errors = validate_launcher_value(
            {"active_profile": "a", "profiles": [{"id": "a", "apps": {}}]})
        self.assertTrue(any("'name' fehlt" in e for e in errors))
        errors = validate_launcher_value(
            {"active_profile": "a", "profiles": [{"name": "A"}]})
        self.assertTrue(any("'id' fehlt" in e for e in errors))

    def test_duplicate_profile_ids_rejected_case_insensitive(self):
        errors = validate_launcher_value({"active_profile": "coding", "profiles": [
            {"id": "coding", "name": "A", "apps": {}},
            {"id": "Coding", "name": "B", "apps": {}},
        ]})
        self.assertTrue(any("bereits vergeben" in e for e in errors))

    def test_active_profile_must_exist(self):
        errors = validate_launcher_value({"active_profile": "nope", "profiles": [
            {"id": "coding", "name": "Coding", "apps": {}}]})
        self.assertTrue(any("kein vorhandenes Profil" in e for e in errors))
        errors = validate_launcher_value({"profiles": [
            {"id": "coding", "name": "Coding", "apps": {}}]})
        self.assertTrue(any("active_profile" in e for e in errors))

    def test_profile_app_state_validation(self):
        def launcher_with_state(state):
            return {"active_profile": "a", "profiles": [
                {"id": "a", "name": "A", "apps": {"vscode": state}}]}
        errors = validate_launcher_value(launcher_with_state({"autostart": "ja"}))
        self.assertTrue(any("'autostart' muss true oder false sein" in e for e in errors))
        errors = validate_launcher_value(
            launcher_with_state({"placement": {"monitor": "mars"}}))
        self.assertTrue(any("placement.monitor" in e for e in errors))
        errors = validate_launcher_value(launcher_with_state({"profil": True}))
        self.assertTrue(any("unbekanntes Feld 'profil'" in e for e in errors))
        errors = validate_launcher_value(launcher_with_state("an"))
        self.assertTrue(any("muss ein Objekt sein" in e for e in errors))

    def test_cross_check_only_with_app_ids(self):
        launcher = {"active_profile": "a", "profiles": [
            {"id": "a", "name": "A", "apps": {"geist": {"autostart": True}}}]}
        # Ohne app_ids: nur strukturell -> gueltig.
        self.assertEqual(validate_launcher_value(launcher), [])
        # Mit app_ids: unbekannter Key wird abgelehnt.
        errors = validate_launcher_value(launcher, app_ids=["vscode"])
        self.assertTrue(any("keiner App zugeordnet" in e for e in errors))
        self.assertEqual(validate_launcher_value(launcher, app_ids=["Geist"]), [])

    def test_settings_update_dispatch(self):
        self.assertEqual(validate_settings_update({"launcher": self._VALID}), [])
        # Beide Keys im Update -> Cross-Check greift.
        launcher = {"active_profile": "a", "profiles": [
            {"id": "a", "name": "A", "apps": {"geist": {"autostart": True}}}]}
        apps = [{"id": "vscode", "command": "code"}]
        errors = validate_settings_update({"launcher": launcher, "apps": apps})
        self.assertTrue(any("keiner App zugeordnet" in e for e in errors))

    def test_non_string_value_rejected(self):
        errors = validate_settings_update({"city": 42})
        self.assertTrue(any("city" in e for e in errors))

    def test_non_dict(self):
        self.assertTrue(validate_settings_update(["nicht", "dict"]))

    def test_error_messages_do_not_leak_values(self):
        errors = validate_settings_update({"anthropic_api_key": "super-secret-value-123"})
        self.assertNotIn("super-secret-value-123", " ".join(errors))


class ValidateMusicTests(unittest.TestCase):
    """Musik-Felder (Phase 3): selected_music_file ist NUR ein .mp3-Dateiname —
    nie ein Pfad. music_volume ist eine Zahl in [0, 1] (Punkt-Dezimal)."""

    def test_valid_filename(self):
        self.assertEqual(validate_settings_update({"selected_music_file": "song.mp3"}), [])
        self.assertEqual(
            validate_settings_update({"selected_music_file": "Track (Live) [2024].MP3"}), [])

    def test_empty_deselects(self):
        self.assertEqual(validate_settings_update({"selected_music_file": ""}), [])
        self.assertEqual(validate_settings_update({"selected_music_file": "   "}), [])

    def test_absolute_path_rejected(self):
        errors = validate_settings_update({"selected_music_file": "C:\\Musik\\song.mp3"})
        self.assertTrue(any("selected_music_file" in e for e in errors))

    def test_traversal_rejected(self):
        for bad in ("..\\song.mp3", "../song.mp3", ".."):
            self.assertTrue(validate_settings_update({"selected_music_file": bad}), repr(bad))

    def test_separators_rejected(self):
        for bad in ("folder/song.mp3", "folder\\song.mp3"):
            self.assertTrue(validate_settings_update({"selected_music_file": bad}), repr(bad))

    def test_colon_rejected(self):
        # Laufwerksbuchstaben (C:song.mp3) und NTFS-Streams (song.mp3:x).
        for bad in ("C:song.mp3", "song.mp3:stream"):
            self.assertTrue(validate_settings_update({"selected_music_file": bad}), repr(bad))

    def test_non_mp3_rejected(self):
        errors = validate_settings_update({"selected_music_file": "song.wav"})
        self.assertTrue(any(".mp3" in e for e in errors))

    def test_non_string_rejected(self):
        self.assertTrue(validate_settings_update({"selected_music_file": 5}))

    def test_music_folder_is_generic_text(self):
        self.assertEqual(validate_settings_update({"music_folder": "C:\\Musik"}), [])
        self.assertTrue(validate_settings_update({"music_folder": 5}))

    def test_music_volume_valid(self):
        for value in (0, 1, 0.25, "0.25", ""):
            self.assertEqual(validate_settings_update({"music_volume": value}), [], repr(value))

    def test_music_volume_invalid(self):
        # "0,25" bewusst ungueltig: launch-session.ps1 parst invariant (Punkt).
        for value in (-0.1, 1.1, "laut", "0,25", True, [0.2]):
            self.assertTrue(validate_settings_update({"music_volume": value}), repr(value))

    def test_error_messages_do_not_leak_value(self):
        errors = validate_settings_update({"selected_music_file": "geheim-xyz.wav"})
        self.assertNotIn("geheim-xyz", " ".join(errors))


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_warnings_do_not_leak_secrets(self):
        cfg = {
            "anthropic_api_key": "super-secret-value-123",
            "elevenlabs_api_key": "another-secret-456",
            "obsidian_inbox_path": os.path.join(tempfile.gettempdir(), "jarvis_nope_vault"),
        }
        joined = " ".join(config_loader.check_runtime_environment(cfg))
        self.assertNotIn("super-secret-value-123", joined)
        self.assertNotIn("another-secret-456", joined)


if __name__ == "__main__":
    unittest.main()

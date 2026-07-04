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
    save_settings,
    validate_config,
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
        errors = validate_settings_update({"browser_url": "https://x.de"})
        self.assertTrue(any("browser_url" in e for e in errors))

    def test_apps_must_be_list_of_strings(self):
        self.assertTrue(validate_settings_update({"apps": "obsidian://open"}))
        self.assertTrue(validate_settings_update({"apps": [1, 2]}))

    def test_non_string_value_rejected(self):
        errors = validate_settings_update({"city": 42})
        self.assertTrue(any("city" in e for e in errors))

    def test_non_dict(self):
        self.assertTrue(validate_settings_update(["nicht", "dict"]))

    def test_error_messages_do_not_leak_values(self):
        errors = validate_settings_update({"anthropic_api_key": "super-secret-value-123"})
        self.assertNotIn("super-secret-value-123", " ".join(errors))


class SaveSettingsTests(unittest.TestCase):
    _BASE = {
        "anthropic_api_key": "sk-ant-secret-111",
        "elevenlabs_api_key": "el-secret-222",
        "user_name": "Alt",
        "city": "Hamburg",
        # Nicht UI-editierbar — muss beim Speichern unangetastet bleiben:
        "workspace_path": "C:\\irgendwo",
        "browser_url": "https://alt.example",
        "unbekanntes_feld": {"x": 1},
    }

    def _write_cfg(self, data: dict) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_save_updates_value(self):
        path = self._write_cfg(self._BASE)
        merged = save_settings(path, {"city": "Berlin", "user_name": "Neu"})
        self.assertEqual(merged["city"], "Berlin")
        with open(path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["city"], "Berlin")
        self.assertEqual(on_disk["user_name"], "Neu")

    def test_save_preserves_secrets_and_unknown_keys(self):
        path = self._write_cfg(self._BASE)
        save_settings(path, {"city": "Berlin"})
        with open(path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["anthropic_api_key"], "sk-ant-secret-111")
        self.assertEqual(on_disk["elevenlabs_api_key"], "el-secret-222")
        self.assertEqual(on_disk["workspace_path"], "C:\\irgendwo")
        self.assertEqual(on_disk["browser_url"], "https://alt.example")
        self.assertEqual(on_disk["unbekanntes_feld"], {"x": 1})

    def test_save_rejects_protected_key_and_leaves_file_untouched(self):
        path = self._write_cfg(self._BASE)
        with self.assertRaises(ConfigError):
            save_settings(path, {"anthropic_api_key": "sk-neu", "city": "Berlin"})
        with open(path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["city"], "Hamburg")
        self.assertEqual(on_disk["anthropic_api_key"], "sk-ant-secret-111")

    def test_save_atomic_no_tmp_left(self):
        path = self._write_cfg(self._BASE)
        save_settings(path, {"city": "Berlin"})
        self.assertFalse(os.path.exists(path + ".tmp"))

    def test_unicode_roundtrip(self):
        path = self._write_cfg(self._BASE)
        save_settings(path, {"city": "Lübeck", "obsidian_inbox_path": "C:\\Vault\\Übersicht"})
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        # ensure_ascii=False: Umlaute stehen lesbar in der Datei, kein ü
        self.assertIn("Lübeck", raw)
        self.assertEqual(json.loads(raw)["obsidian_inbox_path"], "C:\\Vault\\Übersicht")

    def test_missing_file_raises_config_error(self):
        missing = os.path.join(tempfile.gettempdir(), "jarvis_nope_settings.json")
        with self.assertRaises(ConfigError):
            save_settings(missing, {"city": "Berlin"})

    def test_apps_list_roundtrip(self):
        path = self._write_cfg(self._BASE)
        save_settings(path, {"apps": ["obsidian://open", "notion://"]})
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["apps"], ["obsidian://open", "notion://"])


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

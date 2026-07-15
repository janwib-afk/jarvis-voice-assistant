"""
Phase-0 Test-Config-Seam: Die Testsuite laeuft ohne persoenliche config.json.

Beweist vier Verhalten:
  1. ``resolve_config_path`` bevorzugt ``JARVIS_CONFIG_PATH``, sonst den Default (pur).
  2. Produktion ohne gueltige Config schlaegt weiterhin hart fehl (``ConfigError``).
  3. Es existiert eine eingecheckte, offensichtlich synthetische Test-Fixture.
  4. Im normalen Testlauf ist die AKTIVE Config diese Fixture, NICHT die
     persoenliche config.json (kein stiller Fallback).

Assertions geben absichtlich KEINE Config-Werte/Pfade aus (keine Secrets in der
Testausgabe) — Verhalten 4 nutzt daher assertTrue mit erklaerender Meldung.

    python -m unittest discover -s tests
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

from config_loader import ConfigError, load_config, resolve_config_path

FIXTURE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "fixtures", "config.test.json")
)
SENTINEL_USER = "Testfixture Nutzer"

try:
    import server  # verdrahtet Config-Load beim Import
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    _IMPORT_ERROR = e


class ResolveConfigPathTests(unittest.TestCase):
    """Reine Aufloesung: Env-Override schlaegt Default, leer wird ignoriert."""

    def test_env_override_wins(self):
        self.assertEqual(
            resolve_config_path({"JARVIS_CONFIG_PATH": "/x/y.json"}, "/default.json"),
            "/x/y.json",
        )

    def test_default_when_unset(self):
        self.assertEqual(resolve_config_path({}, "/default.json"), "/default.json")

    def test_blank_env_falls_back_to_default(self):
        self.assertEqual(
            resolve_config_path({"JARVIS_CONFIG_PATH": "   "}, "/default.json"),
            "/default.json",
        )


class ProductionConfigStillFailsHardTests(unittest.TestCase):
    """Ohne Env-Override und ohne vorhandene Default-Config bleibt es ein Fehler."""

    def test_missing_default_config_raises(self):
        missing = os.path.join(tempfile.gettempdir(), "jarvis_seam_no_such_config.json")
        path = resolve_config_path({}, missing)
        with self.assertRaises(ConfigError):
            load_config(path)


class SyntheticFixtureTests(unittest.TestCase):
    """Die eingecheckte Fixture ist gueltig, synthetisch und secret-/pfadfrei."""

    def test_fixture_exists_and_is_valid(self):
        cfg = load_config(FIXTURE)  # gueltig -> kein Raise
        self.assertEqual(cfg.get("user_name"), SENTINEL_USER)

    def test_fixture_keys_are_obviously_synthetic(self):
        with open(FIXTURE, encoding="utf-8") as f:
            cfg = json.load(f)
        for key in ("anthropic_api_key", "elevenlabs_api_key"):
            self.assertIn("test", cfg[key].lower())

    def test_fixture_has_no_personal_data(self):
        with open(FIXTURE, encoding="utf-8") as f:
            raw = f.read().lower()
        for needle in ("janwi", "appdata", "obsidian_inbox_path\": \"c:"):
            self.assertNotIn(needle, raw)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class ActiveTestConfigTests(unittest.TestCase):
    """Im discover-Lauf ist die aktive Config die Fixture (kein stiller Fallback)."""

    def test_active_config_is_synthetic_fixture(self):
        self.assertTrue(
            os.path.abspath(server.CONFIG_PATH) == FIXTURE,
            "server.CONFIG_PATH zeigt nicht auf die Test-Fixture "
            "(stiller Fallback auf die echte config.json?).",
        )

    def test_no_silent_fallback_to_personal_config(self):
        self.assertTrue(
            server.config.get("user_name") == SENTINEL_USER,
            "Aktive Config ist nicht die synthetische Fixture "
            "(Sentinel-user_name fehlt) — moeglicher Fallback auf echte Config.",
        )


if __name__ == "__main__":
    unittest.main()

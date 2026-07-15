"""
Regressionstests fuer die reine Entscheidungslogik des Smoke-Tests
(``scripts/smoke_lib.py``): Gesamturteil und Skip-Klassifikation.

Erwartete Ergebnisse folgen der SPEZIFIKATION (gruen nur ohne Failures/Errors/
unerwartete Skips; server-Import-Skips gelten als unerwartet), nicht der
Implementierung des Runners.

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)

from smoke_lib import classify_skips, suite_ok


class SuiteOkTests(unittest.TestCase):
    def test_green_run_without_skips_is_ok(self):
        self.assertTrue(suite_ok(tests_run=10, failures=0, errors=0, unexpected_skips=0))

    def test_zero_tests_is_not_ok(self):
        # Eine leere Sammlung darf nicht als "gruen" durchgehen.
        self.assertFalse(suite_ok(tests_run=0, failures=0, errors=0, unexpected_skips=0))

    def test_failed_test_is_not_ok(self):
        self.assertFalse(suite_ok(tests_run=10, failures=1, errors=0, unexpected_skips=0))

    def test_error_is_not_ok(self):
        self.assertFalse(suite_ok(tests_run=10, failures=0, errors=1, unexpected_skips=0))

    def test_unexpected_skip_is_not_ok(self):
        self.assertFalse(suite_ok(tests_run=10, failures=0, errors=0, unexpected_skips=1))


class ClassifySkipsTests(unittest.TestCase):
    def test_no_skips_yields_no_unexpected(self):
        self.assertEqual(classify_skips([]), [])

    def test_playwright_skip_is_expected(self):
        skips = [("t.id", "playwright-Paket nicht installiert")]
        self.assertEqual(classify_skips(skips), [])

    def test_server_import_skip_is_unexpected(self):
        # Ein nicht importierbares Servermodul skippt ganze Klassen — das MUSS
        # als unerwartet gelten (sonst wirkt die Suite still gruen).
        skips = [("t.id", "server import nicht moeglich: ConfigError(...)")]
        self.assertEqual(classify_skips(skips), skips)

    def test_mixed_returns_only_unexpected(self):
        expected = ("a", "playwright-Paket nicht installiert")
        unexpected = ("b", "irgendein anderer Grund")
        self.assertEqual(classify_skips([expected, unexpected]), [unexpected])


class SkipCaseOverallFailsTests(unittest.TestCase):
    def test_unexpected_skip_makes_overall_fail(self):
        skips = [("t", "server import nicht moeglich: x")]
        unexpected = classify_skips(skips)
        self.assertFalse(
            suite_ok(tests_run=10, failures=0, errors=0, unexpected_skips=len(unexpected))
        )


if __name__ == "__main__":
    unittest.main()

"""Prompt 20A §6 — Test-Environment-Isolation.

Belegt, dass ``guard_env`` den EXAKTEN Ausgangszustand wiederherstellt (fehlend vs.
vorhandener Wert), dass Setup/Teardown reihenfolgeunabhaengig sauber bleiben und
dass die Standard-Suite keinen echten Wetterzugriff ausloest.
"""
import os
import unittest

import tests  # noqa: F401
from tests.env_guard import guard_env

import assistant_core
import server

_KEY = "JARVIS_TEST_ENV_ISOLATION_PROBE"


class GuardEnvTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop(_KEY, None)

    def test_absent_variable_is_restored_to_absent(self):
        os.environ.pop(_KEY, None)

        class _Inner(unittest.TestCase):
            def runTest(inner):
                guard_env(inner, _KEY)
                os.environ[_KEY] = "geaendert"

        t = _Inner()
        t.run()                                    # setUp/runTest/cleanup laufen
        self.assertNotIn(_KEY, os.environ,
                         "urspruenglich fehlende Variable blieb gesetzt")

    def test_present_sentinel_value_is_restored_exactly(self):
        os.environ[_KEY] = "original-sentinel"

        class _Inner(unittest.TestCase):
            def runTest(inner):
                guard_env(inner, _KEY)
                os.environ[_KEY] = "zwischendurch-anders"
                os.environ.pop(_KEY, None)         # sogar ein Pop wird korrigiert

        _Inner().run()
        self.assertEqual("original-sentinel", os.environ.get(_KEY),
                         "vorhandener Wert wurde nicht exakt wiederhergestellt")

    def test_restore_runs_even_when_the_test_body_raises(self):
        os.environ[_KEY] = "vorher"

        class _Boom(unittest.TestCase):
            def runTest(inner):
                guard_env(inner, _KEY)
                os.environ[_KEY] = "kaputt"
                raise RuntimeError("Setup/Body-Abbruch")

        _Boom().run()                              # Fehler wird vom Runner gefangen
        self.assertEqual("vorher", os.environ.get(_KEY),
                         "addCleanup lief trotz Ausnahme nicht")


class OrderIndependenceTests(unittest.TestCase):
    """Zwei Muster (Popper und Setter) in BEIDEN Reihenfolgen — kein Rest-Drift."""

    def _popper(self):
        class _P(unittest.TestCase):
            def runTest(inner):
                guard_env(inner, _KEY)
                os.environ.pop(_KEY, None)
        return _P()

    def _setter(self):
        class _S(unittest.TestCase):
            def runTest(inner):
                guard_env(inner, _KEY)
                os.environ[_KEY] = "1"
        return _S()

    def _run_both(self, first, second):
        os.environ[_KEY] = "start"
        try:
            first().run()
            second().run()
            self.assertEqual("start", os.environ.get(_KEY))
        finally:
            os.environ.pop(_KEY, None)

    def test_popper_then_setter(self):
        self._run_both(self._popper, self._setter)

    def test_setter_then_popper(self):
        self._run_both(self._setter, self._popper)


class NoRealWeatherTests(unittest.TestCase):
    """§6.7: Im Standardzustand (JARVIS_SKIP_STARTUP_REFRESH gesetzt) loest der
    Serverstart KEINEN Refresh und damit keinen echten Wetterzugriff aus."""

    def test_module_app_startup_does_not_refresh(self):
        from fastapi.testclient import TestClient
        guard_env(self, "JARVIS_SKIP_STARTUP_REFRESH")
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"   # Standard-Suite-Zustand

        calls = []
        saved = assistant_core.refresh_data
        assistant_core.refresh_data = lambda: calls.append(1)
        try:
            with TestClient(server.app):
                pass
        finally:
            assistant_core.refresh_data = saved
        self.assertEqual([], calls,
                         "Startup-Refresh lief trotz gesetztem Skip — moeglicher "
                         "echter wttr.in-Zugriff")

    def test_weather_uses_a_network_tripwire_free_default_when_skipped(self):
        """Tripwire: waere die echte Netz-Ebene erreicht worden, faellt der Test."""
        import urllib.request
        guard_env(self, "JARVIS_SKIP_STARTUP_REFRESH")
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"
        from fastapi.testclient import TestClient

        hits = []
        real_urlopen = urllib.request.urlopen

        def _tripwire(req, *a, **k):
            url = getattr(req, "full_url", str(req))
            if "wttr.in" in url:
                hits.append(url)
                raise AssertionError("echter wttr.in-Zugriff im Test")
            return real_urlopen(req, *a, **k)

        urllib.request.urlopen = _tripwire
        try:
            with TestClient(server.app):
                pass
        finally:
            urllib.request.urlopen = real_urlopen
        self.assertEqual([], hits)


if __name__ == "__main__":
    unittest.main()

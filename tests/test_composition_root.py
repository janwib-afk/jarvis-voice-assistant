"""Composition-Root-Tests (Slice 1): Import-Sicherheit + App-Factory.

Seam (RFC-0002 + Amendment 1): `import server` ist seiteneffektfrei —
lädt keine (persönliche) Config, erzeugt keine Provider-Clients/Browser/Tasks,
ruft nie `sys.exit`; Config und OWNED-Clients entstehen erst im FastAPI-Lifespan.
Öffentliche Fläche: `server.create_app(runtime)` + `runtime.Runtime`.

Import-Sicherheit wird in einem frischen SUBPROZESS geprüft (isoliert vom Zustand
der übrigen Suite). Es geht KEIN Provideraufruf raus (nur Objekt-/Importprüfung).

    python -m unittest discover -s tests
"""
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_import(code, extra_env=None, timeout=90):
    env = dict(os.environ)
    env.pop("JARVIS_CONFIG_PATH", None)   # Default: echte config.json-Pfad-Auflösung
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout)


class ImportSafetyTests(unittest.TestCase):
    def test_import_loads_no_config_and_no_clients(self):
        # Selbst mit vorhandener echter config.json wird beim Import NICHTS geladen.
        r = _run_import(
            "import server; "
            "assert server.runtime.config is None, 'config beim Import geladen'; "
            "assert server.runtime.ai is None, 'ai beim Import erzeugt'; "
            "assert server.runtime.http is None, 'http beim Import erzeugt'; "
            "print('IMPORT_SAFE_OK')")
        self.assertEqual(r.returncode, 0, f"stderr:\n{r.stderr}")
        self.assertIn("IMPORT_SAFE_OK", r.stdout)

    def test_import_does_not_sys_exit_when_config_missing(self):
        missing = os.path.join(os.environ.get("TEMP", "/tmp"), "jarvis_cr_no_such_config.json")
        r = _run_import("import server; print('IMPORTED')",
                        extra_env={"JARVIS_CONFIG_PATH": missing})
        self.assertEqual(r.returncode, 0, f"Import beendete den Prozess: stderr:\n{r.stderr}")
        self.assertIn("IMPORTED", r.stdout)

    def test_import_starts_no_browser_and_no_task(self):
        r = _run_import(
            "import server, browser_tools; "
            "assert browser_tools._browser is None, 'Browser beim Import gestartet'; "
            "assert server.runtime._refresh_task is None, 'Refresh-Task beim Import gestartet'; "
            "print('NO_BROWSER_NO_TASK_OK')")
        self.assertEqual(r.returncode, 0, f"stderr:\n{r.stderr}")
        self.assertIn("NO_BROWSER_NO_TASK_OK", r.stdout)

    def test_import_creates_app_object(self):
        r = _run_import(
            "import server; from fastapi import FastAPI; "
            "assert isinstance(server.app, FastAPI); print('APP_OK')")
        self.assertEqual(r.returncode, 0, f"stderr:\n{r.stderr}")
        self.assertIn("APP_OK", r.stdout)


# In-Process-Factory-Tests nutzen die synthetische Fixture (tests/__init__.py).
import tests  # noqa: E402,F401  wählt die synthetische Test-Config vor 'import server'

try:
    import server  # noqa: E402
    import runtime as runtime_mod  # noqa: E402
    _IMPORT_ERROR = None
except BaseException as e:  # pragma: no cover
    server = None
    runtime_mod = None
    _IMPORT_ERROR = e


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class FactoryTests(unittest.TestCase):
    def test_create_app_returns_fastapi(self):
        from fastapi import FastAPI
        app = server.create_app(server.runtime)
        self.assertIsInstance(app, FastAPI)

    def test_two_apps_have_separate_runtimes(self):
        rt_a = runtime_mod.Runtime.for_production()
        rt_b = runtime_mod.Runtime.for_production()
        app_a = server.create_app(rt_a)
        app_b = server.create_app(rt_b)
        self.assertIsNot(app_a, app_b)
        self.assertIs(app_a.state.runtime, rt_a)
        self.assertIs(app_b.state.runtime, rt_b)
        self.assertNotEqual(rt_a.session_token, rt_b.session_token)

    def test_injected_clients_are_borrowed(self):
        rt = runtime_mod.Runtime.for_production(ai=object(), http=object())
        self.assertFalse(rt.owns_clients, "injizierte Clients müssen BORROWED sein")

    def test_for_production_is_side_effect_free(self):
        # for_production darf keine Config laden und keine Clients erzeugen.
        rt = runtime_mod.Runtime.for_production()
        self.assertIsNone(rt.config)
        self.assertIsNone(rt.ai)
        self.assertIsNone(rt.http)
        self.assertTrue(rt.session_token)          # Token erzeugt (billig, keine I/O)
        self.assertTrue(rt.config_path)            # Pfad aufgelöst


FIXTURE = os.path.join(ROOT, "tests", "fixtures", "config.test.json")


class _RecordingClient:
    """Fake-Client mit beobachtbarem Lifecycle (BORROWED-Nachweis)."""

    def __init__(self):
        self.closed = 0

    async def aclose(self):
        self.closed += 1


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class RuntimeIsolationTests(unittest.TestCase):
    """Zwei App-Runtimes besitzen getrennten Laufzeitzustand (serielle Isolation)."""

    def test_two_runtimes_have_separate_state_objects(self):
        a = runtime_mod.Runtime.for_production()
        b = runtime_mod.Runtime.for_production()
        self.assertNotEqual(a.session_token, b.session_token)
        for field in ("ws_clients", "conversations", "pending_confirm", "startup_warnings"):
            self.assertIsNot(getattr(a, field), getattr(b, field), f"{field} geteilt")

    def test_mutating_runtime_a_does_not_touch_runtime_b(self):
        a = runtime_mod.Runtime.for_production()
        b = runtime_mod.Runtime.for_production()
        a.ws_clients.add("client-a")
        a.conversations["sid"] = [{"role": "user", "content": "hallo"}]
        a.pending_confirm["sid"] = "MEMORY_FORGET"
        a.startup_warnings.append("warnung-a")
        self.assertEqual(b.ws_clients, set())
        self.assertEqual(b.conversations, {})
        self.assertEqual(b.pending_confirm, {})
        self.assertEqual(b.startup_warnings, [])

    def test_two_runtimes_can_hold_different_configs(self):
        a = runtime_mod.Runtime.for_production(config_path=FIXTURE, environ={})
        b = runtime_mod.Runtime.for_production(config_path=FIXTURE, environ={})
        a.load_config()
        b.load_config()
        self.assertIsNot(a.config, b.config)          # getrennte Config-Objekte
        a.config["user_name"] = "Nur-A"
        self.assertNotEqual(b.config.get("user_name"), "Nur-A")


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    """Ressourcen öffnen/schließen ausschließlich im Lifespan; owned vs borrowed."""

    async def test_owned_clients_open_on_start_and_close_on_shutdown(self):
        rt = runtime_mod.Runtime.for_production(config_path=FIXTURE, environ={})
        self.assertIsNone(rt.ai)          # vor dem Start: nichts geöffnet
        self.assertIsNone(rt.http)
        await rt.aopen()
        self.assertIsNotNone(rt.ai)       # erst beim Start geöffnet
        self.assertIsNotNone(rt.http)
        self.assertTrue(rt.owns_clients)
        await rt.aclose()
        self.assertIsNone(rt._refresh_task)

    async def test_injected_clients_are_borrowed_and_never_closed(self):
        fake_ai, fake_http = _RecordingClient(), _RecordingClient()
        rt = runtime_mod.Runtime.for_production(
            config_path=FIXTURE, environ={}, ai=fake_ai, http=fake_http)
        await rt.aopen()
        self.assertIs(rt.ai, fake_ai)     # injizierte Clients werden benutzt
        await rt.aclose()
        self.assertEqual(fake_ai.closed, 0, "BORROWED ai wurde geschlossen")
        self.assertEqual(fake_http.closed, 0, "BORROWED http wurde geschlossen")

    async def test_shutdown_is_idempotent(self):
        rt = runtime_mod.Runtime.for_production(config_path=FIXTURE, environ={})
        await rt.aopen()
        await rt.aclose()
        await rt.aclose()          # doppeltes Close ist sicher (kein Fehler)
        self.assertTrue(rt._closed)

    async def test_wire_runs_once(self):
        rt = runtime_mod.Runtime.for_production(config_path=FIXTURE, environ={})
        rt.load_config()
        rt.wire()
        self.assertTrue(rt._wired)
        rt.wire()                  # idempotent — kein Re-Wiring
        self.assertTrue(rt._wired)

    async def test_missing_config_fails_closed_on_start(self):
        missing = os.path.join(os.environ.get("TEMP", "/tmp"), "jarvis_cr_missing.json")
        rt = runtime_mod.Runtime.for_production(config_path=missing, environ={})
        import config_loader
        with self.assertRaises(config_loader.ConfigError):
            await rt.aopen()       # Produktion ohne gültige Config startet nicht

    async def test_startup_failure_cleans_up_opened_resources(self):
        # Config ohne anthropic_api_key: http wird geöffnet, ai-Erzeugung scheitert.
        # Der Lifespan-finally muss das bereits geöffnete http schließen (kein Leak).
        # Slice 5: config ist eine read-only Projektion — die unvollstaendige
        # Config kommt jetzt aus einer echten Temp-Datei statt aus einem Patch.
        import json, tempfile
        tmp = tempfile.mkdtemp(prefix="jarvis-cr-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"schema_version": 1, "elevenlabs_api_key": "x",
                       "anthropic_api_key": "vorhanden"}, f)
        rt = runtime_mod.Runtime.for_production(config_path=path, environ={})
        # ai-Erzeugung scheitert, weil der Key nach dem Laden entfernt wird.
        original_wire = rt.wire
        def _break_key():
            rt.configuration._snapshot = None
            raise KeyError("anthropic_api_key")
        rt.wire = _break_key
        with self.assertRaises(KeyError):
            async with rt.lifespan(object()):
                pass                                  # pragma: no cover
        self.assertTrue(rt._closed, "aclose lief nicht nach Startup-Fehler")

    async def test_new_instance_can_start_after_previous_shutdown(self):
        first = runtime_mod.Runtime.for_production(config_path=FIXTURE, environ={})
        await first.aopen()
        await first.aclose()
        second = runtime_mod.Runtime.for_production(config_path=FIXTURE, environ={})
        await second.aopen()
        self.assertIsNotNone(second.ai)
        await second.aclose()


if __name__ == "__main__":
    unittest.main()

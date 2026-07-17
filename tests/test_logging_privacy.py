"""Regressionstests fuer die im RFC-0004 belegten Leckvektoren L1-L6.

Jeder Test faehrt einen ECHTEN Code-Pfad mit synthetischem Sentinel und prueft am
kombinierten Log-Output (stdlib-Root-Logger UND obslog-Sink), dass der Sentinel
NICHT erscheint. Sichere Metadaten (Typ, Laenge, Codeort) muessen erhalten bleiben.

Diese Tests waren vor der jeweiligen Migration rot (der Sentinel leckte ueber
logger.debug/info/warning), danach gruen.
"""
import asyncio
import dataclasses
import logging
import time
import unittest
from unittest import mock

import tests  # noqa: F401  — synthetische Config-Fixture

import obslog
import actions
import assistant_core
import clipboard_tools

try:
    import server
    from fastapi.testclient import TestClient
    _WS_IMPORT_ERROR = None
except BaseException as _e:  # auch SystemExit (ConfigError) abfangen
    server = None
    TestClient = None
    _WS_IMPORT_ERROR = _e

VALID_ORIGIN = "http://127.0.0.1:8340"

S_CLIP = "SENTINEL-CLIPBOARD-Kontonummer-NEVER"
S_VAULT = "SENTINEL-VAULT-Projekt-Nordlicht-NEVER"
S_USER = "SENTINEL-USERINPUT-Passwort-NEVER"
S_EXC = "SENTINEL-EXCEPTION-Inhalt-NEVER"


class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


class _RootCapture:
    """Faengt ALLE stdlib-Logrecords am Root-Logger ab (formatiert wie ein Sink)."""

    def __enter__(self):
        self.lines: list[str] = []
        handler = logging.Handler()
        handler.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(name)s %(levelname)s %(message)s")

        def emit(record):
            try:
                self.lines.append(fmt.format(record))
            except Exception:
                self.lines.append("<<formatter-error>>")

        handler.emit = emit
        self._handler = handler
        root = logging.getLogger()
        self._old_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *exc):
        root = logging.getLogger()
        root.removeHandler(self._handler)
        root.setLevel(self._old_level)


def run(coro):
    return asyncio.run(coro)


class _PrivacyTestCase(unittest.TestCase):
    def setUp(self):
        self.sink = obslog.MemorySink()
        obslog.configure(sink=self.sink, fmt="text", level="DEBUG")
        self._saved_ai = assistant_core.ai
        # Fake-LLM fuer den Summary-Schritt — es geht nie ein Providercall raus.
        assistant_core.ai = _FakeAI()

    def tearDown(self):
        assistant_core.ai = self._saved_ai
        obslog.reset()

    def combined(self, root_cap):
        return "\n".join(root_cap.lines + self.sink.lines)


class _FakeMessages:
    async def create(self, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(content=[SimpleNamespace(text="Kurze Zusammenfassung.")])


class _FakeAI:
    def __init__(self):
        self.messages = _FakeMessages()


class ActionResultLeakTests(_PrivacyTestCase):
    """L2/L3: Clipboard-/Vault-Inhalt darf nicht ueber 'Action-Ergebnis' lecken."""

    def test_clipboard_content_never_logged(self):
        self._saved_clip = clipboard_tools.get_clipboard_text
        clipboard_tools.get_clipboard_text = lambda: S_CLIP
        try:
            with _RootCapture() as cap:
                run(assistant_core.run_action_and_respond(
                    "sess-l2", actions.Action("CLIPBOARD", "zusammenfassen"), _FakeWS()))
            combined = self.combined(cap)
        finally:
            clipboard_tools.get_clipboard_text = self._saved_clip
        self.assertNotIn(S_CLIP, combined, "L2: Clipboard-Inhalt im Log")
        # Sichere Metadaten bleiben: das Action-Ende wird strukturiert gemeldet.
        self.assertIn("action.finished", combined)
        self.assertIn("CLIPBOARD", combined)

    def test_project_context_vault_content_never_logged(self):
        async def fake_ctx(payload):
            return f'Frage: "x"\n\n{S_VAULT}'

        spec = actions.spec_for("PROJECT_CONTEXT")
        import dataclasses
        with mock.patch.dict(
                actions.REGISTRY,
                {"PROJECT_CONTEXT": dataclasses.replace(
                    spec, execute=lambda payload, ctx: fake_ctx(payload))}):
            with _RootCapture() as cap:
                run(assistant_core.run_action_and_respond(
                    "sess-l3", actions.Action("PROJECT_CONTEXT", "Nordlicht"), _FakeWS()))
            combined = self.combined(cap)
        self.assertNotIn(S_VAULT, combined, "L3: Vault-Inhalt im Log")


class ExceptionLeakTests(_PrivacyTestCase):
    """L5/L6: Exception-Message und roher Traceback duerfen nicht lecken."""

    def test_action_exception_message_and_traceback_never_logged(self):
        async def boom(payload, ctx):
            raise RuntimeError(f"Fehler mit {S_EXC}")

        import dataclasses
        spec = actions.spec_for("SEARCH")
        with mock.patch.dict(
                actions.REGISTRY,
                {"SEARCH": dataclasses.replace(spec, execute=boom)}):
            with _RootCapture() as cap:
                run(assistant_core.run_action_and_respond(
                    "sess-l5", actions.Action("SEARCH", "x"), _FakeWS()))
            combined = self.combined(cap)
        self.assertNotIn(S_EXC, combined, "L5/L6: Exception-Inhalt/Traceback im Log")
        # Sichere Exception-Metadaten bleiben sichtbar.
        self.assertIn("action.failed", combined)
        self.assertIn("RuntimeError", combined)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_WS_IMPORT_ERROR!r}")
class UserInputLeakTests(unittest.TestCase):
    """L4: Roher Nutzer-Text darf nicht ueber den WS-Empfangspfad ins Log."""

    def setUp(self):
        self.sink = obslog.MemorySink()
        obslog.configure(sink=self.sink, fmt="text", level="DEBUG")
        self.client = TestClient(server.app)

    def tearDown(self):
        obslog.reset()

    def _wait_for(self, record, marker, timeout=3.0):
        deadline = time.monotonic() + timeout
        while marker not in record and time.monotonic() < deadline:
            time.sleep(0.02)
        return marker in record

    def test_raw_user_text_never_logged(self):
        seen: list[str] = []

        async def fake_process(session_id, text, ws, mutate_launcher=None):
            seen.append(text)

        # _configure_logging wird im Lifespan aufgerufen — als No-op patchen, damit
        # der Test-Sink nicht durch den produktiven stderr-Sink ersetzt wird.
        with _RootCapture() as cap, \
                mock.patch.object(server, "_configure_logging", lambda: None), \
                mock.patch.object(server.assistant_core, "process_message", fake_process):
            # Token autoritativ aus der App-Runtime (das globale SESSION_TOKEN kann
            # im Vollsuite-Lauf durch andere Tests veralten).
            token = server.app.state.runtime.session_token
            with self.client.websocket_connect(
                    f"/ws?token={token}",
                    headers={"origin": VALID_ORIGIN}) as sock:
                sock.receive_json()  # health-Frame abholen
                sock.send_json({"text": S_USER})
                self.assertTrue(self._wait_for(seen, S_USER), "Nachricht nicht verarbeitet")
            combined = "\n".join(cap.lines + self.sink.lines)
        self.assertNotIn(S_USER, combined, "L4: roher Nutzer-Text im Log")
        # Sichere Metadaten bleiben: der Empfang wird strukturiert (mit Laenge) gemeldet.
        self.assertIn("message.received", combined)


if __name__ == "__main__":
    unittest.main()

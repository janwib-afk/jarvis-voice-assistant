"""Slice 4 — Runtime Ownership + Injection (RFC-0007 §7/§17, Amendment 1 §A1.6).

Die Runtime besitzt Registry, Regeln und **genau einen** Coordinator; die Konstruktion
bleibt import- und I/O-frei. Der Capability-Hook wird ueber ``server/_run_turn`` in
``assistant_core`` injiziert — ohne Rueckreferenz von ``assistant_core`` auf ``server``
oder eine globale Runtime.

``ConversationSession`` bleibt alleiniger Besitzer von Turn, Task, Queue, Cancel und
Confirmation (RFC-0006) — hier nur negativ geprueft: der Coordinator besitzt nichts davon.
"""
import asyncio
import inspect as _inspect
import os
import subprocess
import sys
import unittest

import tests  # noqa: F401

import capability as cap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RuntimeOwnershipTests(unittest.TestCase):
    """Genau ein Coordinator, runtime-eigen, keine neuen Modul-Globals (§7)."""

    def _runtime(self):
        import runtime
        return runtime.Runtime(config_path="unused.json", session_token="tok-123")

    def test_runtime_owns_exactly_one_coordinator(self):
        rt = self._runtime()
        self.assertIsInstance(rt.capabilities, cap.Coordinator)
        # genau eine Instanz — nicht pro Aufruf eine neue
        self.assertIs(rt.capabilities, rt.capabilities)

    def test_coordinator_carries_the_active_rules(self):
        rt = self._runtime()
        report = rt.capabilities.health()
        self.assertEqual(report["rules"], tuple(r.name for r in cap.ACTIVE_RULES))

    def test_dedupe_scope_is_bound_to_the_session_token(self):
        # Verhaltensbasiert ueber die tatsaechlich vom Runtime gebauten Coordinator:
        # zwei Runtimes mit verschiedenen Tokens erzeugen fuer dieselbe Anfrage
        # verschiedene Keys — der lokale Dedupe-Scope ist an die konkrete App
        # gebunden (§19). Ein Probe-Vertrag wird ueber den oeffentlichen Builder
        # ``pilot_contracts`` eingespeist, damit ``rt.capabilities`` ihn kennt.
        import runtime

        probe = cap.CapabilityContract(
            name="probe.thing", version=1, title="T",
            inputs=cap.InputSchema(fields=("q",)), output=cap.OutputSchema(fields=("t",)),
            effects=(cap.EffectClass.READ_LOCAL,), reads=(cap.DataClass.LOCAL,),
            writes=(), scopes=(), timeout_s=5, retry=cap.Retry.NEVER, cancellable=True,
            preview=cap.Preview.NONE, verify=cap.Verify.NONE, health=cap.Health.PASSIVE,
            audit=(), fixture={}, execute=None)
        req = cap.CapabilityRequest("probe.thing", cap.Provenance.OPERATOR, {"q": "x"})

        import capability._pilots as pilots
        orig = pilots.pilot_contracts
        pilots.pilot_contracts = lambda deps: [probe]
        try:
            r1 = runtime.Runtime(config_path="a.json", session_token="tok-A")
            r2 = runtime.Runtime(config_path="a.json", session_token="tok-B")
            k1 = r1.capabilities.idempotency_key(req)
            k2 = r2.capabilities.idempotency_key(req)
        finally:
            pilots.pilot_contracts = orig
        self.assertNotEqual(k1, k2, "Dedupe-Scope nicht an den Session-Token gebunden")

    def test_construction_is_import_and_io_free(self):
        # Import + Runtime-Konstruktion + Coordinator ohne Config/Netz/Clients.
        code = (
            "import runtime\n"
            "rt = runtime.Runtime(config_path='unused.json', session_token='t')\n"
            "assert rt.config is None, 'Config bei Konstruktion geladen'\n"
            "assert rt.ai is None and rt.http is None, 'Client bei Konstruktion erzeugt'\n"
            "import capability\n"
            "assert isinstance(rt.capabilities, capability.Coordinator)\n"
            "assert rt.capabilities.health()['capabilities'] >= 0\n"
            "print('RUNTIME_CAP_OK')\n"
        )
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        env.pop("JARVIS_CONFIG_PATH", None)
        p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=90)
        self.assertEqual(p.returncode, 0, f"stderr:\n{p.stderr}")
        self.assertIn("RUNTIME_CAP_OK", p.stdout)


class NoServiceLocatorTests(unittest.TestCase):
    """Kein Service Locator, keine Rueckreferenz assistant_core -> server/runtime."""

    def test_assistant_core_never_imports_server(self):
        import assistant_core
        src = _inspect.getsource(assistant_core)
        self.assertNotIn("import server", src)
        self.assertNotIn("from server", src)

    def test_assistant_core_has_no_runtime_module_global(self):
        import assistant_core
        self.assertFalse(hasattr(assistant_core, "runtime"),
                         "assistant_core darf keine globale Runtime referenzieren")

    def test_capability_package_exposes_no_mutable_module_global(self):
        import capability._coordinator as mod
        mutable = [n for n, v in vars(mod).items()
                   if not n.startswith("__") and isinstance(v, (list, dict, set))]
        self.assertEqual(mutable, [])


class CapabilityHookInjectionTests(unittest.TestCase):
    """Der Hook fliesst durch server/_run_turn in assistant_core (§17)."""

    def test_process_message_accepts_a_capabilities_hook(self):
        import assistant_core
        params = _inspect.signature(assistant_core.process_message).parameters
        self.assertIn("capabilities", params)
        self.assertIsNone(params["capabilities"].default,
                          "capabilities muss optional sein (Default None)")

    def test_run_action_and_respond_accepts_a_capabilities_hook(self):
        import assistant_core
        params = _inspect.signature(assistant_core.run_action_and_respond).parameters
        self.assertIn("capabilities", params)

    def test_hook_reaches_run_action_and_respond_unchanged(self):
        """Behavioral: was process_message bekommt, gibt es an die Ausfuehrung weiter."""
        import assistant_core

        seen = {}

        async def _fake_run(ctx, action, sink, mutate_launcher=None, capabilities=None):
            seen["capabilities"] = capabilities

        class _FakeAI:
            async def create(self, **kw):
                class _R:
                    content = [type("C", (), {"text": "[ACTION:SEARCH] wetter"})()]
                return _R()

        marker = object()
        ctx = tests_turn_context()
        sink = _CollectingSink()

        orig_run = assistant_core.run_action_and_respond
        orig_ai = assistant_core.ai
        assistant_core.run_action_and_respond = _fake_run
        assistant_core.ai = type("AI", (), {"messages": _FakeAI()})()
        try:
            asyncio.run(assistant_core.process_message(
                ctx, "such was", sink.sink(), capabilities=marker))
        finally:
            assistant_core.run_action_and_respond = orig_run
            assistant_core.ai = orig_ai
        self.assertIs(seen.get("capabilities"), marker)

    def test_server_run_turn_injects_the_runtime_coordinator(self):
        # Quelltextbeleg: der Injektionspunkt ist server/_run_turn, gebunden an rt.
        import server
        src = _inspect.getsource(server.websocket_endpoint)
        self.assertIn("capabilities=", src)
        self.assertIn("rt.capabilities", src)


def tests_turn_context():
    import conversation
    return conversation.TurnContext(
        history=[], pending=None,
        request_confirmation=lambda a: None, correlation_id="c")


class _CollectingSink:
    def __init__(self):
        self.frames = []

    async def _send(self, frame):
        self.frames.append(frame)

    def sink(self, correlation_id="c"):
        import wire_protocol as wp
        ch = wp.ConversationChannel(self._send, wp.ProtocolContext.legacy(),
                                    "s", wp.WireProtocol())
        return ch.event_sink(correlation_id)


if __name__ == "__main__":
    unittest.main()

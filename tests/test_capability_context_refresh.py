"""Slice 10 — den letzten direkten Refresh-Bypass schliessen (Amendment 2 §A2.8).

Startup und Settings-Save liefen seit Prompt 19 ueber ``context.refresh``. Der dritte
Ausloeser — die Aktivierungsnachricht in ``assistant_core.process_message`` — rief
``refresh_data`` weiterhin **direkt** auf und lief damit an Policy, Timeout,
Wirkungsdeklaration und Audit vorbei.

Geprueft wird: derselbe Vertrag, **genau ein** Refresh, gleiche Position relativ zu
History und Prompt-Erstellung, keine zusaetzlichen Provider-Aufrufe.
"""
import asyncio
import unittest
from unittest import mock

import tests  # noqa: F401

import assistant_core
import capability as cap
import wire_protocol as wp


class _CollectingSink:
    def __init__(self):
        self.frames = []

    async def _send(self, frame):
        self.frames.append(frame)

    def sink(self, correlation_id="c"):
        ch = wp.ConversationChannel(self._send, wp.ProtocolContext.legacy(),
                                    "s", wp.WireProtocol())
        return ch.event_sink(correlation_id)


class _FakeAI:
    def __init__(self, reply="Alles klar."):
        outer = self

        class _Messages:
            async def create(self, **kw):
                outer.last_system = kw.get("system", "")

                class _R:
                    content = [type("C", (), {"text": reply})()]
                return _R()

        self.messages = _Messages()
        self.last_system = ""


def _turn_ctx():
    import conversation
    return conversation.TurnContext(
        history=[], pending=None, request_confirmation=lambda a: None,
        correlation_id="c")


class _CountingCoordinator:
    """Faengt ab, welche Capabilities angefragt werden."""

    def __init__(self, inner):
        self._inner = inner
        self.requested = []

    async def attempt(self, request, evidence=None, **kw):
        self.requested.append(request.capability)
        return await self._inner.attempt(request, evidence, **kw)

    def __getattr__(self, item):
        return getattr(self._inner, item)


def _coord():
    return _CountingCoordinator(cap.Coordinator(
        cap.build_registry(cap.CapabilityDeps()), cap.ACTIVE_RULES,
        audit=lambda *a, **k: None))


def _run(text, coord, ai):
    orig = assistant_core.ai
    assistant_core.ai = ai
    try:
        asyncio.run(assistant_core.process_message(
            _turn_ctx(), text, _CollectingSink().sink(), capabilities=coord))
    finally:
        assistant_core.ai = orig


class ActivateRefreshTests(unittest.TestCase):
    def setUp(self):
        self._calls = []
        self._saved = assistant_core.refresh_data
        assistant_core.refresh_data = lambda: self._calls.append(1)

    def tearDown(self):
        assistant_core.refresh_data = self._saved

    def test_activate_runs_through_the_capability(self):
        coord = _coord()
        _run("Jarvis activate", coord, _FakeAI())
        self.assertIn("context.refresh", coord.requested)

    def test_activate_refreshes_exactly_once(self):
        coord = _coord()
        _run("Jarvis activate", coord, _FakeAI())
        self.assertEqual(1, len(self._calls),
                         f"erwartet genau ein Refresh, waren {len(self._calls)}")

    def test_a_normal_message_does_not_refresh(self):
        coord = _coord()
        _run("Wie ist das Wetter?", coord, _FakeAI())
        self.assertEqual([], self._calls)
        self.assertNotIn("context.refresh", coord.requested)

    def test_no_direct_refresh_bypass_remains_in_the_source(self):
        """Der Beleg gegen ein stilles Wiedereinschleichen des Bypasses."""
        import inspect
        # Nur CODE pruefen: ein Kommentar, der den alten Aufruf erwaehnt, ist
        # Dokumentation und kein Bypass.
        code = "\n".join(
            line for line in inspect.getsource(assistant_core.process_message).splitlines()
            if not line.lstrip().startswith("#"))
        self.assertNotIn("to_thread(refresh_data)", code)

    def test_refresh_happens_before_the_prompt_is_built(self):
        """Gleiche Position wie zuvor: der Refresh wirkt auf DIESEN Prompt."""
        order = []
        assistant_core.refresh_data = lambda: order.append("refresh")
        ai = _FakeAI()
        real_build = assistant_core.build_system_prompt

        def _build():
            order.append("prompt")
            return real_build()

        coord = _coord()
        with mock.patch.object(assistant_core, "build_system_prompt", _build):
            _run("Jarvis activate", coord, ai)
        self.assertEqual(["refresh", "prompt"], order[:2])

    def test_no_extra_provider_call_is_introduced(self):
        """``context.refresh`` fuehrt keinen zusaetzlichen LLM-Aufruf ein."""
        ai = _FakeAI()
        calls = []
        real_create = ai.messages.create

        async def _counting(**kw):
            calls.append(1)
            return await real_create(**kw)

        ai.messages.create = _counting
        _run("Jarvis activate", _coord(), ai)
        self.assertEqual(1, len(calls), "genau ein LLM-Aufruf (die Antwort selbst)")


class SharedContractTests(unittest.TestCase):
    """Alle drei Ausloeser benutzen denselben Vertrag (§A2.8)."""

    def test_context_refresh_is_a_single_registered_contract(self):
        registry = cap.build_registry(cap.CapabilityDeps())
        self.assertIn("context.refresh", registry)
        names = [n for n in registry.names() if "refresh" in n]
        self.assertEqual(["context.refresh"], names)

    def test_runtime_startup_uses_the_same_contract(self):
        import inspect
        import runtime as runtime_mod
        source = inspect.getsource(runtime_mod.Runtime.refresh_context)
        self.assertIn("context.refresh", source)


if __name__ == "__main__":
    unittest.main()

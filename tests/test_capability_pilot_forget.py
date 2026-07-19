"""Slice 7 — Pilot memory.forget (RFC-0007 §16, Amendment 1 §A1.5).

Erster Attempt ergibt ``needs:confirmation``; der bestehende gesprochene
Confirmation-Pfad bleibt unveraendert; ``Ja`` fuehrt denselben pending Attempt aus.
**Kein** Authorization Grant, **kein** neuer Session-Zustand, **keine** neue Wire-Form.
Modellinhalt kann sich niemals selbst bestaetigen; ``CancelledError`` bleibt erhalten.

Kontrollierte Grenze: ``memory.forget_memory`` (Vault) — nie echter Vault.
"""
import asyncio
import unittest
from unittest import mock

import tests  # noqa: F401

import capability as cap


class ForgetCensusTests(unittest.TestCase):
    def test_memory_forget_is_in_the_pilot_registry(self):
        reg = cap.build_registry(cap.CapabilityDeps())
        self.assertIn("memory.forget", reg)

    def test_memory_forget_effects_are_frozen(self):
        reg = cap.build_registry(cap.CapabilityDeps())
        view = reg.inspect("memory.forget")
        # destructive (Loeschung) + network-read (Summary-LLM + TTS, Folgeeffekt).
        self.assertEqual(view.effects,
                         frozenset({cap.EffectClass.DESTRUCTIVE,
                                    cap.EffectClass.NETWORK_READ}))
        self.assertEqual(view.reads, frozenset({cap.DataClass.PERSONAL}))
        self.assertEqual(view.writes, frozenset({cap.DataClass.PERSONAL}))
        self.assertIs(view.tier, cap.Tier.GOVERNED)

    def test_forget_is_migrated(self):
        self.assertTrue(cap.is_migrated("MEMORY_FORGET"))


class ConfirmationGateTests(unittest.TestCase):
    """Erster Attempt: needs:confirmation; Vault bleibt unberuehrt (SI-7)."""

    def _coord(self, forget):
        return cap.Coordinator(cap.build_registry(cap.CapabilityDeps()),
                               cap.ACTIVE_RULES, audit=lambda *a, **k: None)

    def test_first_attempt_needs_confirmation_and_does_not_touch_the_vault(self):
        touched = []

        def _forget(q):
            touched.append(q)
            return "geloescht"

        with mock.patch("memory.forget_memory", _forget):
            out = asyncio.run(cap.run_migrated(self._coord(_forget),
                                               _Action("MEMORY_FORGET", "urlaub"),
                                               None, confirmed=False))
        self.assertEqual(touched, [], "Vergessen lief OHNE Bestaetigung")
        self.assertNotIn("geloescht", out)

    def test_confirmed_attempt_executes_and_is_byte_identical(self):
        def _forget(q):
            return f"Ich habe '{q}' vergessen."

        with mock.patch("memory.forget_memory", _forget):
            import actions
            legacy = asyncio.run(actions.spec_for("MEMORY_FORGET").execute(
                "urlaub", _fake_action_ctx()))
            migrated = asyncio.run(cap.run_migrated(self._coord(_forget),
                                                    _Action("MEMORY_FORGET", "urlaub"),
                                                    None, confirmed=True))
        self.assertEqual(migrated, legacy)

    def test_model_content_can_never_self_confirm(self):
        # Ein [ACTION:MEMORY_FORGET] aus der LLM-Antwort ist derived; ohne echte
        # Operator-Bestaetigung (confirmed) fuehrt es NIE aus.
        touched = []
        with mock.patch("memory.forget_memory", lambda q: touched.append(q) or "x"):
            asyncio.run(cap.run_migrated(self._coord(None),
                                         _Action("MEMORY_FORGET", "urlaub"),
                                         None, confirmed=False))
        self.assertEqual(touched, [])

    def test_forget_stays_confirmation_not_authorization(self):
        # SI-2: Voice erfuellt nie einen Grant; memory.forget bleibt Confirmation.
        # Die Policy verlangt CONFIRMATION, nie AUTHORIZATION.
        reg = cap.build_registry(cap.CapabilityDeps())
        contract = reg.get("memory.forget")
        req = cap.CapabilityRequest("memory.forget", cap.Provenance.DERIVED, {"query": "x"})
        decision = cap.decide(contract, req,
                              cap.Evidence(confirmed=False, target_allowed=True))
        self.assertIn(cap.Requirement.CONFIRMATION, decision.requirements)
        self.assertNotIn(cap.Requirement.AUTHORIZATION, decision.requirements)
        self.assertNotIn(cap.Requirement.AUTHORIZATION, decision.denials)


class OrchestrationTests(unittest.TestCase):
    """Der gesprochene Confirmation-Pfad bleibt unveraendert (§17)."""

    def test_yes_path_passes_confirmed_true_to_the_execution(self):
        import assistant_core

        seen = {}
        real_run = cap.run_migrated

        async def _spy(coord, action, ctx, confirmed=False):
            seen["confirmed"] = confirmed
            seen["action"] = action.type
            return await real_run(coord, action, ctx, confirmed=confirmed)

        class _FakeMessages:
            async def create(self, **kw):
                class _R:
                    content = [type("C", (), {"text": "Erledigt."})()]
                return _R()

        pending = _Action("MEMORY_FORGET", "urlaub")
        ctx = _turn_ctx(pending=pending)
        coord = cap.Coordinator(cap.build_registry(cap.CapabilityDeps()),
                                cap.ACTIVE_RULES, audit=lambda *a, **k: None)

        orig_ai = assistant_core.ai
        assistant_core.ai = type("AI", (), {"messages": _FakeMessages()})()
        try:
            with mock.patch("memory.forget_memory", lambda q: "vergessen"), \
                    mock.patch.object(cap, "run_migrated", _spy):
                asyncio.run(assistant_core.process_message(
                    ctx, "Ja bitte", _CollectingSink().sink(), capabilities=coord))
        finally:
            assistant_core.ai = orig_ai
        self.assertEqual(seen.get("action"), "MEMORY_FORGET")
        self.assertTrue(seen.get("confirmed"), "Ja muss confirmed=True durchreichen")

    def test_cancellation_propagates_unchanged(self):
        def _slow_forget(q):
            raise asyncio.CancelledError()

        coord = cap.Coordinator(cap.build_registry(cap.CapabilityDeps()),
                                cap.ACTIVE_RULES, audit=lambda *a, **k: None)
        with mock.patch("memory.forget_memory", _slow_forget):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(cap.run_migrated(coord, _Action("MEMORY_FORGET", "x"),
                                             None, confirmed=True))


# ── Helfer ──────────────────────────────────────────────────────────────────

class _Action:
    def __init__(self, type_, payload):
        self.type = type_
        self.payload = payload


def _turn_ctx(pending=None):
    import conversation
    return conversation.TurnContext(
        history=[], pending=pending, request_confirmation=lambda a: None,
        correlation_id="c")


def _fake_action_ctx():
    import assistant_core
    return assistant_core._action_context(_turn_ctx(), None)


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

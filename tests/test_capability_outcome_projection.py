"""Slice 2 — Outcome-Projektion und Adapter-Haertung (Amendment 2 §A2.7).

Vor der Massenmigration muss feststehen, was ein **Nicht-Erfolg** beobachtbar
ausloest. Bis hierher projizierte der migrierte Pfad jedes Outcome auf einen
blossen String und schickte danach unbedingt ein ``done`` — eine abgelehnte oder
fehlgeschlagene Wirkung sah am Draht aus wie eine gelungene.

Geprueft wird am oeffentlichen Seam: den **Frames**, die ``run_action_and_respond``
emittiert, und den Folgeeffekten (Summary-LLM, TTS). Kein Test greift auf
Coordinator-Interna zu; der Coordinator selbst wird als Fake an seiner echten
Grenze ersetzt.
"""
import asyncio
import unittest

import tests  # noqa: F401

import assistant_core
import capability as cap
import wire_protocol as wp


class _Action:
    def __init__(self, type_, payload=""):
        self.type = type_
        self.payload = payload


class _FixedCoordinator:
    """Fake an der echten Grenze: liefert genau ein vorgegebenes ``Outcome``."""

    def __init__(self, outcome):
        self._outcome = outcome
        self.calls = 0

    async def attempt(self, request, evidence=None, **kw):
        self.calls += 1
        return self._outcome


class _CollectingSink:
    def __init__(self):
        self.frames = []

    async def _send(self, frame):
        self.frames.append(frame)

    def sink(self, correlation_id="c"):
        ch = wp.ConversationChannel(self._send, wp.ProtocolContext.legacy(),
                                    "s", wp.WireProtocol())
        return ch.event_sink(correlation_id)

    def phases(self):
        return [f.get("phase") for f in self.frames if f.get("type") == "action"]

    def components(self):
        return [f.get("component") for f in self.frames if f.get("type") == "error"]


def _turn_ctx():
    import conversation
    return conversation.TurnContext(
        history=[], pending=None, request_confirmation=lambda a: None,
        correlation_id="c")


class _CountingAI:
    """Zaehlt Summary-LLM-Aufrufe — der Folgeeffekt, der nie nach einem
    Nicht-Erfolg laufen darf (§A2.5)."""

    def __init__(self):
        self.calls = 0
        outer = self

        class _Messages:
            async def create(self, **kw):
                outer.calls += 1

                class _R:
                    content = [type("C", (), {"text": "Zusammenfassung."})()]
                return _R()

        self.messages = _Messages()


def _outcome(status, value=None, **kw):
    return cap.Outcome(status=status, value=value, **kw)


def _run(action, coordinator, sink, ai):
    orig = assistant_core.ai
    assistant_core.ai = ai
    try:
        asyncio.run(assistant_core.run_action_and_respond(
            _turn_ctx(), action, sink.sink(), capabilities=coordinator))
    finally:
        assistant_core.ai = orig


class TypedLegacyProjectionTests(unittest.IsolatedAsyncioTestCase):
    """``run_migrated`` liefert eine typisierte Projektion, keinen nackten String."""

    async def test_ok_projection_carries_text_and_ok_flag(self):
        coord = _FixedCoordinator(_outcome(cap.OutcomeStatus.OK, {"text": "Ergebnis"}))
        result = await cap.run_migrated(
            coord, _Action("SEARCH", "x"), _fake_ctx())
        self.assertEqual("Ergebnis", result.text)
        self.assertTrue(result.ok)
        self.assertIs(cap.OutcomeStatus.OK, result.status)

    async def test_denied_projection_is_not_ok(self):
        coord = _FixedCoordinator(_outcome(cap.OutcomeStatus.DENIED))
        result = await cap.run_migrated(coord, _Action("SEARCH", "x"), _fake_ctx())
        self.assertFalse(result.ok)
        self.assertIs(cap.OutcomeStatus.DENIED, result.status)

    async def test_partial_is_degraded_but_not_ok(self):
        """§A2.7: ``partial`` ist ausdruecklich degradiert, nie uneingeschraenktes done."""
        coord = _FixedCoordinator(
            _outcome(cap.OutcomeStatus.PARTIAL, {"text": "halb"}))
        result = await cap.run_migrated(coord, _Action("SEARCH", "x"), _fake_ctx())
        self.assertFalse(result.ok)
        self.assertTrue(result.degraded)

    async def test_every_status_has_a_speakable_text(self):
        for status in cap.OutcomeStatus:
            with self.subTest(status=status):
                value = {"text": "t"} if status is cap.OutcomeStatus.OK else None
                coord = _FixedCoordinator(_outcome(status, value))
                result = await cap.run_migrated(
                    coord, _Action("SEARCH", "x"), _fake_ctx())
                self.assertTrue(result.text.strip(), f"{status} ohne Text")


class NoFalseDoneTests(unittest.TestCase):
    """Der Kern des Slices: ein Nicht-Erfolg darf nie wie ein Erfolg aussehen."""

    def test_ok_still_emits_done(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.OK, {"text": "Treffer"})),
             sink, ai)
        self.assertEqual(["start", "done"], sink.phases())

    def test_denied_emits_error_not_done(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.DENIED)), sink, ai)
        self.assertEqual(["start", "error"], sink.phases())
        self.assertNotIn("done", sink.phases())

    def test_needs_emits_error_not_done(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("MEMORY_FORGET", "x"),
             _FixedCoordinator(_outcome(
                 cap.OutcomeStatus.NEEDS,
                 requirements=frozenset({cap.Requirement.CONFIRMATION}))), sink, ai)
        self.assertEqual(["start", "error"], sink.phases())

    def test_timeout_emits_error_not_done(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.TIMEOUT)), sink, ai)
        self.assertEqual(["start", "error"], sink.phases())

    def test_failed_emits_error_not_done(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.FAILED,
                                        error_type="RuntimeError")), sink, ai)
        self.assertEqual(["start", "error"], sink.phases())

    def test_partial_does_not_emit_unqualified_done(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.PARTIAL, {"text": "halb"})),
             sink, ai)
        self.assertNotIn("done", sink.phases())


class NoSuccessFollowOnAfterFailureTests(unittest.TestCase):
    """§A2.5: Summary und TTS sind Teil des Wirkungsvertrags — kein Erfolgs-Nachlauf."""

    def test_summary_llm_runs_on_success(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.OK, {"text": "Treffer"})),
             sink, ai)
        self.assertEqual(1, ai.calls)

    def test_summary_llm_does_not_run_after_denied(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.DENIED)), sink, ai)
        self.assertEqual(0, ai.calls)

    def test_summary_llm_does_not_run_after_failed(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("MEMORY_FORGET", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.FAILED,
                                        error_type="OSError")), sink, ai)
        self.assertEqual(0, ai.calls)

    def test_failure_still_speaks_the_existing_wording(self):
        """Bestehende Fehlertexte bleiben erhalten — nur der falsche done faellt weg."""
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.DENIED)), sink, ai)
        spoken = [f for f in sink.frames if f.get("type") == "response"]
        self.assertEqual(1, len(spoken))
        self.assertIn("nicht funktioniert", spoken[0]["text"])

    def test_failure_reports_an_error_frame_to_the_client(self):
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"),
             _FixedCoordinator(_outcome(cap.OutcomeStatus.FAILED,
                                        error_type="RuntimeError")), sink, ai)
        self.assertIn("browser", sink.components())


class CancellationAndTimeoutOwnershipTests(unittest.TestCase):
    """``CancelledError`` bleibt unveraendert; der Coordinator bleibt Timeout-Owner."""

    def test_cancelled_error_propagates_unchanged(self):
        class _Cancelling:
            async def attempt(self, request, evidence=None, **kw):
                raise asyncio.CancelledError()

        sink, ai = _CollectingSink(), _CountingAI()
        with self.assertRaises(asyncio.CancelledError):
            _run(_Action("SEARCH", "x"), _Cancelling(), sink, ai)
        self.assertEqual(["start", "error"], sink.phases())

    def test_migrated_path_has_no_second_wait_for(self):
        """Nur der Coordinator besitzt den Timeout (§A2.7).

        Der Fake laeuft laenger als das ActionSpec-Timeout von SEARCH; wuerde der
        Adapter ein eigenes ``wait_for`` legen, schlueg es hier zu.
        """
        import actions

        class _Slow:
            async def attempt(self, request, evidence=None, **kw):
                await asyncio.sleep(0.05)
                return _outcome(cap.OutcomeStatus.OK, {"text": "spaet"})

        self.assertGreater(actions.spec_for("SEARCH").timeout, 0.05)
        sink, ai = _CollectingSink(), _CountingAI()
        _run(_Action("SEARCH", "x"), _Slow(), sink, ai)
        self.assertEqual(["start", "done"], sink.phases())


class ImmutableMappingTests(unittest.TestCase):
    """``MIGRATED_ACTIONS`` ist eine Sicherheitszuordnung — nicht zur Laufzeit biegbar."""

    def test_mapping_cannot_be_mutated(self):
        with self.assertRaises(TypeError):
            cap.MIGRATED_ACTIONS["SEARCH"] = "web.evil"

    def test_mapping_cannot_gain_entries(self):
        with self.assertRaises(TypeError):
            cap.MIGRATED_ACTIONS["NEW"] = "x.y"


def _fake_ctx():
    import actions
    return actions.ActionContext()


if __name__ == "__main__":
    unittest.main()

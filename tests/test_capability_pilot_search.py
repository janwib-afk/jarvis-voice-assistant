"""Slice 5 — Pilot web.search (RFC-0007 §22, Amendment 1 §A1.1/§A1.2).

`[ACTION:SEARCH]` bleibt byte- und shape-exakt; der Legacy-Adapter setzt Provenance
`derived` und fuehrt `web.search` ueber **denselben** Coordinator. Das rohe Ergebnis
wird byte-identisch in die bestehende Action-/Summary-/TTS-Orchestrierung projiziert.

Kontrollierte Grenze: `browser_tools.search_and_read` (Provider) — nie echtes Netz.
"""
import asyncio
import unittest
from unittest import mock

import tests  # noqa: F401

import capability as cap


class WebSearchCensusTests(unittest.TestCase):
    """Der Wirkungs-Zensus des Piloten (§23) — eingefroren und mutationsgeprueft."""

    def test_web_search_is_in_the_pilot_registry(self):
        reg = cap.build_registry(cap.CapabilityDeps())
        self.assertIn("web.search", reg)

    def test_web_search_effects_are_frozen(self):
        reg = cap.build_registry(cap.CapabilityDeps())
        view = reg.inspect("web.search")
        # network-read (Suche + Summary-LLM + TTS) + local-execute (sichtbarer
        # Chromium-Prozess + PowerShell-Fokus). Folgeeffekte vollstaendig (§A1.2).
        self.assertEqual(view.effects,
                         frozenset({cap.EffectClass.NETWORK_READ,
                                    cap.EffectClass.LOCAL_EXECUTE}))
        self.assertEqual(view.reads, frozenset({cap.DataClass.PUBLIC}))
        self.assertEqual(view.writes, frozenset())
        self.assertIs(view.tier, cap.Tier.GOVERNED)

    def test_web_search_version_is_one(self):
        reg = cap.build_registry(cap.CapabilityDeps())
        self.assertEqual(reg.get("web.search").version, 1)


class LegacyAdapterTests(unittest.TestCase):
    """Der Adapter setzt derived und projiziert das Ergebnis byte-identisch."""

    def test_search_maps_to_web_search(self):
        """Phase 5C loest die Pilotgrenze ab.

        Bis Prompt 19 behauptete dieser Test zusaetzlich, SEARCH sei die EINZIGE
        migrierte Voice-Action. Diese Praemisse faellt mit Amendment 2 §A2.1
        planmaessig weg; die Vollstaendigkeit (22/22) belegt seither der
        Phase-5C-Audit, nicht mehr eine Negativliste an dieser Stelle.
        """
        self.assertTrue(cap.is_migrated("SEARCH"))
        self.assertEqual("web.search", cap.MIGRATED_ACTIONS["SEARCH"])

    def test_migrated_result_is_byte_identical_to_the_legacy_path(self):
        fake = {"title": "Wetter Hamburg", "url": "https://x.test/w",
                "content": "17 Grad, wolkig. " * 200}

        async def _search(q):
            return dict(fake)

        with mock.patch("browser_tools.search_and_read", _search):
            # Legacy: das rohe Ergebnis von actions._exec_search.
            import actions
            legacy = asyncio.run(actions.spec_for("SEARCH").execute(
                "wetter hamburg", _fake_action_ctx()))
            # Migriert: dieselbe Eingabe ueber den Coordinator.
            coord = _coord()
            action = _Action("SEARCH", "wetter hamburg")
            migrated = asyncio.run(cap.run_migrated(coord, action, None))
        self.assertEqual(migrated.text, legacy)

    def test_adapter_uses_derived_provenance(self):
        seen = {}

        async def _search(q):
            return {"title": "t", "url": "u", "content": "c"}

        real_attempt = cap.Coordinator.attempt

        async def _spy(self, request, evidence=None, **kw):
            # ``**kw`` spiegelt die erweiterte Coordinator-Signatur (meta/bindings,
            # Amendment 2 §A2.4) — das geprueffte Verhalten bleibt unveraendert.
            seen["provenance"] = request.provenance
            seen["capability"] = request.capability
            return await real_attempt(self, request, evidence, **kw)

        with mock.patch("browser_tools.search_and_read", _search), \
                mock.patch.object(cap.Coordinator, "attempt", _spy):
            asyncio.run(cap.run_migrated(_coord(), _Action("SEARCH", "x"), None))
        self.assertIs(seen["provenance"], cap.Provenance.DERIVED)
        self.assertEqual(seen["capability"], "web.search")

    def test_search_failure_stays_speakable(self):
        async def _search(q):
            return {"error": "kein Netz"}

        with mock.patch("browser_tools.search_and_read", _search):
            out = asyncio.run(cap.run_migrated(_coord(), _Action("SEARCH", "x"), None))
        self.assertIn("fehlgeschlagen", out.text)


class OrchestrationIntegrationTests(unittest.TestCase):
    """SEARCH ueber run_action_and_respond dispatcht durch den Coordinator (§17)."""

    def test_search_is_dispatched_through_the_coordinator(self):
        import assistant_core

        dispatched = {}
        real_run = cap.run_migrated

        async def _spy(coord, action, ctx, confirmed=False):
            dispatched["action"] = action.type
            return await real_run(coord, action, ctx, confirmed=confirmed)

        async def _search(q):
            return {"title": "T", "url": "U", "content": "C"}

        class _FakeMessages:
            async def create(self, **kw):
                class _R:
                    content = [type("C", (), {"text": "Kurzfassung."})()]
                return _R()

        ctx = _turn_ctx()
        sink = _CollectingSink()
        coord = _coord()

        orig_ai = assistant_core.ai
        assistant_core.ai = type("AI", (), {"messages": _FakeMessages()})()
        try:
            with mock.patch("browser_tools.search_and_read", _search), \
                    mock.patch.object(cap, "run_migrated", _spy):
                asyncio.run(assistant_core.run_action_and_respond(
                    ctx, _Action("SEARCH", "wetter"), sink.sink(), capabilities=coord))
        finally:
            assistant_core.ai = orig_ai
        self.assertEqual(dispatched.get("action"), "SEARCH")

    def test_not_yet_migrated_action_still_uses_execute_action(self):
        """Der Legacy-Fallback traegt weiterhin, was noch nicht migriert ist.

        NEWS war hier bis Prompt 19 das Beispiel; seit Phase 5C Slice 3 laeuft es
        ueber den Coordinator. Das Beispiel ist deshalb auf eine noch offene
        Action gewechselt. Der Fallback selbst faellt planmaessig in Slice 12 —
        dieser Test wird dort durch seine Umkehrung ersetzt.
        """
        import assistant_core

        called = {"legacy": False}
        real_exec = assistant_core.execute_action

        async def _spy_exec(action, ctx, mutate_launcher=None):
            called["legacy"] = True
            return await real_exec(action, ctx, mutate_launcher)

        self.assertFalse(cap.is_migrated("APP_PLACE"))
        with mock.patch.object(assistant_core, "execute_action", _spy_exec):
            asyncio.run(assistant_core.run_action_and_respond(
                _turn_ctx(), _Action("APP_PLACE", ""), _CollectingSink().sink(),
                capabilities=_coord()))
        self.assertTrue(called["legacy"],
                        "APP_PLACE ist nicht migriert und muss ueber den Fallback laufen")


# ── Helfer ──────────────────────────────────────────────────────────────────

class _Action:
    def __init__(self, type_, payload):
        self.type = type_
        self.payload = payload


def _coord():
    return cap.Coordinator(cap.build_registry(cap.CapabilityDeps()), cap.ACTIVE_RULES,
                           audit=lambda *a, **k: None)


def _turn_ctx():
    import conversation
    return conversation.TurnContext(
        history=[], pending=None, request_confirmation=lambda a: None,
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

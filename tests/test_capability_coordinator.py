"""SEAM-CAPABILITY-COORDINATION — Lifecycle (RFC-0007 §10/§11, Amendment 1 §A1.6).

Geprueft ueber die oeffentliche Oberflaeche ``Coordinator.attempt`` und das
geschlossene Ergebnismodell. Kontrollierte Grenze: **Fake-Vertraege** (kein Provider,
kein Netz, kein Dateisystem) plus injizierte Clock und Audit-Senke.

Verboten (TEST_SEAMS): keine Assertions auf interne Stufenlisten, keine Call-Counts auf
``decide``, kein Zugriff auf private Helfer. Dass keine Stufe uebersprungen wird, ist
**verhaltensbasiert** belegt: was nicht laufen darf, hinterlaesst keine Spur.
"""
import asyncio
import unittest

import tests  # noqa: F401

import capability as cap


class _Clock:
    """Deterministische Uhr — der Coordinator misst Dauer, die Tests nicht."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 0.25
        return self.t


class _Audit:
    """Aufzeichnende Audit-Senke (zweiter Adapter neben obslog.event)."""

    def __init__(self):
        self.events = []

    def __call__(self, name, **fields):
        self.events.append((name, fields))

    def outcomes(self):
        return [f.get("outcome") for n, f in self.events if n == "capability.attempted"]


def _contract(execute, **over):
    base = dict(
        name="test.thing", version=1, title="T",
        inputs=cap.InputSchema(fields=("query",)),
        output=cap.OutputSchema(fields=("text",)),
        effects=(cap.EffectClass.READ_LOCAL,),
        reads=(cap.DataClass.LOCAL,), writes=(),
        scopes=(), timeout_s=5, retry=cap.Retry.NEVER, cancellable=True,
        preview=cap.Preview.NONE, verify=cap.Verify.SELF_REPORTED,
        health=cap.Health.PASSIVE,
        audit=("name", "version", "outcome", "duration_ms"),
        fixture={"query": "x"}, execute=execute,
    )
    base.update(over)
    return cap.CapabilityContract(**base)


def _coord(contract, audit=None, rules=None):
    return cap.Coordinator(
        cap.Registry([contract]),
        rules if rules is not None else cap.ACTIVE_RULES,
        clock=_Clock(), audit=audit or _Audit(),
    )


def _req(name="test.thing", provenance=cap.Provenance.OPERATOR, **payload):
    return cap.CapabilityRequest(name, provenance, payload or {"query": "x"})


def _run(coro):
    return asyncio.run(coro)


class LifecycleOrderTests(unittest.TestCase):
    """validate -> preview -> authorize -> execute -> verify; keine Stufe entfaellt."""

    def test_successful_attempt_returns_ok_with_the_declared_output(self):
        async def ex(payload, ctx):
            return {"text": "ergebnis fuer " + payload["query"]}
        out = _run(_coord(_contract(ex)).attempt(_req(query="wetter"), cap.Evidence()))
        self.assertIs(out.status, cap.OutcomeStatus.OK)
        self.assertEqual(out.value["text"], "ergebnis fuer wetter")

    def test_execute_never_runs_when_the_policy_denies(self):
        ran = []

        async def ex(payload, ctx):
            ran.append(1)
            return {"text": "darf nicht passieren"}

        c = _contract(ex, name="web.search",
                      effects=(cap.EffectClass.NETWORK_READ,),
                      reads=(cap.DataClass.PUBLIC,), writes=())
        out = _run(_coord(c).attempt(_req("web.search"),
                                     cap.Evidence(target_allowed=False)))
        self.assertIs(out.status, cap.OutcomeStatus.DENIED)
        self.assertEqual(ran, [], "execute lief trotz deny")

    def test_execute_never_runs_when_the_policy_needs_something(self):
        ran = []

        async def ex(payload, ctx):
            ran.append(1)
            return {"text": "darf nicht passieren"}

        c = _contract(ex, name="memory.forget",
                      effects=(cap.EffectClass.DESTRUCTIVE,),
                      reads=(cap.DataClass.PERSONAL,),
                      writes=(cap.DataClass.PERSONAL,))
        out = _run(_coord(c).attempt(_req("memory.forget"), cap.Evidence(confirmed=False)))
        self.assertIs(out.status, cap.OutcomeStatus.NEEDS)
        self.assertIn(cap.Requirement.CONFIRMATION, out.requirements)
        self.assertEqual(ran, [], "execute lief trotz offener Anforderung")

    def test_validate_runs_before_authorize(self):
        # Ein Schemaverstoss ist ein Adapterfehler und wirft — auch dann, wenn die
        # Policy ohnehin verweigert haette. Damit ist die Reihenfolge belegt.
        ran = []

        async def ex(payload, ctx):
            ran.append(1)
            return {"text": "x"}

        c = _contract(ex, name="web.search",
                      effects=(cap.EffectClass.NETWORK_READ,),
                      reads=(cap.DataClass.PUBLIC,), writes=())
        with self.assertRaises(cap.SchemaError):
            _run(_coord(c).attempt(
                cap.CapabilityRequest("web.search", cap.Provenance.OPERATOR,
                                      {"schmuggel": "y"}),
                cap.Evidence(target_allowed=False)))
        self.assertEqual(ran, [])

    def test_unknown_capability_raises_and_is_never_an_outcome(self):
        async def ex(payload, ctx):
            return {"text": "x"}
        with self.assertRaises(cap.UnknownCapability):
            _run(_coord(_contract(ex)).attempt(_req("nicht.da"), cap.Evidence()))


class OutcomeModelTests(unittest.TestCase):
    """Geschlossenes Ergebnismodell (§11): Domaenenablehnungen sind Ergebnisse."""

    def test_execution_error_becomes_failed_not_an_exception(self):
        async def ex(payload, ctx):
            raise RuntimeError("kaputt")
        out = _run(_coord(_contract(ex)).attempt(_req(), cap.Evidence()))
        self.assertIs(out.status, cap.OutcomeStatus.FAILED)
        self.assertEqual(out.error_type, "RuntimeError")

    def test_error_message_never_leaks_into_the_outcome(self):
        async def ex(payload, ctx):
            raise RuntimeError("geheimer vault inhalt")
        out = _run(_coord(_contract(ex)).attempt(_req(), cap.Evidence()))
        self.assertNotIn("geheim", repr(out))

    def test_timeout_becomes_an_outcome_not_an_exception(self):
        async def ex(payload, ctx):
            await asyncio.sleep(10)
        out = _run(_coord(_contract(ex, timeout_s=0.01)).attempt(_req(), cap.Evidence()))
        self.assertIs(out.status, cap.OutcomeStatus.TIMEOUT)

    def test_every_status_is_from_the_closed_model(self):
        self.assertEqual(
            {s.value for s in cap.OutcomeStatus},
            {"ok", "partial", "denied", "needs", "timeout", "cancelled", "failed"})


class VerifyTests(unittest.TestCase):
    """verify darf ok zu partial herabstufen, nie umgekehrt (§11)."""

    def test_incomplete_result_is_downgraded_to_partial(self):
        async def ex(payload, ctx):
            return {}  # 'text' fehlt
        out = _run(_coord(_contract(ex)).attempt(_req(), cap.Evidence()))
        self.assertIs(out.status, cap.OutcomeStatus.PARTIAL)
        self.assertIn("text", out.pending)

    def test_partial_is_never_upgraded_to_ok(self):
        async def ex(payload, ctx):
            return {}
        for verify in (cap.Verify.SELF_REPORTED, cap.Verify.OBSERVABLE):
            with self.subTest(verify=verify):
                out = _run(_coord(_contract(ex, verify=verify)).attempt(
                    _req(), cap.Evidence()))
                self.assertIsNot(out.status, cap.OutcomeStatus.OK)

    def test_verify_none_is_recorded_instead_of_claiming_success(self):
        async def ex(payload, ctx):
            return {}
        audit = _Audit()
        c = _contract(ex, verify=cap.Verify.NONE)
        out = _run(_coord(c, audit=audit).attempt(_req(), cap.Evidence()))
        self.assertIs(out.status, cap.OutcomeStatus.OK)
        self.assertTrue(any(n == "capability.unverified" for n, _ in audit.events),
                        "verify='none' muss vermerkt werden, statt Erfolg zu behaupten")

    def test_audit_records_the_outcome_after_a_normal_execution_error(self):
        async def ex(payload, ctx):
            raise RuntimeError("kaputt")
        audit = _Audit()
        _run(_coord(_contract(ex), audit=audit).attempt(_req(), cap.Evidence()))
        self.assertEqual(audit.outcomes(), ["failed"])


class CancellationTests(unittest.TestCase):
    """CancelledError unveraendert; danach KEIN Verify (Amendment 1 §A1.6)."""

    def test_cancelled_error_propagates_unchanged(self):
        async def ex(payload, ctx):
            await asyncio.Event().wait()

        async def scenario():
            co = _coord(_contract(ex, timeout_s=30))
            task = asyncio.create_task(co.attempt(_req(), cap.Evidence()))
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        _run(scenario())

    def test_no_audit_and_no_verify_after_cancellation(self):
        async def ex(payload, ctx):
            await asyncio.Event().wait()

        audit = _Audit()

        async def scenario():
            co = _coord(_contract(ex, timeout_s=30), audit=audit)
            task = asyncio.create_task(co.attempt(_req(), cap.Evidence()))
            await asyncio.sleep(0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        _run(scenario())
        self.assertEqual(audit.outcomes(), [],
                         "nach CancelledError darf kein Outcome verbucht werden")

    def test_cancelled_outcome_is_only_a_cooperative_domain_cancellation(self):
        # Amendment 1 F3: 'cancelled' meint NUR eine vom Executor normal gemeldete
        # Stornierung — nicht die propagierte CancelledError.
        async def ex(payload, ctx):
            return cap.Cancelled("nutzer hat abgelehnt")
        out = _run(_coord(_contract(ex)).attempt(_req(), cap.Evidence()))
        self.assertIs(out.status, cap.OutcomeStatus.CANCELLED)


class IdempotencyTests(unittest.TestCase):
    """Deterministischer Schluessel — aber kein Cache, kein Dedupe (§19, Amendment F4)."""

    async def _ex(self, payload, ctx):
        return {"text": "x"}

    def test_key_is_deterministic_for_the_same_request(self):
        co = _coord(_contract(self._ex))
        a = co.idempotency_key(_req(query="wetter"))
        b = co.idempotency_key(_req(query="wetter"))
        self.assertEqual(a, b)

    def test_key_changes_with_input_version_and_scope(self):
        c1 = _contract(self._ex)
        c2 = _contract(self._ex, version=2)
        base = cap.Coordinator(cap.Registry([c1]), cap.ACTIVE_RULES,
                               clock=_Clock(), audit=_Audit())
        other_version = cap.Coordinator(cap.Registry([c2]), cap.ACTIVE_RULES,
                                        clock=_Clock(), audit=_Audit())
        other_scope = cap.Coordinator(cap.Registry([c1]), cap.ACTIVE_RULES,
                                      clock=_Clock(), audit=_Audit(),
                                      dedupe_scope="andere-session")
        k = base.idempotency_key(_req(query="wetter"))
        self.assertNotEqual(k, base.idempotency_key(_req(query="anders")))
        self.assertNotEqual(k, other_version.idempotency_key(_req(query="wetter")))
        self.assertNotEqual(k, other_scope.idempotency_key(_req(query="wetter")))

    def test_wire_ids_can_never_reach_the_key(self):
        # §18/§19: event_id ist kein Idempotency Key, correlation_id keine Job-ID.
        co = _coord(_contract(self._ex))
        with self.assertRaises(cap.SchemaError):
            co.idempotency_key(cap.CapabilityRequest(
                "test.thing", cap.Provenance.OPERATOR,
                {"query": "x", "event_id": "abc"}))

    def test_identical_attempts_both_execute_there_is_no_cache(self):
        runs = []

        async def ex(payload, ctx):
            runs.append(payload["query"])
            return {"text": "x"}

        async def scenario():
            co = _coord(_contract(ex))
            await co.attempt(_req(query="wetter"), cap.Evidence())
            await co.attempt(_req(query="wetter"), cap.Evidence())
        _run(scenario())
        self.assertEqual(runs, ["wetter", "wetter"], "Prompt 19 baut keinen Cache")

    def test_the_key_reaches_the_execution(self):
        seen = []

        async def ex(payload, ctx):
            seen.append(ctx.idempotency_key)
            return {"text": "x"}

        co = _coord(_contract(ex))
        _run(co.attempt(_req(query="wetter"), cap.Evidence()))
        self.assertEqual(seen, [co.idempotency_key(_req(query="wetter"))])


class NoRetryAndNoTaskOwnershipTests(unittest.TestCase):
    """Kein Retry, keine Task-/Queue-/Lock-Verantwortung (§11/§19)."""

    def test_a_failing_capability_is_attempted_exactly_once(self):
        runs = []

        async def ex(payload, ctx):
            runs.append(1)
            raise RuntimeError("kaputt")

        _run(_coord(_contract(ex, retry=cap.Retry.ON_TRANSPORT)).attempt(
            _req(), cap.Evidence()))
        self.assertEqual(len(runs), 1, "retry ist deklarative Eignung, keine Engine")

    def test_coordinator_owns_no_task_queue_or_lock(self):
        co = _coord(_contract(lambda p, c: None))
        forbidden = [n for n, v in vars(co).items()
                     if isinstance(v, (asyncio.Queue, asyncio.Lock, asyncio.Task))]
        self.assertEqual(forbidden, [])


class PassiveHealthAndAuditTests(unittest.TestCase):
    """Health ist passiv; Audit traegt nur Allowlist-Metadaten (§20, Amendment F5)."""

    def test_health_never_executes_and_costs_nothing(self):
        ran = []

        async def ex(payload, ctx):
            ran.append(1)
            return {"text": "x"}

        co = _coord(_contract(ex))
        report = co.health()
        self.assertEqual(ran, [])
        self.assertEqual(report["capabilities"], 1)

    def test_audit_carries_only_allowlisted_metadata(self):
        async def ex(payload, ctx):
            return {"text": "geheimes ergebnis"}

        audit = _Audit()
        _run(_coord(_contract(ex), audit=audit).attempt(
            _req(query="geheime suchanfrage"), cap.Evidence()))
        for name, fields in audit.events:
            for key in fields:
                with self.subTest(event=name, field=key):
                    self.assertIn(key, {"capability", "version", "outcome",
                                        "duration_ms", "effects", "reason"})
            self.assertNotIn("geheim", repr(fields))

    def test_audit_event_names_are_known_to_obslog(self):
        # Ein unbekannter Eventname wuerde von obslog stumm verworfen — dann waere
        # das Audit eine Behauptung ohne Wirkung.
        import obslog
        audit = _Audit()

        async def ex(payload, ctx):
            return {}
        _run(_coord(_contract(ex, verify=cap.Verify.NONE), audit=audit).attempt(
            _req(), cap.Evidence()))
        for name, _ in audit.events:
            with self.subTest(event=name):
                self.assertIn(name, obslog._CATALOG)


if __name__ == "__main__":
    unittest.main()

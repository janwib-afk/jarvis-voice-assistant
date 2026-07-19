"""SEAM-POLICY — reiner Policy Kernel (RFC-0007 §12, Amendment 1 §A1.5).

``decide`` wird als **Tabelle** geprueft: jede aktive Regel hat mindestens einen
Erlaubnis- und einen Ablehnungs-/needs-Fall. Zusaetzlich Permutationstests, weil die
Komposition ausdruecklich reihenfolgeunabhaengig ist.

Verboten (TEST_SEAMS): keine Assertions auf Regel-Reihenfolge, keine Call-Counts auf
``decide``, kein Zugriff auf private Helfer.
"""
import itertools
import unittest

import tests  # noqa: F401

import capability as cap


def _contract(**over):
    base = dict(
        name="test.thing", version=1, title="T",
        inputs=cap.InputSchema(fields=("query",)),
        output=cap.OutputSchema(fields=("text",)),
        effects=(cap.EffectClass.READ_LOCAL,),
        reads=(cap.DataClass.LOCAL,), writes=(),
        scopes=(), timeout_s=5, retry=cap.Retry.NEVER, cancellable=True,
        preview=cap.Preview.NONE, verify=cap.Verify.NONE,
        health=cap.Health.PASSIVE, audit=(), fixture={}, execute=None,
    )
    base.update(over)
    return cap.CapabilityContract(**base)


def _req(provenance=cap.Provenance.OPERATOR, name="test.thing"):
    return cap.CapabilityRequest(capability=name, provenance=provenance, payload={})


NETWORK = _contract(name="web.search",
                    effects=(cap.EffectClass.NETWORK_READ,),
                    reads=(cap.DataClass.PUBLIC,), writes=(),
                    scopes=(cap.Scope.WEB,))
DESTRUCTIVE = _contract(name="memory.forget",
                        effects=(cap.EffectClass.DESTRUCTIVE,),
                        reads=(cap.DataClass.PERSONAL,),
                        writes=(cap.DataClass.PERSONAL,),
                        scopes=(cap.Scope.VAULT,))
EXTERNAL = _contract(name="mail.send",
                     effects=(cap.EffectClass.EXTERNAL_WRITE,),
                     reads=(cap.DataClass.PERSONAL,),
                     writes=(cap.DataClass.PERSONAL,))
TRIVIAL = _contract(name="profile.status",
                    effects=(cap.EffectClass.READ_LOCAL,),
                    reads=(cap.DataClass.LOCAL,), writes=())


class ActiveRuleSetTests(unittest.TestCase):
    """Nur erfuellbare Regeln sind aktiv (D6). Der Rest ist datiert, nicht scharf."""

    def test_exactly_three_rules_are_active_in_phase_5(self):
        self.assertEqual(
            tuple(r.name for r in cap.ACTIVE_RULES),
            ("provenance", "confirm-destructive", "safe-target"),
        )

    def test_dated_rules_are_named_but_not_active(self):
        active = {r.name for r in cap.ACTIVE_RULES}
        for dated in ("presence-unlocked", "preview-transfer", "budget", "grant"):
            with self.subTest(rule=dated):
                self.assertIn(dated, cap.DATED_RULES)
                self.assertNotIn(dated, active)

    def test_presence_is_never_silently_waved_through(self):
        # D6: 'unknown' als erlaubt durchzuwinken waere fail-open unter
        # fail-closed-Namen. Die Regel ist deshalb GAR NICHT aktiv.
        d = cap.decide(TRIVIAL, _req(), cap.Evidence(presence=cap.Presence.UNKNOWN),
                       cap.ACTIVE_RULES)
        self.assertNotIn(cap.Requirement.PRESENCE_UNLOCKED, d.requirements)


class TrivialPathTests(unittest.TestCase):
    def test_trivial_capability_passes_the_policy_with_nothing_to_do(self):
        # §10: der triviale Pfad ueberspringt die Policy nicht — er besteht sie.
        d = cap.decide(TRIVIAL, _req(), cap.Evidence(), cap.ACTIVE_RULES)
        self.assertTrue(d.allowed)
        self.assertEqual(d.requirements, frozenset())
        self.assertEqual(d.denials, frozenset())


class ConfirmRuleTests(unittest.TestCase):
    """destructive verlangt Confirmation (SI-7)."""

    def test_destructive_without_confirmation_needs_confirmation(self):
        d = cap.decide(DESTRUCTIVE, _req(), cap.Evidence(confirmed=False), cap.ACTIVE_RULES)
        self.assertFalse(d.allowed)
        self.assertIn(cap.Requirement.CONFIRMATION, d.requirements)

    def test_destructive_with_confirmation_is_allowed(self):
        d = cap.decide(DESTRUCTIVE, _req(), cap.Evidence(confirmed=True), cap.ACTIVE_RULES)
        self.assertTrue(d.allowed)

    def test_non_destructive_never_needs_confirmation(self):
        d = cap.decide(TRIVIAL, _req(), cap.Evidence(confirmed=False), cap.ACTIVE_RULES)
        self.assertNotIn(cap.Requirement.CONFIRMATION, d.requirements)


class SafeTargetRuleTests(unittest.TestCase):
    """network-read verlangt ein zulaessiges Ziel (D7)."""

    def test_network_read_with_allowed_target_is_allowed(self):
        d = cap.decide(NETWORK, _req(), cap.Evidence(target_allowed=True), cap.ACTIVE_RULES)
        self.assertTrue(d.allowed)

    def test_network_read_with_blocked_target_is_denied(self):
        d = cap.decide(NETWORK, _req(), cap.Evidence(target_allowed=False), cap.ACTIVE_RULES)
        self.assertFalse(d.allowed)
        self.assertIn(cap.Requirement.SAFE_TARGET, d.denials)

    def test_unknown_target_is_fail_closed_and_never_allowed(self):
        d = cap.decide(NETWORK, _req(), cap.Evidence(target_allowed=None), cap.ACTIVE_RULES)
        self.assertFalse(d.allowed)
        self.assertIn(cap.Requirement.SAFE_TARGET, d.requirements)

    def test_capability_without_network_read_ignores_the_target(self):
        d = cap.decide(TRIVIAL, _req(), cap.Evidence(target_allowed=None), cap.ACTIVE_RULES)
        self.assertTrue(d.allowed)


class ProvenanceRuleTests(unittest.TestCase):
    """SI-1/SI-2: untrusted Inhalt autorisiert nie (Amendment 1 §A1.5)."""

    def test_derived_may_run_a_safe_network_read(self):
        # Amendment E4: sonst wuerde jede Sprachsuche bestaetigungspflichtig und
        # das beobachtbare Verhalten sich aendern (§28.4).
        d = cap.decide(NETWORK, _req(cap.Provenance.DERIVED),
                       cap.Evidence(target_allowed=True), cap.ACTIVE_RULES)
        self.assertTrue(d.allowed)

    def test_derived_external_write_is_denied_outright(self):
        d = cap.decide(EXTERNAL, _req(cap.Provenance.DERIVED),
                       cap.Evidence(confirmed=True, target_allowed=True), cap.ACTIVE_RULES)
        self.assertFalse(d.allowed)
        self.assertIn(cap.Requirement.AUTHORIZATION, d.denials)

    def test_operator_external_write_needs_authorization_but_is_not_denied(self):
        d = cap.decide(EXTERNAL, _req(cap.Provenance.OPERATOR),
                       cap.Evidence(confirmed=True), cap.ACTIVE_RULES)
        self.assertEqual(d.denials, frozenset())
        self.assertIn(cap.Requirement.AUTHORIZATION, d.requirements)

    def test_derived_can_never_satisfy_confirmation_by_being_derived(self):
        # Ein [ACTION:...] aus der LLM-Antwort ist immer derived; nur eine echte
        # Operator-Bestaetigung desselben Turns erfuellt die Anforderung.
        without = cap.decide(DESTRUCTIVE, _req(cap.Provenance.DERIVED),
                             cap.Evidence(confirmed=False), cap.ACTIVE_RULES)
        with_conf = cap.decide(DESTRUCTIVE, _req(cap.Provenance.DERIVED),
                               cap.Evidence(confirmed=True), cap.ACTIVE_RULES)
        self.assertIn(cap.Requirement.CONFIRMATION, without.requirements)
        self.assertTrue(with_conf.allowed)

    def test_derived_never_removes_a_requirement_that_operator_has(self):
        # Provenance darf nur hinzufuegen oder beibehalten, nie entfernen (§14).
        for contract in (NETWORK, DESTRUCTIVE, EXTERNAL, TRIVIAL):
            for ev in (cap.Evidence(), cap.Evidence(confirmed=True),
                       cap.Evidence(target_allowed=True),
                       cap.Evidence(confirmed=True, target_allowed=True)):
                with self.subTest(contract=contract.name, evidence=ev):
                    op = cap.decide(contract, _req(cap.Provenance.OPERATOR), ev,
                                    cap.ACTIVE_RULES)
                    dv = cap.decide(contract, _req(cap.Provenance.DERIVED), ev,
                                    cap.ACTIVE_RULES)
                    self.assertTrue(op.requirements <= dv.requirements | dv.denials)
                    self.assertTrue(op.denials <= dv.denials)


class CompositionTests(unittest.TestCase):
    """deny gewinnt, needs akkumuliert, allow nur ohne beides (§12)."""

    def test_deny_wins_over_needs(self):
        d = cap.decide(DESTRUCTIVE, _req(cap.Provenance.DERIVED),
                       cap.Evidence(confirmed=False, target_allowed=False),
                       cap.ACTIVE_RULES)
        self.assertFalse(d.allowed)

    def test_needs_accumulate_across_rules(self):
        both = _contract(name="screen.describe",
                         effects=(cap.EffectClass.DESTRUCTIVE,
                                  cap.EffectClass.NETWORK_READ),
                         reads=(cap.DataClass.PERSONAL,),
                         writes=(cap.DataClass.PERSONAL,))
        d = cap.decide(both, _req(), cap.Evidence(), cap.ACTIVE_RULES)
        self.assertEqual(d.requirements,
                         frozenset({cap.Requirement.CONFIRMATION,
                                    cap.Requirement.SAFE_TARGET}))

    def test_allow_is_only_representable_without_deny_and_needs(self):
        with self.assertRaises(ValueError):
            cap.Decision(allowed=True, requirements={cap.Requirement.CONFIRMATION})

    def test_result_is_independent_of_rule_order(self):
        cases = [
            (NETWORK, cap.Evidence(target_allowed=True)),
            (NETWORK, cap.Evidence(target_allowed=False)),
            (DESTRUCTIVE, cap.Evidence(confirmed=False)),
            (EXTERNAL, cap.Evidence()),
        ]
        for contract, ev in cases:
            for prov in (cap.Provenance.OPERATOR, cap.Provenance.DERIVED):
                expected = None
                for order in itertools.permutations(cap.ACTIVE_RULES):
                    d = cap.decide(contract, _req(prov), ev, order)
                    got = (d.allowed, d.denials, d.requirements)
                    if expected is None:
                        expected = got
                    self.assertEqual(got, expected,
                                     f"{contract.name}/{prov} haengt von der Reihenfolge ab")

    def test_decide_is_deterministic(self):
        a = cap.decide(DESTRUCTIVE, _req(), cap.Evidence(), cap.ACTIVE_RULES)
        b = cap.decide(DESTRUCTIVE, _req(), cap.Evidence(), cap.ACTIVE_RULES)
        self.assertEqual((a.allowed, a.denials, a.requirements),
                         (b.allowed, b.denials, b.requirements))

    def test_decide_is_total_and_never_raises_for_domain_reasons(self):
        # §12: der Kern wirft nie aus Domaenengruenden.
        for contract in (NETWORK, DESTRUCTIVE, EXTERNAL, TRIVIAL):
            for prov in cap.Provenance:
                for presence in cap.Presence:
                    for confirmed in (True, False):
                        for target in (True, False, None):
                            cap.decide(
                                contract,
                                cap.CapabilityRequest(contract.name, prov, {}),
                                cap.Evidence(presence=presence, confirmed=confirmed,
                                             target_allowed=target),
                                cap.ACTIVE_RULES)

    def test_empty_rule_set_allows_nothing_by_accident(self):
        # Deny-by-default bezieht sich auf Regeln, nicht auf deren Abwesenheit:
        # ohne Regeln gibt es keine Anforderung — das ist dokumentiert, nicht zufaellig.
        d = cap.decide(DESTRUCTIVE, _req(), cap.Evidence(), ())
        self.assertTrue(d.allowed)


class PolicyPurityTests(unittest.TestCase):
    """§28.1: Reinheit verhaltensbasiert in einer Sandbox nachgewiesen."""

    def test_policy_import_and_decide_touch_no_io_no_clock(self):
        import os
        import subprocess
        import sys

        probe = (
            "import builtins, socket, subprocess as sp, time, datetime\n"
            "def trip(kind):\n"
            "    def f(*a, **k):\n"
            "        raise SystemExit('IO:' + kind)\n"
            "    return f\n"
            "builtins.open = trip('open')\n"
            "socket.socket = trip('socket')\n"
            "socket.getaddrinfo = trip('dns')\n"
            "sp.Popen = trip('subprocess')\n"
            "time.time = trip('clock')\n"
            "time.monotonic = trip('clock')\n"
            "time.perf_counter = trip('clock')\n"
            # datetime.datetime ist unveraenderlich; deshalb die KLASSE am Modul
            # ersetzen statt eine Methode zu patchen.
            "class _NoClock:\n"
            "    def __getattr__(self, n):\n"
            "        raise SystemExit('IO:clock')\n"
            "datetime.datetime = _NoClock()\n"
            "import capability as c\n"
            "ct = c.CapabilityContract(\n"
            "    name='probe.thing', version=1, title='T',\n"
            "    inputs=c.InputSchema(fields=('q',)), output=c.OutputSchema(fields=('t',)),\n"
            "    effects=(c.EffectClass.DESTRUCTIVE, c.EffectClass.NETWORK_READ),\n"
            "    reads=(c.DataClass.PERSONAL,), writes=(c.DataClass.PERSONAL,),\n"
            "    scopes=(c.Scope.VAULT,), timeout_s=5, retry=c.Retry.NEVER,\n"
            "    cancellable=True, preview=c.Preview.NONE, verify=c.Verify.NONE,\n"
            "    health=c.Health.PASSIVE, audit=(), fixture={}, execute=None)\n"
            "for prov in c.Provenance:\n"
            "    for tgt in (True, False, None):\n"
            "        c.decide(ct, c.CapabilityRequest('probe.thing', prov, {}),\n"
            "                 c.Evidence(target_allowed=tgt), c.ACTIVE_RULES)\n"
            "print('PURE')\n"
        )
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, env=env, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout} stderr={proc.stderr}")
        self.assertIn("PURE", proc.stdout)


if __name__ == "__main__":
    unittest.main()

"""Phase-5C-Abschluss-Audit (Prompt 20, Slice 13).

Ein **deterministischer** Gesamtnachweis, der im Fast-Gate laeuft. Er prueft die
sieben Zusagen aus Amendment 2 an EINER Stelle, damit ein Rueckschritt nicht in
einem der thematischen Testmodule untergeht:

1. 22/22 Action-Mappings
2. alle genannten Contracts sind registrierbar
3. neun von zehn mutierenden REST-Routen sind capability-gesteuert
4. `DELETE /launcher/profiles/{id}` ist exakt die einzige Ausnahme
5. kein gespeichertes ``ActionSpec.risk``
6. kein produktiver ``execute_action``-Fallback
7. keine ungeprueften produktiven Browser-/HTTP-Callsites im migrierten Scope

Der Audit liest ausschliesslich Produktionscode — er vergleicht nie eine Tabelle
gegen sich selbst.
"""
import inspect
import pathlib
import unittest

import tests  # noqa: F401

import actions
import assistant_core
import browser_tools
import capability as cap
import server

_ROOT = pathlib.Path(__file__).resolve().parent.parent


class Audit1_ActionMapping(unittest.TestCase):
    def test_all_22_actions_are_mapped(self):
        self.assertEqual(22, len(actions.REGISTRY))
        self.assertEqual(set(actions.REGISTRY), set(cap.MIGRATED_ACTIONS))

    def test_21_distinct_capability_names(self):
        """Geteilte Vertraege sind erlaubt — ON/OFF nutzen denselben."""
        self.assertEqual(21, len(set(cap.MIGRATED_ACTIONS.values())))


class Audit2_ContractsRegistrable(unittest.TestCase):
    def test_every_mapped_name_is_registered(self):
        registry = cap.build_registry(cap.CapabilityDeps())
        for action_type, name in sorted(cap.MIGRATED_ACTIONS.items()):
            with self.subTest(action_type=action_type):
                self.assertIn(name, registry)

    def test_registry_builds_without_dependencies(self):
        """Der Bau ist I/O-frei und darf ohne Runtime gelingen."""
        self.assertGreaterEqual(len(cap.build_registry(cap.CapabilityDeps())), 21)

    def test_every_contract_declares_effects(self):
        registry = cap.build_registry(cap.CapabilityDeps())
        for name in registry.names():
            with self.subTest(name=name):
                self.assertTrue(registry.get(name).effects,
                                f"{name} ohne erklaerte Wirkung")


class Audit3_And_4_Routes(unittest.TestCase):
    def test_nine_of_ten_mutating_routes_are_governed(self):
        register = server.MUTATING_ROUTE_CAPABILITIES
        self.assertEqual(10, len(register))
        self.assertEqual(9, sum(1 for v in register.values() if v is not None))

    def test_profile_delete_is_the_only_exception(self):
        register = server.MUTATING_ROUTE_CAPABILITIES
        exceptions = [k for k, v in register.items() if v is None]
        self.assertEqual([("DELETE", "/launcher/profiles/{profile_id}")], exceptions)


class Audit5_NoStoredRisk(unittest.TestCase):
    def test_actionspec_stores_no_risk(self):
        self.assertNotIn("risk", actions.ActionSpec.__dataclass_fields__)

    def test_confirm_actions_is_derived_and_minimal(self):
        self.assertEqual(frozenset({"MEMORY_FORGET"}), actions.CONFIRM_ACTIONS)


class Audit6_NoProductionFallback(unittest.TestCase):
    def test_no_execute_action_call_remains_in_the_turn_path(self):
        code = "\n".join(
            line for line in
            inspect.getsource(assistant_core.run_action_and_respond).splitlines()
            if not line.lstrip().startswith("#"))
        self.assertNotIn("execute_action", code)

    def test_capabilities_is_required(self):
        for fn in (assistant_core.process_message,
                   assistant_core.run_action_and_respond):
            with self.subTest(fn=fn.__name__):
                param = inspect.signature(fn).parameters["capabilities"]
                self.assertIs(inspect.Parameter.empty, param.default)


class Audit7_NoUnguardedNetworkCallsites(unittest.TestCase):
    """Jede produktive Navigation laeuft transportseitig durch den Guard."""

    def test_browser_tools_has_no_raw_goto(self):
        source = inspect.getsource(browser_tools)
        for line_no, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or ".goto(" not in stripped:
                continue
            with self.subTest(line=line_no):
                self.assertIn("_guarded_goto", stripped,
                              f"ungeschuetztes goto in browser_tools:{line_no}")

    def test_the_only_raw_goto_lives_inside_the_guard_itself(self):
        source = pathlib.Path(_ROOT / "capability" / "_ssrf.py").read_text(
            encoding="utf-8")
        raw = [n for n, line in enumerate(source.splitlines(), 1)
               if ".goto(" in line and not line.strip().startswith("#")]
        self.assertEqual(1, len(raw),
                         "genau ein roher goto — der in guarded_goto selbst")

    def test_httpx_clients_never_follow_redirects_automatically(self):
        """§A2.6: kein automatisches ungeprueftes Redirect-Following."""
        source = inspect.getsource(browser_tools)
        self.assertNotIn("follow_redirects=True", source)
        self.assertGreaterEqual(source.count("follow_redirects=False"), 1)

    def test_browser_tools_uses_the_runtime_guard(self):
        self.assertTrue(hasattr(browser_tools, "configure_guard"))
        self.assertTrue(hasattr(browser_tools, "_active_guard"))


class Audit8_HonestResidualBalance(unittest.TestCase):
    """Die ehrliche Restbilanz darf nicht stillschweigend verschwinden."""

    def test_risk_register_still_marks_tm001_and_tm002_as_open(self):
        text = (_ROOT / "docs" / "security" / "RISK_REGISTER.md").read_text(
            encoding="utf-8")
        self.assertIn("TM-001", text)
        self.assertIn("TM-002", text)
        self.assertNotIn("| TM-002 | SSRF über Browser/HTTP (nur Schema geprüft, "
                         "Redirects offen) | **high** | mitigated |", text)

    def test_presence_rules_stay_dated_and_inactive(self):
        active = {r.name for r in cap.ACTIVE_RULES}
        self.assertNotIn("presence-unlocked", active)
        self.assertNotIn("preview-transfer", active)
        self.assertIn("presence-unlocked", cap.DATED_RULES)

    def test_no_grant_runtime_was_introduced(self):
        """§A2.10: keine Grant-Laufzeit, kein ``awaiting-authorization``."""
        self.assertNotIn("AWAITING_AUTHORIZATION",
                         {s.name for s in cap.OutcomeStatus})


if __name__ == "__main__":
    unittest.main()

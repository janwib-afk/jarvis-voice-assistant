"""Slice 12 — gespeichertes ``risk`` und Legacy-Fallback entfernen (§A2.9).

Bis hierher trug ``ActionSpec`` ein **gespeichertes** ``risk``-Feld, aus dem
``CONFIRM_ACTIONS`` abgeleitet wurde. Damit gab es zwei Sicherheitswahrheiten: die
Wirkungsklassen der Capability **und** eine handgepflegte Risikospalte, die
auseinanderlaufen konnten.

Ab jetzt gilt genau eine: die Confirmation folgt aus dem ``destructive``-Effekt des
kanonischen Vertrags. Eine Mutation dieses Effekts **muss** den abgeleiteten Status
aendern — sonst waere die Ableitung nur Dekoration.

Ausserdem faellt der produktive ``asyncio.wait_for(execute_action(...))``-Fallback:
mit 22/22 hat er keinen Nutzer mehr, und solange er existiert, ist ein Rueckfall an
Policy und Timeout-Ownership vorbei jederzeit einen Tippfehler entfernt.
"""
import inspect
import unittest

import tests  # noqa: F401

import actions
import assistant_core
import capability as cap


class NoStoredRiskTests(unittest.TestCase):
    def test_actionspec_has_no_stored_risk_field(self):
        self.assertNotIn("risk", actions.ActionSpec.__dataclass_fields__)

    def test_no_risk_constructor_argument_remains(self):
        source = inspect.getsource(actions)
        self.assertNotIn('risk="confirm"', source)
        self.assertNotIn("risk='confirm'", source)

    def test_risk_is_still_readable_as_a_derived_property(self):
        """Bestehende Konsumenten brechen nicht — der Wert ist nur nicht mehr gespeichert."""
        self.assertEqual("confirm", actions.spec_for("MEMORY_FORGET").risk)
        self.assertEqual("low", actions.spec_for("SEARCH").risk)

    def test_the_derived_property_is_read_only(self):
        spec = actions.spec_for("SEARCH")
        with self.assertRaises(AttributeError):
            spec.risk = "confirm"


class ConfirmDerivedFromEffectsTests(unittest.TestCase):
    def test_confirm_actions_is_exactly_memory_forget(self):
        self.assertEqual(frozenset({"MEMORY_FORGET"}), actions.CONFIRM_ACTIONS)

    def test_confirm_follows_the_destructive_effect(self):
        """Die Ableitung ist echt: genau die destructive-Vertraege sind dabei."""
        registry = cap.build_registry(cap.CapabilityDeps())
        expected = {
            action_type for action_type, name in cap.MIGRATED_ACTIONS.items()
            if cap.EffectClass.DESTRUCTIVE in registry.get(name).effects
        }
        self.assertEqual(expected, set(actions.CONFIRM_ACTIONS))

    def test_no_second_risk_table_exists(self):
        """§A2.9: kein zweiter Katalog, keine gespeicherte Risikospalte."""
        source = inspect.getsource(actions)
        self.assertNotIn("RISK_TABLE", source)
        self.assertNotIn("_RISK_BY_ACTION", source)


class NoProductionFallbackTests(unittest.TestCase):
    def test_run_action_and_respond_has_no_execute_action_fallback(self):
        code = "\n".join(
            line for line in
            inspect.getsource(assistant_core.run_action_and_respond).splitlines()
            if not line.lstrip().startswith("#"))
        self.assertNotIn("execute_action", code)
        self.assertNotIn("asyncio.wait_for", code)

    def test_every_action_runs_through_the_coordinator(self):
        for action_type in actions.REGISTRY:
            with self.subTest(action_type=action_type):
                self.assertTrue(cap.is_migrated(action_type))

    def test_action_execute_functions_still_exist_behind_the_adapters(self):
        """RFC-0001 bleibt bindend: ``execute``/``describe`` verschwinden nicht."""
        for action_type, spec in actions.REGISTRY.items():
            with self.subTest(action_type=action_type):
                self.assertTrue(callable(spec.execute))


if __name__ == "__main__":
    unittest.main()

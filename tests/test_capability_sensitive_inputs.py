"""Slice 6 — sensitive Eingaben CLIPBOARD und SCREEN (Amendment 2 §A2.5).

Der Kern ist eine **Reihenfolge-Korrektur**. Bisher sprach Jarvis „Ich werfe kurz einen
Blick auf deinen Bildschirm." **bevor** irgendeine Entscheidung gefallen war — eine
Wirkung vor der Freigabe. Die geforderte Reihenfolge lautet:

``Policy-Allow -> autorisierte kurze Rueckmeldung -> Capture -> Verarbeitung``

Die Rueckmeldung bleibt also **vor** Aufnahme und Upload, wandert aber **hinter** die
Freigabe. Sie laeuft ueber den schmalen ``feedback``-Port der Invocation-Bindings.

Kontrollierte Grenzen: ``screen_capture`` (Bildschirm) und ``clipboard_tools``
(Betriebssystem) — ausschliesslich synthetische Fakes. **Nie** ein echter Screenshot,
**nie** ein echter Zwischenablage-Inhalt.
"""
import asyncio
import unittest
from unittest import mock

import tests  # noqa: F401

import actions
import capability as cap

SYNTHETIC_CLIP = "Synthetischer Zwischenablage-Text"
SYNTHETIC_SCREEN = "Auf dem Bildschirm ist ein Testfenster zu sehen."


class _Action:
    def __init__(self, type_, payload=""):
        self.type = type_
        self.payload = payload


def _coord(rules=cap.ACTIVE_RULES):
    return cap.Coordinator(cap.build_registry(cap.CapabilityDeps()), rules,
                           audit=lambda *a, **k: None)


class CanonicalMappingTests(unittest.TestCase):
    def test_sensitive_inputs_are_mapped(self):
        self.assertEqual("clipboard.process", cap.MIGRATED_ACTIONS["CLIPBOARD"])
        self.assertEqual("screen.describe", cap.MIGRATED_ACTIONS["SCREEN"])


class ScreenOrderingTests(unittest.TestCase):
    """Policy-Allow -> Rueckmeldung -> Capture. Nie eine Wirkung vor der Freigabe."""

    def _run(self, rules=cap.ACTIVE_RULES, evidence_ok=True):
        order = []

        async def _feedback(text):
            order.append(("feedback", text))

        async def _describe(ai, question=""):
            order.append(("capture", question))
            return SYNTHETIC_SCREEN

        with mock.patch("screen_capture.describe_screen", _describe):
            result = asyncio.run(cap.run_migrated(
                _coord(rules), _Action("SCREEN", "Was siehst du?"),
                actions.ActionContext(), feedback=_feedback))
        return order, result

    def test_feedback_comes_before_the_capture(self):
        order, result = self._run()
        self.assertEqual(["feedback", "capture"], [step for step, _ in order])
        self.assertTrue(result.ok)

    def test_feedback_wording_is_unchanged(self):
        order, _ = self._run()
        self.assertEqual("Ich werfe kurz einen Blick auf deinen Bildschirm.",
                         order[0][1])

    def test_no_feedback_and_no_capture_when_the_policy_denies(self):
        """Eine abgelehnte Wirkung darf sich nicht einmal ankuendigen."""
        deny_all = (cap.Rule(
            name="test-deny-all", why="Testregel",
            apply=lambda c, r, e: ({"test-deny-all"}, set())),)
        order, result = self._run(rules=deny_all)
        self.assertEqual([], order, "es wurde vor/trotz der Ablehnung gewirkt")
        self.assertFalse(result.ok)

    def test_missing_feedback_port_does_not_break_the_capture(self):
        captured = []

        async def _describe(ai, question=""):
            captured.append(question)
            return SYNTHETIC_SCREEN

        with mock.patch("screen_capture.describe_screen", _describe):
            result = asyncio.run(cap.run_migrated(
                _coord(), _Action("SCREEN", "x"), actions.ActionContext()))
        self.assertTrue(result.ok)
        self.assertEqual(["x"], captured)


class ClipboardTests(unittest.TestCase):
    def test_clipboard_result_is_byte_identical(self):
        with mock.patch("clipboard_tools.get_clipboard_text",
                        lambda: SYNTHETIC_CLIP):
            legacy = asyncio.run(actions.spec_for("CLIPBOARD").execute(
                "Fasse zusammen", actions.ActionContext()))
            migrated = asyncio.run(cap.run_migrated(
                _coord(), _Action("CLIPBOARD", "Fasse zusammen"),
                actions.ActionContext()))
        self.assertEqual(legacy, migrated.text)

    def test_clipboard_default_task_is_preserved(self):
        with mock.patch("clipboard_tools.get_clipboard_text",
                        lambda: SYNTHETIC_CLIP):
            migrated = asyncio.run(cap.run_migrated(
                _coord(), _Action("CLIPBOARD", ""), actions.ActionContext()))
        self.assertIn("Fasse den Inhalt kurz zusammen.", migrated.text)

    def test_empty_clipboard_wording_is_preserved(self):
        with mock.patch("clipboard_tools.get_clipboard_text", lambda: ""):
            migrated = asyncio.run(cap.run_migrated(
                _coord(), _Action("CLIPBOARD", ""), actions.ActionContext()))
        self.assertEqual("Die Zwischenablage ist leer oder enthält keinen Text.",
                         migrated.text)


class SensitiveEffectCensusTests(unittest.TestCase):
    def _view(self, name):
        return cap.build_registry(cap.CapabilityDeps()).inspect(name)

    def test_screen_declares_sensitive_read_and_upload(self):
        view = self._view("screen.describe")
        self.assertIn(cap.EffectClass.READ_SENSITIVE, view.effects)
        self.assertIn(cap.EffectClass.NETWORK_READ, view.effects)
        self.assertIn(cap.DataClass.SENSITIVE, view.reads)
        self.assertIn(cap.Scope.SCREEN, view.scopes)

    def test_clipboard_declares_sensitive_read_and_upload(self):
        view = self._view("clipboard.process")
        self.assertIn(cap.EffectClass.READ_SENSITIVE, view.effects)
        self.assertIn(cap.EffectClass.NETWORK_READ, view.effects)
        self.assertIn(cap.DataClass.SENSITIVE, view.reads)
        self.assertIn(cap.Scope.CLIPBOARD, view.scopes)

    def test_neither_writes_anything(self):
        for name in ("screen.describe", "clipboard.process"):
            with self.subTest(name=name):
                self.assertEqual(frozenset(), self._view(name).writes)

    def test_secret_is_structurally_not_declarable(self):
        """SI-5 bleibt gueltig: kein Vertrag darf ``secret`` als Datenklasse tragen."""
        for name in ("screen.describe", "clipboard.process"):
            with self.subTest(name=name):
                view = self._view(name)
                self.assertNotIn(cap.DataClass.SECRET, view.reads)
                self.assertNotIn(cap.DataClass.SECRET, view.writes)


class PresenceStaysDatedTests(unittest.TestCase):
    """Presence-/Preview-Regeln bleiben datiert und inaktiv (§A2.10)."""

    def test_presence_rule_is_not_active(self):
        active = {r.name for r in cap.ACTIVE_RULES}
        self.assertNotIn("presence-unlocked", active)
        self.assertIn("presence-unlocked", {r for r in cap.DATED_RULES})

    def test_unknown_presence_is_never_treated_as_confirmed_presence(self):
        self.assertIs(cap.Presence.UNKNOWN, cap.Evidence().presence)


if __name__ == "__main__":
    unittest.main()

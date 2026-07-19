"""Slice 4 — Vault- und Memory-Lesepfade (Amendment 2 §A2.5).

`INBOX_READ`, `MEMORY_READ`, `NOTES_RECENT`, `PROJECT_CONTEXT` lesen **persoenliche**
Daten. Der Vertrag muss das sagen — und sensible Inhalte duerfen weder in Logs noch in
Audit, Fehlermeldungen oder Fixtures landen.

Kontrollierte Grenze: ``memory.*`` (Dateisystem). Es wird ausschliesslich mit
synthetischen Inhalten gearbeitet; kein echter Vault wird angefasst.
"""
import asyncio
import unittest
from unittest import mock

import tests  # noqa: F401

import actions
import capability as cap

#: Synthetischer, klar erkennbarer Inhalt — nie ein echter Vault-Auszug.
SECRET_ISH = "Gehaltsverhandlung Montag, Zielmarke 12345"


class _Action:
    def __init__(self, type_, payload=""):
        self.type = type_
        self.payload = payload


def _coord(audit=None):
    deps = cap.CapabilityDeps(target_guard=cap.TargetGuard(
        resolver=lambda h: ["93.184.216.34"]))
    return cap.Coordinator(cap.build_registry(deps), cap.ACTIVE_RULES,
                           audit=audit or (lambda *a, **k: None), deps=deps)


def _run(action):
    return asyncio.run(cap.run_migrated(_coord(), action, actions.ActionContext()))


class CanonicalMappingTests(unittest.TestCase):
    def test_read_paths_are_mapped(self):
        self.assertEqual("vault.inbox.read", cap.MIGRATED_ACTIONS["INBOX_READ"])
        self.assertEqual("memory.read", cap.MIGRATED_ACTIONS["MEMORY_READ"])
        self.assertEqual("vault.notes.recent", cap.MIGRATED_ACTIONS["NOTES_RECENT"])
        self.assertEqual("vault.project.context",
                         cap.MIGRATED_ACTIONS["PROJECT_CONTEXT"])


class ByteIdenticalReadTests(unittest.TestCase):
    def test_inbox_read_is_byte_identical(self):
        with mock.patch("memory.inbox_available", lambda: True), \
                mock.patch("memory.read_today_inbox_sync", lambda: SECRET_ISH):
            legacy = asyncio.run(
                actions.spec_for("INBOX_READ").execute("", actions.ActionContext()))
            migrated = _run(_Action("INBOX_READ"))
        self.assertEqual(legacy, migrated.text)
        self.assertTrue(migrated.ok)

    def test_inbox_read_unavailable_wording_is_preserved(self):
        with mock.patch("memory.inbox_available", lambda: False):
            legacy = asyncio.run(
                actions.spec_for("INBOX_READ").execute("", actions.ActionContext()))
            migrated = _run(_Action("INBOX_READ"))
        self.assertEqual(legacy, migrated.text)
        self.assertIn("nicht konfiguriert", migrated.text)

    def test_memory_read_is_byte_identical(self):
        with mock.patch("memory.read_memory_sync", lambda: SECRET_ISH):
            legacy = asyncio.run(
                actions.spec_for("MEMORY_READ").execute("", actions.ActionContext()))
            migrated = _run(_Action("MEMORY_READ"))
        self.assertEqual(legacy, migrated.text)

    def test_memory_read_empty_wording_is_preserved(self):
        with mock.patch("memory.read_memory_sync", lambda: "   "):
            migrated = _run(_Action("MEMORY_READ"))
        self.assertEqual("Ich habe mir dauerhaft noch nichts gemerkt.", migrated.text)

    def test_notes_recent_is_byte_identical(self):
        with mock.patch("memory.read_recent_notes_sync", lambda: SECRET_ISH):
            legacy = asyncio.run(
                actions.spec_for("NOTES_RECENT").execute("", actions.ActionContext()))
            migrated = _run(_Action("NOTES_RECENT"))
        self.assertEqual(legacy, migrated.text)

    def test_project_context_is_byte_identical(self):
        with mock.patch("memory.vault_available", lambda: True), \
                mock.patch("memory.get_project_context_sync", lambda q: SECRET_ISH):
            legacy = asyncio.run(actions.spec_for("PROJECT_CONTEXT").execute(
                "Bericht", actions.ActionContext()))
            migrated = _run(_Action("PROJECT_CONTEXT", "Bericht"))
        self.assertEqual(legacy, migrated.text)
        self.assertIn("Bericht", migrated.text)

    def test_project_context_without_vault_is_preserved(self):
        with mock.patch("memory.vault_available", lambda: False):
            migrated = _run(_Action("PROJECT_CONTEXT", "Bericht"))
        self.assertIn("Kein Obsidian-Vault konfiguriert", migrated.text)


class SensitiveDataDoesNotLeakTests(unittest.TestCase):
    """Persoenliche Inhalte gehoeren nie ins Audit — die Allowlist verhindert es."""

    def test_audit_never_carries_vault_content(self):
        seen = []

        def _audit(name, **fields):
            seen.append((name, fields))

        with mock.patch("memory.read_memory_sync", lambda: SECRET_ISH):
            asyncio.run(cap.run_migrated(
                _coord(audit=_audit), _Action("MEMORY_READ"),
                actions.ActionContext()))
        self.assertTrue(seen, "es wurde gar nicht auditiert")
        blob = repr(seen)
        self.assertNotIn(SECRET_ISH, blob)
        self.assertNotIn("12345", blob)

    def test_contract_fixture_is_synthetic(self):
        """Eine eingecheckte Fixture darf nie ein echter Vault-Auszug sein."""
        registry = cap.build_registry(cap.CapabilityDeps())
        for name in ("vault.inbox.read", "memory.read", "vault.notes.recent",
                     "vault.project.context"):
            with self.subTest(name=name):
                blob = repr(dict(registry.get(name).fixture))
                self.assertNotIn(SECRET_ISH, blob)


class ReadEffectCensusTests(unittest.TestCase):
    """Wirkungen direkt aus dem Produktionscode (§A2.5)."""

    def _view(self, name):
        return cap.build_registry(cap.CapabilityDeps()).inspect(name)

    def test_all_read_paths_declare_read_sensitive(self):
        for name in ("vault.inbox.read", "memory.read", "vault.notes.recent",
                     "vault.project.context"):
            with self.subTest(name=name):
                self.assertIn(cap.EffectClass.READ_SENSITIVE, self._view(name).effects)

    def test_all_read_paths_declare_the_summary_network_effect(self):
        """Alle vier haben ein ``summary_task`` — der Inhalt geht an das LLM."""
        for name in ("vault.inbox.read", "memory.read", "vault.notes.recent",
                     "vault.project.context"):
            with self.subTest(name=name):
                self.assertIn(cap.EffectClass.NETWORK_READ, self._view(name).effects)

    def test_read_paths_read_personal_and_write_nothing(self):
        for name in ("vault.inbox.read", "memory.read", "vault.notes.recent",
                     "vault.project.context"):
            with self.subTest(name=name):
                view = self._view(name)
                self.assertIn(cap.DataClass.PERSONAL, view.reads)
                self.assertEqual(frozenset(), view.writes)

    def test_read_paths_are_governed_not_trivial(self):
        for name in ("vault.inbox.read", "memory.read", "vault.notes.recent",
                     "vault.project.context"):
            with self.subTest(name=name):
                self.assertIs(cap.Tier.GOVERNED, self._view(name).tier)

    def test_timeouts_match_the_action_specs(self):
        registry = cap.build_registry(cap.CapabilityDeps())
        for action_type, name in (("INBOX_READ", "vault.inbox.read"),
                                  ("MEMORY_READ", "memory.read"),
                                  ("NOTES_RECENT", "vault.notes.recent"),
                                  ("PROJECT_CONTEXT", "vault.project.context")):
            with self.subTest(action_type=action_type):
                self.assertEqual(actions.spec_for(action_type).timeout,
                                 registry.get(name).timeout_s)


if __name__ == "__main__":
    unittest.main()

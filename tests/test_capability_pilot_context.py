"""Slice 9 — Pilot context.refresh (RFC-0007 §2.6.3, Amendment 1 §A1.2).

Startup und Post-Settings-Save laufen ueber DIESELBE Capability. Bestehende Lifespan-,
Commit- und Degraded-Semantik bleiben erhalten. Wetterzugriff und Vault-Scan sind
vollstaendig deklariert. Kein Config-File, kein Vault, kein Netz in Tests; keine
zusaetzlichen Startup-Aufrufe oder Providerkosten.
"""
import asyncio
import json
import os
import tempfile
import unittest

import tests  # noqa: F401
from tests.env_guard import guard_env
from fastapi.testclient import TestClient

import assistant_core
import capability as cap
import memory
import runtime as runtime_mod
import server


class ContextRefreshCensusTests(unittest.TestCase):
    def test_context_refresh_in_registry(self):
        reg = cap.build_registry(cap.CapabilityDeps())
        self.assertIn("context.refresh", reg)

    def test_effects_declare_weather_and_vault(self):
        reg = cap.build_registry(cap.CapabilityDeps())
        view = reg.inspect("context.refresh")
        # network-read (wttr.in) + read-sensitive (Vault-Scan) — vollstaendig (§2.6.3).
        self.assertEqual(view.effects,
                         frozenset({cap.EffectClass.NETWORK_READ,
                                    cap.EffectClass.READ_SENSITIVE}))
        self.assertIs(view.tier, cap.Tier.GOVERNED)


class RuntimeRefreshTests(unittest.TestCase):
    def setUp(self):
        self._saved = assistant_core.refresh_data
        self.calls = []
        assistant_core.refresh_data = lambda: self.calls.append(1)

    def tearDown(self):
        assistant_core.refresh_data = self._saved

    def _runtime(self):
        return runtime_mod.Runtime(config_path="unused.json", session_token="t")

    def test_refresh_context_dispatches_through_the_coordinator(self):
        rt = self._runtime()
        events = []
        rt.capabilities._audit = lambda name, **f: events.append((name, f))
        outcome = asyncio.run(rt.refresh_context())
        self.assertIs(outcome.status, cap.OutcomeStatus.OK)
        self.assertEqual(self.calls, [1], "refresh_data genau einmal (keine Extra-Kosten)")
        self.assertTrue(any(f.get("capability") == "context.refresh"
                            for n, f in events if n == "capability.attempted"))

    def test_refresh_failure_becomes_a_failed_outcome_not_a_crash(self):
        def _boom():
            raise RuntimeError("wttr.in weg")
        assistant_core.refresh_data = _boom
        rt = self._runtime()
        rt.capabilities._audit = lambda *a, **k: None
        outcome = asyncio.run(rt.refresh_context())
        self.assertIs(outcome.status, cap.OutcomeStatus.FAILED)


class StartupAndSettingsTests(unittest.TestCase):
    """Startup und Settings-Save laufen ueber die Capability; Degraded erhalten."""

    _CONFIG = {
        "anthropic_api_key": "k", "elevenlabs_api_key": "k",
        "user_name": "T", "user_role": "D", "user_address": "du", "city": "Hamburg",
        "apps": [], "launcher": {"active_profile": "default",
                                 "profiles": [{"id": "default", "name": "S", "apps": []}]},
    }

    def setUp(self):
        guard_env(self, "JARVIS_SKIP_STARTUP_REFRESH")
        os.environ.pop("JARVIS_SKIP_STARTUP_REFRESH", None)  # Startup-Refresh AKTIV
        fd, self.cfg = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump(dict(self._CONFIG, schema_version=1), f, ensure_ascii=False)
        self._saved_token = server.SESSION_TOKEN
        self._saved_refresh = assistant_core.refresh_data
        self._saved_memory = (memory.VAULT_PATH, memory.INBOX_PATH)
        memory.configure(vault_path="", inbox_path="")

    def tearDown(self):
        server.SESSION_TOKEN = self._saved_token
        assistant_core.refresh_data = self._saved_refresh
        memory.configure(*self._saved_memory)
        # JARVIS_SKIP_STARTUP_REFRESH stellt guard_env exakt wieder her.
        if os.path.exists(self.cfg):
            os.remove(self.cfg)

    def test_startup_refresh_runs_through_the_capability(self):
        calls = []
        assistant_core.refresh_data = lambda: calls.append(1)
        events = []
        rt = runtime_mod.Runtime.for_production(
            config_path=self.cfg, environ={}, ai=object(), http=object())
        rt.capabilities._audit = lambda name, **f: events.append((name, f))
        app = server.create_app(rt)
        with TestClient(app):
            # Lifespan-Startup hat den Refresh-Task erzeugt; kurz auslaufen lassen.
            pass
        # Der Startup-Refresh lief GENAU einmal ueber die Capability.
        self.assertEqual(calls, [1])
        self.assertTrue(any(f.get("capability") == "context.refresh"
                            for n, f in events if n == "capability.attempted"))

    def test_settings_save_failure_stays_degraded(self):
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"  # nur der Save-Refresh interessiert

        def _boom():
            raise RuntimeError("wttr.in weg")

        rt = runtime_mod.Runtime.for_production(
            config_path=self.cfg, environ={}, ai=object(), http=object())
        app = server.create_app(rt)
        with TestClient(app) as client:
            assistant_core.refresh_data = _boom  # erst NACH dem Startup scharf schalten
            resp = client.post("/settings",
                               headers={"X-Jarvis-Token": rt.session_token},
                               json={"city": "Bremen"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertIn("degraded", body)


if __name__ == "__main__":
    unittest.main()

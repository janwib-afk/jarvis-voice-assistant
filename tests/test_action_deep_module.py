"""Contract-Tests der Action-Seam (RFC-0001: Action als deep module).

Getestet wird ausschliesslich das oeffentliche Action-Interface:

    spec = actions.spec_for(TYP)
    result = await spec.execute(payload, ctx)     # Ausfuehrung
    text   = spec.describe(prompt_ctx)            # Selbstbeschreibung

Kein Patchen von Modul-Globals (``ai``/``conversations``), keine internen
Call-Counts, keine echten Provider/Apps/Screens/Clipboards. Erwartete Werte
stammen aus der Spezifikation (docs/contracts/LEGACY_ACTION_PROTOCOL.md), nicht
aus einer Neuberechnung durch den Produktionscode.
"""
import asyncio
import unittest

import tests  # noqa: F401  — synthetische Config-Fixture (JARVIS_CONFIG_PATH)

import actions


def run(coro):
    """Coroutine synchron ausfuehren (unittest ohne IsolatedAsyncioTestCase)."""
    return asyncio.run(coro)


def ctx(**kwargs) -> "actions.ActionContext":
    """Request-scoped Ausfuehrungskontext mit Test-Defaults."""
    return actions.ActionContext(**kwargs)


class SessionSummaryActionTests(unittest.TestCase):
    """SESSION_SUMMARY ist rein: liest den Verlauf ausschliesslich aus ctx.history."""

    def test_renders_session_log_from_context_history(self):
        result = run(actions.spec_for("SESSION_SUMMARY").execute("", ctx(history=(
            {"role": "user", "content": "Wie ist das Wetter?"},
            {"role": "assistant", "content": "Sonnig, 20 Grad."},
        ))))
        self.assertEqual(
            result,
            "Sitzungsprotokoll:\nDu: Wie ist das Wetter?\nJarvis: Sonnig, 20 Grad.",
        )

    def test_empty_history_reports_no_session_content(self):
        result = run(actions.spec_for("SESSION_SUMMARY").execute("", ctx(history=())))
        self.assertEqual(result, "Diese Sitzung hat noch keinen nennenswerten Verlauf.")

"""
Reine, testbare Entscheidungslogik des Smoke-Tests (ohne Seiteneffekte).

Trennt erwartete von unerwarteten Skips und faellt das Gesamturteil. So kann
``scripts/smoke-test.py`` bei jedem UNERWARTETEN Skip mit Exit != 0 enden,
ohne dass die Testausgabe still gruen wirkt.
"""

# Skip-Gruende, die als ERWARTET gelten (Substring-Match auf den Grund-Text).
# Alles andere ist ein unerwarteter Skip. Insbesondere "server import nicht
# moeglich" (kaputte/fehlende Config) darf NICHT erwartet sein — sonst wuerden
# ganze Testklassen still uebersprungen und die Suite wirkte gruen.
EXPECTED_SKIP_MARKERS = (
    "playwright-Paket nicht installiert",
)


def classify_skips(skipped, expected_markers=EXPECTED_SKIP_MARKERS):
    """Filtert die UNERWARTETEN Skips aus ``result.skipped``.

    ``skipped`` ist eine Liste von ``(test, reason)``-Paaren (unittest) oder
    einfachen Strings. Rueckgabe: die Teilliste, deren Grund keinen erwarteten
    Marker enthaelt.
    """
    unexpected = []
    for item in skipped:
        if isinstance(item, (tuple, list)) and len(item) > 1:
            reason = str(item[1])
        else:
            reason = str(item)
        if not any(marker in reason for marker in expected_markers):
            unexpected.append(item)
    return unexpected


def suite_ok(tests_run, failures, errors, unexpected_skips):
    """Gesamturteil: gruen nur bei >0 Tests, ohne Failures/Errors/unerwartete Skips."""
    return tests_run > 0 and failures == 0 and errors == 0 and unexpected_skips == 0

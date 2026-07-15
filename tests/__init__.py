"""Test-Bootstrap: wählt die synthetische Test-Fixture aus.

Damit läuft die gesamte Suite ohne persönliche ``config.json`` und fällt NIE
still auf sie zurück. ``setdefault`` respektiert ein von außen gesetztes
``JARVIS_CONFIG_PATH`` (z.B. ein eigener Fixture-Pfad in CI); sonst greift die
eingecheckte Fixture ``tests/fixtures/config.test.json``.

Wirkung: ``unittest discover -s tests`` importiert die Testmodule als Paket
``tests.*`` und führt damit dieses ``__init__`` VOR jedem ``import server`` aus,
sodass ``server`` beim Import bereits die Fixture (nicht die echte Config) lädt.
"""
import os

_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "config.test.json"
)
os.environ.setdefault("JARVIS_CONFIG_PATH", _FIXTURE)

# Kein Startup-Refresh in Tests: verhindert echte Wetter-/Vault-Zugriffe, falls
# ein Test die App-Lifespan startet (Standardtests kosten nie Provider).
os.environ.setdefault("JARVIS_SKIP_STARTUP_REFRESH", "1")

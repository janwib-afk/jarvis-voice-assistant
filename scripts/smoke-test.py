"""
Jarvis — Smoke-Test

Ein Befehl prueft die Grundgesundheit des Projekts, ohne echte API-Aufrufe:

    python scripts/smoke-test.py

1. Alle benoetigten Python-Pakete installiert (mit Installationsbefehl bei Fehlen)
2. config.json vorhanden und gueltig
3. Alle Module importierbar
4. Server startet (TestClient) und /health antwortet
5. Testsuite gruen (entspricht: python -m unittest discover -s tests)

Es werden KEINE bezahlten APIs angefragt: der Startup-Refresh ist per
JARVIS_SKIP_STARTUP_REFRESH deaktiviert, /health ist passiv und die Unit-Tests
mocken alle LLM-/TTS-/Browser-Aufrufe.

Exit-Code 0 = alles ok, 1 = mindestens ein Schritt fehlgeschlagen.
"""
import contextlib
import importlib.util
import logging
import os
import sys
import unittest

# Kein Netz-/Vault-Zugriff beim App-Start (siehe _startup_refresh in server.py).
os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Standardmaessig die synthetische Test-Fixture waehlen — der Smoke-Test braucht
# KEINE persoenliche config.json. setdefault: ein aussen gesetztes
# JARVIS_CONFIG_PATH (z.B. eigener Fixture-Pfad in CI) bleibt erhalten.
os.environ.setdefault(
    "JARVIS_CONFIG_PATH", os.path.join(ROOT, "tests", "fixtures", "config.test.json")
)

# Windows-Konsole (cp1252) sicher auf UTF-8 stellen fuer die Haekchen.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

OK = "✓"
FAIL = "✗"

_failures = []


def report(ok, name, detail=""):
    line = f"  {OK if ok else FAIL} {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    if not ok:
        _failures.append(name)


# import-Name -> pip-Paketname (fuer verstaendliche Meldungen bei Fehlen).
_REQUIRED_PACKAGES = {
    "anthropic": "anthropic",
    "httpx": "httpx",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "starlette": "starlette",
    "playwright": "playwright",
}


def check_dependencies():
    """Prueft die Third-Party-Pakete VOR den Modul-Importen — so wird ein reiner
    Setup-Fehler (fehlendes Paket) klar als solcher benannt, nicht als Codefehler."""
    missing = [
        (module, pip)
        for module, pip in sorted(_REQUIRED_PACKAGES.items())
        if importlib.util.find_spec(module) is None
    ]
    if not missing:
        report(True, "Dependencies", f"{len(_REQUIRED_PACKAGES)} Pakete installiert")
        return
    report(False, "Dependencies", "fehlen: " + ", ".join(m for m, _ in missing))
    print("      → Installiere alle auf einmal: pip install -r requirements.txt")
    if any(module == "playwright" for module, _ in missing):
        print("      → Browser danach installieren: python -m playwright install chromium")


def check_config():
    import config_loader
    # Die AKTIVE Config pruefen (per JARVIS_CONFIG_PATH gewaehlt = Test-Fixture),
    # nicht zwingend die persoenliche config.json. Nur den Dateinamen ausgeben
    # (kein persoenlicher Pfad in der Ausgabe).
    path = config_loader.resolve_config_path(os.environ, os.path.join(ROOT, "config.json"))
    name = os.path.basename(path)
    if not os.path.exists(path):
        report(False, "Config", f"aktive Config fehlt ({name})")
        return
    try:
        config_loader.load_config(path)
        report(True, "Config", f"{name} vorhanden und gueltig")
    except config_loader.ConfigError as e:
        report(False, "Config", str(e).replace("\n", " "))


def check_imports():
    for name in (
        "obslog", "wire_protocol", "actions", "config_loader", "browser_tools", "screen_capture",
        "tts", "memory", "clipboard_tools", "app_launcher", "monitors",
        "health", "assistant_core", "server",
    ):
        try:
            __import__(name)
            report(True, f"Import {name}")
        except BaseException as e:  # auch SystemExit (Config-Fehler) abfangen
            report(False, f"Import {name}", repr(e))


def check_health():
    try:
        import server
        from fastapi.testclient import TestClient
        logging.getLogger("httpx").setLevel(logging.WARNING)
        # Amendment 1 (voll-lazy Import): Config/Clients öffnen im FastAPI-Lifespan.
        # 'with' fährt den Lifespan — damit prüft dieser Schritt den echten Start.
        with TestClient(server.app) as client:
            resp = client.get("/health")
        body = resp.json()
        assert resp.status_code == 200, f"Status {resp.status_code}"
        assert body["ok"] is True, "ok ist nicht True"
        assert set(body["services"]) == {"config", "llm", "tts", "browser", "vault"}
        degraded = [k for k, v in body["services"].items() if not v.get("ok")]
        detail = "alle Dienste ok" if not degraded else "degradiert: " + ", ".join(degraded)
        report(True, "Server startet, /health antwortet", detail)
    except BaseException as e:
        report(False, "Server startet, /health antwortet", repr(e))


def check_tests():
    import smoke_lib
    # Die EINGECHECKTE Test-Fixture darf von keinem Test veraendert oder migriert
    # werden (RFC-0003/Phase 4D): sie ist v1 und liegt in Git. Wir sichern ihre
    # Bytes vor dem Lauf und vergleichen danach — so kann kein Test sie still
    # umschreiben (z.B. indem er einen mutierenden Client an ihren Pfad bindet).
    fixture = os.path.join(ROOT, "tests", "fixtures", "config.test.json")
    with open(fixture, "rb") as f:
        fixture_before = f.read()

    # Test-Environment-Integritaet (Prompt 20A §6.6): die Suite darf die beiden
    # Startschalter NICHT netto veraendern. Wuerde ein Test JARVIS_SKIP_STARTUP_
    # REFRESH pauschal poppen statt exakt wiederherzustellen, wuerde ein spaeterer
    # Lifespan-Test echtes wttr.in erreichen — reihenfolgeabhaengig und
    # kostenwirksam. Snapshot vorher, Vergleich nachher.
    _ABSENT = object()
    _ENV_KEYS = ("JARVIS_SKIP_STARTUP_REFRESH", "JARVIS_CONFIG_PATH")
    env_before = {k: os.environ.get(k, _ABSENT) for k in _ENV_KEYS}

    suite = unittest.TestLoader().discover(os.path.join(ROOT, "tests"))
    # Test-Logs/-Prints nicht in die ✓/✗-Ausgabe mischen — ABER das Logging-
    # Subsystem NICHT global abschalten. `logging.disable(CRITICAL)` wuerde auch
    # WARNING/ERROR-Records unterdruecken, sodass die obslog-Schutznetz-Tests einen
    # leeren Stream saehen (echter Records-fuehrender Fehlerpfad = Fast-Gate rot).
    # Stattdessen: (1) Konsolen-Streams waehrend des Laufs auf devnull umleiten —
    # `sys.stderr` wird dynamisch gelesen (obslog `_StderrSink`, `lastResort`), also
    # verstummt die Konsole, waehrend echte Records weiter verarbeitet werden; und
    # (2) bereits am Root haengende Handler fuer den Lauf loesen (ein frueherer
    # check_health-Start kann ueber den Lifespan einen Handler installiert haben, der
    # das *damalige* stderr gebunden hat und die Umleitung sonst umginge). Beides wird
    # im finally garantiert wiederhergestellt.
    root_logger = logging.getLogger()
    saved_handlers = root_logger.handlers[:]
    root_logger.handlers[:] = []
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            with contextlib.redirect_stderr(devnull), contextlib.redirect_stdout(devnull):
                result = unittest.TextTestRunner(verbosity=0, stream=devnull).run(suite)
    finally:
        root_logger.handlers[:] = saved_handlers

    with open(fixture, "rb") as f:
        fixture_after = f.read()
    if fixture_after != fixture_before:
        report(False, "Test-Fixture unveraendert",
               "tests/fixtures/config.test.json wurde von der Suite veraendert "
               "— ein Test schreibt in die eingecheckte Fixture.")
        return False
    report(True, "Test-Fixture unveraendert", "config.test.json bytegleich")

    env_after = {k: os.environ.get(k, _ABSENT) for k in _ENV_KEYS}
    drifted = [k for k in _ENV_KEYS if env_before[k] != env_after[k]]
    if drifted:
        report(False, "Test-Environment unveraendert",
               "die Suite hat veraendert: " + ", ".join(drifted)
               + " — ein Test stellt den Ausgangswert nicht exakt wieder her.")
        return False
    report(True, "Test-Environment unveraendert",
           "JARVIS_SKIP_STARTUP_REFRESH/JARVIS_CONFIG_PATH byte-/wertgleich")
    # Unerwartete Skips (alles ausser den bekannten Umgebungs-Skips) lassen den
    # Smoke-Test fehlschlagen — verhindert, dass die Suite "still gruen" wirkt,
    # obwohl z.B. server.py wegen kaputter Config nicht importiert werden konnte
    # (dann skippen ganze Testklassen).
    unexpected = smoke_lib.classify_skips(result.skipped)
    ok = smoke_lib.suite_ok(result.testsRun, len(result.failures),
                            len(result.errors), len(unexpected))
    detail = (f"{result.testsRun} Tests, {len(result.failures)} Failures, "
              f"{len(result.errors)} Errors, {len(result.skipped)} Skips")
    report(ok, "Testsuite", detail)
    # ALLE Skip-Gruende vollstaendig melden, mit erwartet/unerwartet-Kennzeichen.
    if result.skipped:
        reasons: dict[str, int] = {}
        for _test, reason in result.skipped:
            reasons[reason] = reasons.get(reason, 0) + 1
        for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            tag = "unerwartet" if smoke_lib.classify_skips([("", reason)]) else "erwartet"
            print(f"      ⚠ {n}× uebersprungen ({tag}): {reason}")
    if unexpected:
        print(f"      {FAIL} {len(unexpected)} unerwartete Skip(s) → Smoke faellt fehl.")
    if result.failures or result.errors:
        for test, _ in result.failures + result.errors:
            print(f"      {FAIL} {test.id()}")
        print("      Details: python -m unittest discover -s tests -v")


def main():
    print("Jarvis Smoke-Test")
    check_dependencies()
    check_config()
    check_imports()
    check_health()
    check_tests()
    if _failures:
        print(f"\n{FAIL} {len(_failures)} Schritt(e) fehlgeschlagen: " + ", ".join(_failures))
        return 1
    print(f"\n{OK} Alles ok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

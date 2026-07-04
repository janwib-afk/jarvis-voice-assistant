"""
Jarvis — Smoke-Test

Ein Befehl prueft die Grundgesundheit des Projekts, ohne echte API-Aufrufe:

    python scripts/smoke-test.py

1. config.json vorhanden und gueltig
2. Alle Module importierbar
3. Server startet (TestClient) und /health antwortet
4. Testsuite gruen (entspricht: python -m unittest discover -s tests)

Exit-Code 0 = alles ok, 1 = mindestens ein Schritt fehlgeschlagen.
"""
import logging
import os
import sys
import unittest

# Kein Netz-/Vault-Zugriff beim App-Start (siehe _startup_refresh in server.py).
os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


def check_config():
    import config_loader
    path = os.path.join(ROOT, "config.json")
    if not os.path.exists(path):
        report(False, "Config", f"config.json fehlt ({path})")
        return
    try:
        config_loader.load_config(path)
        report(True, "Config", "config.json vorhanden und gueltig")
    except config_loader.ConfigError as e:
        report(False, "Config", str(e).replace("\n", " "))


def check_imports():
    for name in ("actions", "config_loader", "browser_tools", "screen_capture", "server"):
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
        client = TestClient(server.app)
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
    suite = unittest.TestLoader().discover(os.path.join(ROOT, "tests"))
    logging.disable(logging.CRITICAL)  # Test-Logs nicht in die ✓/✗-Ausgabe mischen
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            result = unittest.TextTestRunner(verbosity=0, stream=devnull).run(suite)
    finally:
        logging.disable(logging.NOTSET)
    detail = f"{result.testsRun} Tests, {len(result.failures)} Failures, {len(result.errors)} Errors"
    if result.skipped:
        detail += f", {len(result.skipped)} uebersprungen"
    report(result.wasSuccessful(), "Testsuite", detail)
    if not result.wasSuccessful():
        for test, _ in result.failures + result.errors:
            print(f"      {FAIL} {test.id()}")
        print("      Details: python -m unittest discover -s tests -v")


def main():
    print("Jarvis Smoke-Test")
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

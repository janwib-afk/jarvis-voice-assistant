"""Sichere Windows-Native-Adapter-Smokes (kein echtes Fenster, keine Hardware).

Prueft die native Schicht auf Vertragsebene — OHNE ein pywebview-Fenster zu
oeffnen, ohne echte App zu starten, ohne Audiohardware. Der Launcher wird NUR
kompiliert (nicht importiert — er hat Import-Seiteneffekte: Logrotation,
stdout/stderr-Umleitung). Fuer echte Fenster-/Tray-/Win+J-/Mica-/Clap-/Mikrofon-
Tests siehe docs/quality/WINDOWS_NATIVE_TESTS.md (Self-hosted/manuell).

Nutzung:  python tests/native/windows_native_smoke.py
Exit 0 = alle sicheren Smokes grün (auf Nicht-Windows: sauber uebersprungen).
"""
import os
import platform
import py_compile
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

RESULTS = []


def check(name, ok, note=""):
    RESULTS.append((name, bool(ok)))
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{' — ' + note if note else ''}")


def run():
    # 1. Launcher kompiliert (Syntax/Import-Ebene) — OHNE Ausfuehrung.
    launcher = os.path.join(ROOT, "jarvis-launcher.pyw")
    try:
        py_compile.compile(launcher, doraise=True)
        check("jarvis-launcher.pyw kompiliert (ohne Ausfuehrung)", True)
    except py_compile.PyCompileError as e:
        check("jarvis-launcher.pyw kompiliert (ohne Ausfuehrung)", False, str(e))

    # 2. Native Bruecken-Abhaengigkeiten importierbar (kein Fenster/Hook).
    for mod in ("webview", "pystray", "keyboard"):
        try:
            __import__(mod)
            check(f"native Abhaengigkeit importierbar: {mod}", True)
        except Exception as e:
            check(f"native Abhaengigkeit importierbar: {mod}", False, f"{type(e).__name__}: {e}")

    # 3. Monitor-Adapter liefert kontrolliert eine Liste (ctypes; leer = Fallback).
    import monitors
    try:
        mons = monitors.detect_monitors()
        check("monitors.detect_monitors() liefert Liste",
              isinstance(mons, list), f"{len(mons)} Monitor(e)")
    except Exception as e:
        check("monitors.detect_monitors() liefert Liste", False, str(e))

    # 4. Prozess-Adapter mit Fake: Allowlist-App 'startet', ohne echten Prozess.
    import app_launcher
    started = []
    app_launcher.configure(
        [{"id": "smoke", "name": "Smoke", "command": r"C:\nicht\vorhanden.exe", "type": "process"}],
        None)
    orig = app_launcher._start_process
    app_launcher._start_process = lambda cmd: started.append(cmd)
    try:
        res = app_launcher.launch("Smoke")
    finally:
        app_launcher._start_process = orig
    check("App-Start ueber Fake-Adapter (kein echter Prozess)",
          res.get("ok") and started == [r"C:\nicht\vorhanden.exe"], str(res.get("message")))
    # Unbekannte App wird NICHT gestartet.
    unknown = app_launcher.launch("gibtsnicht")
    check("Unbekannte App nicht startbar", unknown.get("ok") is False and unknown.get("app") is None)

    # 5. Placement-Allowlists zwischen den Modulen konsistent (kein echter Move).
    import actions
    import config_loader
    check("Placement-Monitor-Allowlist konsistent (actions/config/app_launcher)",
          tuple(actions.PLACE_MONITORS) == tuple(config_loader._PLACEMENT_MONITORS)
          == tuple(app_launcher.PLACEMENT_MONITORS))
    check("Placement-Zone-Allowlist konsistent (actions/config/app_launcher)",
          tuple(actions.PLACE_ZONES) == tuple(config_loader._PLACEMENT_ZONES)
          == tuple(app_launcher.PLACEMENT_ZONES))


def main():
    if platform.system() != "Windows":
        print("[skip] Windows-Native-Smokes werden nur auf Windows ausgefuehrt "
              "(aktuell: %s) — sauber uebersprungen, NICHT als grün gewertet." % platform.system())
        return 0
    run()
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n[verify] {passed}/{len(RESULTS)} Windows-Native-Adapter-Smokes erfolgreich")
    return 0 if all(ok for _, ok in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())

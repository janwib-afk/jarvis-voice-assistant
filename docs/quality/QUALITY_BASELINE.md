# Jarvis – Quality Baseline (Phase 0)

> Verbindliche Testklassifikation, Mocking-/Kostenregeln und die frische
> Qualitätsbaseline. Stand **2026-07-13**. Ergänzt [../system/CURRENT_STATE.md](../system/CURRENT_STATE.md)
> (historische Baseline von Prompt 1) und wird in Phase 3 um die CI-Pipeline erweitert.

## 1. Frische Zahlen (2026-07-13)

| Prüfung | Befehl | Ergebnis | Exit |
|---|---|---|---|
| Unit/Contract/Integration-Suite | `python -m unittest discover -s tests` | **503 Tests, 0 Failures, 0 Errors, 0 Skips** | 0 |
| Smoke (config-unabhängig) | `python scripts/smoke-test.py` | 503 Tests, 0/0/0/0 Skips, „Alles ok" | 0 |
| Browser-E2E Phase 4 | `python docs/redesign/phase-4/tools/verify_phase4.py` ¹ | 27/27 | 0 |
| Browser-Motion Phase 5 | `python docs/motion/tools/verify_phase5.py` ¹ | 13/13 | 0 |

Test-Zusammensetzung: 484 (Baseline Prompt 1) + 9 (`test_config_seam.py`) + 10
(`test_smoke_lib.py`) = **503**.

¹ Voraussetzung: lokaler Harness `docs/design-baseline/tools/baseline_server.py`
läuft auf 127.0.0.1:8341 (Fake-LLM/TTS); UTF-8-Konsole (`PYTHONUTF8=1`), sonst bricht
der Tool-`print()` unter Windows-cp1252 an Nicht-ASCII-Zeichen ab (kein Funktionsfehler).

## 1b. Frische Zahlen (2026-07-18, Phase 4J / RFC-0006)

Der Abschnitt oben bleibt als **datierter Schnappschuss vom 2026-07-13** unverändert
stehen. Hier die am 2026-07-18 tatsächlich gemessenen Werte nach Abschluss von Phase 4J:

| Prüfung | Befehl | Ergebnis | Exit |
|---|---|---|---|
| Unit/Contract/Integration-Suite | `python -m unittest discover -s tests` | **870 Tests, 0 Failures, 0 Errors, 0 Skips** | 0 |
| Smoke (config-unabhängig) | `python scripts/smoke-test.py` | 870 Tests, 0/0/0/0 Skips, Fixture bytegleich, „Alles ok" | 0 |
| Windows-Native-Adapter-Smokes | `python tests/native/windows_native_smoke.py` | 9/9 | 0 |
| Voice-Contract (purer Reducer) | `python tests/browser/e2e_voice_contract.py` | 55/55 | 0 |
| Browser-Flows (vollständig) | `python tests/browser/e2e_functional.py` | 15/15 | 0 |
| Race-/Stale-Matrix Server | `python -m unittest tests.test_race_matrix` | 12/12 | 0 |
| Race-/Stale-Matrix Browser | `python tests/browser/e2e_race_matrix.py` | 16/16 | 0 |
| Audio-Seam | `python tests/browser/e2e_audio_seam.py` | 19/19 | 0 |
| Accessibility/Tastatur | `python tests/browser/e2e_a11y.py` | 22/22 | 0 |
| Reduced Motion | `python tests/browser/e2e_reduced_motion.py` | 16/16 | 0 |
| Visual Regression (ohne Baseline-Update) | `python tests/browser/e2e_visual.py` | 12/12, davon 10 pixelgenau identisch | 0 |
| Browser-E2E Phase 4 | `python docs/redesign/phase-4/tools/verify_phase4.py` ¹ | 27/27 | 0 |
| Browser-Motion Phase 5 | `python docs/motion/tools/verify_phase5.py` ¹ | 13/13 | 0 |

Race-Matrix und Audio-Seam wurden zusätzlich **je fünfmal hintereinander flakefrei**
ausgeführt und per Mutationsnachweis gegen Scheingrün abgesichert.

**Umgebungsgrenze, ausdrücklich offen:** Playwright-Chromium besitzt keinen verwendbaren
MP3-Codec. Der Erfolgspfad der Wiedergabe ist deshalb über einen rein testseitigen
Audio-Seam geprüft (Adapter- und Zustandssemantik), **nicht** die Dekodierung durch den
Browser. Siehe [TEST_SEAMS.md](TEST_SEAMS.md) → SEAM-AUDIO-PLAYBACK.

## 2. Testklassen

| Klasse | Zweck | Testdateien / Harness | Befehl | Umgebung | Automatisiert |
|---|---|---|---|---|---|
| **unit** | Reine Logik/Hilfsfunktionen, externe Grenzen gemockt | `test_config.py`, `test_config_seam.py` (Resolver), `test_smoke_lib.py`, `test_actions.py`, `test_browser_tools.py`, `test_tts.py`, `test_memory.py`, `test_inbox.py`, `test_monitors.py`, `test_clap_trigger.py`, `test_frontend.py` (statischer JS-Guard) | `python -m unittest discover -s tests` | keine Config/kein Netz (Fixture via `JARVIS_CONFIG_PATH`) | ja |
| **contract** | Öffentliche REST-/WS-Verträge gegen die echte App (`TestClient`) | `test_ws.py`, `test_settings_api.py`, `test_launcher_api.py`, `test_music_api.py`, `test_dashboard_api.py`, `test_config_seam.py` (`ActiveTestConfigTests`) | dito | Fixture-Config, kein Netz | ja |
| **integration** | Gesprächsfluss + mehrere Module verdrahtet, APIs gemockt | `test_integration_research.py`, `test_confirm_flow.py`, `test_voice_launcher.py`, `test_app_launcher.py`, `test_prompt.py` | dito | Fixture-Config, LLM/TTS/Browser gestubbt | ja |
| **browser** | Echte Chromium-E2E/Visual/Motion gegen den gestubbten Harness | `docs/redesign/phase-4/tools/verify_phase4.py`, `docs/motion/tools/verify_phase5.py`, Harness `baseline_server.py` | `python docs/.../verify_phaseX.py` (Harness auf 8341) | Playwright-Chromium, lokal, 127.0.0.1 | ja (separat, nicht in der `unittest`-Suite) |
| **windows-native** | Statische Guards für Windows-Skripte (keine Hardware) | `test_launcher_ps1.py` (launch-session.ps1) | `python -m unittest discover -s tests` | Windows-Dateien vorhanden | ja (statisch) |
| **external-manual** | Echte Hardware/kostenpflichtige Provider — ehrlich manuell | echtes STT, echte ElevenLabs-TTS, echter Claude-Inhalt/Vision, echter App-Start + Fensterplatzierung, Doppelklatschen, native pywebview-Größen, Screenreader | manuell im Launcher | echte Keys/Hardware | **nein** — Anleitung in `docs/final-audit/evidence/EVIDENCE.md` |

## 3. Skip-Policy

- **Erwartete Skips** (Umgebungslimit, kein Defekt): Skip-Grund enthält einen Marker
  aus `scripts/smoke_lib.py::EXPECTED_SKIP_MARKERS` — aktuell nur
  `"playwright-Paket nicht installiert"` (2 Tests in `test_config.py`).
- **Unerwartete Skips** (alles andere) lassen den Smoke-Test **fehlschlagen**
  (`suite_ok(...) == False`, Exit ≠ 0). Insbesondere `"server import nicht moeglich"`
  (kaputte/fehlende Config) skippt sonst ganze Klassen still — das gilt jetzt als Fehler.
- **Aktueller Lauf: 0 Skips** (Playwright ist installiert; Fixture verhindert
  Server-Import-Skips). Nachgewiesen negativ: mit `JARVIS_CONFIG_PATH` auf eine fehlende
  Datei meldet der Smoke-Test 131 **unerwartete** Skips und endet mit Exit 1 (kein
  stiller Rückfall auf die persönliche Config).

## 4. Config-Unabhängigkeit (Phase-0-Seam)

- Produktion nutzt `config.json`; kontrollierte Starts/Tests wählen über
  `JARVIS_CONFIG_PATH` ausdrücklich die eingecheckte, synthetische Fixture
  `tests/fixtures/config.test.json` (Dummy-Keys, keine persönlichen Pfade).
- Auswahlmechanik: `config_loader.resolve_config_path(os.environ, default)`; die
  Testsuite setzt die Variable in `tests/__init__.py` (+ `import tests` als erster
  Import in jeder server-importierenden Testdatei); der Smoke-Test setzt sie am Kopf.
- **Kein stiller Fallback**: ist die gewählte Config fehlerhaft/fehlt, bleibt es ein
  harter `ConfigError` (nie Rückfall auf `config.json`). Bewiesen durch
  `test_config_seam.py::ActiveTestConfigTests` und den negativen Smoke-Lauf.

## 5. Mocking-Regeln

- Eigene REST-/WS-/Persistenzschichten werden **real** getestet (Starlette
  `TestClient`, echte `config_loader`/`memory`-Dateizugriffe in Temp-Ordnern).
- Nur **externe Grenzen** werden gemockt: Anthropic (LLM/Vision), ElevenLabs (TTS),
  Wetter (`wttr.in`), Playwright-Browser, Screen/Clipboard/Audio.
- Erwartete Werte werden aus der **Spezifikation** abgeleitet, nicht aus der
  Implementierung nachgebaut (siehe `test_smoke_lib.py`).
- `JARVIS_SKIP_STARTUP_REFRESH=1` (in `tests/__init__.py` + Smoke) verhindert echte
  Wetter-/Vault-Zugriffe bei App-Start.

## 6. Kostenregeln

- **Standardtests verursachen 0 Providerkosten.** Alle LLM-/TTS-/Wetter-/Browser-Pfade
  sind gemockt oder übersprungen; die Fixture enthält Dummy-Keys.
- Keine kostenpflichtigen Dienste in der automatisierten Suite oder im Smoke-Test.
- Echte Provider werden ausschließlich manuell (`external-manual`) angefasst.

## 7. Windows-/Hardware-Abgrenzung

- Getestet unter **Windows 11 / CPython 3.14.5** (Referenz); Mindest-Python **3.10**
  (siehe [../system/SYSTEM_CHARTER.md](../system/SYSTEM_CHARTER.md)).
- Hardware-/OS-nahe Fähigkeiten (Mikrofon, Doppelklatschen, native Fensterplatzierung,
  pywebview-Fenstergrößen, echter Screenreader) sind **external-manual** — sie werden
  **nicht** durch irreführende grüne Automatisierung ersetzt.

## 8. Bekannte Lücken

- Keine CI (`.github/` fehlt) — die PR-Pipeline folgt in Phase 3.
- Keine automatisierte Visual-Regression (Screenshots werden erzeugt, aber ohne
  Pixel-Diff-Gate).
- Browser-E2E läuft nur mit manuell gestartetem Harness (nicht Teil der `unittest`-Suite).
- `playwright-best-practices`-Referenzen sind zum Zeitpunkt von Prompt 1 unvollständig
  (Ergänzung in Phase 0, siehe Skill-Readiness im Phase-0-Bericht).
- Kritische E2E-Flows werden noch nicht 5× wiederholt (Flake-Nachweis: Phase 3).

## 9. Spätere CI-Aufteilung (Phase 3, geplant)

PR-Pipeline: **Syntax → unit → contract → REST/WS-Integration → Browser-Smoke**, mit
Gate „0 unerwartete Skips" und „0 kostenpflichtige Provideraufrufe". Nightly/Native/
Soak/Fault-Injection/Visual-Regression folgen in Phase 11/13. Frischer Windows-Runner
muss ohne persönliche `config.json` grün sein (Seam aus Phase 0 erfüllt die
Voraussetzung).

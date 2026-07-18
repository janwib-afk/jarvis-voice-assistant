# Jarvis – CI-Pipeline (Phase 3B)

> Schnelle PR-Pipeline: [`.github/workflows/pr.yml`](../../.github/workflows/pr.yml).
> Anbieter: GitHub Actions (Repo hat ein GitHub-Remote). Runner: `windows-latest`,
> Python **3.12**. Keine echten Provider, keine Secrets, keine persönliche Config.

## PR-Gates (schnell)

| Gate | Job / Schritt | Lokales Äquivalent |
|---|---|---|
| 1 Syntax/Import | `fast` › Gate 1 | `python -m compileall -q server.py runtime.py configuration.py obslog.py wire_protocol assistant_core.py actions.py config_loader.py app_launcher.py memory.py browser_tools.py monitors.py tts.py health.py screen_capture.py clipboard_tools.py` |
| 2 Unit | `fast` › Smoke + unittest | `python -m unittest discover -s tests` |
| 3 Contract | `fast` › unittest (test_actions/test_config/test_ws/test_conversation_ws …) | `python -m unittest discover -s tests` |
| 4 REST-/WS-Integration | `fast` › unittest (test_ws/test_settings_api/test_launcher_api/test_conversation_ws) | `python -m unittest discover -s tests` |
| 5 Browser-Smoke | `browser` › Gate 5 | `python tests/browser/e2e_functional.py --smoke` |
| 6 Skip-Policy | `fast` › Smoke | `python scripts/smoke-test.py` |
| 7 Windows-Adapter-Smokes | `fast` › Gate 7 | `python tests/native/windows_native_smoke.py` |
| (+) Voice-State-Contract | `browser` | `python tests/browser/e2e_voice_contract.py` |
| (+) Accessibility | `browser` | `python tests/browser/e2e_a11y.py` |
| (+) Reduced Motion | `browser` | `python tests/browser/e2e_reduced_motion.py` |

**Eigenschaften:** Windows-Runner · dokumentierte Python-Version (3.12) · frische
Dependency-Installation · Chromium-Installation · synthetische Config (Test-Fixture
bzw. gestubbter E2E-Server) · keine Secrets/echten Provider/persönliche Config ·
Job-Timeouts (15/25 min) · Abbruch veralteter Runs (`concurrency`) · Failure
Artifacts (`JARVIS_E2E_ARTIFACTS` → Upload bei Fehler) · keine stillen Skips
(Smoke-Test bricht bei unerwarteten Skips ab).

## Vollständige lokale PR-Äquivalenz

```powershell
$env:PYTHONUTF8 = "1"
python -m compileall -q server.py runtime.py configuration.py obslog.py wire_protocol assistant_core.py actions.py config_loader.py app_launcher.py memory.py browser_tools.py monitors.py tts.py health.py screen_capture.py clipboard_tools.py
python scripts/smoke-test.py
python -m unittest discover -s tests
python tests/native/windows_native_smoke.py
python -m playwright install chromium   # einmalig
python tests/browser/e2e_voice_contract.py
python tests/browser/e2e_functional.py --smoke
python tests/browser/e2e_a11y.py
python tests/browser/e2e_reduced_motion.py
```

## Nightly-/Release-Gates (spätere Phasen — NICHT im schnellen PR-Lauf)

| Gate | Befehl | Phase |
|---|---|---|
| Vollständige Browser-E2E (11 Flows) | `python tests/browser/e2e_functional.py` | jetzt lokal, Nightly ab Phase 11 |
| Flake-Gate (kritische Flows 5×) | `python tests/browser/e2e_functional.py --repeat 5` | Nightly |
| Visual-Regression | `python tests/browser/e2e_visual.py` | Nightly (Phase 11) |
| Motion-/A11y-Harness | `python docs/redesign/phase-4/tools/verify_phase4.py`, `verify_phase5.py` (Baseline-Server auf 8341) | Nightly |
| Native-Hardware, Soak, Fault-Injection, Installer/Rollback | Self-hosted/manuell | Phase 11/13 |

## Manuelle Grenzen

- **Self-hosted/manuell:** echte pywebview-Fenster, Tray, Win+J, Mica, echte
  App-Positionierung, Doppelklatschen, echtes Mikrofon/STT/TTS, Screenreader —
  siehe [WINDOWS_NATIVE_TESTS.md](WINDOWS_NATIVE_TESTS.md) (nie auf Hosted-Runnern).
- **Visual-Baseline-Freigabe:** neue Baselines werden nur nach ausdrücklicher
  Nutzerbestätigung akzeptiert (`e2e_visual.py --update`), nie blind aktualisiert.

## Hosted-Runner-Evidenz (Phase-3-Gate)

- **Datum:** 2026-07-15
- **Repository (persönlicher Fork):** `janwib-afk/jarvis-voice-assistant`
  (Fork von `Julian-Ivanov/jarvis-voice-assistant`)
- **Runner:** frischer GitHub-**hosted** Windows-Runner (`runs-on: windows-latest`,
  beide Jobs)
- **Auslöser:** `workflow_dispatch` auf `master`
- **Getesteter Commit:** `e8079151b0bc9ec1342efc2481e71b457e76cc0f`
  (`test: establish phase 3 Windows hosted-runner gate`)
- **Run-ID / URL:** 29378212904 ·
  https://github.com/janwib-afk/jarvis-voice-assistant/actions/runs/29378212904
- **Ergebnis:**
  - Job **Fast gates (syntax/unit/contract/integration/skip/native):** `success`
    (alle Schritte grün — compileall, Smoke, volle Unittest-Suite, Windows-Native-Smokes)
  - Job **Browser gates (Chromium):** `success`
    (Chromium-Install, Browser-Smoke, Accessibility, Reduced Motion — alle grün)
- **Skips:** nur der `if: failure()`-Schritt „Upload failure artifacts" wurde
  übersprungen (erwartet bei Erfolg); **0 unerwartete Skips**.
- **Kosten/Secrets:** keine Secrets referenziert; Tests nutzen synthetische
  Fixtures/gestubbte Provider → **0 echte Provideraufrufe, keine persönliche Config**.

> Ein zweiter `workflow_dispatch`-Lauf validiert den finalen Commit (inkl. dieser
> Dokumentation) — siehe Phase-3-Bericht.

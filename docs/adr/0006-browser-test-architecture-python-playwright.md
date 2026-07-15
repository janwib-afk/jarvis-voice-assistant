# ADR 0006 – Browser-Testarchitektur: Python Playwright

- **Status:** akzeptiert (Phase 3B, 2026-07-14) — unter der Nutzer-Delegation
  („folge deiner Empfehlung"). Python Playwright reicht aus; kein zweiter
  Node-/TypeScript-Teststack.
- **Betrifft:** [../quality/BROWSER_TEST_STRATEGY.md](../quality/BROWSER_TEST_STRATEGY.md),
  [../quality/TEST_SEAMS.md](../quality/TEST_SEAMS.md) (SEAM-BROWSER-UI), `tests/browser/*`.

## Warum ADR (3 Kriterien)

1. **Teuer zurückzunehmen:** legt Runner, Harness-Muster und CI-Struktur für alle
   künftigen Browser-/Visual-/A11y-Tests fest.
2. **Ohne Kontext überraschend:** „Warum kein `@playwright/test` (Node), wo die
   Playwright-Doku Node-zentriert ist?" braucht Begründung.
3. **Echter Trade-off:** Node-Toolchain-Features (eingebauter Test-Runner,
   `toHaveScreenshot`, Trace-Viewer-UI) vs. einheitlicher Python-Stack ohne
   zweite Sprache/Toolchain.

## Kontext

Das gesamte Projekt (Runtime, Tests, bestehende UI-Harnesses) ist Python. Es
existieren bereits bewährte Python-Playwright-Harnesses:
`docs/design-baseline/tools/baseline_server.py` (sicherer Fake-Provider-Server),
`capture_baseline.py` (deterministische Screenshots),
`docs/redesign/phase-4/tools/verify_phase4.py` und
`docs/motion/tools/verify_phase5.py` (funktionale/A11y-/Motion-Checks, grün).
`requirements.txt` pinnt `playwright`, `Pillow`, `numpy`.

## Entscheidung

- **Runner:** Python Playwright (`playwright.sync_api`) bleibt der E2E-Runner.
- **Kein zweiter Stack:** kein Node/TypeScript-Testframework — es fehlt keine
  konkret benötigte, nicht ersetzbare Fähigkeit:
  - Visual-Regression: selbst gebaut mit Pillow/numpy-Pixeldiff gegen eine
    bestätigte Baseline (`tests/browser/e2e_visual.py`) — Determinismus über feste
    Uhr/Animationen-aus/lokale Fonts.
  - Accessibility: semantische DOM-/Keyboard-Prüfung über
    `get_by_role`/`get_by_label` (`e2e_a11y.py`); ein Axe-Lauf würde Node/CDN
    erfordern und ist bewusst nicht Teil der Pflichtprüfungen.
  - Trace/Video/Screenshots, Netzwerk-Interception, WebSocket-Beobachtung,
    Reduced-Motion, Responsive: alle in Python-Playwright vorhanden.
- **Wiederverwendung:** die sicheren Harness-Ideen (Fake-Provider, Loopback,
  Freeze) werden in `tests/browser/e2e_server.py`/`e2e_harness.py` übernommen;
  die bestehenden Audit-Harnesses/-Screenshots bleiben **unverändert** erhalten.

## Alternativen

1. **`@playwright/test` (Node/TS)** — bester eingebauter Runner + Snapshot-API,
   aber zweite Sprache/Toolchain, doppelte CI-Installation, geteiltes Wissen.
   Verworfen: kein zwingender Mehrbedarf.
2. **pytest-playwright** — dünner Wrapper; die Suiten sind als eigenständige
   Skripte (wie verify_phase4/5) einfacher in getrennte CI-Gates zu schneiden.
   Optional später, kein Blocker.

## Konsequenzen

- Ein einziger Python-Stack für Runtime + alle Tests; CI installiert nur Python +
  Chromium.
- Visual-Baseline-Management ist selbst gebaut (Pixeldiff + Toleranz) statt über
  eine Framework-Snapshot-API — dafür voll transparent und plattform-gepinnt.

## Sicherheitsauswirkungen

Alle Browsertests laufen gegen einen lokalen Fake-Provider-Server (Dummy-Keys,
LLM/TTS/Desktop gestubbt) mit strikter Netzwerk-Policy (nur Loopback + data:/
blob:) — 0 echte Provideraufrufe, 0 externe Hosts.

## Rücknahmekriterien

Neu bewerten, falls ein konkret benötigtes Feature (z. B. verlässliche
Cross-Browser-Snapshot-Diffs mit Maskierung) in Python-Playwright nachweislich
fehlt — dann Node-Stack als zusätzliches, isoliertes Gate mit ausdrücklicher
Nutzerfreigabe (nicht als Ersatz).

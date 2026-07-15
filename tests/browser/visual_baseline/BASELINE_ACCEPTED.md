# Visual-Regression-Baseline — akzeptiert

- **Bestätigt vom Nutzer am 2026-07-14** („Ja, als Baseline bestätigen").
- **Plattform (gepinnt):** Windows 11, Chromium (headless, Playwright), Device-Scale 1.
- **Umfang:** 12 PNGs (siehe Dateien in diesem Verzeichnis), Viewports
  1920×1080 / 1000×800 / 420×560.
- **Aufnahme:** deterministisch — feste Uhr + Animationen aus, lokale Fonts
  vollständig geladen, synthetische Daten aus dem E2E-Stub, 0 externe Assets.
- **Prüfung:** `python tests/browser/e2e_visual.py` (Pixeldiff, Toleranz 0,2 %).
- **Aktualisierung nur nach erneuter ausdrücklicher Freigabe:**
  `python tests/browser/e2e_visual.py --update` — **nie** blind aktualisieren.

Hinweis: `docs/design-baseline/screenshots` ist die Phase-0-Baseline VOR dem
Redesign und ist NICHT das Vergleichsziel dieser automatisierten Suite.

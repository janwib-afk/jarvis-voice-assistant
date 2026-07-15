# Implementation-Handoff für Phase 4 (aus Phase 3, 2026-07-11)

Verbindliche Reihenfolge für die produktive Umsetzung. Quellen: `DESIGN.md` (visuell) + `docs/ux/*` (Struktur/Verhalten) + UX-Prototyp (`docs/ux/prototype/`, 34/34 validierte Prüfungen) als Referenzimplementierung der Interaktionslogik.

## Reihenfolge (jeder Schritt einzeln verifizierbar, style.css bleibt stets lauffähig)

| # | Paket | Betroffene Dateien | Kern | DoD |
|---|---|---|---|---|
| 1 | **Token-Zielwerte + Fonts** | `frontend/design-tokens.css`, neu `frontend/assets/fonts/*` (aus `docs/design-direction/prototype/assets/fonts`), `frontend/index.html` (@font-face-Link bzw. Preload) | Phase-1-Tokens auf DESIGN-§5-Werte; neue Tokens (bg-raised/-inset, copper, warning, info, edge-light, focus-halo, Dot-Semantik ok=Moos); Fraunces/Plex einbinden | Frozen-Capture zeigt neue Palette überall konsistent; Kontrast-Skript 0 Fails; 471 Tests grün |
| 2 | **Fokus-System + Fußleiste** | `frontend/style.css`, `frontend/index.html` (Fußleisten-Markup, Stop/Mute ≥44px, Klartext-Labels), `frontend/main.js` (Status-Center-Texte) | `:focus-visible` global; Gerätefußleiste ersetzt Status-Center+lose Buttons; Skip-Link | Tab-Rundgang sichtbar; R1-Framecheck (Kopf+Stop gleichzeitig) in allen Modi; Esc/Stop-Invarianten-Tests grün |
| 3 | **Statuszeile + Zustandsmodell** | `frontend/main.js` (`setOrbState`→Zustandswort-Map, laufende Aktion in Statuszeile, `role=status`), `frontend/style.css` | STATE_MODEL-Bezeichnungen + Dot-Klassen; Aktions-Dedupe (Fokus: Spalte raus) | WS-Tests + neue Guards (Wortliste je Zustand); Sichtprüfung Ketten |
| 4 | **Journal/Transcript** | `frontend/main.js` (`renderTranscript`: Sprecher-Element, Copy fokussierbar, Trefferzahl, Pill), `frontend/index.html`, `frontend/style.css` | Journal-Layout (Marginalzeit, Serifen-Stimme), Suche+Live-Count, Auto-Scroll-Regel | test_frontend-Guards angepasst/ergänzt; Flows 11–15 manuell je 1× |
| 5 | **Navigation/Modi/Kopfleiste** | `frontend/index.html`, `frontend/style.css`, `frontend/main.js` (Fokus auf Bereichs-H1, Tooltip Panel-Nav) | Text-Tabs + Unterstreichung; Panel-Zusagen (Modus-Schalter kompakt, Klartext-Fußleiste) | Guards `rootClass`-Kontrakt unverändert; Panel→KZ-Flow |
| 6 | **Kontrollzentrum-Werkbank** | `frontend/index.html`, `frontend/style.css`, `frontend/main.js` (Bucht-Statuszeile, Zonen als `<button>` mit aria-label, Chip-Wanderung) | Buchten-Optik, progressive Selects s. #7, Profile-Confirm-Klartext | Flows 16–24; Map-Tastaturpfad |
| 7 | **Positions-Selects (neue Funktion)** | `frontend/main.js` (+ `renderApps`), nutzt bestehendes `POST /launcher/apps/{id}/placement` | Selects Monitor/Zone + „Position speichern" im ausgewählten Modul — **keine Server-Änderung** | Neue Unit-Guards (Markup) + manueller POST-Roundtrip im Harness |
| 8 | **Settings-Gruppen + Musik** | `frontend/index.html` (fieldsets/Gruppen), `frontend/settings.js` (dirty-Pill, Verwerfen-Confirm, Fehlerfokus, Fehlerplatz-Reservierung!), `frontend/music.js` (Status-Texte) | Teil-8-Spez; **f-err-Platzreservierung gegen Klick-Schlucken** (Reviewer-Befund, layout-shift) | test_settings_api unverändert grün; Flows 25–29 |
| 9 | **Banner-Vereinheitlichung** | `frontend/main.js` (showErrorBanner→4 Familien, Abhilfetexte), `frontend/style.css` | error/warning/success/info + `role=alert` nur error | Flow 10; disconnected-Sendehinweis |

Danach: Frozen-Capture-Referenz NEU aufnehmen (neue Soll-Optik = Prototyp-Screens), `DESIGN_TOKENS.md` aktualisieren, Phase 5 (Motion, emil-design-eng).

## Abhängigkeiten & Risiken

- Schritt 1 vor allen (Tokens tragen alles); 2+3 vor 4–6 (Fußleiste/Statuszeile werden referenziert); 7 nach 6.
- **Guards in `tests/test_frontend.py`** pinnen exakte Strings (`display:none`-Blöcke, `window-mode-switch`, Boot-Klasse, CONTROL_VIEWS…): Bei Schritt 4/5/6 Guards bewusst MIT der Änderung fortschreiben (nie löschen, semantisch ersetzen).
- **WS-/Sprach-/Launcher-Logik bleibt unberührt** — alle Pakete sind Rendering/Markup/CSS + eng umrissene main.js-UI-Funktionen (`renderTranscript`, `renderApps`, `setOrbState`-Anzeige, `showErrorBanner`); Invarianten aus BASELINE §8 gelten.
- pywebview/WebView2-Gerätetest (Fonts, `font-variation-settings`) in Schritt 1 einplanen (DECISIONS offene Frage 1).
- `error-brick`-Fließtextregel (DESIGN §17.6) in Schritt 9 entscheiden.

## Tests

**Vorhanden:** 471 (unittest, offline) — decken Server/API/Guards; `scripts/smoke-test.py`.
**Neu nötig:** Guards für Zustandswort-Map (main.js-Strings), Journal-Markup (Sprecher-Element, Copy-Button `aria-label`), Positions-Selects-Markup + Placement-POST (TestClient), Settings-dirty/Confirm-Strings, Fußleisten-Markup (Stop `aria-label`, ≥44px-Klasse), Skip-Link. Browser-Regression: `docs/ux/tools/capture_ux.py`-Checks (R1/R2/R3/R4/R7) auf die produktive UI portieren (Harness 8341 statt file://).

## Definition of Done je Oberfläche

Gespräch: Flows 1–15 grün am Harness (Fake-LLM), R1-Framecheck, Live-Regionen announzieren (SR-Smoke via NVDA einmalig manuell). Kontrollzentrum: Flows 16–24 inkl. Weg B ohne Karte; Bucht-Feedback sichtbar. Settings/Musik: Flows 25–29, kein Layout-Shift bei Validierung. Modi: Sichtbarkeitsmatrix stichprobenhaft (Panel-Zusagen!), Zoom-200%-Näherung ohne H-Scroll. Immer: 471+neue Tests grün, `git status` sauber, kein API-Spend.

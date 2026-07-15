# Phase 4 — Produktive Implementierung „Warm Analog Intelligence" (2026-07-12)

Umsetzung von DESIGN.md (Phase 2) + docs/ux/* (Phase 3) im produktiven Frontend. Skills: `frontend-design` (visuelle Hand, Screenshot-Selbstkritik je Paket) + `ui-ux-pro-max` (Verhaltens-Checklisten §1/§2/§5/§8/§9; Abschluss über portierte R-/Flow-Checks). Testbaseline VOR Beginn: 471/0 + Smoke Exit 0 + Frozen-Capture `pre-phase4` (Scratchpad).

## Umgesetzte Arbeitspakete

| AP | Inhalt | Kern-Nachweis |
|---|---|---|
| 1 | Token-Zielwerte (`design-tokens.css` komplett neu bewertet, alte Namen als stabile Schnittstelle + neue Rollen: Flächen-Trio, Kupfer, Warnung/Info, Fokus-System, Dot-ok=Moos) + Fonts lokal (12 woff2 + 3 OFL → `frontend/assets/fonts/`) | verify „Fonts geladen [True,True,True]"; keine 404s |
| 2 | Shell: Wortmarke „Jarvis.", Unterstreichungs-Nav, Geräteschalter (inset/raised), Mixed-Case (24 `text-transform`-Zeilen zählverifiziert entfernt), globales `:focus-visible`, Gerätefußleiste (Status-Klartext + Stop/Mute 44px, fixed) | R1-Framecheck ✓ in Vollbild/Fokus/Panel/kleiner Höhe |
| 3 | Semantik: Skip-Link (erstes Tab-Ziel → Eingabe), Landmarken (`nav/main/footer`, role=banner), sr-only-H1 je Bereich + Fokus nach Bereichswechsel, `aria-pressed/-label` Mute, Copy-`aria-label` je Eintrag | verify AP3/Flow-16-Checks ✓ |
| 4 | Lünetten-Instrument (conic-Messing + Strichskala + Fassungsbett, rein CSS) um bestehendes `#orb`; Zustandswort-Map (STATE_MODEL) in `setOrbState`/`renderStatusCenter`; laufende Aktion + Esc-Hinweis in Statuszeile via `addActionEntry` (eine Darstellungsfunktion = ein Codepfad, direkt testbar); Stop `primary-now` bei speaking/Aktion; **Aktions-Dedupe**: `html.mode-focus #action-history` aus, KZ-Spalte + Panel-Mini bleiben | verify AP4/AP11 ✓; Screens `zustand--action-running-statuszeile.png` |
| 5 | Journal: Panelfläche, Marginal-Zeit (Mono), Sprecher-Element (`.msg-speaker`, JS-Rendering ohne Präfix; Copy-All exportiert weiter „Du:/Jarvis:"), Jarvis-Stimme Fraunces 15.5/1.62, Trefferzahl `#search-count` (role=status), Auto-Scroll nur am Ende + „↓ Neue Nachricht"-Pill, Leerzustand via CSS `:empty`, Eingabe eingelassen + sichtbarer Hint | verify Flow 11/12/AP5 ✓ |
| 6–7 | Werkbank: Subnav/Profil-Unterstreichungen, Bucht eingelassen (Grid-Tokens), Heute flach, App-Kacheln (Surface, Badge Mono, Zustände busy/ok/err), Bernstein-Autostart-Knopf | Screens `control-overview--*` |
| 8 | Map: bestehende Zonen/Chips/Ghost restyled; `#cc-map-status` = Bucht-Feedback; **NEU Weg B: Positions-Selects je App-Modul** (progressive disclosure bei Auswahl/Fokus) → vorhandenes `assignPlacement()` | verify AP8/19B ✓ („Obsidian: Platzierung gespeichert.") |
| 9 | Settings: 7 Gruppen-Fieldsets, dirty-Pill, Verwerfen-Rückfrage (btn-keep/btn-discard, Fokusführung), Fehlerfokus auf Meldung (`setMsg` fokussiert bei Fehlern — Serverfehler sind global, s. Abweichungen), „Gespeichert ✓" | verify AP9 ✓ (4 Checks) |
| 10 | Musik: Wortlaut „Spielt beim nächsten Start: …" (music.js + `#music-status`) | verify AP10 ✓ |
| 11 | Zustandsmodell: Wort/Farbe/Klasse je Zustand (`#status-row.s-*`), Klartext Server/Mikro (`#sc-conn-text/#sc-mic-text`), muted-Überlagerung, disconnected via bestehendem Reconnect-Pfad („Getrennt" + Versuchstext) | verify Zustandswort-Matrix ✓ |
| 12 | Responsive: Panel-Zusagen (Schalter sichtbar, Klartext-Fußleiste 40px-Kontrollen), Fokus ohne Aktionsspalte + Journal-Spaltenfix (`min-width:0`, Toolbar-Umbruch), Vollbild `max-width:1520px`, `max-height:650px`-Degradation, Zoom-200%-Näherung ohne H-Scroll | verify R1/R4/AP12 ✓ + Stress-Shots |
| 13 | Bereinigung: `#btn-settings`-Regeln entfernt (Guard-Beleg), Encoding-Unfall (PS-5.1-ANSI) per Roundtrip repariert und verifiziert (362 Box-Zeichen), Banner-Familien (`eb-warning` für tts/config) | Suite grün nach jedem Schritt |

## Geänderte Dateien

`frontend/design-tokens.css` (Zielwerte+Fonts) · `frontend/style.css` (Mixed-Case-Pass + Phase-4-Gestaltungsschicht vor den Media-Queries + Dead-CSS-Abbau) · `frontend/index.html` (Skip-Link, Wortmarke, Landmarken, Statuszeilen-Wrapper, Journal-Panel+Pill+Count, Ask-Hint, Gerätefußleiste um bestehende IDs, Settings-Gruppen+dirty/confirm, sr-only-H1s) · `frontend/main.js` (nur Renderfunktionen: STATE_WORDS/`setStatusWord`, `renderStatusCenter`, `setOrbState`, `addActionEntry`, `renderTranscript`+Pill, `updateMuteButton`, `buildAppModule`+Selects, `showErrorBanner`-Familien, Fokus nach Nav) · `frontend/settings.js` (dirty/confirm/Fehlerfokus) · `frontend/music.js` (Wortlaut) · NEU `frontend/assets/fonts/*`, `docs/redesign/phase-4/*`.
**Unverändert:** Server/Backend, actions/launcher, `jarvis-launcher.pyw`, WS-/Sprach-/Stop-/Reconnect-Logik, alle API-Pfade/IDs/Events; `tests/test_frontend.py` brauchte KEINE Anpassung (alle Pins gehalten).

## Abweichungen von der Spezifikation (begründet)

1. **Keine große Begrüßungs-Headline** auf der Jarvis-Seite: Das gesprochene Briefing erscheint als erste Journal-Antwort; eine zusätzliche statische Headline würde doppeln und bräuchte serverseitige Namens-Injektion. (UX_ARCH §4 Punkt 1 wird von Statuszeile+Fußleiste getragen.)
2. **Fehlerfokus in Settings auf die Meldung** statt aufs Feld: `/settings`-Fehler sind globale Listen ohne Feldbezug; `aria-live` + Fokus auf `#settings-msg`. Feldvalidierung mit reserviertem Platz bleibt Muster für künftige feldgenaue Checks.
3. **Skip-Link-Ziel einheitlich `#text-input`** („Zur Eingabe springen") in allen Modi — einfacher als modusabhängige Ziele, erfüllt denselben Zweck.
4. **Kein Canvas-Grain** (DESIGN §8 „optional"): Verzicht zugunsten Ruhe/Perf; Lampenlicht trägt die Atmosphäre.
5. **Dot-Semantik-Wechsel** ok=Moos/Bernstein=läuft ist aktiv (FEATURES-Texte sprechen von „Punkten" ohne Farbfestlegung — kein Doku-Konflikt; Klartext steht immer daneben).

## Bekannte Einschränkungen / Risiken

- **Puls-Keyframes tragen noch Alt-Glowfarben** (pulse-listen/-speak interne rgba): visuell nah am neuen Amber; wird in Phase 5 mit dem Motion-System ersetzt (bewusst zurückgestellt).
- Kleine Monitor-Map bei schmaler Bucht: Chips können sich berühren (Bestandsverhalten); Weg B (Selects) ist der präzise Pfad.
- WebView2-Gerätetest (Fraunces `font-variation-settings`) steht aus — bitte einmal regulär per Launcher starten (nicht gegen den echten Server per Browser öffnen — Auto-Begrüßung kostet API-Guthaben).
- `#sc-error` zeigt im Harness eine TTS-Warnung des Stubs — erwartetes Verhalten des Testaufbaus.

## Phase-5-Übergabe (Motion, `emil-design-eng`)

Absichten aus DESIGN §14 umsetzen: Orb-Puls-Keyframes neu (Token-Farben, Frequenz-Semantik 1.8/0.85/0.65s), `--duration-pulse-run`-Dot, Banner-Einflug, Modus-/Bereichs-Übergänge, Start-Aufglimmen; `prefers-reduced-motion`-VOLLabdeckung (heute: Alt-Block + pauschale Neuelemente; Orb-Pulse laufen noch); Pill-/Copy-Mikrofeedback. Statisch ist alles verständlich (verifiziert) — Motion ist reine Veredelung.

## Verifikation (frische Evidenz, 2026-07-12)

- `python -m unittest discover -s tests` → **Exit 0, 471 Tests** (unverändert zur Baseline; keine Guard-Änderung nötig).
- `python scripts/smoke-test.py` → **Exit 0**.
- `docs/redesign/phase-4/tools/verify_phase4.py` (Harness 8341, Fake-LLM/TTS, 0 externe Calls) → **27/27 Prüfungen**, 0 Konsolenfehler.
- **33 Screenshots** unter `screenshots/` (27 Ansichts-/Zustandsserie + 6 Flow-/Stress-Shots) — decken die 17 Pflichtmotive ab (Modi, Views, 6 Orb-Zustände, Tastaturfokus, kleine Höhe, 200 %-Näherung, reduced-motion).
- Git: nur die oben gelisteten Frontend-Dateien + `docs/redesign/phase-4/` neu; Nutzerstände unangetastet; kein Commit.

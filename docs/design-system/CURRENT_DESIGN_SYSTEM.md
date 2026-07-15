# Jarvis — Bestehendes Designsystem (Phase-1-Inventur, 2026-07-11)

Vollinventur der visuellen Sprache vor dem Redesign, erstellt mit dem Skill `extract-design-system` (CLI-Extraktion gegen das Baseline-Harness als Gegenprobe) und vollständiger `style.css`-Analyse. Seit Phase 1 sind alle wiederkehrenden Werte semantische Tokens (`frontend/design-tokens.css`, Referenz: [`DESIGN_TOKENS.md`](DESIGN_TOKENS.md)) — **pixelgleich migriert** (Beweis: [`verification/DIFF_REPORT.md`](verification/DIFF_REPORT.md), 27/27 identisch).

Marker: **`Beibehalten`** · **`Vereinheitlichen`** (Phase 2 zusammenführen) · **`Später neu gestalten`** (Phase-2-Designentscheidung) · **`Prüfen`** · **`Entfernungskandidat`**.

---

## 1. Zusammenfassung der Jarvis-Identität

Warmes Amber-HUD auf Fast-Schwarz (`#0d0b09`): ein monochromes Gold-/Braun-System statt generischem Dark-Theme-Blau. Identitätskern sind (a) der **Orb** als lebendes Statusinstrument (sechs Zustände über Farbe *und* Pulsfrequenz), (b) die **Lamp-Glows** als Lichtraum, (c) konsequente **Uppercase-Mikrotypografie** mit weiter Laufweite, (d) eine einheitliche **Dot+Glow-Feedbacksprache** (gold=ok, pulsierend=läuft, rot=Fehler). Es gab bis Phase 1 **kein** Token-System — 2070 Zeilen mit 31 Hex- und 70 rgba-Literalen; die Skill-CLI bestätigte `cssVariables: {}`.

## 2. Farbinventar

Vollständige Tabellen mit Werten, Häufigkeiten, Semantik und Fundstellen: [`DESIGN_TOKENS.md`](DESIGN_TOKENS.md). Kernstruktur:

- **Neutrale Achse (Text):** `#c4b49a` primär → `#a08060` soft → `#8a6c46` tertiär → `#7a5c38` sekundär (häufigste Farbe, 24×) → `#6a5030` muted → `#5a4630` note → `#4a3826` faint → `#3e3026` user-msg → `#3a2e22` dim → `#2a1e12` chrome. **`Vereinheitlichen`**: Zehn Braunstufen sind zu viele — `note/faint/user-msg` liegen visuell fast aufeinander; Phase 2 sollte auf ~5 Stufen mit definierten Kontrastzielen reduzieren.
- **Akzent:** `#b08850` primär, `#d4a032` hell (Hover/Aktiv/Busy/Run). **`Beibehalten`** als Zweistufenlogik.
- **Status:** Erfolg `#8fa35c` (nur 1 Fundstelle!), Gefahr `#c06060`/`#c05050`; **Warnung existierte nicht** — Token `--color-state-warning` ist neu reserviert (Startwert = accent-bright). **`Prüfen`**: Phase 2 braucht eine echte Warnfarbe.
- **Drei Gold-Alpha-Familien** (Border 200,155,70 / Chrome 200,155,50 / Hover-Fokus 200,150,50): historisch gewachsene Fast-Duplikate, die vermutlich dasselbe Token sein sollten. In Phase 1 exakt erhalten und getrennt benannt. **`Vereinheitlichen`** (größter Einzelposten).
- **Alpha-Leitern:** Border-Familie mit 12 Stufen 0.03–0.35 — **`Vereinheitlichen`** auf ~5 definierte Stufen.
- **Verläufe/Glüheffekte:** 6 Orb-Radialgradienten (12 Stops, jetzt `--orb-*`), 2 Lamp-Glows (`--lamp-*`), Dot-/Auswahl-Glows (`--glow-*`). Orb-Schatten-Stacks + Keyframe-Interna bewusst literal — **`Später neu gestalten`** (Glow-System).

## 3. Typografieinventar

- **Familien:** Systemstack (`--font-family-base`), `'Segoe UI'` für Titelleisten-Chrome (`--font-family-chrome`). Kein Webfont, kein Monospace. **`Beibehalten`** (bis Phase 2 anders entscheidet); CLI bestätigte Segoe UI als gerenderte Schrift.
- **Gewichte:** 300 Grundgewicht, 400 Labels/Überschriften, 600 nur Banner-Label. **`Beibehalten`**.
- **Größen:** Skala 8/9/10/11/12/13/14/18 px (`--font-size-*`); Kern 9–11 px. Ausreißer **11.5 px (×4)** und **12.5 px (×1)** literal geblieben — **`Vereinheitlichen`** (auf 11/12 bzw. 12/13 ziehen). `font-size: 0` (Panel-Statuszeile) ist ein Verstecktrick — **`Prüfen`**.
- **Zeilenhöhen:** 1.4/1.5/1.55/1.6/1.65 als Tokens; fünf Werte für „Fließtext" — **`Vereinheitlichen`** auf 2 Rollen.
- **Laufweiten:** Rollen-Tokens 0.08 (Label) / 0.1 (Button) / 0.12 (Micro) / 0.2 (Caps-wide) / 0.28 em (Display). Sieben Kleinstwerte 0.01–0.06 + 0.14 em literal — **`Vereinheitlichen`**.
- **Hierarchie:** keine klassischen Überschriftenebenen; Hierarchie entsteht aus Laufweite × Größe × Farbstufe (h2 = 11px/0.28em/sekundär; h3 = 10px/0.28em/dim; h4 = 9px/0.2em/sekundär). **`Beibehalten`** als System, Stufen in Phase 2 formalisieren.
- **Transcript:** Du 11px/user-msg, Jarvis 13px/akzent/1.65 — bewusste Sprecher-Asymmetrie, **`Beibehalten`**.

## 4. Spacing- und Layoutsystem

- **Skala:** 2–48 px (`--space-*`, CLI-bestätigt). `gap` vollständig migriert; Einzel-`margin`/`padding` und Kompositwerte literal (dokumentierte Phase-1-Entscheidung: geringes Theming-Potenzial, hohes Editrisiko). **`Später neu gestalten`**: Phase 2 definiert ein echtes 4er-/8er-Raster.
- **Muster:** Flex-Spalten; Kontrollzentrum = 3-Spalten-Flex (Konversation 340px fix · Mitte flexibel · rechte Spalte 250px fix); Apps als 1-Spalten-Grid; Map-Zonen als 3×3-Grid; `display: contents` für layoutneutrale Wrapper (`#cc-right/#cc-shell/#cc-content`) — **`Beibehalten`** (trägt die Panel-Wiederverwendung der Aktionshistorie).
- **Feste Maße:** Win-Bar 38px, Orb 160/96/72px, Buttons 34px, Aktionsspalte 240px. Scrollbereiche: Transcript (max 240px bzw. flex), `#action-list` (`calc(100vh - 140px)` bzw. flex), Inbox 180/104px, Musikliste `calc(100vh - 340px)` — **`Prüfen`**: magische calc-Werte.
- **Overlays/fixe Elemente:** Win-Bar (`--z-titlebar`), Mute/Stop/Status-Center (`--z-chrome`), Banner-Stack (`--z-banner`), Boot-Fallback (9999 inline).
- **Breakpoints:** 1100 (Heute-Strip weg) → 960 (Map weg) → 700 (rechte Spalte/Aktionen weg) — bewusst am Dateiende, gewinnen per Reihenfolge. **`Beibehalten`**, aber Reihenfolge-Kopplung dokumentieren (§11).

## 5. Oberflächen und Effekte

- **Rahmen:** durchgehend 1px solid; Stärke-Ausnahmen nur Banner-Links-Balken (3px) und Orb-Muted-Ring (2px Shadow-Ring). **`Beibehalten`** (1px-Sprache).
- **Radien:** 3/4/5/6/7px + 50% (`--radius-*`) — fünf Stufen ohne klare Rolle. **`Vereinheitlichen`** auf 2–3 Stufen + rund.
- **Schatten/Glows:** Dot-Glows 6px, Auswahl 10px, Busy 8px, Chip-Schatten schwarz — jetzt Komposit-Tokens. Orb-Stacks literal (**`Später neu gestalten`**).
- **Transparenz:** Weiß-Alpha 0.02 als Eingabefläche; Canvas-Alpha 0.85 für Chips; 0.94 Banner. **`Beibehalten`**.
- **Raster:** Map-Bühne mit 26px-`repeating-linear-gradient`-Grid (`--color-grid-line`) — Markenzeichen, **`Beibehalten`**.
- **Trennlinien:** Divider 0.06 / Spalten 0.07 — **`Vereinheitlichen`** (ein Wert).
- **Fokusumrandungen:** ausschließlich `outline: none` + Border-Farbwechsel; kein `:focus-visible`. **`Später neu gestalten`** (A11y-Pflicht in Phase 2, bewusst NICHT in Phase 1 verändert).
- **Scrollbars:** `thin` + Token-Farbe, Webkit 2px. **`Beibehalten`**.
- **Statuspunkte:** 6px-Dots in drei Komponenten (`.sc-dot/.ae-dot/.cc-dot`) mit identischer ok/err-Semantik, aber leicht unterschiedlichen Basisdeklarationen — Werte jetzt tokenvereinheitlicht, Strukturzusammenführung **`Vereinheitlichen`** (gemeinsame `.dot`-Klasse in Phase 2).
- **Orb:** Identitätskern — Gradients tokenisiert, Zustandssemantik **`Beibehalten`**.

## 6. Motion-System

- **Transitions:** 0.15 (Ghost-Geometrie) / 0.2 (Chrome) / 0.25 (Interaktions-Standard) / 0.3 (Fades) / 0.4 (Status) / 0.5s (Orb) — als `--duration-*`; Easing implizit `ease` (Browser-Default, jetzt `--ease-standard` wo explizit). **`Vereinheitlichen`**: 0.2 vs 0.25 vs 0.3 in Phase 2 auf 2 Stufen prüfen.
- **Keyframes:** `pulse-listen` 1.8s · `pulse-think` 0.85s · `pulse-speak` 0.65s · `flash-error` 1.1s ×2 · `banner-in` 0.25s · `map-pulse` 0.6s; Aktions-Dot nutzt `pulse-listen` mit 1.2s (`--duration-pulse-run`). Frequenz-Semantik (ruhig→nervös→sprechrhythmisch) **`Beibehalten`** — Herzstück der Zustandssprache.
- **Hover:** ausschließlich Farb-/Border-/Glow-Wechsel, keine Bewegungs-Hover. **`Beibehalten`**.
- **`prefers-reduced-motion`:** deckt nur Map/Module/Tabs/Musik-Transitions + Map-Puls ab; Orb-Pulse, `flash-error`, `banner-in`, Lamp-Glows laufen weiter (Phase-0-Beleg). **`Später neu gestalten`** (Abdeckung erweitern, bestehende darf nicht schrumpfen — Invariante).

## 7. Komponentenübersicht

| Komponente | Selektoren | Zustände | Marker |
|---|---|---|---|
| Sekundär-Buttons | `.music-actions/.settings-actions button`, `.app-btn`, `#btn-copy-all` | hover, busy/ok/err (app-btn), copied | **`Vereinheitlichen`** — vier fast gleiche Basen (Unterschiede nur Textfarbe/Transition-Liste); gemeinsame Basisklasse in Phase 2 |
| Micro-Buttons | `.profile-action`, `.map-zone-full` | hover/focus, confirm (rot) | **`Vereinheitlichen`** (identische Sprache, 8px/0.12em) |
| Tabs | `.cc-tab`, `.profile-tab` | hover, active, deletable | **`Beibehalten`** — in Phase 1 zusammengeführt (waren byte-identisch) |
| Chrome-Nav | `.pn-btn`, `.wm-btn` | hover, active | **`Vereinheitlichen`** (untereinander fast identisch; nur padding/tracking differieren) |
| Icon-Buttons | `#mute-btn`, `#stop-btn` | hover, muted | **`Beibehalten`**; Basis teilbar (**`Vereinheitlichen`**) |
| Eingaben | `#transcript-search`, `#text-input`, Settings-Inputs/Textarea, `#cc-profile-input`, Radios | focus (Border+Opacity), placeholder | **`Beibehalten`**; zwei Fokusfamilien **`Vereinheitlichen`** |
| Panels/Karten | `.app-module`, `.map-monitor`, `.error-banner`, `#settings-card/#music-card` | hover, focus, selected, off, unassignable | **`Beibehalten`** |
| Statusanzeigen | Status-Center, `#cc-sys-list`, `#cc-map-status`, `#music-msg`, `#settings-msg`, `#cc-app-msg` | ok/off/err/warn | **`Beibehalten`**; Meldungszeilen-Muster **`Vereinheitlichen`** |
| Badges | `.app-module-type` (App/URL) | — | **`Beibehalten`** |
| Toggle | `.app-toggle` (+track/knob) | on, disabled/busy, hover | **`Beibehalten`** |
| Monitor-Map | `.map-canvas/-monitor/-grid/-zone/-ghost/-chips` | assigning, saving, pulse, focus, hover-ghost, selected-chip, unassignable | **`Beibehalten`** — komplexeste Eigenkomponente |
| Transcript | `.msg.user/.jarvis`, `.msg-copy` | hover (Copy sichtbar), copied | **`Beibehalten`**; Copy-Entdeckbarkeit **`Später neu gestalten`** (§10) |
| Aktionshistorie | `.ae` + Dot/Time/Label/Detail | run/ok/err | **`Beibehalten`** |
| Leere Zustände | `.cc-empty`, `#music-status:empty` | — | **`Beibehalten`** |
| Fehler/Erfolg | `.error-banner` (+label/hint/close), `#settings-msg.ok/.error` | persistent vs. 10s | **`Beibehalten`** |

## 8. Responsive Modi

Vollbild (Orb 160px, zentriert) · Fokus „Mitte" (2-Spalten Jarvis bzw. Kontrollzentrum-Shell) · Panel „Klein" 420×560 (Mini-Orb 72px, Panel-Antwort, Mini-Historie, gedämpfte Lamp-Glows) — Root-Klassen-Kontrakt (`rootClass()`, main.js) **`Beibehalten`** (Invariante). Degradation 1100/960/700px s. §4. Bekannter Platz-Bug: Aktionen-Liste kollabiert bei 1000×800 im Kontrollzentrum auf 0 Höhe (Phase-0-Beleg) — **`Später neu gestalten`** (Layout-Priorisierung), in Phase 1 unverändert.

## 9. UI-Zustände

Orb: idle/listening/thinking/speaking/muted/error (Klassen auf `#orb`, Gradients tokenisiert). Interaktion: hover/active/selected/focus/disabled(busy)/deletable/confirm/saving/pulse/assigning/off/unassignable/copied/err/ok/run/warn. Verbindungszustände: Getrennt-Status, Reconnect-Text, ws-Banner ab 3. Versuch. Leere/Lade-Zustände: `cc-empty`, „Lade Monitore…", „Daten laden…". Vollständige visuelle Belege: Phase-0-Screenshots + `verification/`.

## 10. Accessibility-relevante Eigenschaften

**Vorhanden (Beibehalten):** `aria-live` auf allen Statusflächen, `role=tablist/tab/tabpanel/group/switch/button`, `aria-pressed/-selected/-checked/-label`, `lang="de"`, Escape-Capture-Logik, Enter/Space-Aktivierung, PTT, Boot-Fallback.
**Defizite (Später neu gestalten — bewusst nicht in Phase 1 angefasst, da sichtbar):**
- Kein `:focus-visible`, `outline: none` überall → Tastaturfokus praktisch unsichtbar (Phase-0-Beleg: Fokus auf `#mute-btn` nicht erkennbar).
- Sehr niedrige Kontraste der unteren Braunstufen (Timestamps/Platzhalter/inaktive Chrome-Buttons) — mit Token-Ebene jetzt zentral korrigierbar; WCAG-Messung als Phase-2-Eingang.
- `.msg-copy` nur per Maus-Hover entdeckbar (`visibility: hidden`) — Tastatur/Touch ausgeschlossen.
- `prefers-reduced-motion`-Lücken (§6).
- Status-Text-Leiche „JARVIS DENKT NACH…" im No-Audio-Pfad + ewiger `#sc-error` (JS-Verhalten, nicht CSS — Phase-2/3-Fix, **`Prüfen`**).

## 11. Inkonsistenzen und Designschulden (Detail)

1. **Drei Gold-Alpha-Familien** (s. §2) — **`Vereinheitlichen`**, größter Posten.
2. **Zehn Braun-Textstufen** — **`Vereinheitlichen`** auf ~5 mit Kontrastzielen.
3. **12-stufige Border-Alpha-Leiter** — **`Vereinheitlichen`** auf ~5.
4. **Fünf Radien, fünf Zeilenhöhen, 12 Laufweiten, 8+2 Fontgrößen** — **`Vereinheitlichen`** (11.5/12.5px!).
5. **Vier Sekundär-Button-Implementierungen + zwei Chrome-Button-Basen + zwei Micro-Button-Basen + drei Dot-Basen** — **`Vereinheitlichen`** (Phase 1 hat nur die byte-identischen Tabs zusammengeführt).
6. **Reihenfolge-gekoppelte Regeln:** Kommentar in style.css benennt es selbst — Kontrollzentrum-Block „bewusst am Dateiende: die Media-Queries am Schluss müssen die Fokus-Regeln überschreiben" (gleiche Spezifität, letzte gewinnt); ebenso `.profile-tab.deletable` nach `.active`. **`Beibehalten` + dokumentiert** — bei Phase-2-Umbau in Layer/Spezifität überführen.
7. **Doppelte `.app-module`-Definition** (Basis oben, `cursor/transition`-Nachtrag ~40 Zeilen tiefer) — funktioniert nur durch Kaskade. **`Vereinheitlichen`**.
8. **Totes CSS:** `#btn-settings`-Regeln (Element existiert laut Test-Guard nicht mehr: `test_settings_gear_removed_from_title_bar`) — **`Entfernungskandidat`** (in Phase 1 belassen, Nachweis: Guard + grep über index.html/JS ohne Treffer).
9. **JS-gesetzte visuelle Eigenschaften:** nur Map-Geometrie (Layout-Prozentwerte) + `opacity='0'` der Copy-Fallback-Textarea — unkritisch, **`Beibehalten`**.
10. **Magische calc-Höhen** (140/340px-Offsets) — **`Prüfen`**.
11. **Kein `!important`** im gesamten CSS — **`Beibehalten`** (bemerkenswert sauber).
12. **Z-Index undokumentiert** (999/1000/1100 + Boot 9999) — jetzt Tokens + dokumentiert.
13. **Erfolgsgrün nur 1 Fundstelle, keine Warnfarbe** — Status-Palette unterentwickelt, **`Später neu gestalten`**.

## 12. Bestandteile, die bewahrt werden sollten

Amber-Monochrom-Identität · Orb-Zustandssprache inkl. Pulsfrequenz-Semantik · Lamp-Glow-Atmosphäre · Uppercase-Mikrotypografie als Markenzeichen · Dot+Glow-Feedbacksprache · Map-Grid-Bühne · 1px-Border-Sprache · Panel-Modus-Verdichtung · `display: contents`-Wrapper-Trick · Null-`!important`-Disziplin · alle funktionalen Invarianten aus `docs/design-baseline/BASELINE.md` §8.

## 13. Bestandteile, die Phase 2 neu entscheiden muss

1. Konsolidierte Farbleitern (eine Gold-Alpha-Familie, ~5 Braunstufen, ~5 Border-Alphas) mit WCAG-Kontrastzielen je Textstufe.
2. Echte Status-Palette (Warnung!, Erfolg sichtbarer) + Fokus-Sichtbarkeit (`:focus-visible`-System).
3. Glow-/Schatten-System für Orb + Komponenten (heute literal-Stacks).
4. Radius-/Größen-/Zeilenhöhen-/Laufweiten-Stufen (je 2–3 statt 5–12).
5. Button-/Dot-/Meldungszeilen-Basisklassen (HTML-Änderungen erlaubt).
6. Spacing-Raster + Layout-Priorisierung (Aktionen-Kollaps bei 800px Höhe).
7. `prefers-reduced-motion`-Vollabdeckung; Motion-Stufen 2 statt 3.
8. Copy-Button-Entdeckbarkeit (Tastatur/Touch).
9. Umgang mit totem `#btn-settings`-CSS und den magischen calc-Werten.
10. Tray-Farben in `jarvis-launcher.pyw` bei Palettenwechsel nachziehen.

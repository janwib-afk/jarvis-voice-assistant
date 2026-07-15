# Phase 7 — Final Findings (Web Interface Guidelines Re-Audit)

- **Re-Audit-Datum:** 2026-07-13
- **Guidelines-Quelle:** `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md` (identisch zum Initial-Audit; Skill `web-design-guidelines` v1.0.0)
- **Basis:** [INITIAL_FINDINGS.md](INITIAL_FINDINGS.md) (0×P0 · 0×P1 · 4×P2 · 10×P3) + zwei in Teil 2–12 neu gefundene Punkte (Heading-Sprung, Fokus-Ring-Unterdrückung).
- **Ergebnis:** **kein offenes P0/P1.** Alle P2 behoben; risikoarme P3 behoben; Rest-P3 begründet offen.

## Status je Befund

| # | Schweregrad | Befund | Status | Korrektur / Begründung |
|---|---|---|---|---|
| 1 | P2 | `color-scheme: dark` fehlt | **behoben** | `color-scheme: dark` in `index.html` (Boot-`<style>`, vor externer CSS) + `design-tokens.css` `:root`; `<meta name="theme-color">` ergänzt. Browser: `html`/native `<select>` `colorScheme = dark`. |
| 2 | P2 | Orb-Beschnitt „Mitte"/Zoom | **behoben (Kernfall)** | Neuer `@media (max-height: 860px)`-Tier verkleinert den Basis-Orb auf 132px → Mitte 1000×800: `orb_top` 10→**45** (klar über 38px-Titelleiste), Eingabe frei, Vollbild (196px) unverändert. `@media (max-height: 650px)` verkleinert weiter auf 96px. Rest siehe P3-#10. |
| 3 | P2 | Glyph-Buttons ohne `aria-label` | **behoben** | `aria-label` an `#btn-min` („Minimieren"), `#btn-close` („Fenster ausblenden"), `.eb-close` („Meldung schließen"); `type="button"` ergänzt. Browser bestätigt. |
| 4 | P2 | Settings-Form ohne `autocomplete`/`spellcheck` | **behoben** | `#settings-form autocomplete="off" spellcheck="false"` (kaskadiert auf alle Felder). |
| 5 | P2 | **Heading-Sprung h1→h3** (neu, Teil 2–12) | **behoben** | sr-only `<h2 id="cc-today-heading">Heute</h2>` als Elternebene der Heute-h3. Browser-Heading-Walk jetzt monoton: H1→H2 Heute→H3×3→H2 Apps/Aktionen/System. |
| 6 | P3 | Banner `aria-live=polite` statt assertiv | **behoben** | Jeder Banner ist eigene Live-Region: `role="alert"` (echte Störung, assertiv) / `role="status"` (Warnung, höflich); Container-`aria-live` entfernt (kein Doppel). Browser bestätigt. |
| 7 | P3 | Fokus-Ring unterdrückt (neu, Teil 2–12) | **behoben** | `outline: none` aus `.app-module`/`.map-zone`/`.map-zone-full`/`.profile-action` `:focus` entfernt → globaler `:focus-visible`-Messing-Ring erscheint bei Tastaturfokus (Browser: alle geprüften Typen `ring=true`). Inputs behalten Rahmen+Halo (konventionell). |
| 8 | P3 | Ladezustand/Placeholder ohne `…` | **behoben** | Boot „J.A.R.V.I.S. lädt…"; Placeholder „Nachricht an Jarvis…". |
| 9 | P3 | DESIGN.md §-Wortlaut vs. Lünetten-Sweep | **behoben** | §Orb-Zustände + §Do/Don't um die dokumentierte Phase-5-Ausnahme (Sweep nur bei `action-running`) ergänzt. |
| 10 | P3 | Orb-Rest bei sehr niedriger Höhe (<~600px) | **offen (bewusst)** | Nur bei 200 % Zoom des ohnehin kleinen Fensters — **kein realer Desktop-Fensterpfad** (echte Modi: Vollbild/Mitte/Klein alle frei). Orb ist `aria-hidden` (kein Infoverlust), Statuswort/Eingabe-Kern/Stop+Mute bleiben sichtbar. Sauberer Fix = scrollbares Basis-Layout (Regressionsrisiko am Release, verworfen). Empfehlung Folgeversion: `$impeccable layout`. |
| 11 | P3 | Fehlermeldung doppelt (Banner + `#sc-error`) | **offen (bewusst)** | `#sc-error` ist der **persistente** Fußleisten-Detailort (Banner transient/oben, sc-error unten — räumlich getrennt); in Phase 6 bewusst als einziger Detailort behalten. Neukoordination riskiert Fehler-Sichtbarkeit > P3-Nutzen. |
| 12 | P3 | Map-Labels in schmaler Bucht abgeschnitten | **offen (bewusst)** | Dokumentierter Tradeoff; Weg B (Selects „Monitor/Zone/Position speichern") bleibt vollständig lesbar/bedienbar (SR-Primärroute). |
| 13 | P3 | 9px Overflow @375px | **offen (bewusst)** | Unter dem schmalsten realen Fenstermodus (Panel 420px, kbd-hint dort ausgeblendet → 0 Overflow). Overflow-Sweep 1920→430px = 0. |
| 14 | P3 | Font-`preload` | **offen (bewusst)** | Marginal: Fonts lokal, `font-display: swap`, kein FOUT-Problem gemessen. |

## Nicht-Befunde (im Re-Audit bestätigt)

- **Sicherheit/Datenschutz:** GET /settings (Laufzeit, HTTP 200) liefert nur `UI_EDITABLE_KEYS` (apps, city, elevenlabs_voice_id, launcher, music_*, obsidian_*, user_*); `body_contains_api_key: false`, keine Leak-Verdachtsfelder. Keys strukturell ausgeschlossen (`_public_settings`/`PROTECTED_KEYS`).
- **Native `<select>` (Monitor/Zone):** korrekt per `<label htmlFor>` benannt (kein Label-Befund) + jetzt dark via `color-scheme`.
- **Overflow:** 0 über 1920/1600/1366/1024/900/768/600/430; **Konsole/404/externe Hosts: 0/0/0.**

## Nachtrag — unabhängiger Review (Teil 19)

Frischer general-purpose-Subagent (kein Gesprächskontext) hat Frontend, Design-/UX-Doku, Auditdocs und Screenshots geprüft und zentrale Behauptungen im Code gegengeprüft (Kontrastmathematik, Testzahl, Phase-7-Guards, Sicherheitslogik). **Urteil: Freigabeempfehlung gerechtfertigt, kein P0/P1.** Fünf zusätzliche P3:

| ID | Status | Punkt | Handhabung |
|---|---|---|---|
| F1 | **behoben** | Zwei `<h1>` dauerhaft im A11y-Baum (Doku überzeichnete „monoton") | `html.page-jarvis #control-heading` / `html.page-control #jarvis-heading { display:none }` → Browser: genau 1 h1 je Seite; EVIDENCE korrigiert; Guard ergänzt. |
| F2 | offen (P3) | ARIA-Tab-Muster unvollständig (`role=tab` ohne `aria-controls`, Übersicht ohne `role=tabpanel`, keine Pfeiltasten) | Backlog — funktional bedienbar; siehe OPEN_ITEMS. |
| F3 | offen (P3) | `#cc-map-stage` ohne `role="group"`/beschreibendes `aria-label` (Abweichung von eigener ACCESSIBILITY_SPEC §4) | Backlog. |
| F4 | offen (P3) | `#sc-error` räumt transiente Warnung/Fehler nicht ab (+ Doppelung mit Banner) | Deckt sich mit offenem P3 #11; Backlog. |
| F5 | offen (P3) | Orb-Freiheit „Mitte" nur ~7px über Titelleiste | kosmetisch; Folgeversion `align-items: safe center`. |

## Zusammenfassung

Ausgangs 0×P0 · 0×P1 · 4×P2 · 10×P3 → plus 2 in Tiefenprüfung + 5 im Review gefunden: **10 behoben** (5×P2 + 5×P3), **7×P3 bewusst offen** (dokumentiert, keiner release-blockierend). **Kein offenes P0/P1.** Suite 478→**484** (+6 additive Guards), verify_phase4 27/27, verify_phase5 13/13, alles Exit 0.

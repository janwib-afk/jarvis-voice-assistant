# Impeccable critique — Jarvis Frontend (Phase 6, 2026-07-12)

⚠️ DEGRADED: single-context (sub-agent spawn failed: session limit — zwei Spawn-Versuche für A/B durch API-Limit abgebrochen; sequentieller Fallback gemäß reference/critique.md, Assessment B strikt vor A getrennt erhoben)

Method: single-context sequential (B: Detector+Playwright-Messungen · A: Design-Review) · Target: `frontend/index.html` @ http://127.0.0.1:8341 · Register: product · Ignore-Liste: nicht vorhanden.

## Design Health Score

| # | Heuristik | Score | Kernbefund |
|---|---|---|---|
| 1 | Sichtbarkeit Systemstatus | 4 | Zustandswort + Dot + Klartext-Fußleiste + laufende Aktion — vorbildlich |
| 2 | System ↔ Realwelt | 4 | Deutsch, aktiv, Instrumenten-Metapher konsequent |
| 3 | Kontrolle & Freiheit | 3 | Stop/Esc überall; kein Undo (Profil-Löschen nur Confirm) |
| 4 | Konsistenz & Standards | 3 | Token-System stark; Banner-Stripe + Fußleisten-Redundanz fallen heraus |
| 5 | Fehlervermeidung | 3 | Confirms, Diff-Save, Allowlist; Apps-Textarea bleibt Experten-Kante |
| 6 | Wiedererkennen statt Erinnern | 3 | kbd-Hint sichtbar; PTT-Modus nur in Settings entdeckbar |
| 7 | Flexibilität & Effizienz | 3 | Esc/Strg+Enter/Space-PTT; kein Seitenwechsel-Shortcut |
| 8 | Ästhetik & Minimalismus | 3 | ruhig; Vollbild-Leere unter dem Journal + doppeltes Zustandswort |
| 9 | Fehler-Erholung | 3 | Banner mit Ursache+Abhilfe; llm-Fehlertext generisch |
| 10 | Hilfe & Doku | 2 | nur Inline-Hints; keine Hilfe-Fläche (bewusst schlank) |
| **Summe** | | **31/40** | **Good — solide Basis, gezielte Schwächen** |

**Cognitive Load:** 1 Fail von 8 (KZ-Übersicht zeigt 6 Informationsblöcke gleichzeitig; durch Spaltenhierarchie + progressive Selects abgefedert) → niedrig.

## Anti-Patterns-Verdikt

**LLM:** Kein AI-Slop-Gesamteindruck — Lünetten-Signature, Drei-Stimmen-Typografie und Klartext-Vokabular sind eigenständig; ein Linear/Raycast-fluenter Nutzer würde dem Interface vertrauen. Zwei Muster fallen dennoch als „Tell" auf: die 3px-Statuskante der Banner (Side-Stripe) und die Zustandswort-Dopplung in der Fußleiste.
**Detector (deterministic, Exit 2, 5 Findings):** side-tab ×2 (style.css:645+2577, Banner-`border-left:3px`) · layout-transition ×1 (style.css:1791, Map-Ghost-Geometrie) · overused-font ×2 (Fraunces in design-tokens.css:19/27). **False-Positive-Einordnung:** Ghost = dokumentierte Ausnahme (kleines Preview-Element, 150ms, hover-only); Fraunces = festgeschriebene Phase-2-Identität als *Stimme* (nicht Display-Deko) — Identity-Preservation gemäß SKILL.md; Side-Stripe = berechtigter Treffer → Umbau.
**Overlay:** übersprungen — live-server.mjs per Projekt-Sicherheitsrichtlinie ausgeschlossen; Fallback-Signal = eigene Playwright-Messungen (Kontrast/Fokus/Overflow/Konsole/Netz, s. u.).

**Messwerte (Assessment B):** Fonts geladen 3/3 · Konsole 0 · externe Hosts 0 · 404 0 · H-Overflow 0px @1920/1000/420/760 · Stop-Fokusring 2px · Kontraste: status 7.7 ✓ · **kbd-hint 2.91 ✗** · ask-hint 4.03 · sc-conn-text 4.03 · msg-time 3.73.

## Stärken
1. **Statuskommunikation** — Zustand ist gleichzeitig Wort, Farbe, Dot und Instrumentenlicht; disconnected/degraded erklären sich selbst.
2. **Eigenständige Identität** — Lünette + Serifen-Stimme + Espresso/Pergament wirken warm-präzise statt generisch; auch ohne Orb erkennbar (Journal, Buchten, Mono-Meta).
3. **A11y-Fundament** — Skip-Link, sichtbare Messing-Ringe, Live-Regionen, Weg B der Monitor-Zuweisung.

## Priority Issues

| P | Ansicht/Element | Problem | Auswirkung | Fix | Dateien | Verifikation |
|---|---|---|---|---|---|---|
| P1 | Vollbild · Journal | `#transcript` max-height 300px → große tote Fläche unter der Eingabe bei 1080p; Gespräch (Kernaufgabe) wirkt gestaucht | Hierarchie kippt: Leere dominiert das Wichtigste | max-height viewport-relativ (`min(46vh, 520px)`) | style.css | Screens 1080p vorher/nachher |
| P1 | Fußleiste · `#kbd-hint` | Kontrast 2.91:1 (< 3:1) | Hinweis für Tastatur-/Sprachwege faktisch unlesbar für Sehschwächere | Farbe auf `--color-text-muted` + muted global leicht anheben | style.css, design-tokens.css | Messung ≥4.0 |
| P2 | Banner | Side-Stripe (`border-left:3px`) — Detector-Ban, wirkt als AI-Tell | Konsistenz/Charakter | volle 1px-Statusborder + farbiger Titel (Familie bleibt) | style.css ×2 Stellen | Detector side-tab = 0 |
| P2 | Fußleiste · `#sc-state` | Zustandswort doppelt zur Statuszeile (bei „Getrennt" sogar dreifach mit sc-conn-text) | Rauschen, verletzt „ein Schwerpunkt" | sc-state entfernen; Zustand lebt in Statuszeile, Verbindung in sc-conn-text | index.html, main.js, style.css | Sichtprüfung + Suite |
| P2 | Mono-Nebeninfos | msg-time 3.73 · ask-hint/sc-text 4.03 | sekundär, aber unter Komfortziel ≥4/4.5 | `--color-text-muted` #817363→#8b7d6c (+ dim folgt) | design-tokens.css | Messreihe ≥4.0/4.4 |
| P2 | Orb | klickbar (Zuhören-Toggle) ohne Press-Feedback und ohne Title | versteckte Interaktion (Auftrag „Bedienbarkeit") | `:active`-press-soft am Container + `title` am Orb; (Tastatur-Alternative existiert: Mute) | style.css, index.html | Sichtprüfung |
| P3 | Fraunces-Detector-Flag · Ghost-Transition · fehlender Seitenwechsel-Shortcut | dokumentierte Entscheidungen bzw. nice-to-have | — | bewusst offen (Begründungen oben/PASS_LOG) | — | — |

## Persona-Red-Flags
**Alex (Power-User):** Kernpfad <10s ✓ (sprechen/Strg+Enter); Esc universell ✓. Flag: kein Tastatur-Shortcut für Jarvis⇄Kontrollzentrum (P3, Tab-Weg kurz). **Sam (A11y):** Fokusringe/Skip-Link/Live-Regionen ✓; Flags: kbd-hint-Kontrast (P1, s. o.), Orb nicht fokussierbar (funktionale Alternative vorhanden → P3), `#status-action` lang bei langen Details (trunkiert nicht — Minor).

## Minor Observations
Musik-„Neu laden"-Button gleichgewichtig zu „Auswahl entfernen" (quieter-Kandidat: quiet-Stufe) · `#sc-error` kann mit Statuszeile konkurrieren, wenn Warnung dauerhaft (belassen: einziger Fehlerdetail-Ort) · Panel-Mini-Aktionszeilen berühren fast die Fußleiste (Padding-Feinschliff).

## Fragen
1. Verdient der leere Vollbild-Raum unter dem Journal eine Funktion (z. B. Quellen-Ablage) — oder ist mehr Journal die ehrlichere Antwort? (→ mehr Journal.)
2. Braucht ein Ein-Nutzer-Instrument eine Hilfe-Fläche, oder ist die Fußleisten-Hint-Zeile das richtige Maß? (→ Hint-Zeile, lesbar gemacht.)
3. Was wäre der EINE Delight-Moment, der täglich trägt? (→ das Erwachen des Instruments beim Verbinden.)

## Run Notes
Slug/Persistenz: via critique-storage (s. Anhang PASS_LOG) · Ignore-Liste: keine · Unabhängigkeit: B (Messungen/Detector) vollständig VOR A-Synthese erhoben, keine Vermischung roher B-Daten in A-Urteilsbildung · Detector: gelaufen (Exit 2, 5 Findings) · Browser-Sichtbarkeit: headless Playwright · Overlay: übersprungen (Sicherheitsrichtlinie, Fallback dokumentiert) · Live-Server: nicht gestartet · Temp-Dateien: bereinigt.

**Fragen an den Nutzer übersprungen:** Scope wurde im Phase-6-Auftrag vorab festgelegt (P0→P1 fix, P2 bei klarem Gewinn, P3 nur ohne Übergestaltung; Reihenfolge typeset→colorize→quieter→delight→polish→audit).

# Jarvis Motion-System (Phase 5, 2026-07-12)

**These:** Jarvis bewegt sich wie ein präzises analoges Instrument mit digitaler Intelligenz — ruhig im Normalzustand, unmittelbar bei Eingaben, ausdrucksstark nur in besonderen Momenten. Erarbeitet mit `emil-design-eng`; validiert via [tools/verify_phase5.py](tools/verify_phase5.py) (13/13) + [evidence/](evidence/).

## 1–2 · Prinzipien

1. **Bewegung erklärt Zustand** — jede Animation beantwortet „was tut Jarvis gerade?"; Deko ohne Antwort fliegt.
2. **Der Orb ist der einzige Dauer-Schwerpunkt** — pro Ansicht atmet genau ein Element; Listen, Panels, Chrome bleiben still.
3. **Eingaben antworten sofort** — Press-Feedback startet ohne Verzögerung (scale 0.97, Release 140ms); Tastatur-Aktionen (Esc, Strg+Enter, Tab, Suche) animieren **nie**.
4. **Licht endet stabil** — Fehlerimpuls = 2 Pulse, dann statisch; Erfolg/Save enden in Ruhelage; kein Endlos-Blinken.
5. **Wechsel ersetzen, nie stapeln** — Klassentausch tötet den alten Loop im selben Frame (verifiziert); Enter-only-Übergänge, Exit sofort.
6. **Nur transform & opacity** — Glow lebt auf `#orb::after`; box-shadow wird nie animiert; Ausnahme dokumentiert: Ghost-Geometrie (kleines Element, Zonenraster) und Toggle-Knob-`left` (12px).
7. **Reduced Motion ist gleichwertig** — Zustands-Glow bleibt als statisches Licht, Worte/Farben tragen; Bewegung entfällt gezielt, nicht global.
8. **Ambient heißt unaufdringlich** — Frequenzen tragen Semantik (ruhig→wach→konzentriert→sprechend), Amplituden bleiben ≤4.5 %.

## 3–5 · Tokens

| Dauer | Wert | Einsatz |
|---|---|---|
| `--motion-duration-instant` | 100ms | reserviert (sofortiges Feedback) |
| `--motion-duration-fast` | 140ms | Press-Release, Pill/Hinweis-Enter |
| `--motion-duration-standard` | 200ms | Farb-Fades, Banner-Enter, Orb-Übergang |
| `--motion-duration-emphasized` | 260ms | Statusfarbwechsel |
| `--motion-duration-view` | 240ms | Ansichts-Enter |
| `--motion-duration-ambient-idle/-listen/-think/-speak/-run` | 6 / 2.6 / 1.15 / 0.7 / 3.6 s | Orb-Loops + Lünetten-Sweep |

Easing: `--motion-ease-enter/-exit` = `cubic-bezier(0.23,1,0.32,1)` (starkes ease-out) · `-emphasized` = `cubic-bezier(0.77,0,0.175,1)` · `-mechanical` = `cubic-bezier(0.3,0,0,1)` · `-ambient` = ease-in-out (Atmen) · `-standard` = ease (Hover). **ease-in ist verboten.** Distanz/Scale: `--motion-distance-small` 4px · `-medium` 8px · `--motion-scale-press` 0.97 · `-press-soft` 0.985. Alt-Tokens (`--duration-*`) sind auf diese Skala gemappt.

## 6 · Orb-Zustände

| Zustand | Kern (transform) | Glow (`::after`, opacity) | Charakter |
|---|---|---|---|
| idle | `orb-breathe` 6s, scale ≤1.012 | aus | kaum wahrnehmbares Atmen |
| listening | `orb-listen` 2.6s, ≤1.03 | `glow-breathe` .45↔.75 | wache Präsenz |
| thinking / action-running | `orb-think` 1.15s, ≤1.015 | `glow-focus` .55↔.9 | konzentriertes Innenlicht |
| action-running zusätzlich | Lünette: `sweep` 3.6s **linear** (konisches Highlight auf der Skala) | — | laufende Tätigkeit, Fortschrittscharakter am Instrument |
| speaking | `orb-speak` .7s, ≤1.045 | `glow-pulse` .5↔.95 | Sprechimpulse, klar ≠ listening |
| stopping/Wechsel | Transition `background 200ms`, Glow 160ms exit | — | sofort sichtbares Abklingen |
| muted | statisch (Ziegelring) | aus | gedämpft, kein Fehler |
| degraded | Kontextzustand statisch + Ember-Banner | Kontext | zurückhaltend |
| error | `flash-error` 1.05-scale ×2 → statisch | statisch .8 | kontrollierter Impuls, Meldung lesbar |
| confirmation-required | keine Orb-Änderung; Ziegel-Kontur am Element (Fokus dort) | — | gezielte, nicht alarmierende Aufmerksamkeit |

Regeln: Klassentausch ersetzt sofort (kein Doppel-Loop, verifiziert); Zustand bleibt ohne Animation verständlich (Wort + Farbe + Dot); keine Frequenz im photosensitiven Risikobereich (max ~1.4Hz beim Sprechen).

## 7 · Seiten-/Ansichtswechsel

Enter-only: Zielbereich (`#main-col` bzw. `#cc-shell`-Kinder) fährt 4px/Fade in 240ms ease-enter ein; Exit = sofort (display). Auslöser nur Maus-/Klickpfad (`playViewEnter()` in den Nav-Handlern); Fokus wird unabhängig davon gesetzt (nie animiert). Re-Trigger bei schnellem Wechsel startet sauber neu (offsetWidth-Reset), `animationend` räumt auf. Fenstermodi (Vollbild/Mitte/Klein): native Größe bewusst **nicht** animiert.

## 8 · Komponentenfeedback

Alle Pressables (Buttons, Tabs, Icon-Buttons, Musik-Zeilen, Chips, Zonen-Buttons, Schalter): `transition: transform 140ms ease-exit + Farb-Kanäle`; `:active` scale 0.97 (Flächen 0.985); `:disabled:active` ohne Press. Hover bleibt reiner Farbwechsel (kein Bewegungs-Hover → kein `(hover:hover)`-Gate nötig; Regel dokumentiert für künftige Bewegungs-Hovers). Fokusringe erscheinen instant. Erfolg („Kopiert"/„Gespeichert ✓"/ok-Klassen) = Farbwechsel, endet stabil.

## 9 · Dynamische Inhalte

Neue Nachricht: **nur** der neue Eintrag (`.msg-new`, 180ms, 4px) — Such-Rerender animiert nichts; Bestandsnachrichten bewegen sich nie; Auto-Scroll-Regel unangetastet (Pill statt Zurückziehen, Pill-Enter 140ms). Kein Stagger im Transcript (Inhalte sind Gespräch, keine Show). Kopierfeedback 1s Farbwechsel, nicht blockierend.

## 10 · Kontrollzentrum & Map

Auswahl = Kantenwechsel (Farbe, 180ms); Zuweisung bestätigt einmalig via `map-pulse` (0.6s, endet stabil); Ghost erscheint mit Exit-Kurve, Geometrie folgt dem Raster (bewusste Layout-Ausnahme, kleines Element); `run`-Dot pulsiert nur solange die Aktion läuft (`run-dot`, opacity-only); System-/Ok-Dots statisch (Licht = Aktivität). Keine konkurrierenden Dauerimpulse.

## 11 · Formulare

Fokus/Validierung/Fehler: reine Farb-/Kantenwechsel, reservierte Meldeplätze (kein Layout-Sprung, kein Shake); dirty-Pill & Confirm-Zeile faden 140ms ein; Fehlermeldungen bleiben stehen; Erfolg bleibt bis zum Kontextwechsel sichtbar.

## 12 · Reduced Motion (gleichwertig)

Gezielter Block (kein globales `*`): Orb-Loops, Sweep, Run-Dot, Map-Puls, Banner-Einflug, Enter-Fades, Press-Movement → aus; **Zustands-Glow bleibt statisch (opacity .7)**, alle Farben/Worte/Dots unverändert; Ghost nur noch Opacity; Übergänge 120ms. Verifiziert: 0 laufende Animationen in allen Zuständen, Funktionen identisch.

## 13 · Performance

Nur transform/opacity in allen neuen Keyframes; Glow-Layer statt Shadow-Repaint; keine Blur-Animationen; keine CSS-Var-Animationen; WAAPI nur für den Banner-Exit (120ms, Feature-Check + Fallback); JS beschränkt auf Klassen-Toggles + `animationend`; keine neuen Timer.

## 14 · Do / Don't

**Do:** Licht pulsieren lassen, wenn Jarvis etwas TUT · Wechsel unter 260ms · ein Impuls pro Ereignis · Instrument (Lünette) als Träger besonderer Momente.
**Don't:** box-shadow/width/top animieren · ease-in · Endlos-Warnblinken · Stagger im Gespräch · Animation auf Esc/Enter/Fokus · zweiter Dauer-Schwerpunkt neben dem Orb.

## 15 · Implementierungsdetails

Zustands-Loops als Keyframes (Ambient, per Klassentausch ersetzt), Einmal-Effekte als Transitions/Enter-Keyframes mit `animationend`-Cleanup; `--orb-glow-color` pro Zustandsklasse; Sweep maskiert auf den Lünettenring (`mask: radial-gradient`), rotiert per transform; `playViewEnter()`/`.msg-new`/`action-running`-Klasse/`removeBanner()` sind die einzigen JS-Berührungen. Tests: `tests/test_frontend.py::MotionTests` (Guards) + `docs/motion/tools/verify_phase5.py` (Verhalten).

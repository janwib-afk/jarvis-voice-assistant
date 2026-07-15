# Accessibility-Spezifikation (Phase 3)

Basis: Skill-§1 (CRITICAL) + WCAG 2.1 AA. Kontrastwerte: Phase-2-Messung (DESIGN §5, 0 Fails; offener Punkt error-brick-Fließtext → nur Titel/Kanten).

## 1. Semantik & Landmarken

- `header` (Titelleiste) · `nav aria-label="Bereiche"` · `main` (Bereichsinhalt; genau eines sichtbar) · `footer` (Gerätefußleiste) · KZ-Spalten als `section aria-labelledby` (Gespräch/Werkbank/Module).
- Überschriften: h1 = Bereich (visuell dezent erlaubt), h2 = Blöcke (Gespräch, Apps, Aktionen, System, Einstellungen, Musik), h3 = Gruppen (Settings-Gruppen, Heute-Blöcke). Keine Sprünge (`heading-hierarchy`).
- Buttons für Aktionen, Links NUR für echte Ziele (Quellen, „Ordner festlegen"-Verweis) (`Buttons vs. Links`).
- Accessible Names: sprechend + konsistent („Wiedergabe stoppen", „Mikrofon stummschalten", „Antwort kopieren", „Monitor links, Zone Mitte — belegt: Obsidian"); Fensterknöpfe `aria-label` („Minimieren", „Schließen").
- Native Controls bevorzugt: `button`, `input`, `select` (Positions-Selects!), `fieldset/legend` (Mikrofonmodus, Settings-Gruppen), Switch = `button[role=switch]` (bestehend, bleibt).

## 2. Fokus

- `:focus-visible` global sichtbar (2px Messing, Offset 2, dazu Halo bei Feldern) — niemals `outline:none` ohne Ersatz (`focus-states`).
- **Skip-Link** als erstes fokussierbares Element: „Zum Gespräch springen" (Panel: „Zur Eingabe") (`skip-links`).
- Fokusreihenfolge (= visuelle Ordnung): Skip → Nav (Gespräch, Kontrollzentrum) → Modus (Vollbild, Mitte, Klein) → Fensterknöpfe → Bereichsinhalt (Jarvis: Orb → Suche → Alles kopieren → Copy-Buttons im Fluss → Eingabe; KZ: Subnav → Profile(+Aktionen) → Bucht-Zonen → Heute-Links → Apps(Modul→Öffnen→Schalter→Selects) → Aktionen → System) → Fußleiste (Stop → Mute).
- Nach Bereichswechsel: Fokus auf Bereichsüberschrift `tabindex="-1"` (`focus-on-route-change`); nach Settings-Fehler: erstes invalides Feld (`focus-management`); nach Inline-Abbruch (Esc): zurück zum auslösenden Button.
- Keine Fokusfallen; Banner stehlen keinen Fokus; ×-Schließen ist fokussierbar.

## 3. Tastatur (vollständige Karte)

| Taste | Kontext | Wirkung |
|---|---|---|
| Tab/Shift+Tab | überall | Reihenfolge §2 |
| Enter/Space | Buttons/Tabs/Zonen/Schalter | auslösen |
| Strg+Enter | Textfeld | senden |
| Esc | Kaskade | 1) Inline-Edit/Bestätigung/App-Auswahl abbrechen 2) Stop (Audio+Aktion) |
| Space (halten) | außerhalb Feldern, PTT-Modus | sprechen |
| Enter / Esc | Inline-Profil-Eingabe | bestätigen / abbrechen |
| Pfeile | native Selects/Radios | Systemverhalten |

Drag&Drop (Map) hat Tastatur-Äquivalent: Zonen-Buttons + Selects (`keyboard-shortcuts`).

## 4. Screenreader & Live-Regionen

| Inhalt | Technik |
|---|---|
| Jarvis-Antworten (Text) | `aria-live="polite"` am Journal-Neueintrag |
| Zustandswort (Statuszeile) | `role="status"` (polite), entprellt (max 1 Announce/Übergang) |
| Aktions-Start/-Ende | polite („Recherche gestartet/abgeschlossen") |
| Fehlerbanner | `role="alert"` (assertive) |
| Formularfehler | `aria-live` Zusammenfassung + `aria-invalid`+`aria-describedby` je Feld |
| Kopiert/Gespeichert/Autostart | polite |
| Lösch-Bestätigung | assertive einmalig („Nochmal klicken, um ‚Coding' zu löschen") |
| Hover-/Fokus-Deko, Suche-Tippen | keine Live-Region (Trefferzahl: polite, entprellt 500 ms) |

**Monitor-Map-Alternative:** Selects sind die SR-Primärroute; Map-Zonen tragen vollständige `aria-label` inkl. Belegung; nach Zuweisung Announce „Obsidian → Monitor links, rechte Hälfte gespeichert". Karte trägt `role="group" aria-label="Monitor-Zuordnung — alternativ per Auswahlfeldern je App"`.

## 5. Formulare

Sichtbare Labels (`for`), Hilfetexte via `aria-describedby`, Pflichtfelder markiert, Validierung on-blur, Fehler unter Feld + Summary oben mit Ankerlinks (`error-summary`), Read-only ≠ disabled (API-Key-Erklärfeld read-only).

## 6. Kontrast, Zoom, Bewegung, Dichte

- Kontraste: Text ≥7:1 primär/≥4.5:1 sekundär (gemessen); Nicht-Text-Indikatoren ≥3:1; Fehlertexte nie in error-brick <12.5px/600 (DESIGN §17.6).
- **Zoom 200 %:** alle Flows bedienbar; Journal/Listen scrollen; keine horizontalen Scroller; Prototyp-Beleg (halbierter Viewport 760×540 als Näherung — Methode dokumentiert).
- **Reduzierte Bewegung:** alle Pulse/Einflüge aus; Zustands-FARBWECHSEL bleiben (Information); Vollabdeckung ist Phase-4/5-Pflicht (heutige Orb-Lücke dokumentiert).
- **Hohe Dichte:** KZ bleibt bei 1000×800 vollständig bedienbar (Phase-2-Beleg + UX-Prototyp); <650px Höhe entfällt zuerst Nicht-Kritisches (Heute).
- Farbe nie allein: jeder Dot hat Klartext; Zustände zusätzlich über Wort/Icon/Position.
- Interaktionsflächen: COMPONENT_BEHAVIOR §Mindestgrößen.

## 7. Bewusste ARIA-Sparsamkeit

Semantisches HTML zuerst; ARIA nur für: Tabs (`role=tab/tablist` bestehend), Switch, Live-Regionen, `aria-selected/pressed/checked/invalid/describedby`, Landmark-Labels. Keine redundanten `role=button` auf `<button>`.

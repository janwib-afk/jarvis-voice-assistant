# Responsive-Spezifikation: Panel · Fokus · Vollbild (Phase 3)

Die Modi sind Nutzungskontexte, keine Größenstufen (DESIGN §12). UI-Benennung bleibt „Vollbild / Mitte / Klein"; Doku-Synonyme Fokus=Mitte, Panel=Klein.

## Rollen

- **Panel (420×560, always-on-top):** Taschen-Instrument. Sprechen, Zustand sehen, stoppen, letzte Antwort lesen. Nichts Verwaltendes. Weg ins KZ: Nav-Tab (wechselt bewusst auf „Mitte", Tooltip kündigt an, Rückweg „Klein" sichtbar).
- **Fokus/„Mitte" (1000×800, zentriert):** Arbeitsplatz. Längeres Gespräch + aktuelle Aktion + kompakte Werkbank (KZ nutzbar, verdichtet).
- **Vollbild:** volle Atmosphäre + komplette Werkbank; Inszenierung (Begrüßung, großes Instrument).

## Sichtbarkeitsmatrix

| Element | Panel | Fokus | Vollbild |
|---|---|---|---|
| Wortmarke + Ebene-1-Nav | kompakt sichtbar | vollständig | vollständig |
| Modus-Schalter | ausgeblendet (Fensterknöpfe bleiben; Rückweg über Tray/Win+J bzw. „Klein"-Logik im Fokus) → **Korrektur: kompakt sichtbar** (Rückweg-Pflicht, Flow 32) | vollständig | vollständig |
| Begrüßung | ausgeblendet | kompakt (22px) | vollständig (27px) |
| Instrument (Orb+Lünette) | kompakt 92px | kompakt 132px | vollständig 196px |
| Statuszeile (Zustand + laufende Aktion) | vollständig (Kurzform) | vollständig | vollständig |
| Journal | ausgeblendet → ersetzt durch Panel-Antwort | vollständig (flex) | vollständig (max 660px) |
| Panel-Antwort (Serife) | vollständig | ausgeblendet | ausgeblendet |
| Transcript-Suche/Alles kopieren | ausgeblendet | vollständig | vollständig |
| Texteingabe + Hint | vollständig / Hint kompakt | vollständig | vollständig |
| Gerätefußleiste (Klartext-Status) | kompakt (Dots+Zustandswort) | vollständig | vollständig |
| Stop/Mute (≥44px) | vollständig | vollständig | vollständig |
| Mini-Aktionshistorie (3) | vollständig | ausgeblendet (→ Statuszeile) | ausgeblendet (→ Statuszeile) |
| Volle Aktionshistorie | ausgeblendet | verschoben: nur KZ | verschoben: nur KZ |
| KZ gesamt | nicht verfügbar (erzwungener Wechsel) | vollständig, verdichtet | vollständig |
| Profile | — | vollständig (umbrechend) | vollständig |
| Monitor-Bucht | — | kompakt (schmalere Monitore) | vollständig |
| Positions-Selects | — | kontextabhängig (bei Modul-Auswahl) | kontextabhängig |
| Heute-Strip | — | kompakt; <650px Höhe: ausgeblendet | vollständig |
| Apps/Aktionen/System-Spalte | — | vollständig | vollständig |
| Einstellungen/Musik | — | vollständig | vollständig (max 520/560px Inhalt) |
| Fehlerbanner-Stack | vollständig (max 2 sichtbar, Rest gestapelt) | vollständig | vollständig |

## Breakpoint-/Grenzverhalten

Fensterbreiten (Invarianten aus Ist-System, bleiben): <1100px: Heute-Strip weg · <960px: Monitor-Bucht weg (Hinweiszeile „Monitor-Zuordnung braucht mehr Breite — Selects bleiben verfügbar" ▲ neu: Selects sind breitenunabhängig!) · <700px: rechte Spalte weg (Hinweis + Verweis auf Vollbild). Höhen: <650px: Heute weg, Instrument → 92px; Panel-Layout ist eigener Modus, keine Query.
**Maximale Inhaltsbreiten (Vollbild, sehr breite Monitore):** Journal 660px zentriert; KZ-Gesamtbreite max 1520px zentriert (Bucht wächst, Spalten fix 300/264px); Leerraum trägt Atmosphäre (Lampe), keine vierte Spalte.
**Vertikale Prioritäten:** Instrument+Statuszeile nie unter 92px+1 Zeile; Journal/Bucht sind die flexiblen Zonen; Fußleiste immer sichtbar (fixe Höhe, Inhalte scrollen dahinter nicht — `fixed-element-offset` Padding).
**Umordnung:** Panel ordnet linear (Instrument→Antwort→Eingabe→Mini-Aktionen→Fußleiste); Fokus-KZ bricht Profilzeile um (belegt Phase 2); keine Element-Migration zwischen Spalten.
**Rollenwechsel:** Antwort ersetzt Journal (Panel); laufende Aktion wandert von Spalte in Statuszeile (Fokus/Vollbild); Modus-Schalter wird im Panel zur reinen Rückweg-Kontrolle (nur „Mitte/Vollbild" nötig? — bleibt 3-fach für Konsistenz, `navigation-consistency`).
**Zoom 200 %:** Layout bleibt bedienbar (validiert im UX-Prototyp via halbiertem Viewport); Journal scrollt, Fußleiste bleibt erreichbar; keine horizontalen Scroller (`horizontal-scroll`).
**Zurückgesetzt wird beim Größenwechsel:** nichts außer der erzwungenen Panel→Jarvis-Regel; Suche/Auswahl/Formulare bleiben (`state-preservation`).

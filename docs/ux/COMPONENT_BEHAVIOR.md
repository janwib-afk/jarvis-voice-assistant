# Komponentenverhalten (Phase 3)

Zustandsmatrizen je Familie. Legende: ● spezifiziert · — nicht anwendbar. Alle Familien: sichtbarer `:focus-visible` (2px Messing + Offset 2, DESIGN §15), `cursor:pointer`, Feedback <100 ms, Übergänge 150–300 ms (`duration-timing`), Farbe nie allein (`color-not-only`).

## Matrix-Übersicht

| Familie | default | hover | focus-visible | active | selected | disabled | loading | success | warning | error |
|---|---|---|---|---|---|---|---|---|---|---|
| Primärbutton (Speichern) | Bernstein-Fläche, dunkle Schrift | heller (#f0b569) | Ring | amber-deep | — | 40 % Opacity + `disabled` | Spinner + Label „Speichert …" + disabled | „Gespeichert ✓" 2 s (Moos-Text) | — | Fehlerpfad im Formular |
| Sekundär-/Quiet-Button | Kontur/leise | Kontur strong + Text primär | Ring | eingedrückt (Lichtkante aus) | — | 40 % | Spinner klein | Label-Wechsel 2 s | — | Ziegel-Kontur (z. B. „Öffnen" fehlgeschlagen) |
| Icon-Button (Stop/Mute ≥44px) | inset rund + Icon | Text primär + Kontur strong | Ring | gedrückt | Mute: gefüllt Ziegel-soft | 40 % (nie für Stop) | — | — | — | — |
| Nav-/Sub-/Profil-Tab | Text sekundär | Text primär + Unterstreichung subtle | Ring | — | Unterstreichung Messing + `aria-selected` | 45 % + Grund-Tooltip | — | — | — | Profil-Löschen-Confirm: Ziegel-Kontur |
| Texteingabe/Suche/Textarea | inset, sichtbares Label | Kontur subtle | Messing-Kante + Halo | — | — | 45 % + `disabled`; read-only: normal + Schloss-Hinweis (`read-only-distinction`) | — | on-blur-Häkchen optional | — | Ziegel-Kante + Meldung unterm Feld + `aria-invalid` |
| Schalter (Autostart) | Track inset, Knopf muted | Track-Kontur strong | Ring | Knopf gleitet | an: Knopf Bernstein+Glow + „an" | 45 %, busy: zusätzlich Spinner-Ersatz (Knopf pulsiert nicht — busy-Text) | busy bis POST-Antwort | Knopf bleibt; SR „Autostart an" | — | Knopf springt zurück + Zeile |
| App-Modul | Fläche erhöht | Kontur subtle | Ring | — | Messing-Kante + Selects sichtbar | gedimmt + Badge „nicht gefunden" | Öffnen-busy | „Geöffnet ✓" | Pfad-Warnung Zeile | Ziegel-Kante + Abhilfe |
| Monitorzone (Button) | unsichtbare Kante | Ghost-Fläche (assigning) | Ring + Ghost | Zuweisung | Chip vorhanden | Monitor unassignable: 45 % + Grund | „Speichert …" Kante | Puls 1× + Chip | — | Ziegel-Kante + Meldung |
| Positions-Selects (neu) | native `select` gestylt minimal | Kontur | Ring (nativ) | — | Wert = aktuelle Zone | wie Feld | Speichern-Button busy | Zeile „Gespeichert ✓" | — | Zeile + Fokus bleibt |
| Transcript-Copy | unsichtbar bis hover/focus | sichtbar | sichtbar + Ring | — | — | — | — | „Kopiert" 2 s | — | „Kopieren fehlgeschlagen" (Clipboard-Verbot) |
| Statuspunkt+Text | Dot + Klartext | — | — | — | — | — | Puls (läuft) | Moos | Ember | Ziegel |
| Banner | erhöht, Statuskante | ×-Hover | × fokussierbar + Ring | — | — | — | — | Erfolg 4 s Auto-Dismiss (`toast-dismiss`), Fehler persistent | Ember | Ziegel + assertive |
| Musik-Zeile | Fläche | Kontur | Ring | — | Dot Bernstein + „spielt beim Start" | Datei fehlt: gedimmt + Hinweis | Auswahl-POST kurz | Zeilen-Feedback | — | Zeile |

## Interaktionsregeln (global)

- **Mindestgrößen (Desktop-Kalibrierung, dokumentierte Abweichung von 44px-Mobilnorm):** Stop/Mute & Orb ≥44 px; Standard-Buttons ≥32 px Höhe; Map-Zonen ≥44 px; Abstände ≥8 px (`touch-spacing`). Begründung: Maus-präzises Desktop-Ziel, kritische Kontrollen dennoch touch-tauglich.
- **Tastaturauslösung:** Enter+Space für Buttons/Zonen/Toggles; Enter in Inline-Eingaben = bestätigen, Esc = abbrechen; Strg+Enter sendet Text; Space = PTT nur außerhalb Feldern.
- **Fokusreihenfolge** = visuelle Ordnung (ACCESSIBILITY_SPEC §3); kein `tabindex`>0.
- **Tooltips:** nur ergänzend (Titelleisten-Icons, Panel-Nav-Hinweis, Mute-im-PTT); nie einzige Beschriftung; erscheinen auch bei Fokus.
- **Feedbackdauer:** Button-Erfolgstext 2 s; Erfolgs-Banner 4 s; Fehler persistent; „Kopiert" 2 s.
- **Wiederholter Klick / Mehrfachauslösung:** async-Buttons sofort `disabled`+busy (`loading-buttons`); WS-Sends entprellt (Senden-Button disabled bis Zustandswechsel); Stop ist idempotent (Mehrfach-Esc ok).
- **Abbruch laufender Aktionen:** Esc-Kaskade (STATE_MODEL); jede async-UI-Aktion mit Dauer >1 s zeigt Abbruchweg oder ist idempotent wiederholbar.
- **Toasts/Erfolgsmeldungen** stehlen nie den Fokus (`toast-accessibility`); Formularfehler nutzen `aria-live`/`role=alert` (`aria-live-errors`).
- **Fehlerzeilen reservieren ihren Platz** (visibility statt display): On-blur-Validierung darf das Layout nicht verschieben, sonst verfehlt der bereits gedrückte Speichern-Klick den Button (`layout-shift-avoid`; im UX-Prototyp real reproduziert und behoben).

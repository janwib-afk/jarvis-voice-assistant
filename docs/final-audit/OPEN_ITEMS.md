# Phase 7 — Open Items

Nur **tatsächlich offene** Punkte. Stand 2026-07-13. **Kein offenes P0 oder P1.** Keiner der folgenden Punkte blockiert die Veröffentlichung.

| # | Schwere | Punkt | Auswirkung | Begründung offen | Empfohlene Lösung | Risiko | Release-Blocker |
|---|---|---|---|---|---|---|---|
| 1 | P3 | Orb-Rest bei sehr niedriger Höhe (<~600px) | Dekorativer (aria-hidden) Orb kann bei 200 % Zoom des ohnehin kleinen Fensters oben minimal beschnitten werden; Statuswort, Eingabe-Kern, Stop/Mute bleiben sichtbar | Kein realer Desktop-Fensterpfad (echte Modi Vollbild/Mitte/Klein alle frei); Kernfall „Mitte" wurde behoben. Sauberer Fix = scrollbares Basis-Layout mit breiter Screenshot-Wirkung → Regressionsrisiko am Release zu hoch | Folgeversion: oben verankertes, scrollbares Layout unter `@media (max-height)` (`$impeccable layout`) | niedrig | **nein** |
| 2 | P3 | Fehlermeldung doppelt (Banner + `#sc-error`) | Gleicher Fehlertext kurzzeitig oben (Banner) und unten (Fußleiste) | `#sc-error` ist der persistente Detailort nach Banner-Dismiss; räumlich getrennt; Phase-6-Entscheidung; Neukoordination riskiert Fehler-Sichtbarkeit | `#sc-error` bei aktivem Banner auf Kurzform reduzieren | niedrig | nein |
| 3 | P3 | Map-Labels in schmaler Monitor-Bucht abgeschnitten | Kosmetisch; Monitorname evtl. „Linker Mon…" | Weg B (Selects „Monitor/Zone/Position speichern") bleibt vollständig lesbar/keyboard-erreichbar (SR-Primärroute) | Kurzform/Tooltip oder Chip-Umbruch | sehr niedrig | nein |
| 4 | P3 | 9px H-Overflow @375px Breite | Unter dem schmalsten realen Fenstermodus | Panel = 420px (kbd-hint dort ausgeblendet → 0 Overflow); Overflow-Sweep 1920→430px = 0 | `flex-wrap` am `#device-bar` | sehr niedrig | nein |
| 5 | P3 | Kein Font-`preload` | Marginaler FOUT-Spielraum | Fonts lokal, `font-display: swap`, kein Layout-Shift gemessen | `<link rel="preload" as="font">` fürs Regular-Gewicht | sehr niedrig | nein |
| 6 | P3 | ARIA-Tab-Muster Kontrollzentrum unvollständig (Review F2) | `role=tab` ohne `aria-controls`, Übersicht ohne `role=tabpanel`, keine Pfeiltasten-Navigation | Tabs sind als Buttons voll bedienbar; nur SR-Semantik nicht ideal | `aria-controls`/`id` + `role=tabpanel` ergänzen (oder Tabs als schlichte Buttons) | niedrig | nein |
| 7 | P3 | `#cc-map-stage` ohne `role="group"`/`aria-label` (Review F3) | Abweichung von eigener ACCESSIBILITY_SPEC §4 | Map ist visuell/über Weg B nutzbar; nur Gruppierungssemantik fehlt | `role="group"` + beschreibendes `aria-label` | sehr niedrig | nein |

## Manuell zu verifizieren (nicht automatisch prüfbar, keine offenen Defekte)

Diese Punkte sind **nicht offen im Sinne von Fehlern**, sondern nur außerhalb der gestubbten Browser-Prüfung testbar (echte Hardware/APIs). Vor einem echten Release einmal manuell im Launcher durchgehen:

- Echtes STT (Sprache → Text), echte ElevenLabs-Sprachausgabe + Speaking-Puls + Stop, echter Claude-Antwortinhalt.
- Echter App-Start + Fensterplatzierung auf dem Zielmonitor.
- Doppelklatschen-Trigger, native pywebview-Fenstergrößen (Vollbild/Mitte/Klein), echter Screenreader-Durchgang (NVDA/Narrator).

Anleitung je Punkt in [evidence/EVIDENCE.md](evidence/EVIDENCE.md) → „Nicht prüfbar".

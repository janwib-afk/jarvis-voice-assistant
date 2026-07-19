# Jarvis UI-Zustandsmodell (Phase 3)

Ein Zustand zur Zeit (globaler Assistentenzustand). `muted` ist ein **Modifikator** des Hör-Kanals, kein Parallelzustand des Sprechens — Matrix unten. Orb-Paare: DESIGN.md §10.

> **Ist-Stand seit RFC-0006 (Phase 4J, 2026-07-19).** Dieses Dokument bleibt der
> **UX-Vertrag** — es beschreibt, was der Nutzer sieht. Die Laufzeit erzeugt diese Anzeige
> seit Phase 4J jedoch nicht mehr durch Setzen eines flachen Zustands: `setOrbState()` ist
> entfernt, und die Anzeige wird aus fünf **orthogonalen Regionen** (Connection, Capture,
> Playback, Interaction, Overlays) plus der Client-Session-Ebene **abgeleitet**
> (`JarvisVoice.presentation`, `frontend/voice.js`). Das DOM ist Ausgabe, nie Zustandsquelle.
>
> Damit lösen sich zwei alte Ungenauigkeiten dieses Dokuments auf:
> `muted` und `degraded` sind tatsächlich Modifikatoren beziehungsweise Overlays und keine
> Zustände derselben Ebene — genau wie hier beschrieben; und `confirmation-required` pausiert
> weiterhin keine globale Zustandsmaschine, weil es die offene Rückfrage der
> `ConversationSession` ist und keine Region der Anzeige.
>
> Die abgeleiteten Anzeigewerte und ihre CSS-Abbildung stehen im
> [Phase-4J-Migrationsbericht](../architecture/PHASE4J_EXPLICIT_RUNTIME_STATE_MACHINES_MIGRATION.md).
> Die sichtbaren Bezeichnungen, Übergänge und die Escape-Kaskade unten sind unverändert gültig.

## Zustände

| Zustand | Sichtbare Bezeichnung | Orb | Primäraktion | Erlaubte Eingaben | Stop bewirkt | Mute bewirkt | Statusfarbe | Live-Region | Übergänge nach | Fehler-/Recovery-Pfad |
|---|---|---|---|---|---|---|---|---|---|---|
| disconnected | „Getrennt — verbinde neu (Versuch n)" | idle, gedimmt | erneut verbinden (auto) | Text tippen (Queue nein → Hinweis), Nav, Modus | lokal: Audio stoppen | Toggle wirkt lokal | Ziegel-Dot | polite; Banner ab 3. Versuch assertive | connecting | Auto-Reconnect 3→30 s; Banner-Abhilfe „Server starten" |
| connecting | „Verbinde …" | idle, Puls aus | warten | Nav/Modus | wie oben | lokal | Muted-Dot | — | idle · disconnected | Timeout → disconnected |
| idle | „Bereit" | idle | sprechen/tippen | alle | nichts (kein Ziel) — Button neutral | muted | Moos | — | listening · processing (Text) | — |
| listening | „Hört zu" | listening | sprechen | alle | bricht nichts (kein Audio) → kurz „Nichts zu stoppen"? Nein: Stop bleibt wirkungslos-neutral | muted | Bernstein | — | processing · idle (PTT-Ende) · muted | Mic-Fehler → error |
| processing | „Verarbeite …" | thinking (früh) | warten/Stop | Text (queued nein → disabled Senden), Stop, Mute, Nav | Anfrage abbrechen → stopping | muted (wirkt ab nächstem Hören) | Bernstein | — | thinking | WS-Abbruch → disconnected |
| thinking | „Denkt nach" | thinking | Stop | wie processing | LLM-Antwort verwerfen → stopping | wie oben | Bernstein | — | speaking · action-running · idle (leise Antwort) | LLM-Fehler → error |
| action-running | „Recherchiert: <Label> — Esc stoppt" | thinking | **Stop (visuell primär)** | Stop, Mute, Nav, Text (disabled Senden) | Aktion abbrechen → stopping | wie oben | Bernstein pulsierend | polite (Start/Ende) | speaking · idle · error | Aktionsfehler → error-Eintrag + idle |
| speaking | „Spricht" | speaking | **Stop (visuell primär)** | Stop, Mute, Nav, Modus, Tippen erlaubt | Audio + Aktion stoppen → stopping | muted (stoppt NICHT das Sprechen — nur Hörkanal; Hinweis-Tooltip) | Bernstein | polite: Antworttext | idle/listening | TTS-Fehler → degraded |
| stopping | „Stoppt …" (≤1 s) | Zustand einfrieren, Glow aus | warten | keine neuen Sends | idempotent | lokal | Muted | — | idle | hängt >2 s → error-Banner |
| muted | „Mikrofon stumm" | muted (Ziegelring) | Mute lösen | Text, Nav, Stop | wie Kontext | zurück zu idle/listening | Ziegel-Dot Mikro | polite einmalig | vorheriger Hörzustand | — |
| degraded | „Eingeschränkt: <Dienst> nicht verfügbar" | Kontextzustand, Glow normal | weiterarbeiten (Text) | alle außer betroffenem Kanal | wie Kontext | wie Kontext | Ember-Dot am Dienst | Banner polite | idle …; zurück wenn Dienst ok | Banner mit Abhilfe je Dienst |
| error | „Störung — Details im Banner" | error (2 Pulse→statisch) | Banner lesen/Abhilfe | alle | Audio stoppen falls läuft | lokal | Ziegel | **assertive** (Banner) | idle nach nächster erfolgreicher Interaktion | Banner-Abhilfe; persistente Fehler bleiben gelistet |
| confirmation-required | „Bestätigen: <Aktion>" (lokal am Element) | unverändert | bestätigen/abbrechen | nur betroffenes Element + Esc | — (lokal) | — | Ziegel am Element | assertive kurz | zurück zum Ausgangszustand | Esc/anderer Klick = Abbruch |

## Unvereinbarkeiten (Matrix)

- `listening ⊕ speaking ⊕ thinking/processing ⊕ stopping` — genau einer aktiv (globaler Orb-Zustand).
- `muted` überlagert NUR die Hör-Seite: kombinierbar mit speaking/action-running/degraded; nie mit listening (schließt es per Definition aus).
- `degraded` ist Overlay-Flag (Dienstliste) zu jedem Nicht-error-Zustand; `error` verdrängt degraded-Anzeige, bis quittiert.
- `confirmation-required` ist elementlokal (Profil-Löschen, Verwerfen-Rückfrage) und pausiert KEINE globale Zustandsmaschine — Sprache läuft weiter; einzige Sperre: das betroffene Element.
- `disconnected/connecting` verdrängen alle Gesprächszustände; Mikrofon bleibt nutzbar (bestehende Architektur), Erkanntes wird NICHT gesendet → Statuszeile erklärt das.

## Escape-Kaskade (verbindlich)

1. Offene Inline-Bestätigung/-Eingabe oder App-Auswahl → abbrechen.
2. Sonst: Stop-Anforderung (Audio + Aktion) — in jedem Zustand erlaubt, idempotent.
Escape navigiert nie und schließt keine Bereiche.

## Übergangsdiagramm (Kernpfad)

```
connecting → idle ⇄ listening → processing → thinking ┬→ speaking → idle
     ↑                                                ├→ action-running → speaking/idle
disconnected ←──────────── (WS-Verlust, aus jedem) ───┘        │
      └→ connecting (Backoff 3–30 s)                        stopping → idle
muted: Toggle aus idle/listening/…; error: aus processing/thinking/action/speaking; degraded: Dienst-Flag
```

## Wiederherstellung

- Nach `error`: nächste erfolgreiche Interaktion setzt Normalzustand; Banner bleibt bis × (persistent bei llm/ws).
- Nach `disconnected`: Reconnect stellt idle her; Transcript/Einstellungen unverändert (`state-preservation`).
- Nach `stopping`-Hänger (>2 s): error-Banner „Stopp nicht bestätigt — Verbindung prüfen"; lokale Wiedergabe ist bereits still.

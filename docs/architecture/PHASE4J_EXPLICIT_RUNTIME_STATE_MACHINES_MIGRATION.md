# Phase 4J — Explicit Runtime State Machines (Umsetzung von RFC-0006)

> Stand 2026-07-18. Umsetzung von
> [RFC-0006](RFC-0006-explicit-runtime-state-machines.md) **einschliesslich
> [Amendment 1](RFC-0006-explicit-runtime-state-machines.md#amendment-1--vervollständigtes-zustandsinventar)**.
> Basis: `origin/master` `0c5bd5ab9efaf1875542af49be6261a75d234857` (Squash-Merge PR #10).
>
> **TDD, elf einzeln rückrollbare Slices.** Beobachtbares Verhalten und Wire-Contracts
> bleiben unverändert; RFC-0005 wird nicht erweitert. Keine Job-Engine, keine Persistenz,
> kein Capability-/Policy-Kernel.

## Post-Merge-Gate (Prompt-17-Startbedingung)

- `origin/master` = `0c5bd5ab9efaf1875542af49be6261a75d234857` (verifiziert gegen GitHub-API).
- Post-Merge-Lauf **29645372645**: Event `workflow_dispatch`, Branch `master`,
  headSha exakt `0c5bd5ab…`, **Fast success + Browser success**, beide Jobs beendet.
- Branch `phase-4j-explicit-runtime-state-machines` direkt von `origin/master`.

## Frische Baseline (vor Slice 1)

| Prüfung | Ergebnis |
|---|---|
| `python -m unittest discover -s tests` | **819** Tests, OK |
| Modulgrößen | `runtime.py` 186 · `server.py` 971 · `assistant_core.py` 460 · `frontend/main.js` 1856 · `frontend/wire.js` 104 |

> Testzahlen wurden **frisch gemessen**, nicht aus früheren Berichten übernommen.

## Verbindliche Umsetzungspräzisierungen (Prompt 17 §7)

1. **Mute/Sprach-Entstummen** — `StopRecognition` heisst *normale Spracheingabe deaktivieren*;
   der vorhandene Web-Speech-Adapter darf kontrolliert weiterlaufen, um ausschliesslich
   Stop/Entstummen zu erkennen. Keine zweite Engine, kein STT-Umbau.
2. **Playback `locked`** — Startwert; Audio wird bis zur erfolgreichen Nutzergeste gepuffert;
   Autoplay-Block führt zurück nach `locked` + recoverable Overlay.
3. **Fehleranzeige** — `recoverable-error`/`degraded` bleiben Overlays und verändern die
   Presentation **nicht**; nur `fatal-error` ergibt `error`. Keine visuelle Regression.
4. **Initialer Voice-State** — Connection `disconnected`, Capture `unavailable`,
   Playback `locked`, Interaction `idle`, Overlays leer, `greeted=false`, `epoch=0`.
5. **Stop + sofortiger neuer Command** — sofort annehmbar/einreihbar, aber kein zweiter
   Turn parallel: der neue Turn startet erst nach `ExecutionEnded` (I1 bleibt).
6. **Confirmation-Correlation** — Ja/Nein ist ein neuer Command mit eigener Correlation,
   führt den suspendierten Turn aber atomar fort; nie zwei aktive Turns.
7. **Bestehende Cancel-Frames** — zuerst charakterisiert (siehe Slice 1), dürfen nicht still
   entfallen oder umsortiert werden.
8. **Transportbesitz** — `ConversationChannel`/`ConnectionRegistry` bleiben unveränderte
   RFC-0005-Module; Origin/Token/Handshake/64 KiB/Decode/ProtocolError bleiben im WS-Adapter.
9. **Render-Grenze** — nur state-bezogene DOM-Ausgabe läuft über den Render-Effekt.
10. **Async-Signaturen** — reiner Kern synchron und I/O-frei; nur Lifecycle-Methoden dürfen
    die kleinste nötige Async-Verfeinerung erhalten.

---

## Slice-Log

### Slice 1 — Charakterisierung
- **Ziel:** das heutige beobachtbare Verhalten festhalten, **bevor** Zustand wandert.
- **Seams:** SEAM-CONVERSATION (echter `/ws`-Dialog, nur `ai`/`synthesize_speech`/
  `browser_tools` als externe Grenzen ersetzt) + SEAM-BROWSER-UI (echter Playwright-Flow).
- **Charakterisierend → erwartungsgemäss grün**; kein vorgetäuschtes RED.

**Wichtigster Befund — die Cancel-Framefolge war anders als angenommen.** Die erste
Testfassung nahm `action(start) → stop → response → action(error)` an und wurde **rot**.
Empirisch ermittelt gilt tatsächlich:

| # | Frame |
|---|---|
| 1 | `action` (phase `start`) |
| 2 | `stop` |
| 3 | `action` (phase `error`, detail `abgebrochen`) |
| 4 | `response` („Okay, gestoppt.") |

Ursache: `await channel.emit(StopAck)` in `server.py` ist ein Yield-Punkt — der gecancelte
Task durchläuft dort seinen `except asyncio.CancelledError`-Pfad und sendet den
Abbruch-Frame, **bevor** „Okay, gestoppt." folgt. Genau diese Reihenfolge muss die
Migration erhalten (Präzisierung 7). Ohne Charakterisierung hätte die Migration die
falsche Reihenfolge „bewahrt".

**Neu — Kostenschutz ausführbar gemacht.** `tests/browser/e2e_server.py` zählt jetzt, wie
oft die Auto-Begrüssung einen LLM-Call auslöst (`/__e2e__/stats`, nur Zahlen, keine
Inhalte); `JarvisServer.stats()` liest ihn. Der neue Flow **`greeting_once`** erzwingt
**drei** echte WS-Verbindungen und belegt: genau **eine** Begrüssung. Ohne diesen Test
könnte die Voice-Migration bei jedem Reconnect echte Anthropic-/ElevenLabs-Kosten auslösen
(Amendment 1 / M2).

- **Tests:** `tests/test_state_characterization.py` (7) — Cancel-Framefolge, Disconnect
  während Action, Stop im Leerlauf ist reines Ack, Stop verwirft Queue, normale Nachricht
  lässt Confirmation still verfallen, Stop verwirft Confirmation, strikte Sequenzialität.
  Browser: `greeting_once`.
- **Ergebnis:** 7/7 grün; `greeting_once` grün.
- **Geänderte Dateien:** `tests/test_state_characterization.py` (neu),
  `tests/browser/e2e_server.py`, `tests/browser/e2e_harness.py`,
  `tests/browser/e2e_functional.py`, dieses Dokument (neu).
- **Rollback:** Commit reverten (nur Tests/Doku, kein Produktionscode).
- **Commit / Rollback-SHA:** `fe9a5fe` — `test(state): characterize conversation and voice races`

### Slice 2 — Purer Conversation-Kern
- **Ziel:** `step(state, event) -> (state, effects)` als deterministischer, I/O-freier Kern.
- **Seam:** SEAM-CONVERSATION-STATE (rein, ohne Tasks/Locks/Codec).
- **RED:** `ModuleNotFoundError: No module named 'conversation'` → **GREEN:** 23/23.
- **Inhalt:** `conversation/_core.py` — Session `open/closing/closed`; Turn `queued/
  processing/awaiting-confirmation/executing-action/cancelling`; `completed`/`failed`/
  `cancelled` sind **Ergebnisse**; `ready` abgeleitet; Queue-Länge ist Daten.
  `view()` liefert nur semantischen Zustand.
- **Charakterisiertes Verhalten abgebildet:** Stop im Leerlauf = nur Ack; Stop bei
  laufendem Turn = `CancelActive, EmitStopAck, EmitStopped`; wiederholter Stop idempotent;
  Stop leert Queue + verwirft Bestätigung; neuer Command während `cancelling` wird
  eingereiht und startet erst nach `ExecutionEnded` (Präzisierung 5, I1); Bestätigung
  überlebt den auslösenden Turn (Präzisierung 6); `closing`/`closed` ignorieren Commands
  (I4); ungültige Übergänge sind totale No-Ops (§19).
- **Kein Produktions-Wiring** — `server.py`/`assistant_core.py` unverändert.
- **Rollback:** Commit reverten (rein additiv, keine Wirkung auf Produktion).
- **Commit / Rollback-SHA:** `1295ce3` — `feat(state): add pure conversation transition core`
- **Suite:** 826 → **849** grün.

### Slice 3 — Runtime-owned Manager und Sessions
- **Ziel:** Manager erzeugt/besitzt Sessions (D4); Session besitzt aktiven Turn, Queue und
  Cancellation-Lifecycle als **private** Implementierung.
- **Seam:** SEAM-CONVERSATION-STATE (Fake-Kanal + Fake-Runner als Grenzen; Manager,
  Session und Kern laufen real).
- **RED:** `AttributeError: module 'conversation' has no attribute 'ConversationManager'`
  (9 Fehler) → **GREEN:** 9/9.
- **Inhalt:** `conversation/_session.py`; `Runtime` besitzt genau **einen** Manager
  (I/O-frei konstruiert); `Runtime.aclose()` schliesst aktive Sessions **vor** den
  abhängigen Ressourcen (Browser/Clients).
- **Verifiziert:** mehrere Sessions unabhängig; Shutdown bricht alle laufenden Turns ab
  (0 offene Tasks nach `aclose`); geschlossene Session ignoriert Commands;
  Import-Sicherheit `ROOT_HANDLERS_DELTA 0`.
- **Kein Produktions-Wiring** — der WS-Endpunkt nutzt weiterhin seinen eigenen Worker;
  die Sessions werden erst in Slice 5 angehängt.
- **Rollback:** Commit reverten (additiv; `runtime.py` verliert nur Manager-Besitz).
- **Commit / Rollback-SHA:** `37a0fc7` — `feat(state): add runtime-owned conversation sessions`
- **Suite:** 849 → **858** grün.

### Slice 4 — Verlauf und Confirmation in den Session-Besitz
- **Ziel:** Verlauf und offene Bestätigung gehören dem Session-Aggregat, nicht Modul-Globals.
- **Inhalt:** `StartTurn` trägt die beim Turn-Start **konsumierte** Bestätigung (`pending`),
  damit `suspended` genau **eine** Wahrheit bleibt — exakt das frühere
  `pending_confirm.pop()` zu Beginn von `process_message`, inklusive des stillen
  Verfallens. Neuer öffentlicher `TurnContext` (Verlauf, `MAX_HISTORY` 60 /
  `LLM_HISTORY` 16 unverändert, `request_confirmation`, unveränderlicher
  `history_snapshot`). `tests/wire_testing.turn_context()` als öffentlicher Seam-Helfer.
- **Additiv** — `assistant_core`/`server.py` in diesem Commit unverändert.
- **Rollback-SHA:** `e791fcc`

### Slices 5 + 6 — WS-Adapter und session-explizites `assistant_core`
- **Bewusst EIN Commit.** Beide Slices sind wechselseitig abhängig: sobald
  `assistant_core.conversations`/`pending_confirm` entfallen, kann der alte WS-Worker
  nicht mehr laufen — und umgekehrt. Ein Zwischenstand wäre **nie verifiziert** worden.
  Präzedenz: Phase 4A (Prompt 8C) hat aus demselben Grund atomar committet.
- **Slice 5:** Queue, aktiver Turn, Worker und Cancellation sind private
  Session-Implementierung; `server.py` hat **0 Treffer** für `asyncio.Queue`/`worker`/
  `state["task"]`/`state["stopping"]`. Die RFC-0005-Transportgrenze bleibt im Adapter
  (Origin, Token, Handshake, 64 KiB, `receive_text`, `decode_command`, `ProtocolError`).
- **Slice 6:** `conversations`, `pending_confirm`, `end_session` und die Runtime-Aliase
  **vollständig entfernt**; `process_message`/`run_action_and_respond`/`execute_action`/
  `_action_context` nehmen einen expliziten `TurnContext`.
- **Verhaltenskompatibilität belegt:** Slice-1-Charakterisierung unverändert grün —
  inklusive der exakten Cancel-Framefolge. **Alle 14 Browser-Flows grün** gegen das
  migrierte Backend (`stop_action`, `mute`, `reconnect`, `greeting_once`, …).
- **Alt-Tests** auf den öffentlichen Seam umgestellt (7 Dateien), keine neue Schicht auf
  alte Interna.
- **Rollback-SHA:** `8a950cd` · **Suite:** 858 grün

### Slice 7 — Purer Voice-Reducer
- **Ziel:** `frontend/voice.js` als reiner Zustandskern; **keine** Integration.
- **Inhalt:** fünf orthogonale Regionen + Client-Session-Ebene; Presentation immer
  abgeleitet (9 Prioritätsregeln); `degraded`/`recoverable-error` sind additive Overlays,
  nur `fatal-error` ergibt `error`.
- **Runner:** `tests/browser/e2e_voice_contract.py` — **46/46** Fälle per
  `page.evaluate` gegen echten Code; keine Quelltext-Assertions, keine npm-Dependency.
- **Belegt:** initialer Zustand (`locked`, `greeted=false`, `epoch=0`); `muted` **und**
  `playing` gleichzeitig darstellbar; `locked` puffert Audio; `AutoplayBlocked` fällt nach
  `locked` zurück; **genau eine** Begrüßung über drei Reconnects; Epoch-Bumps bei
  Stop/Mute/WsOpen/WsClosed; stale Reconnect-Timer, Audio-Ende nach Stop,
  Recognition-Ende nach Mute und stale Error-Revert verändern **nichts**; normale Sprache
  unter Mute ignoriert, Stop/Entstummen wirken weiter.
- **Reinheit verhaltensbasiert belegt:** Sandbox, in der DOM/Netz/Audio/Timer werfen.
- **CI:** Contract-Runner im Browser-Gate ergänzt (keine neuen Trigger/Secrets).
- **Rollback-SHA:** `6e37582`

### Slice 8a — Client Session und Playback über den Reducer
- **Ziel:** die beiden **materiellen** Amendment-1-Befunde schliessen; alte Globals
  **entfernen**, nicht duplizieren.
- **M2 Greeting-Latch:** `hasGreeted` existiert nicht mehr. Der Reducer hält den Latch auf
  der Client-Session-Ebene; die Begrüssung wird nur gesendet, wenn er den Effekt
  `SendGreeting` liefert. `greeting_once` belegt über **drei** echte WS-Verbindungen, dass
  es bei **einer** bleibt (Kostenschutz).
- **M1 Playback `locked`:** `audioUnlocked` existiert nicht mehr. Freischaltung ist ein
  Übergang `locked → idle` (`UserGesture`); `AutoplayBlocked` fällt nach `locked` zurück;
  Gepuffertes wird nach der Geste abgespielt.
- **M3 Epoch:** `ws.onclose` erhöht die Epoch → geplante Reconnect-/Listen-Timer werden stale.
- **Bewusst offen (Slice 9):** `uiState.jarvisState`, `isMuted`, `isPlaying`, `isListening`,
  `reconnectAttempts`, DOM-Ableitung für `action-running`. Diese Bereiche sind **unverändert**
  in Betrieb — keine doppelte Wahrheit, nur ein noch nicht abgelöster Bereich.
- **Verifiziert:** 14/14 Browser-Flows · Visual grün **ohne** Baseline-Update (max 0.0115 %) ·
  A11y 22/22 · Reduced-Motion 16/16 · Voice-Contract 46/46 · Python-Suite 858.
- **Rollback-SHA:** `899b5ef`

### Slice 9a — DOM ist keine Zustandsquelle mehr
- **Ziel:** Invariante **I9** einlösen — die letzte Stelle entfernen, an der das DOM als
  Zustand gelesen wurde.
- **Vorher:** `const actionRunning = !!document.getElementById('status-action')?.textContent`
  — der Textinhalt eines DOM-Knotens entschied, ob eine Aktion läuft (einer der sechs
  Kernbefunde des Prompt-16-Audits).
- **Jetzt:** Der Action-Lebenszyklus führt die **Interaction-Region** des Reducers
  (`ActionStart`/`ActionDone`); `actionIsRunning()` liest sie ab. Das DOM ist nur noch
  Ausgabe — die CSS-Klasse wird aus dem Zustand **gesetzt**, nicht gelesen.
- **Verifiziert:** 14/14 Browser-Flows · Visual grün **ohne** Baseline-Update · A11y 22/22 ·
  Reduced-Motion 16/16 · Python-Suite 858.
- **Rollback-SHA:** `f2ec57b`

### Slice 9b — Connection-Region abgeleitet
- **Ziel:** `uiState.connected` als zweite Wahrheit entfernen.
- **Inhalt:** `isConnected()` liest die Connection-Region; das Flag ist **entfernt**.
- **Dabei gefundener Regressionsfehler:** `renderStatusCenter()` lief **vor** dem
  `WsOpen`-Dispatch — die Statuszeile hätte beim Verbinden noch „Getrennt" angezeigt.
  Behoben: Zustandsübergang zuerst, Ausgabe danach.
- **Verifiziert:** 14/14 Flows · Visual grün ohne Baseline-Update · A11y 22/22 · RM 16/16 ·
  Suite 858.
- **Rollback-SHA:** `a94383f`

---

## BLOCKER für die Audio-Migration — Testlücke

**Der Audio-Pfad ist vollständig testfrei.** Der E2E-Stub liefert
`_fake_synth → b""`; das Frontend ruft `queueAudio` nur bei
`data.audio && data.audio.length > 0`. Folglich werden **`queueAudio`, `playNext`,
`isPlaying`, der Autoplay-Block und `audio.onended` in keinem Browsertest ausgeführt.**

Eine Migration von `isPlaying` in die Playback-Region wäre daher **prinzipiell nicht
verifizierbar** — genau das, was die Verifikationsdisziplin verbietet. Die Playback-Region
selbst ist im reinen Reducer abgedeckt (Contract-Fälle zu `locked`/`playing`/
`AutoplayBlocked`), die **Integration** aber nicht.

**Erforderliche Reihenfolge:**
1. **Zuerst Abdeckung schaffen:** den E2E-Stub um ein Szenario erweitern, das echtes
   (winziges) Base64-Audio liefert — der stille MP3-Datenstring aus `unlockAudio` genügt.
   Dazu ein Flow, der Wiedergabe, `locked`→`idle` per Nutzergeste, Autoplay-Block und
   `audio.onended` real durchläuft.
2. **Dann migrieren:** `queueAudio`/`playNext`/`stopPlaybackLocal` dispatchen
   `AudioReceived`/`AudioEnded`/`StopRequested`; `isPlaying` entfällt. Achtung: der lokale
   Payload-Puffer und die Reducer-Queue müssen symmetrisch geführt werden (push beim
   Empfang, shift bei `AudioEnded`) — heute shiftet `playNext` **vor** dem Abspielen.

### Slice 9c/9d — Playback- und Capture-Region migriert
- **9c Playback** (`ba688fc`): `isPlaying` **entfernt**. `queueAudio` dispatcht
  `AudioReceived`; der Reducer entscheidet abspielen vs. puffern. `playNext` ist reiner
  Effekt-Ausführer; neues `onAudioFinished()` dispatcht `AudioEnded` und trägt die beim
  **Start** gemerkte Epoch → Audio-Ende nach Stop ist stale (Szenario 12).
  **Queue-Symmetrie** hergestellt: `playNext` liest den Kopf nur (peek), entfernt wird er
  in `onAudioFinished` — vorher wäre der lokale Puffer gegen die Reducer-Queue gedriftet.
- **9d Capture** (`9bd8d22`): `isMuted` **entfernt**; `toggleMute`, Sprach-Mute/-Entstummen
  und `micMode='off'` dispatchen `MuteToggled`.
  **Wichtige Unterscheidung:** `isListening` war **keine** zweite semantische Wahrheit,
  sondern verfolgt die **Engine** — die unter Mute bewusst weiterläuft, um Stop/Entstummen
  zu erkennen (Präzisierung 1). Es ist eine legitime Adapter-Ressource und heisst jetzt
  `recognitionRunning`. Hätte man es in die Capture-Region gepresst, wäre
  `recognition.stop()` unter Mute übersprungen und das Sprach-Entstummen kaputt gewesen.
- **Verifiziert (beide):** 15/15 Flows · Visual grün **ohne** Baseline-Update · A11y 22/22 ·
  Reduced-Motion 16/16 · Voice-Contract 46/46 · Suite 858.

### Audio-Abdeckung (`85ddfe8`) — Blocker aufgelöst
Der Stub liefert per `audio=True` ein echtes stilles MP3 (471 B); Flow `audio_playback`
lässt `queueAudio`/`playNext`/`play()` real laufen.
**Ehrliche Grenze, systematisch ermittelt:** Playwrights Chromium ist ein Open-Source-Build
**ohne MP3-Codec** — `play()` scheitert mit `NotSupportedError`. Erfolgreiche Wiedergabe ist
hier nicht darstellbar; verifiziert wird der zustandsrelevante Fehlschlagpfad (bleibt
`locked`, setzt `recoverable-error`, zieht die Presentation **nicht** auf `error`).
Vollständige Verifikation erfolgreicher Wiedergabe bräuchte einen Build mit Codec oder ein
WAV-Szenario — **offen**.

---

## Stand der Umsetzung

| Slice | Status | Rollback-SHA |
|---|---|---|
| 1 Charakterisierung | ✅ grün | `fe9a5fe` |
| 2 Purer Conversation-Kern | ✅ grün | `1295ce3` |
| 3 Runtime-owned Manager/Sessions | ✅ grün | `37a0fc7` |
| 4 Verlauf + Confirmation migrieren | ✅ grün | `e791fcc` |
| 5 Queue/Worker/Stop/Disconnect migrieren | ✅ grün | `8a950cd` (mit 6) |
| 6 `assistant_core` entkoppeln | ✅ grün | `8a950cd` (mit 5) |
| 7 Purer Voice-Reducer | ✅ grün | `6e37582` |
| 8 Voice-Integration | ✅ grün | `899b5ef` |
| 9 Presentation ableiten | ✅ grün | `f2ec57b`, `a94383f`, `ba688fc`, `9bd8d22`, `1dc9dfb` (9e), `1d0d5fc` (9f) |
| 10 Race-/Stale-/Cleanup-Matrix | ✅ grün | `e41dbfa`, `aeba8a1` (Audio-Seam) |
| 11 Doku + CI | ✅ grün | dieser Commit |

**Backend vollständig migriert (Slices 1–6).** Session-Globals, Runtime-Aliase und
`end_session` sind entfernt; der WS-Endpunkt ist ein dünner Adapter; die Verhaltensgleichheit
ist durch die Slice-1-Charakterisierung **und** alle echten Browser-Flows belegt.

**Frontend vollständig migriert (Slices 7–9f).** `frontend/voice.js` trägt den reinen
Reducer (55 Contract-Fälle). In `main.js` gibt es keine konkurrierende Zustandswahrheit
mehr: `setOrbState()` ist entfernt, die Anzeige wird ausschließlich über
`JarvisVoice.presentation(V.state)` abgeleitet, und `uiState.jarvisState` ist nur noch
Render-Ausgabe.

### Presentation → `orb.className`

`orb.className` erhält nur `idle|listening|thinking|speaking|muted|error` — die CSS hängt
daran. Die zusätzlichen Presentation-Werte werden deshalb ausdrücklich abgebildet:

| Presentation | `orb.className` |
|---|---|
| `disconnected` | `idle` |
| `error` | `error` |
| `speaking` | `speaking` |
| `stopping` | `idle` |
| `action-running` | `thinking` |
| `thinking` | `thinking` |
| `listening` | `listening` |
| `muted` | `muted` |
| `idle` | `idle` |

Die Ableitung ist ohne visuelle Regression eingeführt: 12/12 Visual-Shots grün **ohne**
Baseline-Aktualisierung, davon 9 pixelgenau identisch.

## Erreichter Umfang (Endstand Prompt 17)

**Entfernte semantische Doppelwahrheiten:** `assistant_core.conversations`,
`assistant_core.pending_confirm`, `end_session`, Runtime-Aliase, `hasGreeted`,
`audioUnlocked`, `uiState.connected`, `isPlaying`, `isMuted`, `setOrbState`,
`reconnectAttempts`, DOM-Ableitung für `action-running`.

**Als Adapter-Ressource geklärt (kein Zustand):** `recognitionRunning`, `currentAudio`,
`currentAudioUrl`, `audioQueue` (Payload-Puffer, symmetrisch zur Reducer-Queue),
Timer-Handles, Reconnect-Backoff (`JarvisVoice.createBackoff`, Slice 9f).

**`uiState.jarvisState`** bleibt in Betrieb, aber ausschließlich als **Render-Ausgabe** —
nie als Quelle. Die einzige Wahrheit ist der Reducer-Zustand.

## Slice 10 — Race-, Stale- und Cleanup-Matrix

Die 17 verbindlichen Szenarien aus RFC-0006 §21 haben einen eigenen, benannten Testblock;
jeder Test trägt seine Matrixnummer.

| Datei | Szenarien | Seam |
|---|---|---|
| `tests/test_race_matrix.py` | 1–10, 17 | SEAM-CONVERSATION / SEAM-WS / SEAM-CONVERSATION-STATE |
| `tests/browser/e2e_race_matrix.py` | 11–16 | SEAM-VOICE / SEAM-BROWSER-UI |
| — | 18 | SEAM-JOB-CONTRACT, **ausdrücklich Phase 6**; als Nicht-Ziel festgehalten |

Geprüft wird nur beobachtbares Verhalten (Frames, `snapshot()`, sichtbarer Zustand) — nie
Tasks, Locks oder Queue-Interna. Kein Sleep dient als Race-Lösung. Jedes Stale-Szenario hat
eine **Gegenprobe**, damit kein Test grün sein kann, weil schlicht nichts passiert.

**Der Block war sofort grün — das allein beweist nichts.** Ein Mutationsnachweis belegt,
dass er beißt, und deckte dabei drei echte Schwächen der Tests selbst auf:

| Mutation | erwartet rot |
|---|---|
| Stop leert die Queue nicht mehr | Szenario 6 |
| Stop verwirft die Rückfrage nicht mehr | Szenario 7 |
| Stop meldet immer „gestoppt" | Szenario 9 |
| `scheduleListen` ohne Epoch-Guard | Szenario 11, 13b |
| Reducer verwirft veraltete Ereignisse nicht | Szenario 12 |
| beide Error-Revert-Guards entfernt | Szenario 14 |

*Korrigierte Testschwächen:* Szenario 12 warf das alte Audio-Ende auf einen bereits leeren
Playback (dort ohnehin ein No-Op) — jetzt läuft nach dem Stop eine **neue** Wiedergabe, die
das verspätete Ende ohne Guard fälschlich beenden würde. Szenario 13 prüft Mute und
Disconnect getrennt: Mute schützt die Reducer-Regel, Disconnect die Epoch. Szenario 14 wird
von **zwei** unabhängigen Guards geschützt; Rot entsteht erst, wenn beide fallen — gewollte
Redundanz, keine Testschwäche.

## Audio-Seam — und die ehrlich benannte Umgebungsgrenze

**Playwright-Chromium ist ein Open-Source-Build ohne verwendbaren MP3-Codec.**
`audio.play()` lehnt dort mit `NotSupportedError` ab, unabhängig von jeder
Autoplay-Richtlinie. Der Erfolgspfad der Wiedergabe war deshalb im Browser-Gate nie
ausführbar und damit ungetestet.

Diese Grenze **bleibt bestehen und wird nicht vorgetäuscht.** `tests/browser/e2e_audio_seam.py`
ersetzt vor dem App-Start `window.Audio` durch eine kontrollierbare Implementierung und prüft
damit ausschließlich die **Adapter- und Zustandssemantik** gegen den Reducer: erfolgreicher
`play()`-Pfad, `AudioEnded`, Queue-Fortschritt, Stop während der Wiedergabe, verspätetes
Audio-Ende nach Epoch-Wechsel und Autoplay-Block. Ob Chromium MP3 dekodiert, ist damit
ausdrücklich **nicht** geprüft.

Der Seam liegt **rein auf der Testseite**. Im Produktionscode gibt es dafür keine Setter-,
Inject- oder Test-Modus-API.

### Dabei gefundener Produktionsfehler

`onAudioFinished` leerte den lokalen Puffer **vor** der Stale-Prüfung. Ein bereits
zugestellter Rückruf einer abgebrochenen Wiedergabe löschte damit einen Eintrag aus dem
Puffer der inzwischen **neu** gestarteten Wiedergabe, während die Reducer-Queue ihn noch
führte — ein stiller Audioverlust und ein Verstoß gegen I10/§19 (stale = totaler No-Op).
Der Kommentar behauptete bereits Symmetrie; der Code hielt sie nicht ein.

    RED   lokal=0, reducer=1
    GREEN lokal=1, reducer=1

Behoben: erst fragen, dann ändern. Leere Effekte heißen „veraltet oder es lief nichts" —
dann bleibt auch der lokale Puffer unberührt.

## Ein Verifikator-Fehler, kein Produktionsfehler

`verify_phase5` stand nach Slice 9e bei 12/13: der `muted`-Zweig der Zustandsmatrix übergab
nach der Ereignis-Migration weiterhin das alte Argument `'idle'`, wodurch der Zweig
`else if (w === 'muted')` nie lief. Gemessen in der Schleife:

    angefordert=muted  pres=idle   cls='idle'   anims=['orb-breathe']  capture='idle'
    nach der Korrektur pres=muted  cls='muted'  anims=[]               capture='muted'

Betroffen war ausschließlich der Verifikator. Die Produktionsableitung war korrekt und ist
zusätzlich durch den pixelgenauen `muted`-Visual-Shot belegt.

Die Branch ist an jedem Slice gefahrlos rückrollbar; es gibt keinen halb migrierten Zustand.

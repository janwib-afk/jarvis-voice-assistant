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
| 8 Voice-Integration | ⏳ teilweise (8a grün) | `899b5ef` |
| 9 Presentation ableiten | offen | — |
| 10 Race-/Stale-/Cleanup-Matrix | offen | — |
| 11 Doku + CI | offen | — |

**Backend vollständig migriert (Slices 1–6).** Session-Globals, Runtime-Aliase und
`end_session` sind entfernt; der WS-Endpunkt ist ein dünner Adapter; die Verhaltensgleichheit
ist durch die Slice-1-Charakterisierung **und** alle 14 echten Browser-Flows belegt.

**Frontend: Client Session migriert, Regionen offen.** `frontend/voice.js` ist fertig (46
Contract-Fälle). In `main.js` sind `hasGreeted` und `audioUnlocked` **entfernt** und laufen
über den Reducer (Slice 8a). **Noch nicht migriert:** `uiState.jarvisState`, `isMuted`,
`isPlaying`, `isListening`, `reconnectAttempts` und die DOM-Ableitung für `action-running`
(Slice 9).

**Wichtig für Slice 9:** `orb.className` erhält heute nur `idle|listening|thinking|speaking|
muted|error` — die CSS hängt daran. Die Presentation-Werte `disconnected`, `stopping` und
`action-running` brauchen daher eine ausdrückliche Abbildung auf diese Klassen, sonst
entsteht eine visuelle Regression. Das ist der kritische Punkt der Restmigration.

Die Branch ist an jedem Slice gefahrlos rückrollbar; es gibt keinen halb migrierten Zustand.

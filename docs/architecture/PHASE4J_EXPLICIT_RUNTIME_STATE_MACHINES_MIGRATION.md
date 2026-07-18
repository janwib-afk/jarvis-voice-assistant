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

---

## Stand der Umsetzung

| Slice | Status | Rollback-SHA |
|---|---|---|
| 1 Charakterisierung | ✅ grün | `fe9a5fe` |
| 2 Purer Conversation-Kern | ✅ grün | `1295ce3` |
| 3 Runtime-owned Manager/Sessions | ✅ grün | `37a0fc7` |
| 4 Verlauf + Confirmation migrieren | offen | — |
| 5 Queue/Worker/Stop/Disconnect migrieren | offen | — |
| 6 `assistant_core` entkoppeln | offen | — |
| 7 Purer Voice-Reducer | offen | — |
| 8 Voice-Integration | offen | — |
| 9 Presentation ableiten | offen | — |
| 10 Race-/Stale-/Cleanup-Matrix | offen | — |
| 11 Doku + CI | offen | — |

**Slices 1–3 sind rein additiv:** es wurde noch **kein** beobachtbares Produktionsverhalten
geändert. `server.py` und `assistant_core.py` sind unverändert; der neue Manager ist
verdrahtet, aber noch nicht in Benutzung. Die Branch ist an diesem Punkt jederzeit
gefahrlos rückrollbar.

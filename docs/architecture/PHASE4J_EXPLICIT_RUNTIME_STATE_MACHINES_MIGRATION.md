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
- **Commit:** `test(state): characterize conversation and voice races`

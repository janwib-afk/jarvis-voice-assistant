# Phase 4H — Typed and Versioned Wire Contracts (Umsetzung von RFC-0005)

> Stand 2026-07-18. Umsetzung von
> [RFC-0005](RFC-0005-typed-versioned-wire-contracts.md) inkl. **Amendment 1**
> (`Accepted for incremental implementation`). Basis: `origin/master`
> `48fbab76cbb1dfa6ebf5d659fc8372784f20eba6` (Squash-Merge PR #7).
>
> **TDD, vertikale Slices, je einzeln rückrollbar.** Legacy bleibt byte-/shape-exakt;
> V1 ist opt-in (`Sec-WebSocket-Protocol: jarvis.v1` bzw. `Accept:
> application/vnd.jarvis.v1+json`). Keine State-Machines, kein Capability-/Policy-Kernel,
> keine neue Dependency, kein Pydantic im Wire-Pfad.

## Post-Merge-Gate (Prompt 15 Startbedingung)

- `origin/master` = `48fbab76cbb1dfa6ebf5d659fc8372784f20eba6` (verifiziert).
- Hosted-Run **29611728248**? nein — Prompt-15-Gate: **workflow_dispatch-Run 29618703226**
  auf `sha=48fbab7`, event `workflow_dispatch`, **Fast + Browser + Gesamt success**.
- Branch `phase-4h-typed-versioned-wire-contracts` direkt von `origin/master`.

## Amendment-1-Entscheidungen (A1.A–A1.F)

Siehe RFC-0005 §„Amendment 1". Kurz: A) `Accept: application/vnd.jarvis.v1+json` +
`X-Jarvis-Correlation-ID` + `406`; B) schlanke Command-Envelope
`{protocol_version,type,correlation_id?,payload}`, Server-Felder abgelehnt, additive
ignoriert, UUIDv4; C) 64 KiB WS-Frame / 16 KiB `say_text` / 1 MiB REST-Body, Close
1007/1009/1002, REST 400/413/406; D) `secret` nicht encodierbar, keine `str()/repr()`,
event-spezifische Projektionen, Legacy-Wert redigiert bei bekanntem Runtime-Secret; E)
byte-/shape-exakt = Name/Reihenfolge/Typ/Präsenz/Wert für nicht-sensitive Inputs, Zeit/IDs
über Seams; F) Seams SEAM-WIRE/WS/REST/CONVERSATION/MIXED-WIRE/BROWSER-UI bestätigt.

## Frische Baseline (Slice 0, 2026-07-18, auf 48fbab7)

| Prüfung | Ergebnis |
|---|---|
| `compileall` (Wire-Module folgen) | EXIT 0 |
| `python -m unittest discover -s tests` | **734** Tests, 0 Failures/Errors/Skips, OK |
| `python scripts/smoke-test.py` | EXIT 0 (734 Tests, Fixture bytegleich) |
| `python tests/native/windows_native_smoke.py` | 9/9, EXIT 0 |
| `python tests/browser/e2e_functional.py --smoke` | ALLE FLOWS GRÜN, EXIT 0 |
| Hosted Browser-Gate (Run 29618703226) | success |

Baseline vollständig grün → Migration darf beginnen.

## Öffentliche Modul-Zielgrenze (`wire_protocol`)

`WireProtocol` (negotiate_ws/rest, decode_command, encode_event, present_rest),
`ProtocolContext`, `DecodedCommand`, `ConversationChannel` (+ Send-Lock, EventSink-Fabrik),
`EventSink`, `ConnectionRegistry` (runtime-owned, per-Empfänger-Encode, gemeinsame
Broadcast-Event-ID/Timestamp, eigene Session-ID je Empfänger). Interne Codec-/Validator-/
Redaction-Helfer bleiben privat. `assistant_core`/`server` kennen keine Codec-Interna und
bauen keine Wire-Dicts mehr.

---

## Slice-Log

### Slice 0 — Amendment + frische Baseline
- **Ziel:** Implementierungskonstanten (Amendment 1) verbindlich machen; Baseline neu messen.
- **Änderung:** `RFC-0005` (Amendment 1), dieses Progressdokument. Kein Produktionscode.
- **Ergebnis:** Baseline grün (s.o.).
- **Rollback:** Commit reverten (reine Doku).
- **Commit:** `docs(architecture): clarify wire protocol implementation contracts`.

### Slice 1 — Legacy charakterisieren (Golden-Contracts)
- **Ziel:** die 8 ausgehenden Legacy-Frame-Shapes, eingehende Commands, sofortiger
  Health-Frame, Broadcasts und REST-Kernverträge (Status/Shape/403/`revision`/`conflict`/
  `If-Match`/Epoch-`ts`) über die öffentlichen Seams fixieren.
- **Seam:** SEAM-CONVERSATION (WS-Frames auf `server.app`, nur `ai`/`synthesize_speech`
  ersetzt) + SEAM-REST/SEAM-WS mit eigener Runtime + Temp-Config (Fixture unberührt).
- **Test:** `tests/test_wire_legacy_golden.py` (12 Tests). Charakterisierend → erwartungs-
  gemäß grün (kein vorgetäuschtes RED).
- **GREEN:** `python -m unittest tests.test_wire_legacy_golden` → 12 OK. Volle Suite 746 OK.
- **Sicherheitsinvarianten:** `/health` öffentlich + secret-frei; geschützte Routen 403
  ohne Token; Fixture bytegleich; 0 Provideraufrufe.
- **Geänderte Dateien:** `tests/test_wire_legacy_golden.py` (neu), dieses Dokument.
- **Rollback:** Commit reverten (nur Tests/Doku).
- **Commit:** `test(protocol): lock legacy wire contracts`.
- **Offene Risiken:** `ts`-Exaktwert noch nicht eingefroren (kein Clock-Seam vor Slice 2) —
  hier nur Typ/Epoch-Charakter gelockt.

### Slice 2 — Reiner Typed Core + LegacyCodec/V1Codec
- **Ziel:** transportneutrales Typmodell + Codecs + Decode + Negotiation als reine Logik,
  ohne Produktions-Wiring. Tracer: Health Legacy + Health V1, dann Event für Event.
- **Seam:** SEAM-WIRE (öffentliche `wire_protocol`-Schnittstelle, vollständig serialisierter
  Output; Clock/ID über injizierte Seams eingefroren).
- **RED:** `python -m unittest tests.test_wire_core` — Modul/Events/Decode/Negotiation
  fehlten → 1, dann 13, dann 19 Fehler.
- **GREEN:** 32 Tests OK; import-sicher (ROOT_HANDLERS_DELTA 0). Volle Suite 778 OK.
- **Inhalt:** `wire_protocol/` (Package): `_seams` (System/Fixed-Clock, Uuid/Sequence-IdGen),
  `_model` (Sensitivity, ProtocolContext, 8 Server Events, SayText/Stop, ProtocolError),
  `_codecs` (LegacyCodec byte-/shape-exakt inkl. Epoch-`ts`, V1Codec nested Envelope +
  Sensitivität), `_decode` (Legacy + V1 mit Reserved-Field-/Version-/Größen-/Root-Prüfung),
  `_negotiation` (WS-Subprotocol + REST-Media-Type), `_protocol` (WireProtocol-Fassade).
- **Sicherheitsinvarianten:** keine neue Dependency; kein Pydantic; Import ohne I/O; V1
  weist Server-Feld-Spoofing (`reserved_field`), falsche Major (`unsupported_version`,
  Close 1002), Übergröße (`too_large`), falschen Root (`bad_root`) ab.
- **Geänderte Dateien:** `wire_protocol/*` (neu), `tests/test_wire_core.py` (neu), dieses Dok.
- **Rollback:** Commit reverten (kein Produktions-Wiring — server/assistant_core unberührt).
- **Commit:** `feat(protocol): add typed wire core and codecs`.
- **Offene Punkte:** `present_rest`/`RestResult` (REST-Presentation) entstehen in Slice 7
  gemeinsam mit der Routenmigration; `ConversationChannel`/`EventSink`/`ConnectionRegistry`
  in Slice 3.

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

### Slice 3 — Legacy Channel + Runtime-owned Registry
- **Ziel:** allen Legacy-Verkehr durch den typisierten Kanal leiten; `assistant_core`
  erhält keinen rohen WebSocket mehr; kein App-Code baut Wire-Dicts; opake Session-ID
  statt `str(id(ws))`; Broadcasts über die runtime-besessene Registry. Beobachtbarer
  Legacy-Output UNVERÄNDERT.
- **Seams:** SEAM-WIRE/MIXED-WIRE (Channel/Registry mit Fake-send), SEAM-WS/SEAM-CONVERSATION
  (echter Dialog, Golden), SEAM-REST (Broadcasts via Registry).
- **Änderungen:** `runtime.py` (`wire_protocol`/`connections` Ownership); `server.py`
  (WS-Endpoint: `connections.register`→Channel, `decode_command`, Health/Stop via
  `channel.emit`, Disconnect→`unregister`; Broadcasts→`connections.broadcast`;
  Modul-Global `ws_clients` + `broadcast_json` + `import time` entfernt);
  `assistant_core.py` (`send_error`/`send_spoken_response`/`send_action_event`/
  `process_message`/`run_action_and_respond`: `ws`→`sink`, emittieren semantische Events).
- **Implementierungsnahe Alt-Tests** (send_json/broadcast_json-gekoppelt) über den
  `tests/wire_testing.legacy_sink`-Adapter bzw. Registry-Empfänger auf gleichwertige
  öffentliche Abdeckung umgestellt (test_ws/test_confirm_flow/test_integration_research/
  test_logging_privacy/test_music_api/test_settings_api) — keine Verhaltensabdeckung gelöscht.
- **Tests:** Send-Lock serialisiert konkurrierende Emits; Disconnect leert die Registry;
  Golden-Legacy weiter byte-/shape-exakt. Volle Suite **786** grün; smoke EXIT 0;
  import-sicher (0 Root-Handler); Fixture bytegleich.
- **Sicherheitsinvarianten:** Origin/Token-Gate unverändert vor jeder Verarbeitung;
  opake Session-ID ist nie der Auth-Token; kein `secret` auf dem Wire.
- **Rollback:** diesen Commit reverten (Channel/Registry-Prep `a5727ed` bleibt nutzbar).
- **Commit:** `refactor(protocol): route legacy traffic through typed channel`.
- **Offene Risiken:** alle Verbindungen sind in Slice 3 Legacy (V1-Aushandlung erst Slice 4);
  `rt.ws_clients`-Attribut bleibt (Isolationstest), wird aber nicht mehr genutzt.

### Slice 4 — V1-WebSocket aktivieren
- **Ziel:** `Sec-WebSocket-Protocol: jarvis.v1` aushandeln + bestätigen; fehlt es → exakt
  Legacy; nur nicht unterstütztes `jarvis.vN` → Ablehnung vor accept (Close 1002);
  V1-Command-Envelope decodieren, V1-Event-Envelope senden; Session-/Event-/Correlation-/
  Timestamp-Semantik; strukturierte V1-Fehler; Spoofing abgelehnt.
- **Seam:** SEAM-WS/SEAM-CONVERSATION (echter TestClient-Handshake mit `subprotocols`).
- **RED→GREEN:** V1-Tests hängen bzw. scheitern, wenn der Endpoint auf Legacy gezwungen
  wird (Beweis, dass sie die Aushandlung beobachten) → nach Verdrahtung 10 Tests grün.
- **Änderungen:** `server.py` (WS-Endpoint: `negotiate_ws(ws.scope["subprotocols"])`,
  `accept(subprotocol=…)`, Reject vor accept mit Close 1002; Receive-Loop: `ProtocolError`
  → strukturierter `error`-Envelope, bei `close_code` schließen [unsupported_version 1002,
  too_large 1009]); sofortiger Health mit frischer Server-Correlation. `wire_protocol`:
  `new_correlation_id`.
- **Verifiziert:** sofortiger V1-Health-Envelope; kein Subprotocol → exakt Legacy-Health;
  `jarvis.v2`-only → WebSocketDisconnect; Client-`correlation_id` gespiegelt; Correlation
  über alle Events eines Commands (action start/done + response); Session-ID innerhalb einer
  Verbindung stabil, zwei Verbindungen verschieden; Spoofing von `event_id`/`session_id` →
  `reserved_field`-Fehler; falsche Major → Fehler + Close 1002. Kein Auth-/Origin-Verhalten
  geändert. Volle Suite **796** grün.
- **Sicherheitsinvarianten:** Origin/Token VOR der Versionsverarbeitung; Client bestimmt
  `event_id`/`session_id`/`timestamp`/`sensitivity` nie; Session-ID ≠ Auth-Token.
- **Rollback:** Commit reverten (Legacy bleibt der Default; V1 opt-in).
- **Commit:** `feat(protocol): add versioned websocket transport`.
- **Offene Punkte:** 64-KiB-Frame-Limit + malformed-JSON-Close (1007/1009 am Frame-Level)
  und die vollständige Fault-Matrix → Slice 9; Mixed-Broadcasts (V1+Legacy gleichzeitig,
  gemeinsame Broadcast-Event-ID) → Slice 5.

### Slice 5 — Mixed Clients und Broadcasts
- **Ziel:** Legacy- und V1-Verbindungen laufen gleichzeitig; ein REST-getriggerter
  Broadcast erreicht alle Clients versionsgerecht; ein semantischer Broadcast teilt
  Event-ID + Correlation, je Empfänger aber die eigene Session-ID; tote Verbindung wird
  entfernt, andere erhalten das Event weiter.
- **Seam:** SEAM-MIXED-WIRE (echte parallele TestClient-WS, eigene Runtime + Temp-Config).
- **Änderung:** `wire_protocol._channel` `broadcast(event, *, correlation_id=None)` —
  gemeinsame Event-ID + Correlation + Timestamp für alle Empfänger; `correlation_id`
  bindet in Slice 7 die REST-Request-Correlation.
- **Tests:** Legacy-Client (byte-/shape-exaktes `app_event`) + V1-Client (Envelope)
  gleichzeitig; zwei V1-Clients → gleiche `event_id`/`correlation_id`, verschiedene
  `session_id`; geschlossene Verbindung entfernt, andere empfangen weiter. Volle Suite
  **799** grün; Fixture bytegleich.
- **Sicherheitsinvarianten:** kein konkurrierender Sendefehler (Send-Lock je Kanal);
  Legacy-Empfänger sehen nie V1-Metadaten.
- **Rollback:** Commit reverten.
- **Commit:** `feat(protocol): support mixed-version broadcasts`.
- **Offene Punkte:** REST-Response ↔ Broadcast gemeinsame Correlation erst mit REST-V1
  (Slice 7); Frame-Size/malformed → Slice 9.

### Slice 6 — First-Party-WebSocket-Frontend auf V1
- **Ziel:** zentraler Frontend-Wire-Adapter `frontend/wire.js` bietet `jarvis.v1` an,
  erzeugt V1-Commands, decodiert V1-Envelopes zu UI-Events der Legacy-Form; `main.js`
  migriert; keine visuelle/funktionale UI-Änderung.
- **Seam:** SEAM-BROWSER-UI (echtes Playwright-Verhalten, kein Source-String-Test).
- **Änderung:** `frontend/wire.js` (createSocket mit Subprotocol, sayText/stop als
  V1-Command bzw. Legacy-Fallback, decodeFrame V1-Envelope→Legacy-Form inkl.
  error.message→text, unbekannt/kaputt→null); `main.js` (connect/onmessage/send über
  JarvisWire, `window.__jarvisProtocol`); `index.html` (wire.js vor main.js). Der
  vestigiale `status`-Handler bleibt als dokumentierter, produzentenloser Legacy-Fallback.
- **Test:** neuer Playwright-Flow `protocol_v1` prüft `window.__jarvisProtocol==='jarvis.v1'`
  UND `window.__lastWs.protocol==='jarvis.v1'` (echte Aushandlung gegen den e2e_server, der
  den realen server.app nutzt). Alle Functional-Flows grün; Visual 0.0000% Diff; A11y 22/22;
  Reduced-Motion 16/16. Python-Suite 799 grün.
- **Sicherheitsinvarianten:** keine Wire-Interna im UI verstreut; Auth/Origin/Token
  unverändert.
- **Rollback:** Commit reverten (Legacy-Handshake ohne Subprotocol bleibt funktionsfähig).
- **Commit:** `feat(frontend): migrate websocket client to protocol v1`.

### Slice 7 — REST V1 nach Routenfamilien (gemeinsamer Seam)
- **Ziel:** V1-REST-Presentation für alle Routenfamilien (Health, Settings, Music,
  Dashboard+App-Open, Launcher/Profiles) über EINEN gemeinsamen REST-Seam. Legacy ohne
  V1-Accept bleibt exakt; HTTP-Status maßgeblich; REST-`session_id` immer null.
- **Seam:** SEAM-REST (echte Route mit Status/Header/Body).
- **Änderung:** `server.py` `RestV1Middleware` (BaseHTTPMiddleware): Aushandlung via
  `Accept: application/vnd.jarvis.v1+json`; Legacy → Passthrough (byte-exakt); V1 →
  `wire_protocol.rest_envelope` + `X-Jarvis-Correlation-ID`-Echo; unbekannte Vendor-Version
  → `406`; `_redact_health_v1` (öffentliche Health-Projektion ohne lokale Pfade). Die
  REST-getriggerten Broadcasts (app_open/music/launcher) binden die Request-Correlation
  (`_rest_correlation`); `wire_protocol.rest_envelope`/`rest_error`. V1-Health-Event
  (WS+REST) redigiert Warnungen → Anzahl (`warnings_count`), `sensitivity=public`.
- **Tests:** Health legacy unverändert; V1-Health-Envelope redigiert (kein Pfad),
  Correlation in Body+Header gespiegelt, 406 bei v2; Settings/Launcher V1-Envelope +
  Legacy exakt; Auth (403) bleibt vor der Versionsverarbeitung; app_open-Broadcast teilt
  die Request-Correlation mit der REST-Response. Volle Suite **808** grün; Fixture bytegleich.
- **Sicherheitsinvarianten:** kein Secret in Body/Header/Fehler; V1-Health ist echte sichere
  Projektion (nicht kosmetisch); Legacy-Health-Restrisiko bleibt benannt.
- **Rollback:** Commit reverten (Middleware entfällt → nur Legacy).
- **Commit:** `feat(protocol): present rest routes over protocol v1`.
- **Offene Punkte:** Frame-Size/malformed-Vertrag (WS) + volle Fault-Matrix → Slice 9;
  Frontend-REST auf V1 → Slice 8.

### Slice 8 — First-Party-REST-Frontend auf V1
- **Ziel:** der zentrale Wire-Adapter setzt den V1-Accept + Correlation-Header, erkennt den
  Vendor-Content-Type, entpackt V1-Envelopes und reicht Ergebnisse/Fehler unverändert an
  die bestehende UI. `main.js`/`settings.js`/`music.js` migriert.
- **Seam:** SEAM-BROWSER-UI (echte REST-Flows im Browser).
- **Änderung:** `frontend/wire.js` `fetchV1(url, options)` — setzt Accept
  `application/vnd.jarvis.v1+json` + `X-Jarvis-Correlation-ID`, entpackt die Envelope zu
  ihrem payload (= Legacy-Body), sodass `.ok/.status/.json()` unverändert bleiben;
  Legacy-Antwort ohne Vendor-Content-Type bleibt die echte Response. Alle 11 `fetch`-Sites
  in main/settings/music auf `JarvisWire.fetchV1` umgestellt; `X-Jarvis-Token` und
  Settings-`If-Match` bleiben in `options.headers` erhalten.
- **Verifiziert:** alle Functional-Flows grün (inkl. `settings`/`settings_conflict` mit
  If-Match/revision/409 über V1, `monitor_keyboard`, `window_modes`); Visual 0.0000% Diff;
  A11y 22/22; Reduced-Motion 16/16; Python-Suite 808 grün. Keine visuelle/funktionale
  UI-Änderung; deutsche Fehlermeldungen/Revision-/Conflict-Verhalten erhalten.
- **Rollback:** Commit reverten (Frontend fällt auf rohe fetch/Legacy zurück).
- **Commit:** `feat(frontend): migrate rest consumers to protocol v1`.

### Slice 9 — Fault-/Security-Matrix vervollständigen
- **Ziel:** verbleibende Matrixlücken schließen; kritische Race-/Stop-/Mixed-/Broadcast-
  Tests 5× flakefrei.
- **Änderung:** `server.py` WS-Receive auf `receive_text` + Frame-Größenvertrag
  (64 KiB → Close 1009, VOR JSON-Decoding) + malformed JSON → Close 1007 (V1: strukturierter
  `error` vor Close); REST-Middleware: V1-Body > 1 MiB → 413. `wire_protocol._codecs`:
  `action.detail` bei sensiblen Actions (SCREEN/CLIPBOARD/PROJECT_CONTEXT/RESEARCH) unter
  V1 minimiert (Legacy exakt).
- **Tests:** Unit (Timestamp RFC3339 UTC ms; Event-ID-Eindeutigkeit; action.detail
  minimiert V1 / exakt Legacy; Fehlermeldung ohne Rohwert-Echo) + Integration (WS malformed
  →1007, oversize→1009, oversize say_text, unknown command hält Verbindung offen; REST
  oversize→413). Frühere Slices decken bereits: falscher Root/fehlende Felder/unbekannte
  Major/ID-Spoofing/gemeinsame Broadcast-Event-ID/eigene Session-ID/Health-Pfad-Redaction.
- **5×-Flake:** `test_wire_mixed` + `test_wire_v1_ws` + `test_wire_fault` + `test_ws`
  fünfmal grün. Volle Suite **819** grün; smoke EXIT 0. (`wire_testing`-Import robust
  gemacht — `from tests import ...` —, damit Module auch standalone laufen.)
- **Sicherheitsinvarianten:** Secret-Sentinels nie im serialisierten Output/Logs; keine
  Replay-/Exactly-once-Behauptung.
- **Rollback:** Commit reverten.
- **Commit:** `test(protocol): complete wire fault and privacy matrix`.

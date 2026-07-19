# Jarvis – WebSocket-Protokoll (Ist-Zustand, Dual-Stack: Legacy + V1)

> Dokumentiert das **aktuelle** WS-Protokoll (`server.websocket_endpoint`,
> + typisiertes Modul [`wire_protocol/`](../../wire_protocol/)). Stand 2026-07-18. Alle
> Beispielwerte synthetisch. Bezug:
> [../quality/TEST_SEAMS.md](../quality/TEST_SEAMS.md) (SEAM-WS/-CONVERSATION/-WIRE/-MIXED-WIRE),
> [../architecture/RFC-0005-typed-versioned-wire-contracts.md](../architecture/RFC-0005-typed-versioned-wire-contracts.md).
>
> **Seit Phase 4H (RFC-0005) ist der Endpunkt Dual-Stack:**
> - **Ohne** `Sec-WebSocket-Protocol`-Angabe (Default) spricht der Server das unten
>   dokumentierte **Legacy-Protokoll** — `legacy-unversioned`, **kein**
>   `protocol_version`-Feld, byte-/shape-exakt wie zuvor.
> - Bietet der Client **`jarvis.v1`** an, wird V1 ausgehandelt und bestätigt; alle
>   Frames laufen dann als typisierte **V1-Envelope** (Abschnitt „V1-Protokoll" unten).
>
> Beide Wege erzeugen dieselben semantischen Nachrichten; nur die Serialisierung
> unterscheidet sich (`wire_protocol.LegacyCodec` bzw. `V1Codec`). Die Origin-/Token-
> Prüfung ist identisch und läuft **vor** jeder Versionsverarbeitung.

## Verbindung & Token

- **Endpunkt:** `GET`-Upgrade auf `/ws?token=<SESSION_TOKEN>`.
- **Token:** als Query-Parameter `token`; geprüft mit `secrets.compare_digest`
  (bytewise, `server.py:108`). Das Token wird beim Serverstart erzeugt
  (`secrets.token_urlsafe(24)`) und nur in die ausgelieferte Seite injiziert.
- **Origin-Policy** (`actions.is_origin_acceptable`, `actions.py:415`):
  - lokale Origins (`http(s)://localhost|127.0.0.1|::1`) → erlaubt;
  - literaler Origin `"null"` → **nur mit gültigem Token** (pywebview/WebView2-
    Sandbox-Sonderfall);
  - fehlender (`None`) oder fremder Origin → abgelehnt.
- **Ablehnung:** unzulässiger Origin **oder** ungültiges Token → `ws.close(code=1008)`
  (kein Accept). Reihenfolge: erst Origin-Policy, dann harte Token-Prüfung.
- **Nach Accept:** der Server sendet **sofort** einen `health`-Frame
  (`server.py:129`). Clients, die auf eine Antwort warten, müssen diesen zuerst
  abholen.

## Client-Frames (eingehend)

Der Server liest jeden Frame als Text (`ws.receive_text`), prüft die **Frame-Größe**
(> 64 KiB → Close 1009) und decodiert dann JSON (malformed → Close 1007; im V1-Modus mit
vorangehendem strukturiertem `error`). Danach folgt das Legacy- bzw. V1-Decoding.

| Frame | Felder | Bedeutung |
|---|---|---|
| Text | `{"text": "<nutzertext>"}` | normale Nutzernachricht; `text` wird `.strip()`-t. Leerer Text nach Strip → ignoriert. |
| Stop (explizit) | `{"type": "stop"}` | laufende Verarbeitung abbrechen, Queue leeren |
| Stop (gesprochen) | `{"text": "Stopp"}` | wird über `actions.is_stop_command` als Stop erkannt (kurze reine Stopp-Äußerung) und wie ein Stop-Frame behandelt |

Andere `type`-Werte ohne `text` werden ignoriert (kein Fehlerframe).

## Server-Frames (ausgehend)

| Frame `type` | Felder | Quelle | Wann |
|---|---|---|---|
| `health` | `warnings: [str]` | `server.py:129`, `broadcast_health` | direkt nach Accept; Push nach Settings-Save |
| `response` | `text: str`, `audio: str` (Base64 oder `""`) | `assistant_core.send_spoken_response` | gesprochene Antwort; `audio=""` wenn TTS aus/fehlgeschlagen |
| `action` | `phase: "start"\|"done"\|"error"`, `action: str`, `label: str`, `detail: str`, `ts: float` | `assistant_core.send_action_event` | Aktions-Lebenszyklus für die Historie |
| `error` | `component: str`, `text: str`, `hint: str` | `assistant_core.send_error` | strukturierter Fehler; `component ∈ {llm, tts, browser, action, config}` |
| `stop` | — | `server.py:189` | Bestätigung eines empfangenen Stops |

**Broadcast-Frames** (von REST-Routen an alle Clients, gleiche Verbindung):
`{"type": "music_changed", "selected": str, "ts": float}`,
`{"type": "app_event", "ok": bool, "app": str|null, "name": str, "message": str, "ts": float}`,
`{"type": "launcher_changed", "kind": str, "active_profile": str, "ts": float}`.

Es gibt **kein** eigenes „ack" pro Nachricht; die Antwort ist der `response`-Frame.

## Reihenfolge- und Queue-Garantien

- Nachrichten werden über eine `asyncio.Queue` **strikt sequenziell** von genau
  einem Worker abgearbeitet (`server.py:145`). Eine zweite Nachricht während einer
  laufenden Aktion wartet in der Queue.
- Für eine Nachricht mit gesprochenem Text **und** Aktion gilt: erst der
  `response`-Frame (gesprochener Teil), dann `action`-Frames (`start` … `done`),
  dann ggf. ein weiterer `response`-Frame (Zusammenfassung des Aktionsergebnisses).
- Riskante Aktion (`CONFIRM_ACTIONS`, aktuell `MEMORY_FORGET`): der Server sendet
  zunächst eine Rückfrage als `response`-Frame und wartet auf die nächste Nachricht
  (Ja/Nein), bevor er ausführt (`assistant_core.process_message`, `:707`).

## Stop-Semantik

Bei `{"type":"stop"}` **oder** erkanntem Stop-Wort (`server.py:180`):
1. eine laufende Verarbeitung (falls aktiv) wird abgebrochen;
2. die Queue wird geleert (wartende Nachrichten verworfen);
3. die offene Rückfrage der Session verfällt;
4. ein `stop`-Frame wird gesendet;
5. war eine Aktion aktiv, folgt zusätzlich `{"type":"response","text":"Okay,
   gestoppt.","audio":""}`.

Die **Session lebt weiter**: eine nach dem Stop gesendete Nachricht wird normal
verarbeitet. Ein reiner Stopp beendet die Verbindung nicht.

> Seit RFC-0006 (Phase 4J) entscheidet über diese Reihenfolge der reine
> Transitionskern der `ConversationSession` (`conversation/_core.py`); der WS-Endpunkt
> ist ein dünner Adapter ohne eigene Queue-, Worker- oder Task-Wahrheit. Das beobachtbare
> Frame-Verhalten ist unverändert.

## Disconnect & Fehlerverhalten

- **Disconnect** (`WebSocketDisconnect`): das `finally` schließt die Session über den
  `ConversationManager` — eine laufende Verarbeitung wird garantiert mitgenommen (kein
  Task-Leak) — und meldet den Kanal von der Verbindungsregistry ab. Das frühere
  `assistant_core.end_session` existiert seit RFC-0006 nicht mehr.
- **Unerwartete Verarbeitungsfehler** beenden **nie** die Verbindung: der Worker
  loggt und sendet `{"type":"error","component":"llm","text":"Interner Fehler bei
  der Verarbeitung."}` (`server.py:161`).
- **Provider-/Aktionsfehler** werden als `error`-Frame mit passender `component`
  gemeldet; die Verbindung bleibt nutzbar.

## Audioübertragung

- Audio wird **inline** im `response`-Frame als Base64-String (`audio`) übertragen
  (`assistant_core.send_spoken_response`, `:270`) — kein separater Binär-Frame.
- Kein Audio (TTS aus/fehlgeschlagen) → `audio: ""`; bei komplettem TTS-Ausfall
  zusätzlich ein `error`-Frame `component:"tts"`.

## Sicherheit (Zusammenfassung)

- SI-4 (nur `127.0.0.1`), Origin-Policy + Token-Gate (SI-6-nah); `null`-Origin nur
  mit Token; untrusted LLM-Ausgabe autorisiert nur registrierte Actions (SI-1);
  Secrets nie in Frames (SI-5). Details:
  [../security/SECURITY_REQUIREMENTS.md](../security/SECURITY_REQUIREMENTS.md).

---

## V1-Protokoll (opt-in, `jarvis.v1`)

### Aushandlung

- Der Client verbindet mit `Sec-WebSocket-Protocol: jarvis.v1`
  (`new WebSocket(url, ['jarvis.v1'])`). Der Server handelt über
  `wire_protocol.negotiate_ws(offered)` aus und **bestätigt** das Subprotocol im
  Accept (`ws.accept(subprotocol="jarvis.v1")`).
- Bietet der Client **kein** Subprotocol an → exakt Legacy (kein Accept-Subprotocol).
- Bietet der Client **nur** nicht unterstützte `jarvis.vN` an (z.B. `jarvis.v2`) →
  Ablehnung **vor** Accept mit `ws.close(code=1002)`.
- Additive/unbekannte weitere Subprotocol-Angebote neben `jarvis.v1` sind unschädlich
  (das erste unterstützte gewinnt).

### V1-Envelope (jede Nachricht)

Alle V1-Nachrichten (Server→Client) sind eine geschachtelte Hülle:

```json
{
  "protocol_version": 1,
  "type": "response",
  "event_id": "<uuid4>",
  "correlation_id": "<uuid4>",
  "session_id": "<uuid4>",
  "timestamp": "2026-07-18T12:34:56.789Z",
  "sensitivity": "personal",
  "payload": { "…": "eventspezifisch" }
}
```

- **`protocol_version`** — Integer-Major `1`. Additive Erweiterungen bleiben `1`.
- **`event_id`** — server-erzeugte UUIDv4 **je semantischem Event**. Ein Broadcast ist
  ein Event → **dieselbe** `event_id` an alle Empfänger (keine Replay-/Dedup-Garantie).
- **`correlation_id`** — verbindet einen Client Command (bzw. REST-Request) mit **allen**
  Folge-Events. Eine gültige Client-`correlation_id` (UUIDv4) wird gespiegelt; sonst
  server-erzeugt. Spontane Events (Health nach Connect, Settings-Broadcast) tragen eine
  frische Server-Correlation.
- **`session_id`** — server-erzeugte opake UUIDv4 **pro Verbindung** (stabil innerhalb der
  Verbindung, nach Reconnect neu). **Nicht** der Auth-Token, **nicht** `str(id(ws))`.
  Bei einem Broadcast erhält jeder Empfänger seine **eigene** `session_id`.
- **`timestamp`** — RFC3339-UTC mit Millisekunden (`…Z`), aus dem Clock-Seam.
- **`sensitivity`** — serverseitige Datenklasse (`public`/`local`/`personal`/`sensitive`);
  **`secret` erscheint nie** (der Encoder ist fail-closed). Der Client kann sie nie setzen
  oder herabstufen.

### Client Commands (V1-Envelope, eingehend)

Schlanke Command-Hülle `{protocol_version, type, correlation_id?, payload}`:

| `type` | Payload | Wirkung |
|---|---|---|
| `say_text` | `{"text": "<nutzertext>"}` (≤ 16 KiB) | wie Legacy-`{text}` |
| `stop` | `{}` | wie Legacy-`{type:"stop"}` |

- Der Client darf **nur** `protocol_version`, `type`, optional `correlation_id`, `payload`
  setzen. Server-Felder (`event_id`/`session_id`/`timestamp`/`sensitivity`) im Command →
  Fehler `reserved_field`. Additive unbekannte Felder werden ignoriert.
- `correlation_id` muss, falls gesetzt, eine UUIDv4 sein.

### Server Events (V1, ausgehend)

Dieselben acht semantischen Events wie Legacy, jeweils als V1-Envelope mit `type` ∈
`health`, `response`, `action`, `error`, `stop`, `music_changed`, `app_event`,
`launcher_changed`. Unterschiede zur Legacy-Projektion:

- **`health`** — `payload` ist die **öffentliche Projektion** `{"warnings_count": int}`
  (`sensitivity=public`); die Legacy-Warnliste/Pfade erscheinen nicht.
- **`action`** — bei sensiblen Actions (`SCREEN`, `CLIPBOARD`, `PROJECT_CONTEXT`,
  `RESEARCH`) ist `detail` unter V1 minimiert (Legacy exakt).
- **`error`** — strukturiert: `{component, message, hint, code, retryable}`. Der
  Frontend-Adapter bildet `message` auf das Legacy-Feld `text` ab.

### V1-Fehler- und Close-Semantik

| Situation | Reaktion |
|---|---|
| Malformed JSON | strukturierter `error` (`code:"malformed_json"`) → Close **1007** |
| Frame > 64 KiB | `error` (`code:"too_large"`) → Close **1009** |
| `say_text` > 16 KiB | `error` (`code:"too_large"`), Verbindung **bleibt offen** |
| Falsche Major-Version | `error` (`code:"unsupported_version"`) → Close **1002** |
| Server-Feld im Command | `error` (`code:"reserved_field"`), Verbindung bleibt offen |
| Unbekannter `type` | `error` (`code:"unknown_command"`), Verbindung bleibt offen |

Fehlermeldungen echoen **nie** den Rohwert der fehlerhaften Eingabe.

## Nicht abgedeckt / offen

- **Reconnect-Resume** ist ein Nicht-Ziel: nach Reconnect ist die `session_id` neu; es gibt
  keinen Nachrichten-Replay.
- **obslog-/Audit-Korrelation** (durchgängige `correlation_id` in den Betriebslogs) ist in
  Phase 4H **nicht** verdrahtet (RFC-0005 Nicht-Ziel dieser Phase).
- Das **Legacy-Restrisiko** des Health-Frames (Warntexte/Pfade) besteht nur im
  Legacy-Modus; V1-Health ist die sichere `warnings_count`-Projektion.

# RFC-0005 — Typed and Versioned Wire Contracts

- **Status:** Accepted for incremental implementation
- **Datum:** 2026-07-17 (Proposed); 2026-07-17 (Accepted nach Nutzerfreigabe)
- **Autor:** Masterplan Prompt 14 (Phase 4G), Architektur-only
- **Basis:** `origin/master` `97f94b5b7ceb6ff41ae6dc6cd020148aec271827` (Merge von PR #6, RFC-0004)
- **Nachfolge-Umsetzung:** Prompt 15 (Phase 4H) — **dieser RFC implementiert nichts**
- **Bezug:** RFC-0001 (Action deep module), RFC-0002 (Composition Root), RFC-0003
  (Versioned Configuration), RFC-0004 (Structured Operational Logging & Redaction)

> **Dieser RFC ist reine Architektur.** Er ändert keinen Produktionscode, keine Tests,
> keine Workflows und keine Dependencies. Er inventarisiert die Ist-Verträge, vergleicht
> Architekturvarianten und legt die Entscheidungen D1–D12 fest. Die Produktion nutzt nach
> Annahme weiterhin die **Legacy-Verträge**; die Umsetzung beginnt erst mit Prompt 15.

> **Umsetzungsstatus (2026-07-18, Phase 4H — IMPLEMENTIERT):** Dieser RFC ist inkl.
> [Amendment 1](#amendment-1--prompt-15-implementation-contracts) in Prompt 15
> als tiefes Modul [`wire_protocol/`](../../wire_protocol/) umgesetzt (Variante C). WS-Opt-in
> über `Sec-WebSocket-Protocol: jarvis.v1`, REST-Opt-in über `Accept:
> application/vnd.jarvis.v1+json`; ohne Opt-in bleiben beide Transporte **byte-/shape-exakt
> Legacy**. Nested V1-Envelope, server-erzeugte `event_id`/`session_id`/`timestamp`,
> gespiegelte/erzeugte `correlation_id`, serverseitige `sensitivity` mit fail-closed
> Redaction (`secret` nie auf dem Wire), strukturierte V1-Fehler + Close-Codes
> (1002/1007/1009) / HTTP-Status (400/406/413). Frontend (`frontend/wire.js`) verhandelt V1
> für WS und REST. Belegter Verlauf pro Slice:
> [PHASE4H_TYPED_WIRE_MIGRATION.md](PHASE4H_TYPED_WIRE_MIGRATION.md). Ist-Verträge:
> [../contracts/WEBSOCKET_PROTOCOL.md](../contracts/WEBSOCKET_PROTOCOL.md),
> [../contracts/REST_CONTRACTS.md](../contracts/REST_CONTRACTS.md).

---

## 1. Kontext und Ist-Befund

Jarvis kommuniziert mit dem Frontend über **einen** WebSocket-Endpunkt `/ws` und **17**
JSON-REST-Routen. Die Nachrichten sind heute **untypisiert und unversioniert**
(`legacy-unversioned`): Frames werden als freie `dict`-Literale direkt an zwei Stellen
erzeugt (`server.py`, `assistant_core.py`), es gibt keinen Serialisierungs-Seam, keine
`protocol_version`, keine `event_id`/`correlation_id`, keine Sensitivitätsklasse und nur
teilweise Zeitstempel (Epoch-Float). Das erschwert Client-Korrelation, Versionierung,
maschinelle Fehlerbehandlung und eine zentrale Redaction.

Beweisgestützt aus `server.py`, `assistant_core.py`, `frontend/main.js`, `health.py`,
`docs/contracts/WEBSOCKET_PROTOCOL.md`, `docs/contracts/REST_CONTRACTS.md` sowie den WS-/
REST-/Browser-Tests (Details in §3).

## 2. Ziele und Nicht-Ziele

**Ziele.**
- REST- und WS-Nachrichten **typisieren** und **versionieren** (`protocol_version`).
- V1-Metadaten definieren: `event_id`, `correlation_id`, `session_id`, `timestamp`,
  `sensitivity`.
- Legacy-Verträge über einen **Compatibility Adapter** byte-/shape-exakt erhalten.
- Eine **Versionierungs- und Deprecation-Strategie** festlegen.
- Einen **einzigen Redaction-/Sensitivity-Chokepoint** für ausgehende Nachrichten schaffen
  (kein `secret` auf dem Wire, fail-closed).

**Nicht-Ziele (ausdrücklich).** Kein Protokoll wird implementiert. Keine Conversation-/
Voice-/Job-State-Machine, kein Capability-/Policy-Kernel, keine Job-Persistenz/Replay/
Event-Sourcing/Outbox/Saga/Exactly-once, keine Änderung an Auth-/Token-/Origin-Semantik,
kein Verschieben des Query-Tokens, kein Entfernen von `[ACTION:…]`, keine Umstellung von
Audio auf Binary/Streaming, kein Audit/Telemetrie/Remote-Logging, keine Änderung an
Config-/Memory-/Provider-Verträgen. Vollständige `correlation_id`-Durchreichung in
`obslog`/Audit/Tracing bleibt **Phase 11** (siehe D12).

## 3. Producer-/Consumer- und Contract-Inventar (Ist)

Gezählt wurden nur JSON-Wire-Routen: **17 REST-Routen + 1 WS-Endpunkt**. `GET /`
(HTML-Auslieferung) und `/static` (StaticFiles) gehören **nicht** zum Wire-RFC.

### 3.1 WebSocket `/ws`

- **Handshake:** Token als Query-Param `token` (`secrets.compare_digest`), Origin-Policy
  (`actions.is_origin_acceptable`), danach **sofortiger `health`-Frame** nach Accept
  (`server.py`).
- **Eingehend (Client→Server):** `{ "text": <str> }` (Gesprächsbeitrag) und
  `{ "type": "stop" }` (Stop). Andere `type`-Werte ohne `text` werden ignoriert (kein
  Fehlerframe).

**Ausgehende Frames (Server→Client) — 8 Typen, als freie Dicts erzeugt:**

| Frame `type` | Felder | Producer | Richtung/Trigger | `ts` | Sensitivität (Ist) |
|---|---|---|---|---|---|
| `health` | `warnings:[str]` | `server` (nach Accept), `broadcast_health` | Accept + Push nach Settings-Save | — | local (Warnungen können lokale Pfade nennen) |
| `response` | `text:str`, `audio:str(base64|"")` | `assistant_core.send_spoken_response` | gesprochene Antwort | — | personal/sensitive (Antworttext) |
| `action` | `phase:start|done|error`, `action:str`, `label:str`, `detail:str`, `ts:float` | `assistant_core.send_action_event` | Aktions-Lebenszyklus | ✓ | personal/sensitive (`detail` kann Ausschnitte tragen) |
| `error` | `component:str`, `text:str`, `hint:str` | `assistant_core.send_error` | strukturierter Fehler | — | local/personal |
| `stop` | — | `server` | Stop-Bestätigung | — | public |
| `music_changed` | `selected:str`, `ts:float` | `server` (Broadcast) | nach `POST /music/selection` | ✓ | local (Dateiname) |
| `app_event` | `ok:bool`, `app:str|null`, `name:str`, `message:str`, `ts:float` | `server` (Broadcast) | nach `POST /commands/app/open` | ✓ | local |
| `launcher_changed` | `kind:str`, `active_profile:str`, `ts:float` | `server` (Broadcast) | nach Launcher-Mutation | ✓ | local |

- **Ordering (Ist):** per Verbindung FIFO in Sendereihenfolge. Ein Command kann **mehrere**
  Frames auslösen: `response` (gesprochen) → `action`(`start`…`done`) → ggf. weiterer
  `response` (Zusammenfassung). REST-Broadcasts (`music/app/launcher`) **verschachteln**
  sich mit Gesprächsantworten auf derselben Verbindung.
- **Korrelation (Ist):** keine. Kein `event_id`, kein `correlation_id`.
- **Session (Ist):** `session_id = str(id(ws))` — interne CPython-Objekt-ID, nur intern
  (Historie/`pending_confirm`), **nie** auf dem Wire. `ws_clients` speichert rohe
  WebSockets ohne individuellen Protocol Context.

### 3.2 REST-Routen (17)

| Route | Methode | Auth | Erfolg (Ist) | Fehler/Status (Ist) |
|---|---|---|---|---|
| `/health` | GET | **keine (öffentlich)** | **bare** Report `{ok,warnings,services,startup}` | — |
| `/settings` | GET | Token | `{ok,settings,warnings,revision}` | `403` |
| `/settings` | POST | Token | `{ok,applied,warnings,revision[,degraded]}` | `400`,`403`,`409`(`conflict:true`),`500` |
| `/music/files` | GET | Token | `{ok,folder,selected,files,error}` | `403` |
| `/music/selection` | POST | Token | `{ok,selected}` + Broadcast | `400`,`403`,`404/500` |
| `/dashboard/state` | GET | Token | `{ok,health,tasks,today_inbox,vault,apps,data_loaded,last_refresh}` | `403` |
| `/commands/app/open` | POST | Token | **bare** `{ok,app,name,message}` | `400`,`403`,`404`,`500` |
| `/launcher/apps` | GET | Token | `{ok,active_profile,apps}` | `403` |
| `/launcher/apps/{id}/toggle` | POST | Token | `{ok,apps}` | `400`,`404`,`403`,`500` |
| `/launcher/monitors` | GET | Token | `{ok,monitors}` | `403` |
| `/launcher/apps/{id}/placement` | POST | Token | `{ok,apps}` | `400`,`404`,`403`,`500` |
| `/launcher/profiles` | GET | Token | `_profiles_response {ok,active_profile,profiles}` | `403` |
| `/launcher/profiles` | POST | Token | `_profiles_response` | `400`,`403`,`500` |
| `/launcher/profiles/{id}/activate` | POST | Token | `_profiles_response` | `404`,`403`,`500` |
| `/launcher/profiles/{id}/duplicate` | POST | Token | `_profiles_response` | `404`,`400`,`403`,`500` |
| `/launcher/profiles/{id}/rename` | POST | Token | `_profiles_response` | `404`,`400`,`403`,`500` |
| `/launcher/profiles/{id}` | DELETE | Token | `_profiles_response` | `400`,`404`,`403`,`500` |

- **Auth (Ist):** geschützte Routen prüfen `x-jarvis-token`-Header gegen
  `runtime.session_token`. `/health` und `GET /` sind öffentlich.
- **Erfolgsform uneinheitlich:** meist `{ok:true,…}`, aber `/health` und
  `/commands/app/open` liefern **bare** Domänen-Dicts ohne einheitlichen Wrapper.
- **Fehlerform überwiegend** `{ok:false,errors:[str]}`, aber `/music/files` nutzt
  `error:<str>` (singular) im Erfolgsbericht.

### 3.3 Consumer (Frontend)

`frontend/main.js` liest im WS-`onmessage`-Switch die Typen `response`, `status`,
`health`, `stop`, `action`, `app_event`, `launcher_changed`, `music_changed`, `error`.
REST-Consumer: `/settings`, `/music/*`, `/dashboard/state`, `/commands/app/open`,
`/launcher/*` (Header `X-Jarvis-Token`, `If-Match` optional bei Settings).

## 4. Dokumentationsabweichungen (Doc ≠ Code)

1. **`status`-Frame:** `frontend/main.js` behandelt `data.type === 'status'`
   (`status.textContent = data.text`), **aber kein Producer erzeugt ihn** und
   `WEBSOCKET_PROTOCOL.md` dokumentiert ihn nicht. → **vestigialer Consumer-Handler.**
2. **Settings-Zusätze fehlen im Doc:** `REST_CONTRACTS.md` dokumentiert bei `GET/POST
   /settings` **nicht** `revision`, `conflict:true` (409), `degraded` und `If-Match`
   (RFC-0003-Additive). → **Doc veraltet gegenüber Code.**
3. Beide Contract-Docs sind als `legacy-unversioned` markiert und ansonsten codetreu.

> Diese Abweichungen werden in Prompt 14 **nicht** still korrigiert. Die Legacy-Contract-
> Docs beschreiben weiterhin den Ist-Vertrag; die Korrektur/Aktualisierung erfolgt mit der
> Umsetzung (Prompt 15), wenn V1 eingeführt wird.

## 5. Entscheidungstreiber

- **Sicherheit/Datenschutz:** ein einziger Redaction-Chokepoint für „kein `secret` auf dem
  Wire" und die Health-/Detail-Redaction (§17, §22).
- **Locality/Depth:** heute verstreute Producer ohne Seam; Versionierung/Metadaten/Redaction
  gehören an **einen** Ort.
- **Legacy-Kompatibilität:** das laufende Frontend darf nicht brechen; Legacy muss
  byte-/shape-exakt bleiben.
- **Testbarkeit:** öffentliche Codec-Roundtrips + exakte Legacy-Shapes + deterministische
  IDs/Zeit über Seams.
- **Keine neue Dependency:** Pydantic v2 ist zwar transitiv (FastAPI) vorhanden, wird aber
  im Wire-Pfad **nicht** genutzt (D2).

## 6. Architekturvarianten (Design-it-twice)

### Variante A — Endpoint-nahe typisierte Modelle + additive Metadaten
Typen/Metadaten additiv auf bestehende Dicts, je Producer. **Breite** Schnittstelle,
**flache** Tiefe; Redaction/Versionierung verstreut; Legacy-Client sieht V1-Metadaten
(leaky); Sicherheitsgarantie schwer zentralisierbar. **Deletion-Test:** kein Modul zu
löschen — Komplexität diffus. → verletzt Locality/Depth.

### Variante B — Einheitliche REST-/WS-Envelope
Eine Envelope für beide Transporte. **Impedance-Mismatch:** REST hat HTTP-Status als
eigenen Kanal; die gemeinsame Envelope drückt REST in ein Frame-Modell. Braucht ohnehin
einen Legacy-Adapter, der die Envelope entfernt. → erzwingt künstliche Symmetrie.

### Variante C — Transportneutraler Typed Core + LegacyCodec/V1Codec **(gewählt)**
Tiefes Modul `wire_protocol` mit **kleiner** Schnittstelle (Command decodieren, Server
Event encodieren, REST-Result präsentieren); getrennte `LegacyCodec` + `V1Codec`; ein
Redaction-/Sensitivity-Chokepoint. Legacy byte-exakt, V1 opt-in. **Deletion-Test:** löscht
man es, tauchen Versionierung + Redaction + Metadata über alle 8 Frames + 17 Routen wieder
auf ⇒ verdient sein Gewicht.

## 7. Begründete Auswahl (D1)

**Gewählt: Variante C.** Bestätigt durch die Codebasis: Producer sind verstreut (zwei
Module erzeugen freie Dicts), es gibt keinen Serialisierungs-Seam, und die
Sicherheitsanforderung verlangt EINEN Chokepoint. C liefert **Leverage** (ein Codec zahlt
über 8 Frames + 17 Routen zurück) und **Locality** (Version/Redaction/Metadata an einem
Ort). REST/WS unterscheiden sich real (HTTP-Status vs. Frames) ⇒ B erzwingt Mismatch, A
verstreut die Garantie.

## 8. Öffentliche Schnittstelle des tiefen Moduls (illustrativ)

> Exakte Signaturen werden in Prompt 15 festgelegt. Pydantic-/Codec-Interna dürfen **nicht**
> in `server.py`, `assistant_core.py` oder Tests auslaufen.

```python
# wire_protocol — kleine, tiefe Schnittstelle (transportneutral)

negotiate_ws(subprotocols, ...)   -> ProtocolContext      # Legacy | V1 aus Handshake
negotiate_rest(headers, ...)      -> ProtocolContext      # Legacy | V1 aus Header/Media-Type

decode_command(raw, ctx)          -> ClientCommand | ProtocolError   # eingehend (WS/REST)
encode_event(event, ctx)          -> WireFrame                       # ausgehend, redigiert
present_rest(result, ctx)         -> (http_status:int, body:dict)    # REST-Presentation

# Producer-freundlicher Kanal (kapselt WS + ausgehandelten Context):
class ConversationChannel:            # umschließt eine WS-Verbindung + ProtocolContext
    session_id: str                   # opake Server-ID der Verbindung
    async def emit(event: ServerEvent, *, correlation_id: str | None = None) -> None
# Broadcast an gemischte Clients: encode_event pro Empfänger-Context (siehe §20).
```

`assistant_core`/`server` sprechen nur `ServerEvent`/`ClientCommand`/`ProtocolError` und
`ConversationChannel.emit(...)` — nie Dict-Shapes, nie Codec-Interna. Metadaten
(`event_id`, `timestamp`) erzeugt eine **Metadata Factory** hinter Clock- und ID-Seams.

## 9. Typmodell (Commands, Events, Errors, Envelopes)

Umsetzung als **stdlib-Dataclasses** (D2), keine Pydantic-Typen auf der Schnittstelle.

- **`ClientCommand`** (eingehend): `SayText(text)`, `Stop()`. Erweiterbar additiv.
- **`ServerEvent`** (ausgehend, semantisch): `Health`, `SpokenResponse`,
  `ActionLifecycle(phase, action, label, detail)`, `Error(component, code, message, hint,
  retryable)`, `StopAck`, `MusicChanged`, `AppEvent`, `LauncherChanged`. Jeder Event-Typ
  trägt seine **Sensitivitätsklasse** und die für den Wire zulässige Feldprojektion.
- **`ProtocolError`**: `code` (maschinenlesbar), `message` (sicher), `hint`
  (Recovery), `retryable` (bool). REST: zusätzlich maßgeblicher HTTP-Status.
- **`ProtocolEnvelope`** (nur V1): `{ protocol_version, type, event_id, correlation_id,
  session_id, timestamp, sensitivity, payload }` — Metadaten vom Nutzinhalt getrennt (D3);
  `payload` trägt die typisierte, redigierte Event-Projektion.

## 10. REST- und WS-spezifische Adapter

- **WS-Adapter:** `negotiate_ws` liest `Sec-WebSocket-Protocol`; `encode_event` liefert
  einen Frame-Dict (Legacy: die heutige Form; V1: `ProtocolEnvelope`). Eingehend decodiert
  `decode_command` `{text}`/`{type:stop}` (Legacy) bzw. eine V1-Command-Envelope.
- **REST-Adapter:** `present_rest` bildet ein Ergebnis auf `(HTTP-Status, Body)` ab. Der
  **HTTP-Status bleibt für REST maßgeblich** (D10). Legacy: heutige Bodies; V1: envelope-
  bzw. redigierte Projektion. `decode_command`/Request-Modelle validieren V1-Requests.

## 11. LegacyCodec und V1Codec

- **`LegacyCodec`:** reproduziert die heutigen Formen **byte-/shape-exakt** (Feldnamen,
  Reihenfolge, `ts`-Epoch-Float, `audio`-Base64, `errors`/`error`-Uneinheitlichkeit). Er
  ist die Referenz für die Golden-Contract-Tests (§8-Slice 1 in §24).
- **`V1Codec`:** erzeugt/liest die `ProtocolEnvelope`, setzt Metadaten über die Metadata
  Factory und wendet die Sensitivity-/Redaction-Regeln an (§17).
- Beide sind **Adapter am selben Seam** (die Codec-Grenze). Der `ProtocolContext` wählt
  den Codec.

## 12. Protocol-/Connection-Context und Ownership

- **`ProtocolContext`:** Ergebnis der Aushandlung pro Verbindung (WS) bzw. pro Request
  (REST): `version` (`legacy` | `1`), `session_id` (nur WS), gewählter Codec.
- **`ConversationChannel`:** umschließt eine akzeptierte WS-Verbindung **plus** ihren
  `ProtocolContext`; ersetzt in Prompt 15 das rohe `ws_clients`-Set durch eine **Connection
  Registry**, damit Broadcasts pro Empfänger-Version encodieren können (§20).
- **Ownership (RFC-0002):** der Context wird von der **Composition Root** / dem
  WS-Endpunkt erzeugt und mit der Verbindung/Runtime verwaltet — kein Modul-Global. `obslog`
  bleibt prozessweit (RFC-0004), unberührt.

## 13. Versionsaushandlung (D4)

- **WS:** `Sec-WebSocket-Protocol: jarvis.v1`. Der Server bestätigt das Subprotokoll im
  Handshake **vor** Accept — der sofortige `health`-Frame wird dann bereits als V1-Envelope
  gesendet. **Fehlt** das Subprotokoll → **exakt Legacy**.
- **Warum nicht First-Frame:** der Server sendet den `health`-Frame **sofort nach Accept**,
  bevor ein Client-Frame ankommen könnte; eine First-Frame-Aushandlung würde damit
  kollidieren (der erste ausgehende Frame stünde vor der Aushandlung fest). Das Subprotokoll
  wird dagegen im HTTP-Handshake ausgehandelt und steht beim Bauen des Health-Frames bereit.
- **REST:** Header/Media-Type auf **denselben** Routen (z.B. `Accept: application/
  vnd.jarvis.v1+json` oder `X-Jarvis-Protocol: 1`; finale Wahl in Prompt 15). **Fehlt** die
  V1-Anforderung → **exakt Legacy**. Der bestehende Query-Token bleibt unangetastet.

## 14. Feldsemantik und Anwendbarkeit der Metadaten

| Feld | Bedeutung | WS | REST |
|---|---|---|---|
| `protocol_version` | Integer-Major (D5). `1`; additive Erweiterungen bleiben `1` | ✓ | ✓ |
| `type` | semantischer Event-/Command-Name | ✓ | ✓ (Envelope) |
| `event_id` | ein einzelnes semantisches Wire Event; serverseitig erzeugt | ✓ | ✓ |
| `correlation_id` | verbindet Command/REST-Request mit ALLEN daraus entstehenden Events | ✓ | ✓ |
| `session_id` | opake Server-ID pro akzeptierter WS-Verbindung | ✓ | **null** (REST erfindet keine) |
| `timestamp` | RFC3339 UTC ms (D7) | ✓ | ✓ |
| `sensitivity` | serverseitige Klasse (D8); Client darf nie herabstufen | ✓ | ✓ |
| `payload` | typisierte, redigierte Event-/Result-Projektion | ✓ | ✓ |

## 15. ID-Erzeugung, Validierung und Lebensdauer (D6)

- **`event_id`:** immer **serverseitig** erzeugt (opake Zufalls-ID), pro semantischem Event.
  **Broadcast = EIN semantisches Event ⇒ dieselbe `event_id` an alle Empfänger.**
- **`correlation_id`:** eine vom Client mitgegebene `correlation_id` wird **nur nach
  Formatvalidierung** übernommen und auf allen Folge-Events gespiegelt; fehlt/ungültig →
  server-generiert. **Spontane** (unaufgeforderte) Events erhalten eine frische
  Server-`correlation_id`.
- **`session_id`:** serverseitig als **opake Zufalls-ID pro akzeptierter WS-Verbindung**
  erzeugt; **innerhalb** der Verbindung stabil, nach Reconnect **neu** (Reconnect-Resume ist
  **Nicht-Ziel**). `session_id` ist **niemals** der Auth-/Session-Token und wird nie als
  solcher akzeptiert. **REST** erfindet keine `session_id` → `null`.
- Client-vorgeschlagene `event_id`/`session_id` werden **nie** übernommen.

## 16. Timestamp-Format (D7)

- **V1:** RFC3339 UTC mit Millisekunden, z.B. `2026-07-17T20:15:36.123Z`. Über einen
  **Clock-Seam** deterministisch testbar.
- **Legacy:** der `LegacyCodec` erhält bestehende Epoch-`ts`-Felder **exakt** (Float,
  gleiche Felder, keine neuen Zeitstempel auf Legacy-Frames).

## 17. Sensitivitäts- und Wire-Eligibility-Matrix (D8)

Klassen (aus `SECURITY_REQUIREMENTS.md`): `public`, `local`, `personal`, `sensitive`,
`secret`. **Serverseitige** Klassifizierung; der Client darf eine Klasse **nie** herabstufen.

| Klasse | Wire-Eligibility | Regel |
|---|---|---|
| `public` | erlaubt | frei |
| `local` | erlaubt | z.B. App-/Profil-IDs, Monitor-Map, Dateiname |
| `personal` | erlaubt, aber markiert | Antworttext/History als LLM-Kontext; token-geschützte Routen |
| `sensitive` | erlaubt, aber markiert + minimiert | Screen/Clipboard/Vault-Ausschnitte; nie voller Rohinhalt ohne Zweck |
| `secret` | **VERBOTEN** | Encoder gibt den Rohwert **nie** aus; Feld/Event wird unterdrückt bzw. durch sicheren Marker ersetzt |

- **Fail-closed:** bei Unsicherheit gilt die **höhere** Klasse. Die Klasse ist **nicht**
  kosmetisch — sie steuert echte Redaction/Unterdrückung im Encoder.
- **Health/Detail (D9):** die **V1**-`/health`-Projektion ist `public` und **redigiert
  lokale Pfade** (Vault-Pfad → nur vorhanden/erreichbar-Boolean, kein Rohpfad; keine
  pfadhaltigen Warnungen). `GET /health` bleibt öffentlich (Launcher/Smoke-Liveness). Das
  **Legacy**-`/health` bleibt byte-exakt — der bestehende öffentliche Pfad-Leak (`vault_path`
  in `services.vault.detail`/`warnings`) bleibt als **benanntes Legacy-Restrisiko** bestehen
  und wird erst mit der Consumer-Migration (Prompt 15) geschlossen. Auch `action.detail`
  wird unter V1 gemäß Klasse minimiert/redigiert.

## 18. Fehler-, Close- und HTTP-Status-Semantik (D10)

**V1-Fehler** = `ProtocolError{code, message(sicher), hint, retryable}`. Für **REST bleibt
der HTTP-Status maßgeblich**; die Envelope ergänzt nur die maschinenlesbaren Felder.
Legacy-Fehlerframes/`errors`/`error`-Formen bleiben **unverändert**.

| Fehlerfall | WS (V1) | REST (V1) |
|---|---|---|
| malformed JSON | definierter Close-Code + `ProtocolError` vor Close | `400` + `ProtocolError` |
| falscher Root-Typ | `ProtocolError` (`type=bad_root`) | `400` |
| fehlende Pflichtfelder | `ProtocolError` (`type=invalid_command`) | `400` |
| unbekannter Command | `ProtocolError` (`type=unknown_command`) | `404`/`400` |
| unbekannte Major-Version | Handshake-Ablehnung bzw. `ProtocolError` (`type=unsupported_version`) | `400`/`426` |
| Größenüberschreitung | definierter Close-Code (`too_large`) | `413` |

Konkrete Close-Codes/HTTP-Status werden in Prompt 15 finalisiert; die Klassen stehen fest.

## 19. Ordering-, Interleaving- und Delivery-Garantien (D10)

Dokumentiert werden **nur real haltbare** Eigenschaften:
- **Per-Verbindung FIFO** in Sendereihenfolge (WS).
- Ein Command kann **mehrere** Events erzeugen; REST-Broadcasts **verschachteln** sich mit
  Gesprächsantworten (unverändert zum Ist).
- **Keine** Zusagen zu Exactly-once, Durable Replay, Deduplizierung oder globaler
  Reihenfolge. `event_id` ist **keine** Replay-/Dedup-/Exactly-once-Garantie.

## 20. Broadcasts an gemischte Legacy-/V1-Clients

Eine **Connection Registry** hält je Verbindung ihren `ProtocolContext`. Ein Broadcast ist
**ein** semantisches Event: der Server erzeugt **eine** `event_id` und encodiert das Event
**pro Empfänger-Context** (Legacy-Clients erhalten die Legacy-Form, V1-Clients die
Envelope mit derselben `event_id`). So laufen Legacy- und V1-Verbindungen **gleichzeitig**.

## 21. Compatibility- und Deprecation-Strategie (D11)

- **Legacy bleibt Standard** bzw. gilt bei fehlender Versionsaushandlung; es bleibt
  **byte-/shape-exakt**.
- **Entfernung nur** durch eine spätere **ausdrückliche** Entscheidung, nachdem **alle**
  First-Party-Consumer (Frontend) auf V1 migriert und Contract-/Browser-Tests **grün** sind.
- Kein Deprecation-Zwangstermin in diesem RFC.

## 22. Sicherheits- und Datenschutzgrenzen

- **Auth/Origin/Token unverändert** (Query-Token bleibt, kein Verschieben). `session_id` ist
  **nie** Auth-Token.
- **Ein Redaction-Chokepoint** im Encoder: `secret` nie auf dem Wire (fail-closed);
  Health-/Detail-Redaction (§17). Das ergänzt (nicht ersetzt) die `obslog`-Redaction
  (RFC-0004) — beide sind getrennte Grenzen (Wire vs. Log).
- **Keine** neuen Sinks/Telemetrie/Remote-Logging.

## 23. Öffentliche Test-Seams

Getestet wird **nur** an: der öffentlichen Codec-/Modul-Schnittstelle, dem ausgehandelten
`ProtocolContext`, dem **vollständig serialisierten** Wire-Output und den echten FastAPI-
TestClient-REST-/WS-Dialogen. **Nicht** an privaten Validatoren/Regex/internen Dicts.
Clock- und ID-Seams werden injiziert (deterministische Tests).

## 24. Schrittweise Prompt-15-Migration (je Slice ein Rückrollpunkt)

1. **Legacy charakterisieren** — Golden-Contract-Tests (byte-/shape-exakt) als Sicherung. *(Rollback: revert)*
2. **Reine Wire-Typen** + Metadata Factory + Clock-/ID-Seams (kein Verhalten geändert). *(revert)*
3. **`LegacyCodec`** mit byte-/shape-genauer Kompatibilität; Producer emittieren über den Codec, Output identisch. *(revert → direkte Dicts)*
4. **V1-WS-Codec** + `Sec-WebSocket-Protocol`-Negotiation (V1 opt-in, Legacy Default). *(revert)*
5. **Connection Registry** mit `ProtocolContext`; versionsabhängige Broadcasts. *(revert → `ws_clients`)*
6. **First-Party-Frontend** auf V1 migrieren, Legacy läuft parallel weiter. *(revert Frontend)*
7. **JSON-REST-Routen** schrittweise typisieren + V1-Presentation (Header-Negotiation). *(revert je Route)*
8. **Fehler-/Größen-/Sensitivitäts-/Fault-Tests** ergänzen. *(revert)*
9. **Deprecation-Doku** + vollständige CI-Evidenz. *(revert)*

**Geplante Test-Seams:** öffentliche Codec-Roundtrips; exakte Legacy-Shape-Tests;
deterministische IDs/Zeit über Seams; echte TestClient-REST/WS-Tests; Legacy **und** V1
parallel; Korrelation über `response`/`action`/`error`/`stop`; `session_id` innerhalb einer
Verbindung stabil, nach Reconnect neu; Broadcasts an Clients verschiedener Versionen;
malformed/unknown/wrong-root/oversize; **niemals `secret` auf dem Wire**;
Browser-/Playwright-Nachweis aller bestehenden Flows. Keine echten Provider, keine
persönlichen Configs, keine echten Desktop-Apps.

## 25. Risiken und offene Grenzen

- **Legacy-`/health`-Pfad-Leak** bleibt bis zur Consumer-Migration bestehen (bewusst, §17).
- **Doku-Abweichungen** (§4) werden erst mit der Umsetzung korrigiert.
- **Schutznetz vs. Garantie:** die Wire-Redaction ist eine harte Encoder-Grenze; falsche
  Klassifizierung im Producer bleibt ein Restrisiko (Minderung: fail-closed + Tests).
- **Reconnect-Resume** ist Nicht-Ziel — Clients müssen nach Reconnect neu aufsetzen.
- **Handgeschriebener Codec** kostet mehr Implementierungsarbeit als Pydantic, kauft dafür
  byte-exaktes Legacy und Entkopplung (bewusster Trade-off, D2).

## 26. Auswirkungen auf RFC-0001 bis RFC-0004

- **RFC-0001 (Action):** unberührt; `[ACTION:…]` bleibt. `ActionLifecycle`-Events bilden die
  bestehende Action-Historie typisiert ab, ohne die Action-Semantik zu ändern.
- **RFC-0002 (Composition Root):** der `ProtocolContext`/die Connection Registry werden von
  der Composition Root/dem WS-Endpunkt besessen — kein Modul-Global; konsistent mit E2.
- **RFC-0003 (Configuration):** unberührt; die additiven Settings-Felder (`revision`/
  `conflict`/`degraded`) werden im V1-Vertrag **explizit** typisiert (heute nur im Code).
- **RFC-0004 (obslog):** getrennte Grenze (Log vs. Wire). RFC-0005 entwirft nur die
  Wire-`correlation_id`; die Durchreichung in `obslog`/Audit/Tracing bleibt **Phase 11** und
  erfordert dann eine **ausdrückliche, nicht stille** RFC-0004-Ergänzung (D12).

---

## Anhang A — Entscheidungen D1–D12

| # | Entscheidung | Gewählt |
|---|---|---|
| **D1** | Architektur/Modulform | **Variante C:** transportneutrales tiefes `wire_protocol`-Modul + LegacyCodec/V1Codec |
| **D2** | Typmodell-Implementierung | **stdlib-Dataclasses + handgeschriebener Codec** (Pydantic vorhanden, aber nicht im Wire-Pfad) |
| **D3** | V1-Metadatenform | **Nested V1-Envelope mit `payload`** |
| **D4** | Aushandlung | **WS `Sec-WebSocket-Protocol: jarvis.v1` + REST-Header/Media-Type**; fehlend → exakt Legacy |
| **D5** | Versionsmodell | **Integer-Major `1`**, additiv innerhalb Major, neue Major bei Breaking |
| **D6** | ID-/Session-Semantik | **Server-`event_id`/`session_id`; validierte Client-`correlation_id` gespiegelt; Broadcast = 1 `event_id`**; `session_id` opak/pro Verbindung, nie Auth-Token; REST → `null`; Reconnect-Resume Nicht-Ziel |
| **D7** | Timestamp | **RFC3339 UTC ms**; Legacy-Epoch-`ts` exakt erhalten |
| **D8** | Sensitivität | **serverseitig klassifiziert + hartes Fail-closed**; `secret` nie auf dem Wire; Client kann nie herabstufen |
| **D9** | Health/Detail | **sichere öffentliche V1-Projektion mit Redaction; Legacy `/health` unverändert** (Legacy-Leak als benanntes Restrisiko) |
| **D10** | Fehlermodell/Ordering | **strukturierter V1-Fehler (`code`/`message`/`hint`/`retryable`), HTTP-Status maßgeblich; nur reale Ordering (per-Verbindung FIFO), kein Exactly-once/Replay/global** |
| **D11** | Legacy/Deprecation | **Legacy bleibt Standard**; Entfernung nur durch spätere explizite Entscheidung nach Migration + grünen Tests |
| **D12** | Logging-Grenze | **nur Wire-`correlation_id` jetzt**; obslog-/Audit-Korrelation = Phase 11 (keine stille RFC-0004-Erweiterung) |

Alle D1–D12 wurden vom Nutzer in drei Grilling-Runden bestätigt (jeweils = Empfehlung).

---

## Amendment 1 — Prompt-15 Implementation Contracts

- **Status:** Accepted (2026-07-18, nach Nutzerfreigabe in zwei Grilling-Runden)
- **Zweck:** Die von RFC-0005 bewusst offen gelassenen Implementierungskonstanten
  verbindlich festlegen, **bevor** in Prompt 15 (Phase 4H) Produktionscode entsteht. Ändert
  keine der akzeptierten Entscheidungen D1–D12, sondern präzisiert sie.

### A1.A — REST-V1-Aushandlung und Correlation
- V1 wird über **`Accept: application/vnd.jarvis.v1+json`** angefordert. Der Request-Body
  bleibt `application/json`. **Fehlt** der V1-Accept-Header → **exakt Legacy**. Die
  V1-Response verwendet den Vendor-Media-Type.
- **Correlation** läuft für **alle** Methoden über **`X-Jarvis-Correlation-ID`**. Eine
  gültige Client-ID wird **gespiegelt**; fehlt sie oder ist ungültig, erzeugt der Server
  eine neue. **Response-Envelope und Response-Header** tragen **dieselbe** Correlation-ID.
- Eine nicht unterstützte V1-Repräsentation ergibt **`406 Not Acceptable`**.

### A1.B — Getrennte Client-Command-Envelope
Client Commands verwenden **nicht** die volle Server-Event-Envelope, sondern:
```json
{ "protocol_version": 1, "type": "say_text" | "stop",
  "correlation_id": "<optional UUID>", "payload": { } }
```
- `say_text` benötigt `payload.text`; `stop` verwendet ein leeres Payload-Objekt.
- Clients dürfen `event_id`, `session_id`, `timestamp`, `sensitivity` **niemals** setzen;
  Einschleus-Versuche werden **kontrolliert abgelehnt** (ProtocolError, keine stille
  Übernahme).
- Unbekannte **additive, nicht reservierte** Felder werden für Forward-Compatibility
  **ignoriert**; Pflichtfelder, Typen und bekannte Enums bleiben **strikt**.
- IDs sind kanonische UUIDs; `event_id`/`session_id` werden serverseitig als **UUIDv4**
  erzeugt.

### A1.C — Fault-, Close- und Größenvertrag
- **WS-JSON-Frame** ≤ **64 KiB** eingehend; **`say_text`-Text** ≤ **16 KiB** nach
  Normalisierung; **V1-REST-Body** ≤ **1 MiB**.
- **WS:** malformed JSON → sicherer `ProtocolError`, dann Close **1007**; zu großer Frame →
  Close **1009**; ausgehandelte V1-Verbindung mit falscher Major → `ProtocolError`, dann
  Close **1002**; falscher Root / fehlende Felder / unbekannter Command → `ProtocolError`,
  Verbindung bleibt für **korrigierbare** Fehler **offen**.
- **Handshake:** enthält die Angebotsliste **nur** nicht unterstützte `jarvis.vN` →
  **Ablehnung vor `accept`** (dort ist noch **kein** Error-Frame möglich); enthält sie
  `jarvis.v1` → V1 wird gewählt **und bestätigt**.
- **REST:** malformed/invalid → **400**; zu groß → **413**; unbekannte Repräsentation →
  **406**. Das Größenlimit wird möglichst **vor** vollständigem JSON-Decoding geprüft.

### A1.D — Secret-/Redaction-Verhalten
- Ein Event der Klasse **`secret` ist nicht encodierbar**. Der Encoder gibt **niemals**
  `str()`/`repr()` des abgelehnten Werts aus, sondern erzeugt einen **sicheren generischen
  Fehler ohne Originalwert**.
- Event-spezifische V1-Projektionen **entfernen** bekannte geheime bzw. nicht benötigte
  Felder. `action.detail` wird bei sensiblen Actions **minimiert** bzw. durch einen sicheren
  Marker ersetzt. **V1-Health** ist eine **redigierte öffentliche Projektion** eines intern
  `local`-klassifizierten Reports.
- **Legacy-Shapes bleiben für normale Werte identisch.** Taucht ein **bekannter
  Runtime-Secret**-Wert in einem Legacy-Feld auf, hat „Secret niemals auf dem Wire" Vorrang
  vor Wertgleichheit: **Feldname und Shape bleiben, der Wert wird redigiert**.
- **Keine** Behauptung magischer Erkennung beliebiger Geheimnisse in freiem LLM-Text. Die
  Garantie umfasst **bekannte Runtime-Secrets**, **geschlossene typisierte Felder** und
  **event-spezifische Projektionen**.

### A1.E — Legacy-Präzisierung
- „byte-/shape-exakt" bedeutet **identische Feldnamen, Feldreihenfolge, Typen, Vorhandensein
  und Werte** für **nicht-sensitive** Inputs.
- Dynamische **Zeit/IDs** werden in Golden-Tests über **injizierte Clock-/ID-Seams**
  eingefroren.
- **JSON-Whitespace** ist **kein** Produktvertrag.
- Das öffentliche **Legacy-Health-Restrisiko** (Vault-Pfad in `services.vault.detail`/
  `warnings`) verschwindet **nicht** allein durch Migration des First-Party-Frontends; es
  bleibt bis zu einer **späteren Änderung oder Entfernung** der Legacy-Repräsentation.

### A1.F — Öffentliche Test-Seams (bestätigt)
- **SEAM-WIRE:** öffentliche `wire_protocol`-Schnittstelle und **vollständig serialisierter**
  Output.
- **SEAM-WS:** echter FastAPI-TestClient-Handshake und echter Dialog.
- **SEAM-REST:** echte Route mit Status, Header und Body.
- **SEAM-CONVERSATION:** echter WS-Dialog, nur echte **externe Providergrenzen** ersetzt.
- **SEAM-MIXED-WIRE:** parallele Legacy-/V1-Verbindungen und echter Broadcast.
- **SEAM-BROWSER-UI:** echtes Python-Playwright-Verhalten.
- **Nicht** getestet werden private Validatoren, Regexe, interne Registries oder `__dict__`.

Alle A1.A–A1.F wurden vom Nutzer in zwei Grilling-Runden bestätigt (jeweils = Empfehlung).

# Jarvis – WebSocket-Protokoll (Ist-Zustand, `legacy-unversioned`)

> Dokumentiert das **aktuelle** WS-Protokoll (`server.websocket_endpoint`,
> `server.py:102`, + Frame-Erzeuger in `assistant_core`). Stand 2026-07-14. Alle
> Beispielwerte synthetisch. Es gibt **kein** `protocol_version`-Feld — das
> Protokoll ist `legacy-unversioned` und wird in diesem Prompt **nicht** versioniert
> oder um Frames erweitert. Bezug:
> [../quality/TEST_SEAMS.md](../quality/TEST_SEAMS.md) (SEAM-WS/-CONVERSATION).

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

Der Server liest JSON via `ws.receive_json()` (`server.py:175`).

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
1. laufende Child-Task (falls aktiv) wird gecancelt;
2. die Queue wird geleert (wartende Nachrichten verworfen);
3. `pending_confirm` der Session wird entfernt;
4. ein `stop`-Frame wird gesendet;
5. war eine Aktion aktiv, folgt zusätzlich `{"type":"response","text":"Okay,
   gestoppt.","audio":""}`.

Der Worker **lebt weiter**: eine nach dem Stop gesendete Nachricht wird normal
verarbeitet. Ein reiner Stopp beendet die Verbindung nicht.

## Disconnect & Fehlerverhalten

- **Disconnect** (`WebSocketDisconnect`): das `finally` setzt `stopping=True`,
  cancelt den Worker und nimmt eine laufende Child-Task garantiert mit (kein
  Task-Leak), räumt `ws_clients` auf und ruft `assistant_core.end_session`
  (`server.py:200`).
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

## Nicht abgedeckt / offen

- **Keine** Protokollversionierung (`legacy-unversioned`) — bewusst; ein
  `protocol_version`-Feld folgt frühestens in einer späteren Phase.
- Frame-Verträge des Happy-Path (response/action) über den **echten** WS-Dialog:
  Slice 4 (SEAM-CONVERSATION).

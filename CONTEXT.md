# CONTEXT.md — Jarvis Domain-Glossar

> Verbindliches Vokabular für Jarvis. Nur Begriffe, die **bereits** im Code, in
> Nutzerflüssen oder verbindlicher Doku vorkommen (Ist-Stand). Geplante Begriffe
> stehen getrennt unter „Zielmodell". Diese Datei trifft **keine**
> Architekturentscheidungen — die stehen in `docs/adr/`. Stand 2026-07-13.

Architekturvokabular (module, interface, seam, deep, adapter, leverage, locality)
lebt im Architekturbericht und in `$codebase-design`, nicht hier.

## Etablierte Domänenbegriffe (Ist-Stand)

### Conversation Session
- **Bedeutung:** Der Gesprächszustand einer offenen WebSocket-Verbindung.
- **Verantwortung:** Verlauf und offene Rückfrage eines Clients zusammenhalten.
- **Abgrenzung:** Nicht die WS-Verbindung selbst (Transport) und nicht die
  prozessweiten Kontextdaten (Wetter/Tasks/Vault gelten für alle Sessions).
- **Quellen:** `assistant_core.conversations` (dict `session_id → list`),
  `session_id = str(id(ws))` in `server.py:124`, `end_session` (`assistant_core.py:92`).

### Message
- **Bedeutung:** Ein einzelner Gesprächsbeitrag `{"role", "content"}` im Verlauf.
- **Verantwortung:** Kontext für den nächsten LLM-Aufruf liefern.
- **Abgrenzung:** Nicht das WS-Frame (Transportformat), nicht die gesprochene
  Antwort (TTS-Audio).
- **Quellen:** `assistant_core._remember` (`assistant_core.py:85`), `MAX_HISTORY = 60`
  (nur die letzten 16 gehen an den LLM, `assistant_core.py:678`).

### Action
- **Bedeutung:** Eine vom LLM ausgelöste Fähigkeit, als `[ACTION:TYP] payload`
  am Ende der Antwort. 22 Typen.
- **Verantwortung:** Browser/Screen/Memory/Launcher/Clipboard-Wirkung anstoßen.
- **Abgrenzung:** `Action` = geparster Aufruf (`actions.Action`); `ActionSpec` =
  Metadaten des Typs. Der `[ACTION:...]`-Text ist das Wire-Format, nicht die Action.
- **Quellen:** `actions.parse_action`, `actions.Action`, Ausführung in
  `actions.spec_for(TYP).execute(payload, ctx)`; `assistant_core.execute_action`
  ist seit RFC-0001 nur noch ein Thin Dispatcher (Kontext bauen + Lookup).

### ActionSpec
- **Bedeutung:** Metadaten eines Action-Typs (Label, Payload-Regel, Risk, Timeout,
  Summary-Prompt, is_url/is_browser/speaks_result).
- **Verantwortung:** Parsing, Timeout-Cap, Risk-/Browser-Klassifikation, Summary.
- **Abgrenzung:** Beschreibt den Typ, führt ihn nicht aus (Ausführung liegt in
  `execute_action`).
- **Quellen:** `actions.ActionSpec` + `actions.REGISTRY` (`actions.py:47`),
  abgeleitete Sets `SPEAK_RESULT_ACTIONS`/`CONFIRM_ACTIONS`/`BROWSER_ACTIONS`.

### Confirmation
- **Bedeutung:** Mündliche Ja/Nein-Rückfrage vor einer riskanten Action
  (aktuell nur `MEMORY_FORGET`, `risk="confirm"`).
- **Verantwortung:** Destruktive Wirkung erst nach ausdrücklichem „Ja" ausführen.
- **Abgrenzung:** Nicht Stop/Cancel (bricht ab), nicht die Token-Autorisierung (REST).
- **Quellen:** `actions.is_confirmation`, `CONFIRM_ACTIONS`, `pending_confirm`
  (`assistant_core.py:63`, `660`, `707`).

### App Registry
- **Bedeutung:** Die Allowlist startbarer Apps aus `config.apps`.
- **Verantwortung:** Nur konfigurierte Apps starten (kein `shell=True`, keine freien
  LLM-Kommandos).
- **Abgrenzung:** Die Registry ist die App-Liste; das Launcher Profile wählt daraus
  Autostart/Placement.
- **Quellen:** `app_launcher.APPS`, `normalize_apps`, `launch`, `configure`
  (`app_launcher.py:211`).

### Launcher Profile
- **Bedeutung:** Benannte Session-Konfiguration (`id`, `name`, `apps`-States) für
  den Clap-Start; genau eines ist `active_profile`.
- **Verantwortung:** Pro Profil festlegen, welche Apps mit welchem Placement
  autostarten.
- **Abgrenzung:** Profil referenziert App Registry-Einträge, ersetzt sie nicht.
- **Quellen:** `app_launcher.PROFILES`/`ACTIVE_PROFILE`, `config.launcher`,
  `validate_launcher_value` (`config_loader.py:142`).

### Placement
- **Bedeutung:** Startposition einer App als `{monitor, zone}`.
- **Verantwortung:** Fensterplatzierung beim Session-Start beschreiben.
- **Abgrenzung:** Placement ist die gewünschte Position (Daten); das tatsächliche
  Fenster-Snapping macht `scripts/launch-session.ps1`.
- **Quellen:** `validate_placement_value` (`config_loader.py:120`), Zonen/Monitore
  in `_PLACEMENT_ZONES`/`_PLACEMENT_MONITORS`, `[ACTION:APP_PLACE]`.

### Monitor
- **Bedeutung:** Ein erkannter physischer Bildschirm mit semantischer ID
  (primary/left/right/leftmost/rightmost).
- **Verantwortung:** Ziel für Placement liefern; Monitor-Map im UI.
- **Abgrenzung:** Semantische Monitor-ID ≠ physischer Geräteindex.
- **Quellen:** `monitors.detect_monitors` (`monitors.py`), `GET /launcher/monitors`.

### Window Mode
- **Bedeutung:** Darstellungsmodus des nativen Jarvis-Fensters: Panel, Fokus,
  Vollbild.
- **Verantwortung:** Fenstergröße/-position und UI-Layout umschalten.
- **Abgrenzung:** Window Mode betrifft das Jarvis-Fenster selbst, nicht das
  Placement gestarteter Apps.
- **Quellen:** `jarvis-launcher.pyw` `set_window_mode`, Frontend `applyUiMode`
  (`frontend/main.js`).

### Inbox Entry
- **Bedeutung:** Ein kategorisierter Tageseintrag (Idee/Aufgabe/Termin/Recherche/
  Erinnerung/Notiz) im Obsidian „Brain Dump".
- **Verantwortung:** Kurzlebige Tagesnotizen festhalten.
- **Abgrenzung:** Tagesnotiz ≠ Memory Entry (Langzeit); geht in die Tagesdatei, nicht
  in „Jarvis Memory.md".
- **Quellen:** `memory.write_inbox_entry`, `actions.split_inbox_category`,
  `[ACTION:INBOX_WRITE]`.

### Memory Entry
- **Bedeutung:** Ein dauerhaft gemerkter Fakt in „Jarvis Memory.md" (nutzer-editierbar),
  fließt in den System-Prompt ein.
- **Verantwortung:** Langzeitwissen über den Nutzer, nur auf ausdrücklichen Wunsch.
- **Abgrenzung:** Langzeit ≠ Inbox Entry (Tagesnotiz); nur `MEMORY_WRITE`/`FORGET`
  schreiben/löschen.
- **Quellen:** `memory.append_memory`/`read_memory_sync`/`forget_memory`,
  `memory.MEMORY_FILENAME`, Einbindung in `build_system_prompt` (`assistant_core.py:192`).

### Vault Context
- **Bedeutung:** Token-sparsame lokale Vault-Suche, die kurze passende Ausschnitte
  liefert (Secret-Zeilen ausgenommen).
- **Verantwortung:** Projektbezogene Fragen aus den eigenen Notizen beantworten.
- **Abgrenzung:** Liest nur lokal (kein Web); ≠ Research (Web) und ≠ Memory Entry.
- **Quellen:** `memory.get_project_context_sync`, `[ACTION:PROJECT_CONTEXT]`.

### Research
- **Bedeutung:** Gründliche Web-Recherche über 3–5 Quellen mit gesprochener
  Zusammenfassung, Quellen im Transcript und Autosave in den Brain Dump.
- **Verantwortung:** Fundierte Mehrquellen-Antwort statt nur des ersten Treffers.
- **Abgrenzung:** Research (mehrere Quellen, Autosave) ≠ `SEARCH` (erster Treffer).
- **Quellen:** `assistant_core.run_research` (`assistant_core.py:316`),
  `browser_tools.search_links`, `RESEARCH_SOURCE_PREFIX`.

### Browser Task
- **Bedeutung:** Eine sichtbare Playwright-Aktion (Suche, Seitenbesuch, URL öffnen,
  News, Quellensuche) im geteilten Chromium.
- **Verantwortung:** Reale Browserinteraktion mit Tab-Cap ausführen.
- **Abgrenzung:** Browser Task nutzt den geteilten Browser; ≠ App-Start (App Registry).
- **Quellen:** `browser_tools.search_and_read`/`visit`/`open_url`/`fetch_news`,
  `_new_page_capped`, `MAX_TABS = 5` (`browser_tools.py:18`).

### Health Report
- **Bedeutung:** Passive Statusübersicht (`config`, `llm`, `tts`, `browser`, `vault`)
  ohne kostenpflichtige Aufrufe.
- **Verantwortung:** Launcher/Tests/Smoke sagen, ob der Server bereit ist.
- **Abgrenzung:** Passiver Report ≠ Settings (schreibt Config); verbraucht kein Quota.
- **Quellen:** `health.build_report`, `GET /health` (`server.py:220`).

### Configuration
- **Bedeutung:** Das vollständige persistierte Konfigurationsdokument (`config.json`)
  **inklusive Secrets und unbekannter Felder** — die Gesamtheit, aus der die Settings
  eine Projektion sind.
- **Verantwortung:** Persistente Wahrheit über Persona, Provider-Keys, Pfade, Apps,
  Launcher-Profile, Musik und alle vom Nutzer manuell ergänzten Felder.
- **Abgrenzung:** Configuration ⊃ Settings — die Configuration enthält zusätzlich die
  Secrets (`PROTECTED_KEYS`) und beliebige unbekannte Felder, die byte-/wertgetreu
  erhalten bleiben müssen.
- **Quellen:** `config.json`, `configuration.Configuration` (Laden/Migration/
  Mutation — der einzige Schreibweg), `config_loader` (Validierungsgrundlagen).

### Settings
- **Bedeutung:** Die UI-editierbaren Config-Felder (Whitelist `UI_EDITABLE_KEYS`) — die
  **UI-editierbare Projektion der Configuration**; API-Keys sind ausgeschlossen.
- **Verantwortung:** Persona/Stadt/Apps/Launcher/Musik/Obsidian-Pfade ändern und
  live anwenden.
- **Abgrenzung:** Settings ≠ Secrets (`PROTECTED_KEYS`, nie über die API); Settings ⊂
  Configuration (die Projektion, nicht das Gesamtdokument).
- **Quellen:** `config_loader.UI_EDITABLE_KEYS`, `configuration.settings_view` +
  `configuration.SetSettings`, `GET|POST /settings`.

### Stop/Cancel
- **Bedeutung:** „Stopp"/Esc/Button bricht Wiedergabe UND laufende Action ab; die
  Nachrichten-Queue wird geleert.
- **Verantwortung:** Sofortige Unterbrechung ohne die WS-Verbindung zu beenden.
- **Abgrenzung:** Stop bricht ab; Confirmation fragt vorher nach; Disconnect beendet
  die Session.
- **Quellen:** `actions.is_stop_command`, Worker/Queue in `server.websocket_endpoint`
  (`server.py:142`–`211`), Frontend `requestStop` (`frontend/main.js`).

## Zielmodell (NOCH NICHT implementiert)

Diese Begriffe stammen aus dem Masterplan und sind **im aktuellen Code nicht
vorhanden**. Nicht mit dem Ist-Stand vermischen.

- **Capability** — geplanter Nachfolger des Action-Typs mit typisiertem
  Schema/Preview/Autorisierung/Verify (Phase 5). Heute nur `Action`/`ActionSpec`.
- **Policy** — geplante Datenklassen-/Wirkungsklassen-/Presence-Regeln (Phase 2/5).
- **Job / Workflow** — geplante dauerhafte, wiederaufnehmbare Abläufe mit SQLite
  (Phase 6). Heute laufen Nachrichten nur als flüchtige asyncio-Tasks.
- **Outbox / Saga** — geplante Crash-Sicherheit für externe Wirkungen (Phase 6).
- **Scheduler / Briefing / Workspace-Szene** — geplant (Phase 8).

## Wire-Contracts (RFC-0005 akzeptiert — Umsetzung ab Prompt 15)

Diese Begriffe sind mit [RFC-0005](docs/architecture/RFC-0005-typed-versioned-wire-contracts.md)
**akzeptiert**, aber **im aktuellen Code noch nicht implementiert** (die Produktion nutzt
weiterhin die untypisierten Legacy-Verträge). Nicht mit dem Ist-Stand vermischen.

### Wire Frame
- **Bedeutung:** Das Transportformat einer einzelnen über REST/WS gesendeten Nachricht
  (die serialisierte Form auf der Leitung).
- **Abgrenzung:** **Nicht** die `Message` (Gesprächsbeitrag `{role, content}`) und nicht die
  `Action`.

### Protocol Envelope
- **Bedeutung:** Die V1-Hülle eines Wire Frames: `{protocol_version, type, event_id,
  correlation_id, session_id, timestamp, sensitivity, payload}` — Metadaten getrennt vom
  Nutzinhalt (`payload`).
- **Abgrenzung:** Legacy-Frames haben **keine** Envelope; sie bleiben byte-/shape-exakt.

### Client Command
- **Bedeutung:** Eine typisierte eingehende Nachricht Client→Server (z.B. `SayText`, `Stop`).
- **Abgrenzung:** Nicht die `Action` (die vom LLM ausgelöst wird), nicht die `Message`.

### Server Event
- **Bedeutung:** Eine typisierte ausgehende Nachricht Server→Client (z.B. `Health`,
  `SpokenResponse`, `ActionLifecycle`, `Error`, `StopAck`, `MusicChanged`).
- **Abgrenzung:** **Kein** persistiertes Event-Sourcing-Ereignis. Verschieden vom
  **Operational Log Event** (`obslog`, RFC-0004) — Wire vs. Log sind getrennte Grenzen.

### Protocol Version
- **Bedeutung:** Integer-Major der Wire-Contracts (`1`). Additive Erweiterungen bleiben `1`;
  Breaking Changes erzeugen eine neue Major.
- **Abgrenzung:** Nicht die `schema_version` der Configuration (RFC-0003).

### Event ID
- **Bedeutung:** Server-erzeugte opake ID **eines einzelnen semantischen** Server Events.
  Ein Broadcast ist ein Event → dieselbe Event ID an alle Empfänger.
- **Abgrenzung:** **Keine** Replay-, Deduplizierungs- oder Exactly-once-Garantie.

### Correlation ID
- **Bedeutung:** Verbindet einen Client Command bzw. REST-Request mit **allen** daraus
  entstehenden Server Events. Eine validierte Client-Correlation-ID wird gespiegelt; sonst
  server-erzeugt.
- **Abgrenzung:** Kein Auth-Bezug; spontane Events erhalten eine frische Server-Correlation-ID.

### Conversation Session ID
- **Bedeutung:** Server-erzeugte **opake Zufalls-ID** pro akzeptierter WS-Verbindung; innerhalb
  der Verbindung stabil, nach Reconnect neu (Reconnect-Resume ist Nicht-Ziel).
- **Abgrenzung:** **Nicht** der Auth-/Session-Token; nicht das interne `str(id(ws))`. REST
  erfindet keine Session ID (`null`).

### Sensitivity
- **Bedeutung:** Serverseitige Datenklasse eines Feldes/Events (`public`/`local`/`personal`/
  `sensitive`/`secret`) auf dem Wire. `secret` ist verboten; der Encoder redigiert fail-closed.
- **Abgrenzung:** Der Client darf eine Klasse **nie** herabstufen; die Klasse ist nicht
  kosmetisch, sondern steuert echte Redaction.

### Protocol Context
- **Bedeutung:** Das pro Verbindung (WS) bzw. pro Request (REST) ausgehandelte Ergebnis
  (`legacy` | `v1`, `session_id`, gewählter Codec).
- **Abgrenzung:** Kein Modul-Global; im Besitz der Composition Root / des WS-Endpunkts (RFC-0002).

### Legacy Adapter
- **Bedeutung:** Der `LegacyCodec`, der die heutigen untypisierten Formen byte-/shape-exakt
  reproduziert; Gegenstück zum `V1Codec` am selben Codec-Seam.
- **Abgrenzung:** Erzeugt **keine** neuen Metadaten/Zeitstempel auf Legacy-Frames.

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
- **Quellen:** `config.json`, `config_loader.load_config`/`save_settings`.

### Settings
- **Bedeutung:** Die UI-editierbaren Config-Felder (Whitelist `UI_EDITABLE_KEYS`) — die
  **UI-editierbare Projektion der Configuration**; API-Keys sind ausgeschlossen.
- **Verantwortung:** Persona/Stadt/Apps/Launcher/Musik/Obsidian-Pfade ändern und
  live anwenden.
- **Abgrenzung:** Settings ≠ Secrets (`PROTECTED_KEYS`, nie über die API); Settings ⊂
  Configuration (die Projektion, nicht das Gesamtdokument).
- **Quellen:** `config_loader.UI_EDITABLE_KEYS`/`save_settings`, `GET|POST /settings`,
  `server.apply_settings` (`server.py:263`).

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

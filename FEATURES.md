# Jarvis — Feature-Checkliste

Regressionsschutz: Liste der bestehenden Funktionen. Der Stabilitäts-Pass (und die
vorherige Entfernung der externen Musik-Streaming-Anbindung) entfernt **keine** dieser
Funktionen.

| # | Feature | Quelle | Status |
|---|---------|--------|--------|
| 1 | Double-Clap-Trigger startet die Session | [scripts/clap-trigger.py](scripts/clap-trigger.py) → [scripts/launch-session.ps1](scripts/launch-session.ps1) | ✅ unverändert |
| 2 | Sprach-Konversation (Mikrofon → WS → LLM → TTS) | [frontend/main.js](frontend/main.js), [assistant_core.py](assistant_core.py) `process_message` | ✅ unverändert |
| 3 | Kollegen-Persona (Deutsch, Duzen, auf Augenhoehe) | [assistant_core.py](assistant_core.py) `build_system_prompt` | ✅ config-getrieben (`user_name`/`user_role`/`user_address` statt Hardcode) |
| 4 | Begrüßung mit Wetter + Aufgaben bei „activate" | [assistant_core.py](assistant_core.py) `refresh_data`, `get_weather_sync`, [memory.py](memory.py) `get_tasks_sync` | ✅ unverändert |
| 5 | Obsidian-Vault-Zusammenfassung | [memory.py](memory.py) `get_vault_summary_sync` | ✅ unverändert |
| 6 | Browser-Suche `[ACTION:SEARCH]` | [browser_tools.py](browser_tools.py) `search_and_read` | ✅ unverändert |
| 7 | Seite besuchen `[ACTION:BROWSE]` | [browser_tools.py](browser_tools.py) `visit` | ✅ unverändert |
| 8 | URL öffnen `[ACTION:OPEN]` (nur http/https) | [browser_tools.py](browser_tools.py) `open_url`, [actions.py](actions.py) `normalize_url` | ✅ unverändert |
| 9 | Bildschirm sehen `[ACTION:SCREEN]` (Claude Vision) | [screen_capture.py](screen_capture.py) | ✅ unverändert |
| 10 | Weltnachrichten `[ACTION:NEWS]` | [browser_tools.py](browser_tools.py) `fetch_news` | ✅ unverändert |
| 11 | Obsidian-Inbox lesen/schreiben `[ACTION:INBOX_READ/WRITE]` | [assistant_core.py](assistant_core.py) `execute_action` | ✅ unverändert |
| 12 | Fenster-Snapping (Multi-Monitor) | [scripts/launch-session.ps1](scripts/launch-session.ps1) | ✅ nur robuster |
| 13 | Natives pywebview-Fenster + Tray + Win+J + Mica | [jarvis-launcher.pyw](jarvis-launcher.pyw) | ✅ unverändert |
| 14 | Hintergrundmusik beim Start (lokale MP3) | [scripts/launch-session.ps1](scripts/launch-session.ps1) | ✅ erhalten (externe Streaming-Quelle entfernt) |
| 15 | Mikrofon stummschalten (Stimme + Button) | [frontend/main.js](frontend/main.js) `toggleMute` | ✅ unverändert |
| 16 | Autostart bei Windows-Login (Task Scheduler) | [README.md](README.md), [SETUP.md](SETUP.md) | ✅ unverändert |
| 17 | WS-Security (Origin + Session-Token), Bind an 127.0.0.1 | [server.py](server.py) `websocket_endpoint`, [actions.py](actions.py) `is_origin_acceptable` | ✅ gehärtet |
| 18 | Zentrale Config-Validierung mit klaren Fehlern | [config_loader.py](config_loader.py) | ✅ neu (Stabilität, kein Feature-Verlust) |
| 19 | Status-Center (Server/Mikro/Zustand/letzter Fehler) | [frontend/index.html](frontend/index.html), [frontend/main.js](frontend/main.js) | ✅ neu |
| 20 | Manuelle Texteingabe als Fallback (Strg+Enter) | [frontend/main.js](frontend/main.js) `sendUtterance` | ✅ neu |
| 21 | Startup-Checks: Obsidian-Pfade + Playwright/Chromium (Warnungen, `/health`) | [config_loader.py](config_loader.py) `check_runtime_environment`, [server.py](server.py) | ✅ neu |
| 22 | Browser-Tab-Limit (max. 5, ältester schließt automatisch) | [browser_tools.py](browser_tools.py) `_new_page_capped` | ✅ neu |
| 23 | UI-Modi: Panel (420×560, unten rechts, always-on-top) / Fokus (groß, zentriert) | [jarvis-launcher.pyw](jarvis-launcher.pyw) `set_window_mode`, [frontend/main.js](frontend/main.js) `applyUiMode` | ✅ neu |
| 24 | Klare Orb-Zustände: idle/listening/thinking/speaking/**muted**/**error** | [frontend/main.js](frontend/main.js) `setOrbState`, [frontend/style.css](frontend/style.css) | ✅ neu |
| 25 | Transcript: letzte 20 Nachrichten, Suche, Kopieren (einzeln + alles), Timestamps | [frontend/main.js](frontend/main.js) `renderTranscript` | ✅ neu |
| 26 | Aktionshistorie im Fokus-Modus (WS-Events `type=action`, start/done/error) | [assistant_core.py](assistant_core.py) `send_action_event`, [frontend/main.js](frontend/main.js) `addActionEntry` | ✅ neu |
| 27 | Settings-UI + `GET/POST /settings` (Token-geschützt, Whitelist, Secrets nie über die API) | [server.py](server.py), [config_loader.py](config_loader.py) `save_settings`, [frontend/settings.js](frontend/settings.js) | ✅ neu |
| 28 | Strukturierte Fehler-Banner (Sprachausgabe/KI/Mikrofon/Browser) statt stiller Logs | [assistant_core.py](assistant_core.py) `send_error`, [frontend/main.js](frontend/main.js) `showErrorBanner` | ✅ neu |
| 29 | Mikrofonmodus: Immer zuhören / Push-to-Talk (Leertaste) / Beim Start stumm | [frontend/main.js](frontend/main.js) `applyMicMode` | ✅ neu |
| 30 | `/health` mit Service-Status (config/llm/tts/browser/vault) + Startup-Fortschritt; Launcher und Session-Skript pollen `/health` | [health.py](health.py) `build_report`, [browser_tools.py](browser_tools.py) `status`, [jarvis-launcher.pyw](jarvis-launcher.pyw) `wait_for_server` | ✅ neu |
| 31 | Log-Rotation: `jarvis-launcher.log` (1 MB, 3 Archive) + `jarvis-launch.log` (256 KB) | [jarvis-launcher.pyw](jarvis-launcher.pyw) `_rotate_log`, [scripts/launch-session.ps1](scripts/launch-session.ps1) | ✅ neu |
| 32 | Timeouts/Retries pro Dienst: Claude 30s/2 Retries, ElevenLabs 20s/1 Retry, Wetter 5s/1 Retry, Browser-Aktionen 60s-Gesamt-Cap | [tts.py](tts.py) `synthesize_speech`, [assistant_core.py](assistant_core.py) `get_weather_sync`, `run_action_and_respond` | ✅ neu |
| 33 | Asynchroner Startup: Server nimmt sofort Verbindungen an, Wetter/Tasks/Vault laden im Hintergrund | [server.py](server.py) `_startup_refresh` | ✅ neu |
| 34 | Offline-Fallback: Reconnect mit exponentiellem Backoff (3s→30s), klare Statusmeldung, Mikro bleibt nutzbar | [frontend/main.js](frontend/main.js) `connect`/`ws.onclose` | ✅ neu |
| 35 | Smoke-Test: `python scripts/smoke-test.py` (Config, Imports, Server-Start, Testsuite) | [scripts/smoke-test.py](scripts/smoke-test.py) | ✅ neu |
| 36 | Inbox-Kategorien: `[ACTION:INBOX_WRITE] [Kategorie] text` (Idee/Aufgabe/Termin/Recherche/Erinnerung, Fallback „Notiz"), Eintrag als `## HH:MM · Kategorie` + `#tag` | [actions.py](actions.py) `split_inbox_category`, [memory.py](memory.py) `write_inbox_entry` | ✅ neu |
| 37 | Tagesrückblick: `INBOX_READ` fasst nach Kategorien gruppiert zusammen (aktionsspezifische Summary-Prompts) | [actions.py](actions.py) `REGISTRY` (`summary_task`) | ✅ neu |
| 38 | Morgen-Überblick ersetzt die Activate-Begrüßung: Wetter, heutige Inbox, offene Tasks, zuletzt bearbeitete Notizen | [assistant_core.py](assistant_core.py) `build_system_prompt`, [memory.py](memory.py) `read_today_inbox_sync` | ✅ neu |
| 39 | „Fasse meine letzten Notizen zusammen" `[ACTION:NOTES_RECENT]` (5 zuletzt geänderte Vault-Notizen) | [memory.py](memory.py) `read_recent_notes_sync`, `_walk_vault_md` | ✅ neu |
| 40 | Clipboard: `[ACTION:CLIPBOARD] auftrag` (verarbeiten) + `[ACTION:CLIPBOARD_NOTE]` (als Inbox-Notiz) — via PowerShell `Get-Clipboard`, ohne Zusatzpaket | [clipboard_tools.py](clipboard_tools.py), [assistant_core.py](assistant_core.py) | ✅ neu |
| 41 | Recherche-Modus `[ACTION:RESEARCH] thema`: liest 3–5 Quellen, kurze gesprochene Antwort, Quellen-Links nur im Transcript, Autosave in den Brain Dump (Kategorie Recherche), 180s-Timeout | [browser_tools.py](browser_tools.py) `search_links`, [assistant_core.py](assistant_core.py) `run_research`, `_finish_research` | ✅ neu |
| 42 | Bildschirmanalyse mit Kontextfrage `[ACTION:SCREEN] frage` („Was ist das Problem?", „Fasse diese Seite zusammen") | [screen_capture.py](screen_capture.py) `describe_screen` | ✅ neu |
| 43 | Sitzungszusammenfassung `[ACTION:SESSION_SUMMARY]` („Was haben wir heute gemacht?"), speicherbar via INBOX_WRITE | [assistant_core.py](assistant_core.py) `execute_action` | ✅ neu |
| 44 | Bestätigungs-Mechanismus für riskante Aktionen: `risk="confirm"` in der Registry (anfangs keine) → mündliche Ja/Nein-Rückfrage vor Ausführung | [actions.py](actions.py) `is_confirmation`, [assistant_core.py](assistant_core.py) `pending_confirm` | ✅ neu |
| 45 | Mini-Aktionshistorie auch im Panel-Modus (kompakte Leiste, letzte ~3 Einträge) | [frontend/style.css](frontend/style.css) | ✅ neu |
| 46 | Zentrale Action-Registry: Label, Payload-Regel, Risk, Timeout und Summary-Prompt pro Aktion in einem `ActionSpec` | [actions.py](actions.py) `REGISTRY` | ✅ neu |
| 47 | Stopp: „Stopp"/Esc/Stopp-Button bricht Wiedergabe UND laufende Aktion ab (Nachrichten laufen als Task, Stopp cancelt sie) | [server.py](server.py) `websocket_endpoint`, [actions.py](actions.py) `is_stop_command`, [frontend/main.js](frontend/main.js) `requestStop` | ✅ neu |
| 48 | Langzeit-Gedächtnis `[ACTION:MEMORY_WRITE]`: „Jarvis Memory.md" im Vault (Fallback `memory.md` im Workspace), nutzer-editierbar, fließt in den System-Prompt ein, speichert NUR auf ausdrücklichen Wunsch | [memory.py](memory.py) `append_memory`, `read_memory_sync` | ✅ neu |
| 49 | Recherche-Fallback ohne Browser: `html.duckduckgo.com` via httpx wenn Chromium fehlt oder Selektoren leer sind; dünne Quellenlage (<3) wird ehrlich angesagt | [browser_tools.py](browser_tools.py) `_search_links_fallback`, [assistant_core.py](assistant_core.py) `run_research` | ✅ neu |
| 50 | Modul-Split: server.py (958→~300 Zeilen) nur noch HTTP/WS; Gesprächsfluss in assistant_core.py, TTS in tts.py, Obsidian/Memory in memory.py, Diagnose in health.py | [assistant_core.py](assistant_core.py), [tts.py](tts.py), [memory.py](memory.py), [health.py](health.py) | ✅ neu |
| 51 | Vault-Kontext-Broker `[ACTION:PROJECT_CONTEXT] frage`: lokale, token-sparsame Vault-Suche (Ranking nach Dateiname/Überschrift/Ordner/Text + Recency/Tags), nur kurze Ausschnitte ans LLM, Secret-Dateien/-Zeilen ausgenommen | [memory.py](memory.py) `get_project_context_sync`, [assistant_core.py](assistant_core.py) `execute_action` | ✅ neu |
| 52 | App-Launcher `[ACTION:APP_OPEN] app-name`: startet NUR Apps aus der `config.apps`-Registry (Allowlist, kein `shell=True`, keine freien Kommandos vom LLM); Sprachbefehl und UI-Klick (`POST /commands/app/open`) nutzen dieselbe Logik; `autostart`-Flag steuert den Sessionstart | [app_launcher.py](app_launcher.py), [server.py](server.py) `command_app_open`, [actions.py](actions.py) | ✅ neu |
| 53 | Command Center im Fokus-Modus: drei Spalten (Gespräch · „Heute" mit Tasks/Inbox/letzten Notizen · Apps/Aktionen/System), gespeist aus `GET /dashboard/state` (Token-geschützt); Panel-Modus unverändert | [frontend/main.js](frontend/main.js) `loadDashboardState`, [server.py](server.py) `dashboard_state`, [frontend/style.css](frontend/style.css) | ✅ neu |

## Hinweise

- **Musik:** Die frühere externe Streaming-Anbindung wurde auf ausdrücklichen Wunsch
  vollständig entfernt. Die Start-Musik läuft weiterhin über die lokale MP3-Logik
  (Punkt 14) — kein Funktionsverlust.
- **`OPEN`:** bleibt bewusst auf `http`/`https` beschränkt. App-Schemes wie
  `obsidian://` laufen über die App-Registry (`config.apps`) — per Sprache via
  `APP_OPEN` (Punkt 52) oder Klick im Command Center, immer durch die Allowlist
  in `app_launcher.py`.
- **Architektur (Punkt 50):** Der Modularisierungs-Pass hat Verhalten und
  Wire-Format (`[ACTION:...]`, WS-Frames, `/health`-Shape) bewusst NICHT
  geändert — nur Code verschoben, Registry eingeführt und Stopp/Memory/
  Recherche-Fallback ergänzt.
- **Langzeit-Gedächtnis (Punkt 48):** speichert nur auf ausdrückliche
  Aufforderung („merk dir dauerhaft …"); die Datei ist normales Markdown im
  Vault und kann jederzeit editiert oder gelöscht werden. Tagesnotizen gehen
  weiterhin in den Brain Dump (INBOX_WRITE).
- **Nach Claude-Änderungen:** `python scripts/smoke-test.py` ausführen und diese
  Tabelle gegenprüfen — verhindert „aus Versehen kaputt“-Momente.

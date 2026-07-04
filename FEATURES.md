# Jarvis — Feature-Checkliste

Regressionsschutz: Liste der bestehenden Funktionen. Der Stabilitäts-Pass (und die
vorherige Entfernung der externen Musik-Streaming-Anbindung) entfernt **keine** dieser
Funktionen.

| # | Feature | Quelle | Status |
|---|---------|--------|--------|
| 1 | Double-Clap-Trigger startet die Session | [scripts/clap-trigger.py](scripts/clap-trigger.py) → [scripts/launch-session.ps1](scripts/launch-session.ps1) | ✅ unverändert |
| 2 | Sprach-Konversation (Mikrofon → WS → LLM → TTS) | [frontend/main.js](frontend/main.js), [server.py](server.py) `process_message` | ✅ unverändert |
| 3 | Kollegen-Persona (Deutsch, Duzen, auf Augenhoehe) | [server.py](server.py) `build_system_prompt` | ✅ config-getrieben (`user_name`/`user_role`/`user_address` statt Hardcode) |
| 4 | Begrüßung mit Wetter + Aufgaben bei „activate" | [server.py](server.py) `refresh_data`, `get_weather_sync`, `get_tasks_sync` | ✅ unverändert |
| 5 | Obsidian-Vault-Zusammenfassung | [server.py](server.py) `get_vault_summary_sync` | ✅ unverändert |
| 6 | Browser-Suche `[ACTION:SEARCH]` | [browser_tools.py](browser_tools.py) `search_and_read` | ✅ unverändert |
| 7 | Seite besuchen `[ACTION:BROWSE]` | [browser_tools.py](browser_tools.py) `visit` | ✅ unverändert |
| 8 | URL öffnen `[ACTION:OPEN]` (nur http/https) | [browser_tools.py](browser_tools.py) `open_url`, [actions.py](actions.py) `normalize_url` | ✅ unverändert |
| 9 | Bildschirm sehen `[ACTION:SCREEN]` (Claude Vision) | [screen_capture.py](screen_capture.py) | ✅ unverändert |
| 10 | Weltnachrichten `[ACTION:NEWS]` | [browser_tools.py](browser_tools.py) `fetch_news` | ✅ unverändert |
| 11 | Obsidian-Inbox lesen/schreiben `[ACTION:INBOX_READ/WRITE]` | [server.py](server.py) `execute_action` | ✅ unverändert |
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
| 26 | Aktionshistorie im Fokus-Modus (WS-Events `type=action`, start/done/error) | [server.py](server.py) `send_action_event`, [frontend/main.js](frontend/main.js) `addActionEntry` | ✅ neu |
| 27 | Settings-UI + `GET/POST /settings` (Token-geschützt, Whitelist, Secrets nie über die API) | [server.py](server.py), [config_loader.py](config_loader.py) `save_settings`, [frontend/settings.js](frontend/settings.js) | ✅ neu |
| 28 | Strukturierte Fehler-Banner (Sprachausgabe/KI/Mikrofon/Browser) statt stiller Logs | [server.py](server.py) `send_error`, [frontend/main.js](frontend/main.js) `showErrorBanner` | ✅ neu |
| 29 | Mikrofonmodus: Immer zuhören / Push-to-Talk (Leertaste) / Beim Start stumm | [frontend/main.js](frontend/main.js) `applyMicMode` | ✅ neu |
| 30 | `/health` mit Service-Status (config/llm/tts/browser/vault) + Startup-Fortschritt; Launcher und Session-Skript pollen `/health` | [server.py](server.py) `health`, [browser_tools.py](browser_tools.py) `status`, [jarvis-launcher.pyw](jarvis-launcher.pyw) `wait_for_server` | ✅ neu |
| 31 | Log-Rotation: `jarvis-launcher.log` (1 MB, 3 Archive) + `jarvis-launch.log` (256 KB) | [jarvis-launcher.pyw](jarvis-launcher.pyw) `_rotate_log`, [scripts/launch-session.ps1](scripts/launch-session.ps1) | ✅ neu |
| 32 | Timeouts/Retries pro Dienst: Claude 30s/2 Retries, ElevenLabs 20s/1 Retry, Wetter 5s/1 Retry, Browser-Aktionen 60s-Gesamt-Cap | [server.py](server.py) `synthesize_speech`, `get_weather_sync`, `process_message` | ✅ neu |
| 33 | Asynchroner Startup: Server nimmt sofort Verbindungen an, Wetter/Tasks/Vault laden im Hintergrund | [server.py](server.py) `_startup_refresh` | ✅ neu |
| 34 | Offline-Fallback: Reconnect mit exponentiellem Backoff (3s→30s), klare Statusmeldung, Mikro bleibt nutzbar | [frontend/main.js](frontend/main.js) `connect`/`ws.onclose` | ✅ neu |
| 35 | Smoke-Test: `python scripts/smoke-test.py` (Config, Imports, Server-Start, Testsuite) | [scripts/smoke-test.py](scripts/smoke-test.py) | ✅ neu |
| 36 | Inbox-Kategorien: `[ACTION:INBOX_WRITE] [Kategorie] text` (Idee/Aufgabe/Termin/Recherche/Erinnerung, Fallback „Notiz"), Eintrag als `## HH:MM · Kategorie` + `#tag` | [actions.py](actions.py) `split_inbox_category`, [server.py](server.py) `write_inbox_entry` | ✅ neu |
| 37 | Tagesrückblick: `INBOX_READ` fasst nach Kategorien gruppiert zusammen (aktionsspezifische Summary-Prompts) | [server.py](server.py) `SUMMARY_TASKS` | ✅ neu |
| 38 | Morgen-Überblick ersetzt die Activate-Begrüßung: Wetter, heutige Inbox, offene Tasks, zuletzt bearbeitete Notizen | [server.py](server.py) `build_system_prompt`, `read_today_inbox_sync` | ✅ neu |
| 39 | „Fasse meine letzten Notizen zusammen" `[ACTION:NOTES_RECENT]` (5 zuletzt geänderte Vault-Notizen) | [server.py](server.py) `read_recent_notes_sync`, `_walk_vault_md` | ✅ neu |
| 40 | Clipboard: `[ACTION:CLIPBOARD] auftrag` (verarbeiten) + `[ACTION:CLIPBOARD_NOTE]` (als Inbox-Notiz) — via PowerShell `Get-Clipboard`, ohne Zusatzpaket | [clipboard_tools.py](clipboard_tools.py), [server.py](server.py) | ✅ neu |
| 41 | Recherche-Modus `[ACTION:RESEARCH] thema`: liest 3–5 Quellen, kurze gesprochene Antwort, Quellen-Links nur im Transcript, Autosave in den Brain Dump (Kategorie Recherche), 180s-Timeout | [browser_tools.py](browser_tools.py) `search_links`, [server.py](server.py) `run_research`, `_finish_research` | ✅ neu |
| 42 | Bildschirmanalyse mit Kontextfrage `[ACTION:SCREEN] frage` („Was ist das Problem?", „Fasse diese Seite zusammen") | [screen_capture.py](screen_capture.py) `describe_screen` | ✅ neu |
| 43 | Sitzungszusammenfassung `[ACTION:SESSION_SUMMARY]` („Was haben wir heute gemacht?"), speicherbar via INBOX_WRITE | [server.py](server.py) `execute_action` | ✅ neu |
| 44 | Bestätigungs-Mechanismus für riskante Aktionen: `CONFIRM_ACTIONS` (anfangs leer) → mündliche Ja/Nein-Rückfrage vor Ausführung | [actions.py](actions.py) `is_confirmation`, [server.py](server.py) `pending_confirm` | ✅ neu |
| 45 | Mini-Aktionshistorie auch im Panel-Modus (kompakte Leiste, letzte ~3 Einträge) | [frontend/style.css](frontend/style.css) | ✅ neu |

## Hinweise

- **Musik:** Die frühere externe Streaming-Anbindung wurde auf ausdrücklichen Wunsch
  vollständig entfernt. Die Start-Musik läuft weiterhin über die lokale MP3-Logik
  (Punkt 14) — kein Funktionsverlust.
- **`OPEN`:** bleibt bewusst auf `http`/`https` beschränkt (App-Schemes wie `obsidian://`
  laufen über den Launcher/`config.apps`, nicht über die Sprach-Aktion).
- Dieser Pass hat **keine** Architektur- oder UI-Änderungen vorgenommen — nur
  Fehlertoleranz, Config-Validierung und eine WS-Randfall-Absicherung.
- **Nach Claude-Änderungen:** `python scripts/smoke-test.py` ausführen und diese
  Tabelle gegenprüfen — verhindert „aus Versehen kaputt“-Momente.

# Jarvis – Test-Seams (Phase 3A / Prompt 6)

> Öffentliche Test-Seams, an denen Prompt 6 ein verhaltensorientiertes
> Sicherheitsnetz aufbaut. **Ein Seam wird erst getestet, nachdem der Nutzer
> ihn ausdrücklich bestätigt hat.** Stand: Entwurf zur Bestätigung.
>
> Grundregeln (aus `$tdd`): Test am öffentlichen Interface, nicht an Interna;
> eigene Module nicht mocken; nur externe Grenzen kontrolliert ersetzen; erwartete
> Werte aus den bestätigten Verträgen (siehe `docs/contracts/`) ableiten.
>
> Status ∈ {`proposed`, `approved`, `deferred`, `rejected`}.
> **Vom Nutzer bestätigt am 2026-07-14** („Alle wie vorgeschlagen"): alle Seams
> `approved`; SEAM-BROWSER-UI und der native Windows-Anteil `deferred → Prompt 7`.

## Überblick

| Seam ID | Testebene | Öffentliche Oberfläche | Externe Grenze (ersetzt) | Aktuelle Abdeckung | Status |
|---|---|---|---|---|---|
| SEAM-REST | Contract (TestClient) | FastAPI-App, echte Routen, Token-Auth | — (nur pro Route, s.u.) | teilweise | approved |
| SEAM-WS | Contract/Integration (TestClient WS) | `/ws` Handshake + Frames + Stop | LLM/TTS via `process_message`-Stub bzw. Adapter | gut (Handshake/Stop) | approved |
| SEAM-ACTION | Contract (pur) | `actions.parse_action` + Registry | keine | sehr gut | approved |
| SEAM-ACTION-EXEC | Contract (Action-Interface) | `spec.execute(payload, ctx)` + `spec.describe(prompt_ctx)` + `render_action_block` | nur externe Grenzen (Browser/Screen/Clipboard/Prozessstart); Vault/Inbox = Tempdir | sehr gut (22/22, `test_action_deep_module`) | approved (RFC-0001, Phase 4B) |
| SEAM-CONVERSATION | Integration (echter WS-Dialog) | `/ws` Dialog → `process_message` | `ai`, `synthesize_speech` (+ Aktions-Grenzen) | teilweise (nicht über WS) | approved |
| SEAM-CONFIG | Contract/Integration (Temp-Datei) | `config_loader` Load/Validate (Leaf) | Dateisystem = real (Tempdir) | gut | approved |
| SEAM-CONFIGURATION | Contract (Configuration-Interface) | `Configuration.snapshot`/`settings_view`/`mutate(intent, expected_revision)` + `schema_version_of`/`migrate_document`/`read_document` | echte Temp-Datei; keine privaten Lock-/Hash-/Temp-Helfer | sehr gut (`test_configuration`, 5× flakefrei) | approved (RFC-0003, Phase 4D) |
| SEAM-MEMORY | Contract/Integration (Temp-Vault) | `memory` Inbox/Vault/Memory-Fns | Dateisystem = real (Tempdir); `ai` bei Dedup | gut | approved |
| SEAM-PROVIDERS | Boundary-Fakes | `ai`/`synthesize_speech`/`browser_tools`/`clipboard`/`monitors` | jede Grenze spezifisch | gut | approved |
| SEAM-LAUNCHER | Contract/Integration (TestClient) | Launcher-/Profil-REST + `app_launcher` Helfer | `_start_url`/`_start_process` | gut | approved |
| SEAM-WINDOWS | Contract (Datenebene) | `monitors.detect_monitors`, `/launcher/monitors` | `monitors._enum_monitors_raw` (ctypes) | teilweise | approved (native Smokes → **Prompt 7**) |
| SEAM-BROWSER-UI | — | sichtbares Browserverhalten, Rollen/Labels | — | — | **deferred → Prompt 7** |

Legende „aktuelle Abdeckung": grob, verweist auf bestehende Tests (unten je Seam).

---

## SEAM-REST

- **Nutzer-/Caller-Verhalten:** Das Frontend (und Launcher/Tests) rufen lokale
  REST-Endpunkte mit dem Session-Token (`x-jarvis-token`) auf und erhalten
  JSON-Zustandsberichte bzw. wenden Settings/Profile an.
- **Öffentliches Interface:** `server.app` über `fastapi.testclient.TestClient`;
  echte Routen, echte Requestvalidierung, echte Token-Prüfung
  (`server._settings_token_ok`, `server.py:236`), echte Serialisierung.
- **Eingaben:** HTTP-Methode + Pfad, `x-jarvis-token`-Header, JSON-Body,
  Pfadparameter (`app_id`, `profile_id`).
- **Beobachtbare Ausgaben:** Statuscode, JSON-Felder (`ok`, `errors`,
  `settings`/`apps`/`profiles`/`warnings`), Fehlerform `{ok:false, errors:[…]}`.
- **Security-Invarianten:** SI-4 (nur lokal), Token-Gate für alle sensiblen
  Routen; Secrets (`PROTECTED_KEYS`) nie in Responses (SI-5); `/health` bewusst
  ungeschützt und secret-frei.
- **Reale eigene Infrastruktur:** FastAPI-Routing, `config_loader`-Validierung,
  `health.build_report`, `app_launcher`-Logik, atomare Persistenz (Temp-Config).
- **Kontrollierte externe Grenze:** keine generische — nur pro Route: Prozessstart
  (`app_launcher._start_url/_start_process`), Monitor-Enumeration
  (`monitors.detect_monitors`).
- **Verbotene interne Prüfungen:** keine Assertions auf interne Call-Reihenfolge/
  Call-Counts; keine privaten Helfer (`_public_settings`, `_scan_music_folder`)
  direkt aufrufen — nur über die Route beobachten.
- **Testebene:** Contract (Route-für-Route).
- **Aktuelle Abdeckung:** `test_settings_api.py`, `test_dashboard_api.py`,
  `test_launcher_api.py`, `test_music_api.py`, `test_ws.py::HealthEndpointTests`.
- **Bestehende Testschuld:** keine gravierende; Auth-Ablehnung ist pro Routen-
  Gruppe noch nicht durchgängig als eigener Contract-Test erfasst.
- **Status:** approved (bestätigt 2026-07-14).

## SEAM-WS

- **Nutzer-/Caller-Verhalten:** Browser/pywebview verbinden `/ws?token=…` mit
  lokalem/`null`-Origin, senden `{text}`/`{type:"stop"}` und erhalten Frames.
- **Öffentliches Interface:** `TestClient(server.app).websocket_connect(...)`;
  echter Origin-/Token-Handshake (`server.py:102`,
  `actions.is_origin_acceptable`), echte Queue/Stop-Logik, ausgehende Frames.
- **Eingaben:** `token`-Query, `origin`-Header, Client-Frames `{text}` /
  `{type:"stop"}`.
- **Beobachtbare Ausgaben:** Verbindung akzeptiert/`1008`-Close; Frames
  `health`, `response`, `action` (start/done/error), `error`, `stop`.
- **Security-Invarianten:** SI-4 (lokal), Origin-Policy + Token-Gate; `null`-Origin
  nur mit gültigem Token (pywebview); Stopp bricht Wirkung ab (SI-7-nah).
- **Reale eigene Infrastruktur:** WS-Endpunkt, Worker/Queue, Cancellation,
  `pending_confirm`-Aufräumen.
- **Kontrollierte externe Grenze:** für **Stop-/Transport-Mechanik** wird
  `assistant_core.process_message` durch einen kontrollierten langlaufenden Stub
  ersetzt (nötig für deterministisches Cancel-Timing — keine echten Provider);
  für **Frame-Verträge** siehe SEAM-CONVERSATION (echtes `process_message`, nur
  Provider ersetzt).
- **Verbotene interne Prüfungen:** kein direktes Setzen von `conversations`;
  keine Assertions auf interne Task-Objekte — nur Frames/Verbindungszustand.
- **Testebene:** Contract (Handshake) + Integration (Stop).
- **Aktuelle Abdeckung:** `test_ws.py::WebSocketHandshakeTests` (6 Origin/Token-
  Fälle + Health-Frame), `::StopFlowTests` (Stop/Disconnect/Queue/Pending),
  `::FrameShapeTests` (send_error/send_action_event).
- **Bestehende Testschuld:** `StopFlowTests` patcht die interne Funktion
  `process_message` und setzt `pending_confirm` global (Zeile 275). Vertretbar als
  Transport-Double (deterministisches Cancel braucht eine steuerbare
  langlaufende Task), bleibt aber als Legacy-Schuld markiert; die Frame-Verträge
  der Happy-Path werden künftig über SEAM-CONVERSATION real abgedeckt.
- **Status:** approved (bestätigt 2026-07-14).

## SEAM-ACTION

- **Nutzer-/Caller-Verhalten:** `process_message` gibt LLM-Text an
  `parse_action`; nur gültige, registrierte Actions werden ausgeführt.
- **Öffentliches Interface:** `actions.parse_action`, `actions.Action`,
  `actions.REGISTRY`/`spec_for`/`label_for`, `normalize_url`,
  `parse_place_payload`, `split_inbox_category`, `is_confirmation`,
  `is_stop_command`, `is_origin_acceptable`.
- **Eingaben:** roher LLM-Text mit `[ACTION:TYPE] payload`.
- **Beobachtbare Ausgaben:** `(spoken_text, Action|None, error|None)`; Payload-/
  URL-/Risk-Regeln; unbekannte/ungültige Tags → keine Action.
- **Security-Invarianten:** SI-1 (nur registrierte Actions), SI-6 (nur http/https,
  keine `javascript:`/`file:`/`data:`), Confirm-Actions markiert (SI-7).
- **Reale eigene Infrastruktur:** die gesamte Parser-/Registry-Logik (pur, ohne
  Netz/Config).
- **Kontrollierte externe Grenze:** keine (rein).
- **Verbotene interne Prüfungen:** keine (Interface ist bereits die Oberfläche).
- **Testebene:** Contract (pur).
- **Aktuelle Abdeckung:** `test_actions.py` (umfangreich, 92 Referenzen).
- **Bestehende Testschuld:** keine.
- **Status:** approved (bestätigt 2026-07-14).

## SEAM-CONVERSATION

- **Nutzer-/Caller-Verhalten:** Nutzer sendet Text über `/ws`; Jarvis antwortet
  (`response`), führt ggf. eine Aktion aus (`action` start/done), fragt bei
  riskanten Aktionen mündlich nach und meldet Fehler strukturiert.
- **Öffentliches Interface:** **echter WS-Dialog** (`TestClient` WS) → Worker →
  `assistant_core.process_message`. Beobachtung ausschließlich über Frames.
- **Eingaben:** Client-`{text}`-Frames; gefälschte Provider-Antworten über den
  bestätigten Adapter (`ai`).
- **Beobachtbare Ausgaben:** `response` (Text/Audio-Base64), `action`
  start/done/error, `error` (component/text/hint), Confirm-Rückfrage als
  `response`, Stop.
- **Security-Invarianten:** SI-1 (untrusted LLM-Text autorisiert nur registrierte
  Actions), SI-7 (MEMORY_FORGET erst nach mündlichem Ja), Secrets nie in Frames
  (SI-5).
- **Reale eigene Infrastruktur:** `process_message`, `run_action_and_respond`,
  `execute_action`, `pending_confirm`, Verlauf, Frame-Erzeugung.
- **Kontrollierte externe Grenze:** `assistant_core.ai` (Anthropic),
  `assistant_core.synthesize_speech` (ElevenLabs), plus je nach Aktion
  `browser_tools`/`screen_capture`/`clipboard_tools`. **Keine** internen Funktionen
  patchen.
- **Verbotene interne Prüfungen:** kein Setzen/Lesen von `conversations`/
  `pending_confirm`; kein Patchen von `send_spoken_response`/
  `run_action_and_respond`/`process_message`; keine Call-Count-Assertions.
- **Testebene:** Integration (End-to-End innerhalb des Prozesses, ohne echte
  Provider).
- **Aktuelle Abdeckung:** `test_integration_research.py` (RESEARCH-Flow, aber über
  direkten `process_message`-Aufruf, nicht über den WS-Dialog); `test_confirm_flow.py`
  (Confirm-Flow, aber implementation-coupled).
- **Bestehende Testschuld (Ziel dieser Seam, sie zu ersetzen):**
  - `test_confirm_flow.py` patcht `send_spoken_response` + `run_action_and_respond`
    (interne Fns) und setzt `conversations`/`pending_confirm` global.
  - `test_integration_research.py` ruft `process_message` direkt auf und setzt
    `conversations` global (Provider korrekt als Grenze ersetzt).
  - `test_inbox.py` ruft `_finish_research` (privat) direkt auf und setzt
    `conversations` für den SESSION_SUMMARY-Pfad.
  Ersatz: neue Frame-Verträge über den echten WS-Dialog. **Alte Tests bleiben in
  Prompt 6 bestehen** (nicht löschen) und werden erst entfernt, wenn die Seam
  gleichwertige Abdeckung trägt und die volle Suite grün ist.
- **Status:** approved (bestätigt 2026-07-14).

## SEAM-CONFIG

- **Nutzer-/Caller-Verhalten:** Serverstart lädt/validiert `config.json`;
  Settings-Speichern merged UI-Felder atomar zurück und bewahrt Secrets/unbekannte
  Felder.
- **Öffentliches Interface:** `config_loader.load_config`, `validate_config`,
  `validate_settings_update`, `save_settings`, `resolve_config_path`, sowie die
  `validate_*_value`-Prüfer.
- **Eingaben:** Pfad zu einer **temporären** JSON-Datei; Update-Dicts.
- **Beobachtbare Ausgaben:** geladene/gemergte Config; Fehlerlisten; Datei erneut
  über `load_config` lesbar; atomarer Fehler lässt Hauptdatei unversehrt.
- **Security-Invarianten:** SI-5 (Secrets nie in Meldungen — nur Schlüsselnamen);
  `PROTECTED_KEYS` nicht über Settings änderbar; Whitelist `UI_EDITABLE_KEYS`.
- **Reale eigene Infrastruktur:** gesamte Validierung + atomarer Schreibpfad
  (`.tmp` → `os.replace`); echtes Tempdir.
- **Kontrollierte externe Grenze:** keine (Dateisystem ist Ziel des Vertrags,
  daher real, im Tempdir).
- **Verbotene interne Prüfungen:** keine privaten Helfer (`_looks_like_placeholder`)
  isoliert testen; keine persönliche `config.json` lesen.
- **Testebene:** Contract/Integration (Temp-Datei).
- **Aktuelle Abdeckung:** `test_config.py` (89 Referenzen), `test_config_seam.py`.
- **Bestehende Testschuld:** keine gravierende.
- **Status:** approved (bestätigt 2026-07-14).

## SEAM-MEMORY

- **Nutzer-/Caller-Verhalten:** Inbox schreiben/lesen, Langzeit-Gedächtnis
  schreiben/lesen/vergessen, Vault-Kontext suchen — alles über einen **temporären**
  Vault/Inbox-Ordner.
- **Öffentliches Interface:** `memory.write_inbox_entry`, `read_today_inbox_sync`,
  `inbox_available`, `append_memory`, `read_memory_sync`, `forget_memory`,
  `get_project_context_sync`, `read_recent_notes_sync`, `get_vault_summary_sync`,
  `memory_file_path`, `configure`.
- **Eingaben:** Temp-Pfade (`configure`), Markdown-Fixtures, Text-Einträge,
  Suchbegriffe.
- **Beobachtbare Ausgaben:** Rückgabe-Strings; über öffentliche Lesewege erneut
  geprüfter Dateiinhalt; Secret-Dateien/-Zeilen erscheinen **nicht** im
  Projektkontext.
- **Security-Invarianten:** SI-5/SI-8 (Secret-Pfade/-Zeilen gefiltert,
  `memory.py:204/211`), handschriftlicher Freitext bleibt bei `forget_memory`
  unangetastet, MEMORY_WRITE nur explizit.
- **Reale eigene Infrastruktur:** gesamte Memory-/Vault-Logik; echtes Tempdir.
- **Kontrollierte externe Grenze:** `ai` nur im Dedup-Pfad von
  `write_inbox_entry` (FakeAI); sonst keine.
- **Verbotene interne Prüfungen:** keine privaten Helfer (`_context_excerpt`,
  `_walk_vault_md`) isoliert prüfen, wenn das Verhalten über die öffentliche
  Funktion beobachtbar ist; keine echten persönlichen Vault-Inhalte.
- **Testebene:** Contract/Integration (Temp-Vault).
- **Aktuelle Abdeckung:** `test_memory.py` (40 Referenzen, inkl. Secret-Filter),
  `test_inbox.py`.
- **Bestehende Testschuld:** `test_inbox.py` nutzt teils `conversations`-Global +
  `_finish_research` (siehe SEAM-CONVERSATION).
- **Status:** approved (bestätigt 2026-07-14).

## SEAM-PROVIDERS

- **Nutzer-/Caller-Verhalten:** Jarvis ruft externe Dienste; Tests dürfen **nie**
  echte Provider/Netzwerke/Prozesse treffen.
- **Öffentliches Interface (Grenzen):** `assistant_core.ai` (Anthropic),
  `assistant_core.synthesize_speech`/`tts.synthesize_speech` (ElevenLabs),
  `browser_tools.search_links`/`visit`/`search_and_read`/`fetch_news`
  (externe Websites/Browser), `clipboard_tools.subprocess.run` (Clipboard),
  `monitors._enum_monitors_raw` (Windows-API), `screen_capture` (Screen/Vision).
- **Eingaben:** je Grenze ein **spezifischer** Fake (SDK-Stil), keine generische
  Fake-Fabrik mit großer Fallunterscheidung.
- **Beobachtbare Ausgaben:** die Rückgabeform der jeweiligen Grenze
  (`SimpleNamespace(content=[…])` für `ai`; `(bytes, err)` für TTS; Dicts für
  Browser; `CompletedProcess` für Clipboard).
- **Security-Invarianten:** 0 echte Provideraufrufe; keine echten Kosten; keine
  echten Desktop-/Browserwirkungen; keine Secret-Werte in Fakes.
- **Reale eigene Infrastruktur:** alles hinter der Grenze (Aufrufer bleibt real).
- **Kontrollierte externe Grenze:** genau diese Liste.
- **Verbotene interne Prüfungen:** keine — Grenzen sind legitime Fakes.
- **Testebene:** Boundary-Fakes (unterstützt REST/WS/CONVERSATION/MEMORY).
- **Aktuelle Abdeckung:** `test_tts.py`, `test_browser_tools.py`,
  `test_clipboard.py`, `test_monitors.py`, plus Nutzung in Integrationstests.
- **Bestehende Testschuld:** keine.
- **Status:** approved (bestätigt 2026-07-14).

## SEAM-LAUNCHER

- **Nutzer-/Caller-Verhalten:** UI-Klick/Sprach-Aktion startet nur Allowlist-Apps;
  Profile werden über öffentliche Endpunkte verwaltet; wiederholte Änderungen sind
  idempotent.
- **Öffentliches Interface:** REST (`/commands/app/open`, `/launcher/*`) via
  TestClient; `app_launcher.launch`, `list_apps`, `find_app`, `find_profile`,
  `launcher_with_*` (pure Helfer), `configure`.
- **Eingaben:** App-/Profilnamen, Toggle/Placement-Bodies; Temp-Config.
- **Beobachtbare Ausgaben:** `{ok, app, name, message}` bzw. Profil-Response;
  Statuscodes (404 unbekannt, 400 Guard); WS-Broadcast `launcher_changed`/
  `app_event`.
- **Security-Invarianten:** nur Allowlist (`app_launcher.launch`, `:479`), keine
  freien Shell-Argumente (`_start_process` startet nur den Executable-Pfad, keine
  Shell), `command` verlässt den Server nie.
- **Reale eigene Infrastruktur:** Allowlist-/Profil-Logik, Validierung, Persistenz
  (Temp-Config).
- **Kontrollierte externe Grenze:** `_start_url`/`_start_process` (Prozess/URL),
  `monitors.detect_monitors`.
- **Verbotene interne Prüfungen:** keine Assertions auf `subprocess`-Argumente über
  das Nötigste hinaus; Verhalten über `launch()`-Ergebnis/Route beobachten.
- **Testebene:** Contract/Integration.
- **Aktuelle Abdeckung:** `test_app_launcher.py` (68), `test_launcher_api.py` (39),
  `test_voice_launcher.py` (22), `test_dashboard_api.py`.
- **Bestehende Testschuld:** keine gravierende.
- **Status:** approved (bestätigt 2026-07-14).

## SEAM-WINDOWS

- **Nutzer-/Caller-Verhalten:** Monitor-Map/Placement lesen physische
  Monitordaten; das pywebview-Fenster ist der native Host.
- **Öffentliches Interface (in Prompt 6):** `monitors.detect_monitors` und
  `GET /launcher/monitors` — **nur die Datenebene**.
- **Eingaben:** kontrollierte Monitordaten (Fake für `_enum_monitors_raw`).
- **Beobachtbare Ausgaben:** normalisierte Monitorliste; leere Liste bei
  Erkennungsfehler (Route bleibt `ok`).
- **Security-Invarianten:** keine echte Desktopmutation in Standardtests.
- **Reale eigene Infrastruktur:** Normalisierungslogik in `monitors`.
- **Kontrollierte externe Grenze:** `monitors._enum_monitors_raw` (ctypes),
  `sys.platform`-Guard.
- **Verbotene interne Prüfungen:** keine echten ctypes-/Fensteraufrufe.
- **Testebene:** Contract (Datenebene). **Echte Windows-Native-Smokes und
  pywebview-Fensterverhalten → Prompt 7.**
- **Aktuelle Abdeckung:** `test_monitors.py`, `test_launcher_api.py`
  (Monitor-Route).
- **Bestehende Testschuld:** native Smokes fehlen (bewusst, Prompt 7).
- **Status:** approved (bestätigt 2026-07-14; nativer Anteil deferred → Prompt 7).

## SEAM-BROWSER-UI

- **Reserviert für Prompt 7:** sichtbares Browserverhalten, Nutzerrollen/Labels
  (Accessibility), Visual Regression. **Keine** CSS-/Implementierungsselektoren als
  primäre Testoberfläche.
- **Testebene:** E2E/Visual/A11y (nicht in Prompt 6).
- **Status:** deferred → Prompt 7.

---

## Bestehende implementation-coupled Tests (Legacy-Testschuld)

| Test | Gepatchter privater Zustand | Ersetzende bestätigte Seam | Entfernen frühestens |
|---|---|---|---|
| `test_confirm_flow.py` | `conversations`/`pending_confirm` gesetzt; `send_spoken_response`/`run_action_and_respond` gepatcht | SEAM-CONVERSATION (Confirm-Dialog über WS) | wenn Seam gleichwertig deckt + Suite grün |
| `test_integration_research.py` | `conversations` gesetzt; direkter `process_message`-Aufruf (Provider als Grenze korrekt) | SEAM-CONVERSATION (RESEARCH über WS) | wenn Seam gleichwertig deckt + Suite grün |
| `test_inbox.py` (Teil) | `conversations` gesetzt; `_finish_research` (privat) direkt | SEAM-CONVERSATION / SEAM-MEMORY | wenn Seam gleichwertig deckt + Suite grün |
| `test_ws.py::StopFlowTests` | `process_message` gepatcht; `pending_confirm` gesetzt | SEAM-WS (Transport-Double vertretbar) — bleibt vorerst | nur falls steuerbare Cancel-Alternative entsteht |

> Regel: In Prompt 6 wird **kein** bestehender Test gelöscht. Entfernt werden darf
> ein alter Test erst, wenn die öffentliche Seam existiert, gleichwertige oder
> bessere Verhaltensabdeckung vorliegt und die volle Suite + Browserprüfung grün
> sind (frühestens spätere Phase).

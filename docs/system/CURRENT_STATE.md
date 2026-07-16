# Jarvis – Current State Baseline

> Erstellt im Rahmen von Masterplan-Prompt 1 („Aktuellen Projektstand erfassen und
> eine sichere Baseline herstellen"). Dieser Bericht **beschreibt** nur; er setzt
> keine neuen Funktionen um und ändert keinen produktiven Quellcode.

> **Status 2026-07-16 (Phase 4D, RFC-0003 IMPLEMENTIERT):** Die Configuration ist
> jetzt ein Runtime-eigenes deep module mit genau EINEM serialisierten Schreibweg
> ([configuration.py](../../configuration.py), `snapshot()`/`settings_view()`/
> `mutate(intent, expected_revision)`): `schema_version` **v1** (fehlend = v0,
> Migration ergänzt nur den Marker, mit verifiziertem bytegenauem Backup), opake
> `revision` + `409`/`If-Match` auf `/settings`, `os.replace` als Linearization Point,
> kompensierbares Live-Apply, Post-Commit-Refresh/Broadcast. Die Defekte **A–E sind
> behoben**, **F** eingegrenzt. Das **A6-Residual ist aufgelöst**: `server.config`,
> `server.CONFIG_PATH`, `server.STARTUP_WARNINGS`, `assistant_core.PERSIST_LAUNCHER`
> und `config_loader.save_settings` existieren nicht mehr; `Runtime.config` ist eine
> read-only Projektion. Details:
> [PHASE4D_VERSIONED_CONFIGURATION_MIGRATION.md](../architecture/PHASE4D_VERSIONED_CONFIGURATION_MIGRATION.md).
> Suite 688 grün. Die persönliche `config.json` wurde nicht migriert.

> **Status 2026-07-16 (Phase 4C, RFC-0003 akzeptiert):** Für Kandidat 05 (Settings
> Single Writer / versionierte Configuration) wurde
> [RFC-0003](../architecture/RFC-0003-versioned-config-single-writer.md)
> `Accepted for incremental implementation`. Fünf Config-Persistenz-Defekte sind
> unabhängig reproduziert (Datenverlust bei manueller Änderung, Lost-Update,
> Cross-Instance-Schreiben über globalen `CONFIG_PATH`, fehlender Rollback nach
> Dateischreiben, veraltete `Runtime.config`) plus ein Musik-TOCTOU-Risiko. Reiner
> Architekturpass — **kein Produktionscode geändert**; die Umsetzung folgt in Prompt 11
> in sieben rückrollbaren Slices.

## 1. Zweck und Geltungsbereich

**Zweck.** Eine reproduzierbare, ehrliche Bestandsaufnahme des Projekts, bevor der
Jarvis-Masterplan (Composition Root, Capability-/Policy-Kernel, Job-Engine,
Memory-Engine, Scheduler, Connectoren, Zertifizierung) umgesetzt wird.

**Geltungsbereich dieses Prompts.**
- Nur lesende Analyse plus Ausführung isolierter, kostenfreier Prüfungen.
- Die **einzige** durch diesen Prompt beabsichtigte Projektänderung ist diese Datei
  (`docs/system/CURRENT_STATE.md`).
- Nicht durchgeführt (bewusst, gemäß Prompt): jegliche `git reset/checkout/restore/
  clean/stash/add/commit/merge/rebase/push`, Datei-Löschungen/-Verschiebungen,
  Zeilenenden-Normalisierung, Skill-/Paket-Installationen, echte Provider-Calls
  (Anthropic/ElevenLabs/Wetter), externe Browseraktionen, Bugfixes über diesen
  Bericht hinaus.

**Beobachtete Nebenwirkung (dokumentiert, nicht beabsichtigt als „Projektänderung").**
Die in Arbeitsschritt 4 ausdrücklich geforderten Verifikationsskripte
`verify_phase4.py`/`verify_phase5.py` schreiben Screenshots/Videos in
`docs/redesign/phase-4/screenshots/` und `docs/motion/evidence/`. Beide Verzeichnisse
liegen im ohnehin **unversionierten** `docs/`-Baum (`git status`: `?? docs/…`); es wurde
**keine versionierte Datei** dadurch verändert (Zähler „geänderte versionierte Dateien"
blieb 30). Siehe §15.

**Trennung Fakt/Schlussfolgerung.** Abschnitte mit „Beobachtung" nennen direkt
gemessene Fakten; Abschnitte mit „Schlussfolgerung" enthalten Bewertungen daraus.

## 2. Repository- und Arbeitsbaumstatus

**Zeitpunkt.** 2026-07-13, lokal ~21:03–21:06, Zeitzone UTC+02:00 (CEST).

**Branch / HEAD.**
- Branch: `master`
- HEAD: `dd43a624ab20b3228963f3d3350d037092affab8`
  („Doku: Modul-Struktur, Stopp, Langzeit-Gedaechtnis, Recherche-Fallback",
  2026-07-05)

**Umfang der uncommitteten Arbeit (Beobachtung).**
- **Geänderte versionierte Dateien:** 30 (`git diff --name-only | wc -l` = 30).
- **Unversionierte Dateien (rekursiv):** 685 (`git ls-files --others --exclude-standard | wc -l` = 685).
- `git diff --stat`: 30 Dateien, +6772 / −615 Zeilen (ohne Staging; Index leer).

**Grobe Einteilung der Änderungen (versioniert *M* + neu *??*):**

| Bereich | Geändert (versioniert) | Neu (unversioniert, Auswahl) |
|---|---|---|
| Backend | `actions.py`, `assistant_core.py`, `browser_tools.py`, `config_loader.py`, `memory.py`, `server.py`, `tts.py` | `app_launcher.py`, `monitors.py` |
| Frontend | `frontend/index.html`, `frontend/main.js`, `frontend/settings.js`, `frontend/style.css` | `frontend/music.js`, `frontend/design-tokens.css`, `frontend/assets/` (lokale Fonts) |
| Launcher/Windows | `jarvis-launcher.pyw`, `scripts/clap-trigger.py`, `scripts/launch-session.ps1` | – |
| Tests | `tests/test_actions.py`, `test_browser_tools.py`, `test_config.py`, `test_inbox.py`, `test_memory.py`, `test_prompt.py`, `test_settings_api.py`, `test_tts.py`, `test_ws.py` | 10 neue: `test_app_launcher.py`, `test_clap_trigger.py`, `test_dashboard_api.py`, `test_frontend.py`, `test_integration_research.py`, `test_launcher_api.py`, `test_launcher_ps1.py`, `test_monitors.py`, `test_music_api.py`, `test_voice_launcher.py` |
| Dokumentation | `CLAUDE.md`, `FEATURES.md`, `README.md`, `SETUP.md`, `config.example.json` | `docs/` (Redesign-, Motion-, Final-Audit-, Design-Baseline-Doku), `skills-lock.json` |
| Skills/Agent-Konfiguration | `.claude/settings.local.json` | `.agents/skills/`, `.claude/skills/`, `.impeccable/` |

**Zentrale Modulgrößen (Beobachtung, `wc -l`, aktueller Arbeitsbaum):**

| Modul | Zeilen |
|---|---|
| `frontend/style.css` | 2933 |
| `frontend/main.js` | 1852 |
| `server.py` | 741 |
| `assistant_core.py` | 716 |
| `app_launcher.py` | 507 |
| `jarvis-launcher.pyw` | 485 |
| `config_loader.py` | 481 |
| `actions.py` | 430 |
| `memory.py` | 426 |
| `browser_tools.py` | 370 |
| `tts.py` | 146 |
| `monitors.py` | 94 |
| `screen_capture.py` | 61 |
| `health.py` | 54 |
| `clipboard_tools.py` | 36 |

**Zeilenenden (Beobachtung, wichtig für den Checkpoint).**
`git config core.autocrlf` = `true`, **keine** `.gitattributes`-Datei. `git diff`/`git
status` geben für ~25 Dateien die Warnung „LF will be replaced by CRLF the next time
Git touches it" aus. → Beim ersten Commit/Checkout unter dieser Konfiguration würden
Zeilenenden umgeschrieben. Das ist ein realer Checkpoint-Risikopunkt (§12), **wurde in
diesem Prompt nicht angefasst** und darf nicht pauschal normalisiert werden.

**Laufzeit.** `python --version` = **Python 3.14.5**. Vorhandene `.pyc` unter
`tests/__pycache__/` zeigen sowohl `cpython-314` als auch `cpython-310`, d.h. die Suite
lief zuvor auch unter Python 3.10.

## 3. Verifizierte Testbaseline

Alle Werte stammen aus **frischen** Läufen am **2026-07-13**. Vor jeder Ausführung
wurde die Kostenfreiheit/Isolation des Skripts geprüft (§15).

| Befehl | Exit | Ergebnis |
|---|---|---|
| `python scripts/smoke-test.py` | **0** | 6 Pakete ok · Config gültig · 9 Modul-Importe ok · `/health` „alle Dienste ok" · Testsuite **484 Tests, 0 Failures, 0 Errors, 0 übersprungen** |
| `python docs/redesign/phase-4/tools/verify_phase4.py` | **0** ¹ | **27/27** Prüfungen erfolgreich (gegen Baseline-Harness auf 127.0.0.1:8341) |
| `python docs/motion/tools/verify_phase5.py` | **0** ¹ | **13/13** Prüfungen erfolgreich (Motion/Reduced-Motion, Video-Evidence) |

¹ **Ehrliche Einschränkung.** Beide `verify_phase*`-Skripte brauchen (a) den lokalen,
gestubbten Harness `docs/design-baseline/tools/baseline_server.py` **laufend auf Port
8341** und (b) eine UTF-8-Konsole. Der erste `verify_phase4`-Lauf brach mit Exit 1 ab —
**kein Funktionsfehler**, sondern ein `UnicodeEncodeError` im `print()` des Tools
selbst (Windows-Konsole cp1252 kann das Zeichen `→` nicht kodieren; 7 Prüfungen liefen
zuvor bereits „OK"). Der Wiederholungslauf mit gesetztem `PYTHONUTF8=1` (nur
Invocation-Umgebung, **keine Dateiänderung**) lief sauber auf 27/27 bzw. 13/13 durch.

**Vergleich mit der letzten externen Beobachtung.** Erwartet: Smoke Exit 0, 484 Tests,
0/0/0, 0 Skips, 22 Action-Typen, 24 Routen. **Frische Messung deckt sich vollständig:**
Smoke Exit 0 / 484 / 0 / 0 / 0; Action-Typen 22; Routen 24 (§4). Keine Abweichung →
`systematic-debugging` war für die Baseline selbst nicht erforderlich (nur einmalig für
die cp1252-Encoding-Ursache oben angewandt: reproduziert, volle Fehlermeldung gelesen,
Ursache = Konsolen-Encoding, Gegenmaßnahme = `PYTHONUTF8=1`, keine Codeänderung).

**Wichtige Bedingung zum „0 übersprungen" (siehe §9/§11).** Die Null-Skip-Zahl gilt
**nur, weil eine gültige persönliche `config.json` vorhanden ist**. Ohne sie würde der
`server`-Import scheitern und server-abhängige Tests würden per `@unittest.skipIf`
still übersprungen.

## 4. Bestehende Fähigkeiten

**Action-Registry — 22 Typen** (Quelle: `actions.py` `REGISTRY`, Zeilen 47–123;
`ALLOWED_ACTIONS = frozenset(REGISTRY)`):

`SEARCH`, `BROWSE`, `OPEN`, `APP_OPEN`, `PROFILE_ACTIVATE`, `PROFILE_STATUS`,
`APP_AUTOSTART_ON`, `APP_AUTOSTART_OFF`, `APP_PLACE`, `SCREEN`, `NEWS`, `INBOX_READ`,
`INBOX_WRITE`, `MEMORY_WRITE`, `MEMORY_READ`, `MEMORY_FORGET`, `RESEARCH`, `CLIPBOARD`,
`CLIPBOARD_NOTE`, `NOTES_RECENT`, `PROJECT_CONTEXT`, `SESSION_SUMMARY`.

Seit **RFC-0001** (Phase 4B, 2026-07-15) ist die Action ein *deep module*: Metadaten,
**Ausführung** (`execute(payload, ctx)`) und **Prompt-Selbstbeschreibung**
(`describe(prompt_ctx)`) liegen je Action am Registry-Eintrag. **22/22 ausführbar**,
**21/22 beworben** — `BROWSE` ist registriert und ausführbar, aber wie seit jeher nicht
im System-Prompt. Der System-Prompt wird über `actions.render_action_block` aus der
Registry erzeugt (byte-genaue Goldens in `tests/fixtures/prompt_golden/`);
`assistant_core.execute_action` ist nur noch ein Thin Dispatcher, der `if/elif`-Router
existiert nicht mehr. Timeout, Cancel, Confirmation, Summary, TTS, WS-Events,
OPEN-Frühabbruch und RESEARCH-Autosave bleiben Orchestrierung in `assistant_core`.
Details: [PHASE4B_ACTION_DEEP_MODULE_MIGRATION.md](../architecture/PHASE4B_ACTION_DEEP_MODULE_MIGRATION.md).

Jede Aktion ist ein `ActionSpec` mit Feldern Label, Payload-Regel
(`required`/`optional`/`none`), `risk`, `timeout`, `is_url`, `is_browser`,
`speaks_result`, `summary_task`, `summary_max_tokens`.

**FastAPI-/WebSocket-Routen — 24 gesamt** (Quelle: `server.app.routes`, live gezählt):
- 18 App-HTTP-Endpunkte: `GET /`, `GET /health`, `GET|POST /settings`,
  `GET /music/files`, `POST /music/selection`, `GET /dashboard/state`,
  `POST /commands/app/open`, `GET /launcher/apps`,
  `POST /launcher/apps/{app_id}/toggle`, `GET /launcher/monitors`,
  `POST /launcher/apps/{app_id}/placement`, `GET|POST /launcher/profiles`,
  `POST /launcher/profiles/{profile_id}/activate|duplicate|rename`,
  `DELETE /launcher/profiles/{profile_id}`.
- 1 WebSocket: `/ws`.
- 1 Static-Mount: `/static`.
- 4 Framework-Routen: `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`.

**App-, Profil- und Monitor-Fähigkeiten (vorhanden).** Allowlist-App-Launcher
(`app_launcher.py`, `config.apps`, kein `shell=True`); Sprach-Aktionen `APP_OPEN`,
`APP_PLACE`, `APP_AUTOSTART_ON/OFF`, `PROFILE_ACTIVATE`, `PROFILE_STATUS`;
Profile-CRUD-REST (`/launcher/profiles…`); Monitor-Erkennung via ctypes
(`monitors.py`, `GET /launcher/monitors`).

**Stop/Cancel/Bestätigung (vorhanden).** Stop bricht Wiedergabe **und** laufende Aktion
ab: `data.get("type") == "stop"` bzw. `actions.is_stop_command` in
`server.websocket_endpoint`; Nachrichten laufen als abbrechbarer Task.
Bestätigungspflicht über `risk="confirm"` (aktuell `MEMORY_FORGET`) mit mündlicher
Ja/Nein-Rückfrage (`assistant_core.pending_confirm`, `actions.is_confirmation`).

**Browser/Clipboard/Screen/Memory/Vault (vorhanden).** Playwright-Steuerung mit
Tab-Cap und HTML-Fallback (`browser_tools.py`, `_search_links_fallback` über
`html.duckduckgo.com`); Clipboard über PowerShell `Get-Clipboard`
(`clipboard_tools.py`); Screenshot + Claude Vision (`screen_capture.py`); Tages-Inbox
+ Vault-Helfer + Langzeit-Gedächtnis „Jarvis Memory.md" (`memory.py`:
`write_inbox_entry`, `append_memory`, `read_memory_sync`, `read_recent_notes_sync`,
`get_project_context_sync`, `get_vault_summary_sync`).

**Wire-Verträge (vorhanden, aktueller Stand).**
- **WS-Ausgang (untypisiert, `type`-Feld):** `health`, `response`, `action`, `error`,
  `stop`, `music_changed`, `app_event`, `launcher_changed`.
- **WS-Eingang:** Utterance-Frames mit `text`; `{type:"stop"}`; automatische
  Begrüßung „Jarvis activate" beim ersten Connect (Kostenrelevanz, siehe §7/§15).
- **`/health`-Shape:** `{ok, services:{config,llm,tts,browser,vault}, …}` (im Smoke
  fest asserted).
- **LLM-Textprotokoll:** `[ACTION:TYP] payload` als einzige Aktions-Schnittstelle.

## 5. Aktuelle Architektur

**Modul-Globals & Import-Seiteneffekte (Beobachtung, `server.py` 9–94).** Beim reinen
`import server` passiert bereits produktiv: `sys.stdout/stderr.reconfigure` (10–11),
`SESSION_TOKEN = secrets.token_urlsafe(24)` (44), `config = load_config(CONFIG_PATH)`
mit `sys.exit(1)` bei Fehler (47–52), `check_runtime_environment` (56), Erzeugung der
**globalen Provider-Clients** `ai = anthropic.AsyncAnthropic(...)` und `http =
httpx.AsyncClient(...)` (61–62), Verdrahtung `memory.configure`,
`assistant_core.configure`, `assistant_core.init_clients`, `app_launcher.configure`
(65–71), `app = FastAPI()` auf Modulebene (73), Registrierung von
`browser_tools.close`/`_startup_refresh` (79/91), globales `ws_clients: set` (94).

**Test-Seams (vorhanden).** `assistant_core.init_clients(ai, http)` +
`assistant_core.configure(config)` erlauben Client-Injektion; Env-Schalter
`JARVIS_SKIP_STARTUP_REFRESH` unterdrückt Netz-/Dateizugriff beim Start. Der
Baseline-Harness nutzt genau diese Seams (Fake-LLM/TTS, `refresh_data`-Stub,
`app_launcher._start_url/_start_process`-Stubs).

**Vorhandene Browser-/Visual-Test-Harnesses.** `docs/design-baseline/tools/baseline_server.py`
(echter Server, Dummy-Keys, alle teuren Pfade gestubbt, 127.0.0.1:8341),
`capture_baseline.py`, sowie die Playwright-Verifikatoren `verify_phase4.py` (27
Checks) und `verify_phase5.py` (13 Checks). Diese laufen **außerhalb** der 484er
Unit-Suite und benötigen einen manuell gestarteten Harness.

**Bausteine des Masterplans — Ist-Zustand (evidenzbasiert):**

| Baustein | Status | Beleg |
|---|---|---|
| FastAPI-App-Factory / Composition Root | **nicht vorhanden** | `app = FastAPI()` + Config-Load + Client-Erzeugung als Import-Seiteneffekt (`server.py` 47–73) |
| Versioniertes Config-Schema + Migrationen | **nicht vorhanden** | kein `version`-Feld in `config.example.json`; `config_loader` lädt/validiert ein dict |
| Typisierte/versionierte WS-Frames | **nicht vorhanden** | Frames sind untypisierte dicts; keine `protocol_version`/`event_id`/`correlation_id`/`session_id` (Grep: 0 Treffer) |
| Capability-/Policy-Runtime | **teilweise** | Registry + `risk="confirm"` + Allowlist-Launcher vorhanden; aber kein `validate→preview→authorize→execute→verify`-Lifecycle, keine Scopes/Datenklassen/Wirkungsklassen (Grep `capability/policy`: 0) |
| SQLite-Jobdatenbank | **nicht vorhanden** | Grep `sqlite3/aiosqlite`: 0 |
| Jobzustände & Checkpoints | **nicht vorhanden** | keine Job-Engine |
| Transactional Outbox | **nicht vorhanden** | Grep `outbox`: 0 |
| Saga/Kompensation | **nicht vorhanden** | Grep `saga/compensat`: 0 |
| Scheduler | **nicht vorhanden** | Grep `apscheduler/croniter/schedule`: 0 |
| Persistenter Memory-Index / SQLite FTS | **nicht vorhanden** | Memory ist Markdown-Datei + Vault-Walk; kein Index/FTS |
| Connector-Runtime | **nicht vorhanden** | keine Kalender-/Mail-/Task-Connectoren |
| Strukturiertes Audit mit Korrelations-IDs | **nicht vorhanden** | Logging vorhanden, aber ohne durchgehende `correlation_id` |
| Safe Mode / Backup-Restore / Installer / Rollback | **nicht vorhanden** | kein entsprechender Code/Skript gefunden |
| CI-Konfiguration | **nicht vorhanden** | kein `.github/`-Verzeichnis |

*Idempotency-Keys:* Grep `idempotency`: 0 → nicht vorhanden.
*Credential-Ablage (DPAPI/Keyring):* Grep `DPAPI/keyring/CredentialManager`: 0 →
Secrets liegen weiterhin in `config.json` (per Design gitignored; Settings-API
verweigert Lesen/Schreiben der Keys).

## 6. Bereits abgeschlossene UI-/UX-Arbeiten

**Beobachtung (aus Audit-Doku + frischer Verifikation).** Der visuelle Sieben-Phasen-Umbau
ist laut `docs/final-audit/RELEASE_READINESS.md` abgeschlossen: eigenständige „Warm
Analog Intelligence"-Identität, tokengetriebenes Dark-Theme (`frontend/design-tokens.css`),
lokale Fonts (`frontend/assets/fonts/*.woff2`, SIL OFL), Command Center (drei Spalten),
Panel-/Fokus-/Vollbild-Modi, Orb-Zustände idle/listening/thinking/speaking/muted/error,
Reduced-Motion-Pfad. Guidelines-Audit-Ergebnis: **0×P0, 0×P1, alle P2 behoben**.

**Frisch bestätigt (2026-07-13):** `verify_phase4` 27/27 (Fonts, Fenstermodi,
Fokus-Ring, Skip-Link, Mute/Action-Statuszeile, Zoom-200%-Näherung, kleine Höhe) und
`verify_phase5` 13/13 (Zustands-Animationen, Unterbrechbarkeit, Spam-Festigkeit,
Reduced Motion) — alle Exit 0.

**Schlussfolgerung.** Das Frontend ist als **eingefrorene Baseline** zu behandeln
(siehe §13). Offene Punkte sind ausschließlich P3 (§11), keiner release-blockierend.

## 7. Vorhandene Sicherheitsmechanismen

- **WS-Auth-Gate:** Origin-Check (`actions.is_origin_acceptable`) + lokales
  `SESSION_TOKEN`; Bind an 127.0.0.1 (Harness/Server).
- **App-Allowlist:** `app_launcher.py` startet nur `config.apps`-Einträge, kein
  `shell=True`, keine freien LLM-Kommandos; Sprache und UI-Klick teilen dieselbe Logik.
- **`OPEN` nur `http`/`https`** (`actions.normalize_url`); App-Schemes laufen über die
  Registry.
- **Settings-API schützt Secrets strukturell:** `PROTECTED_KEYS` (beide API-Keys)
  werden bei POST abgelehnt; `GET /settings` liefert nur `UI_EDITABLE_KEYS`
  (verifiziert im Phase-7-Audit, `body_contains_api_key: false`).
- **Bestätigungspflicht** für destruktive Aktion `MEMORY_FORGET` (mündliches Ja/Nein).
- **Startup-Kostenschutz für Tests/Harness:** `JARVIS_SKIP_STARTUP_REFRESH`; der
  Harness stubt LLM/TTS, weil das Frontend beim ersten Connect automatisch „Jarvis
  activate" sendet (sonst realer Anthropic-+ElevenLabs-Call).
- **Logging-Trennung:** Betriebslogs INFO, private Inhalte nur DEBUG (Default aus).

**Schlussfolgerung.** Solide Grundabsicherung auf Prozess-/Netz-/Allowlist-Ebene; es
fehlen die im Masterplan geforderten Schichten (Datenklassen/Wirkungsklassen,
Preview-gebundene Autorisierung, Presence-Modell, SSRF-Regeln, Panic-Lock,
Credential-Manager/DPAPI, Prompt-Injection-Abgrenzung für untrusted Web-/Screen-/
Clipboard-/Vault-Inhalte). Ein formelles Threat-Model existiert noch nicht.

## 8. Noch fehlende Masterplan-Bausteine

Verdichtet aus §5 (alle „nicht/teilweise vorhanden"):

1. **Composition Root / App-Factory** ohne Import-Seiteneffekte; Lifespan-gesteuerte
   Ressourcen.
2. **Versioniertes Config-Schema + Migration/Rollback**; **strukturierte Logs mit
   Redaction + `correlation_id`**.
3. **Typisierte, versionierte WS-/REST-Verträge** (protocol_version, event_id,
   session_id, Sensitivitätsklasse) mit Kompatibilitätsadapter für die heutigen Frames.
4. **Capability-/Policy-Kernel** (Schema, Preview, Autorisierung, Timeout, Cancel,
   Verify, Audit, Teilerfolg als eigener Zustand).
5. **Dauerhafte Job-/Workflow-Engine** (SQLite, Jobzustände, Checkpoints, Resume,
   **Transactional Outbox**, **Saga/Kompensation**, Budgets).
6. **Transparente Memory-/Knowledge-Engine** (SQLite-FTS-Index, inkrementeller
   Vault-Index, Tombstones, Provenienz, Export/Vergessen).
7. **Scheduler + Briefings + Workspace-Szenen** (Zeitzonen/DST, Missed-Run-Policy).
8. **Windows-/Voice-/Multimodal-Runtime** (Desktop-Adapter, STT/TTS-Abstraktion,
   Barge-in, Screen-Scope-Vorschau).
9. **Produktivitäts-Connectoren** (Kalender/Tasks/Mail, read-only zuerst).
10. **Observability/Recovery/Distribution** (Safe Mode, Backup/Restore, Installer,
    Rollback) und **Threat-Model** (Phase 2).
11. **Projektlokaler `jarvis-maintainer`-Skill** (Phase 12) und **Systemzertifizierung**
    (Phase 13).

## 9. Test- und Automationslücken

- **Config-Kopplung (belegt).** `tests/test_ws.py` (24–40) importiert `server` in
  `try/except BaseException` und dekoriert seine Klassen mit
  `@unittest.skipIf(server is None, …)`. 12 Testdateien importieren `server`. Fehlt/ist
  ungültig `config.json`, scheitert der Import (`sys.exit(1)`) und die betroffenen
  Tests **überspringen still**. → Die aktuelle „0 Skips"-Baseline ist **an die
  persönliche `config.json` gekoppelt** (Masterplan-Phase-0-Ziel „Tests entkoppeln"
  noch offen; Phase-3-Gate „frischer Runner braucht keine persönliche Config" noch
  nicht erfüllt). *In diesem Prompt nicht durch Entfernen von `config.json` getestet,
  weil das den Arbeitsbaum verändern würde; der Nachweis ist strukturell aus dem Code.*
- **Keine App-Factory für Tests.** Es gibt Seams (`init_clients`/`configure`), aber
  keine kontrollierte Test-App-Factory; Tests hängen am Modul-Import-Zeitpunkt.
- **Keine CI.** Kein `.github/` → keine PR-Pipeline (Syntax/Unit/Contract/Integration/
  Browser-Smoke) wie in Masterplan-Phase 3 vorgesehen.
- **Browser-E2E & Visual Regression laufen außerhalb der Suite.** `verify_phase4/5`
  brauchen den manuell gestarteten Harness auf 8341; sie sind **nicht** Teil der 484er
  `unittest`-Suite und nicht automatisiert/versioniert als Regressionsvergleich (nur
  Screenshot-Erzeugung, kein Pixel-Diff-Gate).
- **Konsolen-Encoding-Falle.** `verify_phase*`-Tools drucken Nicht-cp1252-Zeichen und
  benötigen eine UTF-8-Konsole (`PYTHONUTF8=1`), sonst `UnicodeEncodeError` (kein
  Funktionsfehler, aber reproduzierbar bei Standard-Windows-Konsole).
- **Testarten-Kennzeichnung fehlt.** Keine Markierung von unit/contract/integration/
  browser/windows-native/external-manual (Masterplan-Phase-0-Ziel).

## 10. Skill-Readiness

Quelle: `skills-lock.json` (14 Einträge) + Verzeichnisse `.agents/skills/` und
`.claude/skills/` (jeweils dieselben 14 Skills projektlokal vorhanden).

| Skill | Status | Beleg |
|---|---|---|
| `verification-before-completion` | **vollständig verfügbar** | SKILL.md geladen/genutzt |
| `systematic-debugging` | **vollständig verfügbar** | SKILL.md + Begleitdateien |
| `tdd` | **vollständig verfügbar** | SKILL.md + `mocking.md` + `tests.md` |
| `improve-codebase-architecture` | **vollständig verfügbar** | SKILL.md + `HTML-REPORT.md` |
| `security-threat-model` | **vollständig verfügbar** | SKILL.md + references + `agents/openai.yaml` |
| `webapp-testing` | **vollständig verfügbar** | SKILL.md + examples + scripts |
| `playwright-best-practices` | **installiert, aber unvollständig** | nur `SKILL.md` (1 Datei); die referenzierten Begleitdateien fehlen |
| `codebase-design` | **als Abhängigkeit fehlend** | nicht in `skills-lock.json`, kein Verzeichnis (Phase 1) |
| `domain-modeling` | **als Abhängigkeit fehlend** | nicht vorhanden (Phase 1) |
| `grilling` | **als Abhängigkeit fehlend** | nicht vorhanden (Phase 1) |
| `security-best-practices` | **nicht projektlokal vorhanden** | nicht vorhanden (Phase 2/5/10) |
| `skill-creator` | **erst in späterer Phase erforderlich** | nicht vorhanden (Phase 12) |

**Ebenfalls projektlokal (nicht im Masterplan gelistet, aber vorhanden):**
`emil-design-eng`, `extract-design-system`, `find-skills`, `frontend-design`,
`impeccable`, `ui-ux-pro-max`, `web-design-guidelines`.

**Schlussfolgerung.** Für die frühen Phasen fehlen `codebase-design`,
`domain-modeling`, `grilling` (Phase 1) und `security-best-practices` (Phase 2), und
`playwright-best-practices` ist ohne seine Referenzdateien nur ein Torso. Diese Lücken
decken sich mit dem Masterplan-Vorwort und müssen vor den jeweiligen Phasen geschlossen
werden — **nicht in diesem Prompt** (keine Installs erlaubt).

## 11. Dokumentationsabweichungen

*(nur festgehalten, in diesem Prompt nicht korrigiert)*

1. **`FEATURES.md` Punkt 50 — `server.py`-Größe falsch.** Behauptung: „server.py
   (958→~300 Zeilen) nur noch HTTP/WS". **Fakt:** `server.py` hat **741 Zeilen**. Die
   Rolle „HTTP/WS-Schicht" stimmt, die Zahl „~300" nicht.
2. **P3-Zählung inkonsistent.** `docs/final-audit/OPEN_ITEMS.md` listet **7** offene
   P3 (Zeilen 1–7); `FINAL_FINDINGS.md` sagt **„7×P3 bewusst offen"**;
   `RELEASE_READINESS.md` ist **in sich widersprüchlich**: §1 nennt „sieben P3", aber
   die Tabelle §5, §7 und §20 nennen **„5"**. Belastbar ist **7×P3** (OPEN_ITEMS +
   FINAL_FINDINGS).
3. **Testzahlen — konsistent.** Audit-Doku (478→484) und frischer Smoke (484) stimmen
   überein. **Aber:** der Planungstext („Masterplan 2", `pasted-text.txt`) nennt „471
   Tests" — veralteter Stand gegenüber dem realen 484.
4. **Modulstruktur — überwiegend korrekt.** `CLAUDE.md` bildet die tatsächlichen Module
   (inkl. `monitors.py`, `health.py`, `app_launcher.py`, `screen_capture.py`,
   `clipboard_tools.py`) korrekt ab. `README.md` „Project Structure" führt `monitors.py`
   nicht auf (kleinere Auslassung), ist sonst stimmig.
5. **Skill-Installationsstand.** `skills-lock.json`/Doku implizieren einen kompletten
   Skill-Satz; real fehlen 4–5 Masterplan-Skills und `playwright-best-practices` ist
   unvollständig (§10).
6. **Browser-E2E / Visual Regression / CI.** Die Audit-Doku beschreibt „30 E2E-Abläufe"
   und Screenshot-Evidence; es gibt jedoch **keine CI** und **kein automatisiertes
   Visual-Regression-Gate** — diese Prüfungen sind manuell/harness-gebunden (§9).
7. **Config-Unabhängigkeit / unerwartete Skips.** Doku hebt „0 skipped" hervor; real
   ist diese Null an eine gültige persönliche `config.json` gebunden (§9).

## 12. Risiken für die weitere Umsetzung

- **R1 – Zeilenenden-Falle (hoch für den Checkpoint).** `core.autocrlf=true` ohne
  `.gitattributes`: ein Commit/Checkout kann Zeilenenden von ~25 Dateien umschreiben
  und riesige Pseudo-Diffs erzeugen, die echte Änderungen verdecken. Vor dem Commit
  bewusst entscheiden (z.B. `.gitattributes` mit fixierten EOL) — **nicht** pauschal
  normalisieren.
- **R2 – Sehr großer uncommitteter Arbeitsbaum.** 30 geänderte versionierte + 685
  unversionierte Dateien (viel davon Skills unter `.agents/`/`.claude/`/`.impeccable/`,
  komplette `docs/`). Ohne Checkpoint droht Verlust bei jedem versehentlichen
  destruktiven Git-Kommando.
- **R3 – Import-Seiteneffekte als Umbau-Sperre.** Config-Load und Client-Erzeugung beim
  Import erschweren App-Factory, Tests ohne Config und Lifespan-Verwaltung (Phase 4).
- **R4 – Config-gekoppelte Tests maskieren Skips.** Grüne Suite ohne die Kopplung zu
  entschärfen kann falsche Sicherheit geben (§9).
- **R5 – Untypisierte WS-/Textprotokolle.** `[ACTION:...]` und untypisierte Frames sind
  die Kompatibilitätsfläche; jede Migration muss sie über Adapter erhalten (§13).
- **R6 – Skill-Lücken.** Start von Phase 1/2 ohne `codebase-design`/`domain-modeling`/
  `grilling`/`security-best-practices` bzw. mit unvollständigem `playwright-best-practices`.
- **R7 – Kostenrisiko bei echten Läufen.** Das Frontend löst beim ersten WS-Connect
  automatisch „Jarvis activate" aus → realer Anthropic-/ElevenLabs-Call. Manuelle
  UI-Prüfungen nur gegen den gestubbten Harness (8341), nie gegen den echten Server.

## 13. Eingefrorene Kompatibilitätsbaseline

**Der visuelle Sieben-Phasen-Umbau wird als Baseline eingefroren.** Das Frontend
(Identität, Tokens, Command Center, Fenstermodi, Orb-Zustände, Reduced Motion) gilt ab
hier als Referenz; `verify_phase4` (27/27) und `verify_phase5` (13/13) sind sein
Regressionsnetz. Kein gleichzeitiger Visual- **und** Systemumbau.

**Bis zu einer kontrollierten Migration bleiben kompatibel (dürfen nicht brechen):**
- alle 22 `[ACTION:...]`-Typen (§4) inkl. Payload-/Risk-/Timeout-Semantik,
- die WS-Frame-Typen (Ausgang: `health`, `response`, `action`, `error`, `stop`,
  `music_changed`, `app_event`, `launcher_changed`; Eingang: `text`-Utterance,
  `{type:"stop"}`, Auto-„Jarvis activate"),
- alle 24 Routen / REST-Verträge (§4), inkl. `/settings`-Whitelist-Verhalten und
  `/health`-Shape `{ok, services:{config,llm,tts,browser,vault}}`,
- das `config.json`-Format (apps-Registry-Objekte + Legacy-Strings, `launcher`-Profile,
  `user_*`, `music_*`, Obsidian-Pfade) — Werte bleiben geheim,
- alle in `FEATURES.md` (Punkte 1–53) dokumentierten Funktionen.

Neue, typisierte/versionierte Verträge dürfen nur **zusätzlich** und über
Kompatibilitätsadapter eingeführt werden; das Legacy-Protokoll wird erst nach
vollständiger Contract- und Browser-Abdeckung entfernt.

**Der aktuelle Arbeitsbaum benötigt vor jedem Architekturumbau einen bestätigten
Checkpoint.** Ohne einen solchen Commit/Tag (unter Beachtung von R1) ist der große
uncommittete Stand nicht sicher gegen versehentlichen Verlust.

## 14. Empfohlener nächster Schritt

**Empfehlung (auszuführen erst nach ausdrücklicher Nutzerbestätigung):** Einen
kontrollierten Git-Checkpoint des gesamten aktuellen Stands anlegen — **bewusst**
gegen die Zeilenenden-Falle (R1) abgesichert — damit die Baseline unveränderlich
festgehalten ist, bevor Masterplan-Phase 1 (Domainmodell/Architekturreview) beginnt.

Vorgeschlagene Checkpoint-Strategie (Details in der Abschlussausgabe): erst
`.gitattributes`-Entscheidung, dann Checkpoint-Commit/Tag auf `master` **oder** einem
`baseline/*`-Branch. **In diesem Prompt nicht ausgeführt.**

## 15. Evidenz und ausgeführte Befehle

Alle Läufe am **2026-07-13**, lokal, gegen den Arbeitsbaum unter
`C:\Users\Janwi\jarvis-voice-assistant`. Keine echten Provider-Calls; alle
Browser-Interaktionen ausschließlich gegen `http://127.0.0.1:8341` (gestubbter
Harness). Persönliche Pfade, Config-Werte, Tokens und vollständige Logs werden hier
bewusst **nicht** wiedergegeben.

**Git (nur lesend):**
- `git branch --show-current` → `master`
- `git rev-parse HEAD` → `dd43a624ab20b3228963f3d3350d037092affab8`
- `git status --short` → 30× `M` (versioniert) + 20 Top-Level-`??`-Einträge
- `git diff --name-only | wc -l` → `30`
- `git ls-files --others --exclude-standard | wc -l` → `685`
- `git diff --stat` → 30 Dateien, +6772 / −615
- `git config core.autocrlf` → `true`; `.gitattributes` → nicht vorhanden

**Prüfungen (Sicherheit vorab je Skript verifiziert):**

| # | Befehl | Exit | Kernzahlen |
|---|---|---|---|
| 1 | `python scripts/smoke-test.py` | 0 | 484 Tests · 0 Failures · 0 Errors · 0 übersprungen |
| 2 | `python docs/design-baseline/tools/baseline_server.py --port 8341` (Hintergrund; danach gestoppt) | — | Harness bereit, `/health` = 200 |
| 3 | `python docs/redesign/phase-4/tools/verify_phase4.py` (1. Lauf) | 1 | Abbruch durch cp1252-`UnicodeEncodeError` im Tool-`print()` (kein Funktionsfehler; 7 Checks zuvor OK) |
| 4 | `PYTHONUTF8=1 python docs/redesign/phase-4/tools/verify_phase4.py` | 0 | 27/27 |
| 5 | `PYTHONUTF8=1 python docs/motion/tools/verify_phase5.py` | 0 | 13/13 |

**Kontroll-/Struktur-Belege:**
- Action-Typen: `actions.py` `REGISTRY` (22 `ActionSpec`, Zeilen 47–123).
- Routen: `len(server.app.routes)` = 24 (18 App-HTTP + 1 WS + 1 Mount + 4 Framework).
- Import-Seiteneffekte/Globals: `server.py` Zeilen 9–94.
- Config-gekoppelte Test-Skips: `tests/test_ws.py` Zeilen 24–40.
- Abwesenheit von SQLite/Scheduler/Outbox/Saga/typisierten Frames/Capability-Runtime/
  Credential-Store: Grep über die Kernmodule = 0 Treffer; `.github/` nicht vorhanden.

**Beobachtete Nebenwirkung durch die geforderten Verifikationsläufe (§1).** Frisch
erzeugte/aktualisierte Artefakte unter `docs/redesign/phase-4/screenshots/` und
`docs/motion/evidence/`. Beide Verzeichnisse sind bereits unversioniert (`?? docs/…`);
`git status` zeigt sie nur als Teil des `docs/`-Baums. **Keine versionierte Datei**
wurde durch diesen Prompt verändert (außer der Neuanlage dieser Datei).

---

*Ende der Baseline. Nächste Aktion (Checkpoint) erst nach ausdrücklicher Bestätigung
des Nutzers.*

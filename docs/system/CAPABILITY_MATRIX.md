# Jarvis – Capability Matrix (Phase 0)

> Bestandsaufnahme **aller aktuell vorhandenen** Fähigkeiten. Stand **2026-07-13**.
> Beschreibt den Ist-Zustand — der formale Capability-Vertrag (Schema, Preview,
> Autorisierung, Verify, Audit) entsteht erst in Phase 4/5. Datenklassen/Wirkungsklassen
> sind hier eine **vorläufige** Einordnung nach der Masterplan-Taxonomie (formal in Phase 2).

## Legende

- **Status:** ✅ produktiv vorhanden · 🟡 nur teilweise abgesichert · 🖥 primär UI-seitig ·
  🔧 nur manuell prüfbar (external-manual).
- **Datenklasse:** öffentlich · lokal · persönlich · sensibel · geheim.
- **Wirkung:** read-local · read-sensitive · network-read · local-write · local-execute ·
  external-write · destructive.
- **Autorisierung heute:** Voice/UI-Utterance (implizit) · Allowlist · URL-Policy ·
  Token (X-Jarvis-Token) · **Confirm** (mündliche Ja/Nein-Rückfrage).

> **Ergänzung 2026-07-19 (RFC-0007 akzeptiert).** Diese Matrix bleibt die Bestandsaufnahme
> der Actions. Das **vollständige Wirkungsinventar** — einschließlich der 10 zustandsändernden
> REST-Routen ohne Action-Pfad, der nativen Pfade und der Wirkungen, die an `spec.execute()`
> vorbeilaufen — steht in
> [RFC-0007 §2.6](../architecture/RFC-0007-capability-policy-kernel.md). Dort ist auch belegt,
> dass die unten vorläufig eingeordneten Daten- und Wirkungsklassen in der **Laufzeit nicht
> existieren**: `ActionSpec.risk` kennt nur `low` und `confirm`.

> **Ergänzung 2026-07-19 (Phase 5B, Pilotphase implementiert).** Der Capability-/Policy-Kernel
> existiert jetzt als tiefes Modul [`capability/`](../../capability/); die Daten-,
> Wirkungsklassen, Scopes und Provenance sind damit **in der Laufzeit darstellbar** — aber
> **nur für die vier migrierten Piloten**: `SEARCH`→`web.search`, `MEMORY_FORGET`→
> `memory.forget`, die REST-Route `launcher.profile.rename` und das nutzerauslöserlose
> `context.refresh`. Für diese vier gilt der Vertrag als Wahrheit; ihre Wirkungsklassen sind
> per Wirkungs-Zensus festgenagelt. **Die übrigen 20 Actions und neun REST-Routen tragen
> weiterhin nur `ActionSpec.risk`** und werden erst in Prompt 20 migriert. `SCREEN` und
> `CLIPBOARD` bleiben bis dahin von `SEARCH` nicht unterscheidbar. Details:
> [PHASE5B_CAPABILITY_POLICY_KERNEL_MIGRATION.md](../architecture/PHASE5B_CAPABILITY_POLICY_KERNEL_MIGRATION.md).

## 1. Action-Capabilities (`[ACTION:...]`, 22 Typen)

> Seit RFC-0001 (Phase 4B, 2026-07-15) beschreibt und fuehrt sich jede Action selbst
> aus: Metadaten + `execute` + `describe` liegen am Registry-Eintrag in `actions.py`.
> `assistant_core.execute_action` ist nur noch ein Thin Dispatcher; Timeout, Cancel,
> Confirmation, Summary, TTS und WS-Events bleiben Orchestrierung.
> **Capability-/Policy-Lifecycle (validate/preview/authorize/verify) ist weiterhin
> NICHT implementiert** (Phase 5).

Quelle: `actions.py::REGISTRY`. Nutzer-Entry: gesprochene/getippte Utterance → LLM
emittiert `[ACTION:TYP]`. Stop/Cancel gilt global: laufende Nachrichten laufen als Task,
„Stopp"/Esc/Button cancelt sie (`server.websocket_endpoint`, `actions.is_stop_command`).

| # | Capability | Code-Entry | Datenquelle | Klasse | Wirkung | Autorisierung | Stop | Verifikation | Tests | Bekannte Lücke | Phase |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SEARCH | Websuche | `browser_tools.search_and_read` | Web | öffentlich | network-read | Voice/UI | ✅ | gesprochene Summary | `test_actions`, `test_browser_tools` | keine Preview/Schema | 5 |
| BROWSE | Seite lesen | `browser_tools.visit` | Web | öffentlich | network-read | URL-Policy | ✅ | Summary | `test_actions` | untrusted-Inhalt ungefiltert | 2/5 |
| OPEN | URL öffnen | `browser_tools.open_url`, `actions.normalize_url` | Web | öffentlich | network-read/local-execute | URL-Policy (nur http/https) | ✅ | Bestätigung im UI | `test_actions` (normalize_url) | keine SSRF-Regeln | 2 |
| APP_OPEN | App starten | `app_launcher.launch` | config.apps | lokal | local-execute | **Allowlist** | – | gesprochener Satz | `test_app_launcher`, `test_voice_launcher` | kein Preview/Verify | 5 |
| PROFILE_ACTIVATE | Profil aktivieren | `actions` (`spec.execute`), `app_launcher` | config.launcher | lokal | local-execute/local-write | Voice/UI | – | Statussatz | `test_voice_launcher`, `test_launcher_api` | – | 8 |
| PROFILE_STATUS | Profil-Status | `app_launcher.effective_apps` | config.launcher | lokal | read-local | Voice/UI | – | Statussatz | `test_voice_launcher` | – | 8 |
| APP_AUTOSTART_ON | Clap-Start an | `app_launcher`, `configuration.mutate` | config.launcher | lokal | local-write | Voice/UI | – | Statussatz | `test_voice_launcher`, `test_launcher_api` | – | 8 |
| APP_AUTOSTART_OFF | Clap-Start aus | dito | config.launcher | lokal | local-write | Voice/UI | – | Statussatz | dito | – | 8 |
| APP_PLACE | App platzieren | `app_launcher`, `configuration.mutate` | config.launcher | lokal | local-write | Voice/UI | – | Statussatz | `test_voice_launcher` | – | 8/9 |
| SCREEN | Bildschirm ansehen | `screen_capture.describe_screen` | Bildschirm | **sensibel** | read-sensitive + network-read (Vision) | Voice/UI | ✅ | Beschreibung | begrenzt (gestubbt) | kein Region-Scope / keine Übertragungsvorschau | 2/9 |
| NEWS | Weltnachrichten | `browser_tools.fetch_news` | Web | öffentlich | network-read | Voice/UI | ✅ | Summary | `test_actions` | – | 5 |
| INBOX_READ | Tages-Inbox lesen | `memory.read_today_inbox_sync` | Vault | **persönlich** | read-sensitive | Voice/UI | – | Rückblick-Summary | `test_inbox` | – | 7 |
| INBOX_WRITE | Inbox-Eintrag | `memory.write_inbox_entry` | Vault | persönlich | local-write | Voice/UI | – | Bestätigungssatz | `test_inbox` | – | 7 |
| MEMORY_WRITE | Merken | `memory.append_memory` | Vault/Workspace | persönlich | local-write | Voice (ausdrücklich) | – | Bestätigungssatz | `test_memory` | – | 7 |
| MEMORY_READ | Gedächtnis lesen | `memory.read_memory_sync` | Vault/Workspace | persönlich | read-sensitive | Voice/UI | – | Summary | `test_memory` | – | 7 |
| MEMORY_FORGET | Vergessen | `memory` + `ctx.request_confirmation` (Session-`suspended`) | Vault/Workspace | persönlich | **destructive** | **Confirm** | – | Bestätigt gelöschte Einträge | `test_memory`, `test_confirm_flow` | einzige Confirm-Aktion | 5 |
| RESEARCH | Recherche | `assistant_core.run_research`, `browser_tools.search_links` | Web → Vault | öffentlich→persönlich | network-read + local-write | Voice/UI | ✅ (180 s) | Summary + Quellen im Transcript, Autosave | `test_integration_research` | keine Quellenbewertung/Preview | 6 |
| CLIPBOARD | Zwischenablage verarbeiten | `clipboard_tools`, `assistant_core` | Clipboard | **sensibel** | read-sensitive (+ network-read LLM) | Voice/UI | ✅ | Antwortsatz | `test_actions` | keine Übertragungsvorschau | 2/9 |
| CLIPBOARD_NOTE | Clipboard als Notiz | `clipboard_tools`, `memory` | Clipboard→Vault | sensibel→persönlich | local-write | Voice/UI | – | Bestätigungssatz | `test_actions` | dito | 2/7 |
| NOTES_RECENT | Letzte Notizen | `memory.read_recent_notes_sync` | Vault | persönlich | read-sensitive | Voice/UI | – | Summary | `test_memory` | – | 7 |
| PROJECT_CONTEXT | Vault-Kontext-Broker | `memory.get_project_context_sync` | Vault | persönlich | read-sensitive | Voice/UI | – | projektbezogene Antwort | `test_memory` | Ranking heuristisch; Secret-Filter vorhanden | 7 |
| SESSION_SUMMARY | Sitzungsfazit | `actions` (`spec.execute`) | Conversation-History | lokal | read-local | Voice/UI | – | Summary | `test_confirm_flow`/`test_prompt` (indirekt) | – | 6/7 |

## 2. Konversation, Sprache, Stop

| Capability | Nutzer-Entry | Code-Entry | Klasse | Wirkung | Autorisierung | Stop | Tests | Lücke | Phase |
|---|---|---|---|---|---|---|---|---|---|
| Sprach-Konversation | Mikrofon → WS | `frontend/main.js`, `assistant_core.process_message` | persönlich | network-read (LLM) | Origin+Token | ✅ | `test_ws`, `test_integration_research` | untypisierte Frames | 4 |
| TTS-Wiedergabe | Antwort | `tts.synthesize_speech` | öffentlich | network-read (ElevenLabs) | – | ✅ | `test_tts` | Provider fest | 9 |
| Morgen-Überblick („activate") | „Jarvis activate" | `assistant_core.build_system_prompt`, `refresh_data` | persönlich | network-read (Wetter) + read-sensitive | Voice | ✅ | `test_prompt` | Auto-Call bei Connect (Kostenrisiko) | 8 |
| Stop/Cancel | „Stopp"/Esc/Button | `server.websocket_endpoint`, `actions.is_stop_command` | lokal | – | Voice/UI | ✅ | `test_ws`, 🔧 UX-Checkliste | ms-Budget noch offen | 0/13 |

## 3. Launcher, Profile, Monitore, native UI

| Capability | Nutzer-Entry | Code-Entry | Klasse | Wirkung | Autorisierung | Tests | Status | Phase |
|---|---|---|---|---|---|---|---|---|
| App-Registry/Launch | Klick/Voice | `app_launcher.launch` (Allowlist) | lokal | local-execute | Allowlist | `test_app_launcher` | ✅ | 5/9 |
| Profil-CRUD | Command Center | `/launcher/profiles…` | lokal | local-write | Token | `test_launcher_api` | ✅ | 8 |
| Monitor-Erkennung | Monitor-Map | `monitors.detect_monitors`, `/launcher/monitors` | lokal | read-local | Token | `test_monitors` | ✅ | 9 |
| Fenster-Snapping | Session-Start | `scripts/launch-session.ps1` | lokal | local-execute | – | `test_launcher_ps1` (statisch) | 🟡 (echte Platzierung 🔧) | 9 |
| Doppelklatschen-Trigger | Klatschen | `scripts/clap-trigger.py` | lokal | local-execute | – | `test_clap_trigger` (Pfad-Fallback) | 🟡 (Audio 🔧) | 9 |
| UI-Modi Panel/Fokus/Vollbild | Fenster | `jarvis-launcher.pyw` | lokal | local-execute | – | 🔧 (native Größen) | 🖥/🔧 | 9 |

## 4. HTTP-APIs (Token-geschützt außer `/`, `/health`, `/static`)

| Capability | Route | Code-Entry | Klasse | Wirkung | Autorisierung | Tests | Lücke | Phase |
|---|---|---|---|---|---|---|---|---|
| Health-Report | `GET /health` | `health.build_report` | lokal | read-local | – (passiv) | `test_ws`/Smoke | – | 11 |
| Settings lesen/schreiben | `GET/POST /settings` | `configuration.mutate` | persönlich (Secrets ausgeschlossen) | local-write | Token + Whitelist | `test_settings_api` | – | 4 |
| Dashboard-State | `GET /dashboard/state` | `server.dashboard_state` | persönlich | read-local | Token | `test_dashboard_api` | – | 8 |
| App per UI öffnen | `POST /commands/app/open` | `app_launcher` | lokal | local-execute | Token + Allowlist | `test_dashboard_api` | – | 5 |
| Musik-Auswahl | `GET/POST /music/*` | `server` + `config_loader` | lokal | local-write | Token | `test_music_api` | – | 8 |
| Launcher-Apps/Placement | `GET/POST /launcher/apps…` | `app_launcher` | lokal | local-write | Token | `test_launcher_api` | – | 8/9 |

## 5. Gedächtnis & Vault (Datenhoheit)

| Capability | Code-Entry | Klasse | Wirkung | Autorisierung | Tests | Status | Phase |
|---|---|---|---|---|---|---|---|
| Tages-Inbox (Brain Dump) | `memory.write_inbox_entry`/`read_today_inbox_sync` | persönlich | local-write/read | Voice/UI | `test_inbox` | ✅ | 7 |
| Langzeit-Gedächtnis „Jarvis Memory.md" | `memory.append_memory`/`read_memory_sync` | persönlich | local-write/read | Voice (ausdrücklich) / Confirm bei Forget | `test_memory` | ✅ | 7 |
| Vault-Übersicht/Recent/Kontext | `memory.get_vault_summary_sync`, `read_recent_notes_sync`, `get_project_context_sync` | persönlich | read-sensitive | Voice/UI | `test_memory` | ✅ (Secret-Filter) | 7 |
| API-Keys | `config.json` (gitignored) | **geheim** | – | PROTECTED_KEYS (nie über API) | `test_settings_api`, `test_config` | ✅ (kein DPAPI) | 2/10 |

## 6. Querschnittslücken (für Folgephasen)

- Kein formaler Capability-Vertrag (Schema/Preview/authorize/verify/Audit) — **Phase 5**.
- Keine Datenklassen-/Wirkungsklassen-Runtime, kein Presence-Modell — **Phase 2**.
- Keine Übertragungsvorschau für Screen/Clipboard, keine SSRF-Regeln — **Phase 2/9**.
- Nur eine Confirm-Aktion (`MEMORY_FORGET`); riskante Wirkungen sonst implizit — **Phase 5**.
- Untertrusted Web-/Screen-/Clipboard-/Vault-Inhalte fließen ungefiltert ins LLM — **Phase 2/7**.
- Kein Audit mit Korrelations-IDs, keine Job-Persistenz/Outbox — **Phase 4/6/11**.

## Phase 5C — Wirkungsinventar aller 22 Actions (Prompt 20)

Diese Tabelle ist **aus der laufenden Registry erzeugt**, nicht handgepflegt. Der
Phase-5C-Audit (`tests/test_phase5c_audit.py`) hält sie ehrlich.

| Action | Capability | Effects | Reads | Writes | Scopes | Timeout | Tier |
|---|---|---|---|---|---|---|---|
| `APP_AUTOSTART_OFF` | `launcher.app.autostart.set` | local-write/network-read | local | local | apps/config.launcher | 15s | governed |
| `APP_AUTOSTART_ON` | `launcher.app.autostart.set` | local-write/network-read | local | local | apps/config.launcher | 15s | governed |
| `APP_OPEN` | `launcher.app.open` | local-execute/network-read | local | — | apps | 15s | governed |
| `APP_PLACE` | `launcher.app.placement.set` | local-write/network-read | local | local | apps/config.launcher | 15s | governed |
| `BROWSE` | `web.browse` | local-execute/network-read | public | — | web | 60s | governed |
| `CLIPBOARD` | `clipboard.process` | network-read/read-sensitive | sensitive | — | clipboard | 60s | governed |
| `CLIPBOARD_NOTE` | `clipboard.note.create` | local-write/network-read/read-sensitive | personal | personal | clipboard/vault | 60s | governed |
| `INBOX_READ` | `vault.inbox.read` | network-read/read-sensitive | personal | — | vault | 60s | governed |
| `INBOX_WRITE` | `vault.inbox.write` | local-write/network-read/read-sensitive | personal | personal | vault | 60s | governed |
| `MEMORY_FORGET` | `memory.forget` | destructive/network-read | personal | personal | vault | 60s | governed |
| `MEMORY_READ` | `memory.read` | network-read/read-sensitive | personal | — | vault | 60s | governed |
| `MEMORY_WRITE` | `memory.write` | local-write/network-read | personal | personal | vault | 60s | governed |
| `NEWS` | `web.news` | local-execute/network-read | public | — | web | 60s | governed |
| `NOTES_RECENT` | `vault.notes.recent` | network-read/read-sensitive | personal | — | vault | 60s | governed |
| `OPEN` | `web.open` | local-execute/network-read | public | — | web | 60s | governed |
| `PROFILE_ACTIVATE` | `launcher.profile.activate` | local-write/network-read | local | local | config.launcher | 15s | governed |
| `PROFILE_STATUS` | `launcher.profile.status` | network-read/read-local | local | — | apps/config.launcher | 15s | trivial |
| `PROJECT_CONTEXT` | `vault.project.context` | network-read/read-sensitive | personal | — | vault | 60s | governed |
| `RESEARCH` | `web.research` | local-execute/local-write/network-read | public | personal | vault/web | 180s | governed |
| `SCREEN` | `screen.describe` | network-read/read-sensitive | sensitive | — | screen | 60s | governed |
| `SEARCH` | `web.search` | local-execute/network-read | public | — | web | 60s | governed |
| `SESSION_SUMMARY` | `conversation.summary` | network-read/read-local | personal | — | conversation | 60s | governed |

**Lesehinweise.**
* `network-read` erscheint bei fast jedem Pfad: 15 Actions schicken ihr Ergebnis durch den
  Summary-LLM, sechs Launcher-Actions sprechen es direkt über TTS, `OPEN` ist selbst ein
  Browserpfad. Das ist keine Vorsicht, sondern der belegte Folgeeffekt.
* `APP_AUTOSTART_ON` und `APP_AUTOSTART_OFF` teilen einen Vertrag — 22 Actions auf 21 Namen.
* `vault.inbox.write` und `clipboard.note.create` tragen `read-sensitive`, weil
  `memory.write_inbox_entry` beim Dedup vorhandene persönliche Inbox-Inhalte liest **und**
  an das LLM sendet.
* `memory.forget` ist der einzige `destructive`-Vertrag — daraus wird `CONFIRM_ACTIONS`
  abgeleitet; ein gespeichertes `risk` existiert nicht mehr.


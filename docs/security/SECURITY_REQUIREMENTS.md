# Jarvis – Security Requirements (Phase 2)

> Verbindliche Sicherheitsanforderungen, abgeleitet aus [../../jarvis-voice-assistant-threat-model.md](../../jarvis-voice-assistant-threat-model.md).
> **Anforderungen** — noch keine Runtime. „Geplant" heißt: nicht implementiert.
> Stand 2026-07-14. Enthält den `security-best-practices`-Review (Teil E), je Empfehlung
> an Threat/Asset/Boundary gebunden.

## 1. Globale Security-Invarianten

- **SI-1 (Untrusted-Autorisierung):** Untrusted Inhalt (Web, Vault, Clipboard, Screen,
  Recherchequelle, LLM-Ausgabe) darf Daten liefern oder Vorschläge beeinflussen, aber
  **niemals** eine Aktion autorisieren, eine Wirkungsklasse erhöhen oder Policy ändern.
  (TM-001, TM-008)
- **SI-2 (Voice ≠ Identität):** Eine erkannte Stimme ist **kein** Identitätsnachweis;
  Voice allein autorisiert keine hochriskante/destruktive/`external-write`-Wirkung. (TM-004)
- **SI-3 (Lokal & entsperrt):** Wirkende Aktionen nur bei lokal **entsperrtem** Desktop;
  gesperrter Desktop und Remote-Sitzung dürfen höchstens passiv lesen. (A2/A3)
- **SI-4 (Nur lokal gebunden):** Server bleibt an `127.0.0.1` gebunden, keine öffentliche
  Exposition (`server.py:746`). (SI, SYSTEM_CHARTER)
- **SI-5 (Secrets nie in die Cloud):** `secret`-Daten (API-Keys, Session-Token) werden nie
  als Inhalt übertragen, nie geloggt, nie über die Settings-API gelesen/geschrieben
  (`config_loader.py:35` `PROTECTED_KEYS`). (TM-007)
- **SI-6 (Allowlist-Wirkung):** Prozessstart nur aus der App-Allowlist, ohne Shell
  (`app_launcher.py:471`); `OPEN` nur `http`/`https` (`actions.py:171`). (TM-001, TM-003)
- **SI-7 (Bestätigung für Destruktives):** Destruktive Wirkung nur nach ausdrücklicher
  Bestätigung (`actions.py:136` `CONFIRM_ACTIONS`). (TM-004)
- **SI-8 (Preview vor sensitiver Cloud-Übertragung):** Screen/Clipboard und künftige
  `external-write` benötigen eine sichtbare Übertragungsvorschau + Datenklasse (geplant).
  (TM-005, TM-006)
- **SI-9 (Minimale Logs):** **Rohe private Inhalte erscheinen auf KEINEM Log-Level**
  (verschärft mit RFC-0004, 2026-07-17 — zuvor „nur DEBUG"). Betriebslogs sind
  strukturierte, benannte Ereignisse mit einer geschlossenen Feld-Allowlist
  (`obslog.event`); es gibt kein Freitextfeld und keine Möglichkeit, roh zu loggen.
  Unbekannte/falsch getippte Felder werden verworfen (nur `dropped_fields=<Anzahl>`),
  URLs auf Schema+Host reduziert, Exceptions auf Typ/Ort. Legacy-/Drittanbieter-Logs
  (uvicorn/httpx/anthropic/playwright) laufen durch ein zentrales Schutznetz
  (`obslog.install_protection`) — ein Netz, keine Garantie; die Garantie liefern die
  Allowlist-Ereignisse. (TM-005/006)

## 2. Datenklassen

| Klasse | Beispiele (Jarvis) | Lokale Speicherung | Cloud-Übertragung | Vorschau | Logging | Aufbewahrung | Export/Löschen | Nutzerpräsenz |
|---|---|---|---|---|---|---|---|---|
| `public` | Nachrichten, öffentliche Webseiten, Wetter | erlaubt | erlaubt (network-read) | nein | Metadaten ok | keine besondere | n/a | beliebig lokal |
| `local` | App-Registry, Profile, Monitor-Map, Health, `city` | erlaubt | nur wenn nötig | nein | ok | dauerhaft (config) | via Settings/UI | entsperrt |
| `personal` | user_name/role, History, Inbox, Vault-Summary, Memory | erlaubt | nur als LLM-Kontext mit Zweck | künftig | nur Metadaten (nie roh, kein Level) | Datei/Session | nutzer-editierbare Dateien | entsperrt |
| `sensitive` | Screen-Capture, Clipboard, volle Vault-Notizen, Recherche-Rohtext | transient bevorzugt | **nur mit Vorschau + Secret-Filter** (geplant) | **ja (geplant)** | nie voller Inhalt | transient | n/a | **nur entsperrt** |
| `secret` | Anthropic/ElevenLabs-Keys, Session-Token | `config.json` Klartext (heute) → **DPAPI (Ziel)** | **nie als Inhalt** | n/a | **nie (redacted)** | bis Rotation | Nutzer verwaltet Config | n/a |

## 3. Wirkungsklassen

| Klasse | Aktuelle Beispiele | Autorisierung | Preview | Nutzerpräsenz | Audit | Verify | Cancel/Kompensation | Hintergrund |
|---|---|---|---|---|---|---|---|---|
| `read-local` | INBOX_READ, PROFILE_STATUS, SESSION_SUMMARY, dashboard | voice/UI | nein | entsperrt (locked: nur passiv) | log | Ergebnis | Stop | erlaubt (read-only) |
| `read-sensitive` | SCREEN, CLIPBOARD, MEMORY_READ, PROJECT_CONTEXT, NOTES_RECENT | voice/UI + Preview (Screen/Clip, geplant) | Screen/Clip ja (geplant) | **nur entsperrt** | log (kein Inhalt) | Ergebnis | Stop | **verboten** unbeaufsichtigt |
| `network-read` | SEARCH, BROWSE, NEWS, RESEARCH, Wetter | voice/UI + Host-Policy | nein (SSRF-Policy) | entsperrt | log Zielhost | Inhalt | Stop (Timeout) | erlaubt mit Budget |
| `local-write` | INBOX_WRITE, MEMORY_WRITE, CLIPBOARD_NOTE, APP_AUTOSTART_*, APP_PLACE, PROFILE_ACTIVATE, Settings/Musik | voice/UI (Memory explizit) | Config-Änderung: UI | entsperrt | log | Bestätigungssatz | n/a | nur nutzer-geplant (künftig) |
| `local-execute` | APP_OPEN, OPEN, Sessionstart, Clap | Allowlist/URL-Policy + voice/UI | nein | entsperrt | log | Ergebnis | n/a | nur Sessionstart |
| `external-write` | **keine heute** (künftig: Mail senden, Kalender schreiben) | **UI-Bestätigung + Preview-Hash + Presence** (geplant) | **ja (geplant)** | entsperrt + UI | log + Korrelation | beobachtbare Evidenz | Kompensation (geplant) | **verboten** ohne Vorab-Autorisierung |
| `destructive` | MEMORY_FORGET | **Confirm (Ja/Nein)** + Ziel-Preview | **ja (nennt Einträge)** | entsperrt | log | „gelöscht"-Report | Nutzer sagt Nein | **nie** |

## 4. Regeln für untrusted Inhalte

- Web-/Vault-/Clipboard-/Screen-/Recherche-Inhalt wird als **untrusted** behandelt
  (SI-1). Umsetzung heute: `parse_action` validiert die LLM-Ausgabe strukturell
  (`actions.py:210`), aber es gibt **keine** Instruktion/Daten-Trennung → geplante
  Kontrolle (Phase 5): Wirkungen aus untrusted Text müssen als Vorschlag markiert und
  vor Ausführung autorisiert werden.
- Untrusted Inhalt darf **nie** Nutzerpräsenz oder Autorisierung ersetzen (SI-1/SI-2).

## 5. Autorisierungs-, Preview-, Verify-, Audit-, Cancel-Anforderungen

- **Autorisierung:** Token für alle REST/WS (`server.py:236`), Presence-Regeln (§Identity),
  Confirm für `destructive`, künftig UI-Bestätigung für `external-write`/Hochrisiko.
- **Preview (geplant):** Screen/Clipboard-Übertragung, Config-Änderungen, `external-write`.
- **Verify:** jede Wirkung liefert beobachtbare Evidenz (Ergebnis/Bestätigungssatz);
  Teilerfolg wird als solcher gemeldet (Phase 5/6).
- **Audit (geplant strukturiert, Phase 11):** je Wirkung Korrelations-ID, Quelle,
  Wirkungsklasse, Ergebnis; **ohne** Inhalte.
- **Cancel:** Stop bricht laufende Aktion + Wiedergabe ab (`server.py:180`); Kompensation
  für mehrstufige external-write erst mit Job-Engine (Phase 6).

## 6. SSRF- und Netzwerkregeln (geplant)

Für alle URL-Navigationen (`browser_tools.visit/open_url/fetch_page_text_fallback`):
- Nur `http`/`https` (heute: `actions.py:171`).
- **Host-Denylist** (geplant): `localhost`/`127.0.0.0/8`, `::1`, RFC1918
  (`10/8`,`172.16/12`,`192.168/16`), Link-Local `169.254/16` + `fe80::/10`, ULA
  `fc00::/7`, Cloud-Metadata `169.254.169.254`.
- **Redirect-Ziel re-validieren** (heute `follow_redirects=True` ungeprüft,
  `browser_tools.py:271`); DNS-Rebinding-Schutz.
- Selbstzugriff auf `127.0.0.1:8340` hart blocken (empfohlen). (TM-002, TM-003)

## 7. Screen-/Clipboard-Regeln (geplant)

- Region/aktives Fenster statt automatischem Vollbild (`screen_capture.py:13`).
- Sichtbare Übertragungsvorschau + Datenklasse + Abbruchmöglichkeit vor Cloud-Versand.
- Secret-Muster-Filter vor Übertragung. (TM-005, TM-006)

## 8. Logging und Redaction

- **Strukturierte Betriebslogs (RFC-0004, umgesetzt 2026-07-17):** ausschließlich benannte
  Ereignisse mit geschlossener Feld-Allowlist über `obslog.event(name, **fields)`. Kein
  Freitext-Payload; rohe private Inhalte erscheinen auf **keinem** Level (SI-9). Zentrale,
  fail-closed Redaction: unbekannte/falsch getippte Felder werden verworfen (nur
  `dropped_fields=<Anzahl>`, ohne `str()`/`repr()` auf dem Rohwert), URLs auf Schema+Host,
  Exceptions auf Typ/Ort (nie Message/Traceback). Werte von Secrets sind strukturell nicht
  darstellbar.
- **Import-sicher:** der Import konfiguriert nichts (kein Handler, keine Datei, keine
  Root-Logger-Änderung); die Verdrahtung passiert am Startpfad (`server._configure_logging`).
- **Schutznetz für Legacy/Dritte:** `obslog.install_protection()` sanitiert propagierte
  Records von uvicorn/httpx/anthropic/playwright (URL→Host, Query-Secrets/Token→`<redacted>`,
  kein Traceback) — ein Netz, keine Garantie.
- **Format/Level:** menschenlesbar per Default, JSONL via `JARVIS_LOG_FORMAT`; Level via
  `JARVIS_LOG_LEVEL`. Kein neuer Sink/FileHandler, keine neue Dependency.
- Offen (Phase 11): durchgehende Korrelation (`correlation_id`).

## 9. Panic Lock (geplant, nicht implementiert)

Ein künftiger Panic Lock muss mindestens: Mikrofon deaktivieren, laufende Jobs stoppen,
neue Jobs blockieren, Connectoren sperren, `external-write` blockieren, sichtbaren
Zustand erzeugen, und eine **bewusste lokale Reaktivierung** verlangen. (Phase 9/11)

## 10. Capability-Tabelle (alle 22 Actions + direkte UI-Wirkungen)

Präsenz = erlaubte Nutzerpräsenz; „unlocked" = lokal entsperrter Desktop. „Preview/Audit/
Verify/Cancel" bezeichnen die **Anforderung** (geplant, wo nicht vorhanden).

| Capability/Action | Datenklasse | Wirkungsklasse | Eingangsquelle | Präsenz | Autorisierung | Preview | Audit | Verify | Cancel/Compensate | Threat IDs | Phase |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SEARCH | public | network-read | voice/UI | unlocked | voice/UI + Host-Policy | – | log Host | Inhalt | Stop | TM-001,002 | 5 |
| BROWSE | public | network-read | voice/UI | unlocked | URL-Policy | – | log Host | Inhalt | Stop | TM-001,002 | 5 |
| OPEN | public | local-execute+network-read | voice/UI | unlocked | URL-Policy | – | log Host | geöffnet | Stop | TM-001,002 | 5 |
| APP_OPEN | local | local-execute | voice/UI | unlocked | Allowlist | – | log App | Meldung | – | TM-003 | 5 |
| PROFILE_ACTIVATE | local | local-write | voice/UI | unlocked | voice/UI | – | log | Satz | – | TM-003 | 5/8 |
| PROFILE_STATUS | local | read-local | voice/UI | unlocked/locked-lesend | voice/UI | – | log | Satz | – | – | 5 |
| APP_AUTOSTART_ON | local | local-write | voice/UI | unlocked | voice/UI | UI | log | Satz | – | TM-003 | 8 |
| APP_AUTOSTART_OFF | local | local-write | voice/UI | unlocked | voice/UI | UI | log | Satz | – | TM-003 | 8 |
| APP_PLACE | local | local-write | voice/UI | unlocked | voice/UI | UI | log | Satz | – | TM-003 | 8 |
| SCREEN | sensitive | read-sensitive+network-read | voice/UI | **unlocked** | voice/UI + **Preview** | **ja (geplant)** | log Nutzung | Beschreibung | Stop | TM-005 | 9 |
| NEWS | public | network-read | voice/UI | unlocked | voice/UI | – | log | Inhalt | Stop | TM-001 | 5 |
| INBOX_READ | personal | read-sensitive | voice/UI | unlocked | voice/UI | – | log | Inhalt | – | TM-008 | 7 |
| INBOX_WRITE | personal | local-write | voice/UI | unlocked | voice/UI | – | log | Bestätigung | – | TM-008 | 7 |
| MEMORY_WRITE | personal | local-write | voice (explizit) | unlocked | **explizit** voice/UI | – | log | Bestätigung | – | TM-008 | 7 |
| MEMORY_READ | personal | read-sensitive | voice/UI | unlocked | voice/UI | – | log | Inhalt | – | – | 7 |
| MEMORY_FORGET | personal | **destructive** | voice/UI | unlocked | **Confirm** + Ziel-Preview | **ja** | log | „gelöscht" | Nutzer-Nein | TM-008 | 5 |
| RESEARCH | public→personal | network-read+local-write | voice/UI | unlocked | voice/UI + Host-Policy | – | log Hosts | Summary+Quellen | Stop (180s) | TM-001,002 | 6 |
| CLIPBOARD | sensitive | read-sensitive+network-read | voice/UI | **unlocked** | voice/UI + **Preview** | **ja (geplant)** | log Nutzung | Antwort | Stop | TM-006 | 9 |
| CLIPBOARD_NOTE | sensitive→personal | local-write | voice/UI | unlocked | voice/UI + **Preview** | **ja (geplant)** | log | Bestätigung | – | TM-006,008 | 7/9 |
| NOTES_RECENT | personal | read-sensitive | voice/UI | unlocked | voice/UI | – | log | Inhalt | – | – | 7 |
| PROJECT_CONTEXT | personal | read-sensitive | voice/UI | unlocked | voice/UI | – | log | Antwort | – | TM-008 | 7 |
| SESSION_SUMMARY | personal | read-local | voice/UI | unlocked | voice/UI | – | log | Summary | – | – | 6/7 |
| **UI: POST /settings** | local/personal | local-write | UI (Token) | unlocked | Token + Whitelist | UI | log | 200/Fehler | – | TM-003 | 4 |
| **UI: POST /music/selection** | local | local-write | UI (Token) | unlocked | Token | UI | log | 200 | – | TM-003 | 8 |
| **UI: POST /commands/app/open** | local | local-execute | UI (Token) | unlocked | Token + Allowlist | – | log | Event | – | TM-003 | 5 |
| **UI: /launcher/\*** (toggle/placement/profiles) | local | local-write | UI (Token) | unlocked | Token + Validierung | UI | log | Response | – | TM-003 | 8 |
| **UI: /dashboard/state, /launcher/apps\|monitors\|profiles** | local/personal | read-local | UI (Token) | unlocked | Token | – | log | JSON | – | TM-003 | 8 |
| **Clap-Trigger / Sessionstart** | local | local-execute | Doppelklatschen | physisch anwesend | keine (physisch) | – | log | Apps starten | – | TM-004 | 9 |
| **Win+J / Fenstermodus** | local | local-execute (UI) | lokale UI | unlocked | lokale Präsenz | – | – | Fenster | – | – | 9 |

## 11. security-best-practices-Review (Teil E, je Empfehlung an Threat gebunden)

Getrennt nach Kontrollstatus. Stack: Python/FastAPI (`references/python-fastapi-web-server-security.md`).

- **Vorhanden & belegt:** lokale Bindung (`server.py:746`, SI-4); Token-Gate aller
  sensiblen REST/WS (`server.py:236`, gg. TM-003); Origin-Policy + `null`-nur-mit-Token
  (`actions.py:415`); `compare_digest` (Timing-sicher, `server.py:108`); Whitelist-
  Settings-Validierung (`config_loader.py:316`); Secrets nie über API (`PROTECTED_KEYS`);
  App-Allowlist ohne Shell (`app_launcher.py:471`, gg. TM-001); URL nur http/https
  (gg. gefährliche Schemata); Download-/Tab-/History-Caps (gg. TM-010); atomarer
  Config-Write (`config_loader.py:352`).
- **Teilweise:** URL-Policy prüft Schema, **nicht Host** → SSRF offen (TM-002); Secret-
  Filter existiert für den Vault-Context-Broker (`memory.py` `_SECRET_LINE_RE`), aber
  **nicht** für Screen/Clipboard (TM-005/006).
- **Geplant:** Untrusted-Content-Isolation (SI-1, Phase 5); SSRF-Host-Denylist (§6);
  Screen/Clipboard-Preview+Filter (§7); DPAPI-Secrets (CREDENTIAL_STRATEGY); strukturiertes
  Audit + Redaction (Phase 11); Panic Lock (§9); Presence-Runtime (§Identity).
- **Fehlend:** Rate-/Budget-Grenzen je Workflow (TM-010, Phase 6/11); Dependency-Pinning
  mit Hashes (TM-009).
- **Bewusst akzeptiert:** Token-Lesbarkeit via `GET /` gegen lokale Prozesse (teils
  out-of-scope, TM-003) — bis zum Fenster-Nonce dokumentiert; Malware mit Benutzerrechten.

Keine Empfehlung ist generisch — jede oben ist an Threat/Boundary/Asset gebunden. **Kein
Produktionscode wurde geändert.**

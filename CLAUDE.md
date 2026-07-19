# CLAUDE.md

Dieses Workspace ist **Jarvis** — ein persoenlicher KI-Assistent mit Sprachsteuerung, Browser-Kontrolle und Doppelklatschen-Trigger.

---

## Fuer Claude Code: Setup-Modus

Wenn der Nutzer nach dem Setup fragt oder "Richte Jarvis ein" sagt, folge den Anweisungen in `SETUP.md`. Frage den Nutzer nach seinem Namen, seiner Taetigkeit, und wie er angesprochen werden moechte — diese Infos gehoeren in `config.json` (`user_name`, `user_role`, `user_address`). Der Systemprompt in `assistant_core.py` (`build_system_prompt`) liest sie automatisch aus der Config; im Code muss nichts ersetzt werden. Spaeter sind sie auch im Jarvis-UI aenderbar: Kontrollzentrum → Einstellungen.

**WICHTIG — Pruefe und installiere zuerst alle Voraussetzungen:**

1. **Python**: Pruefe ob Python 3.10+ installiert ist (`python --version`). Falls nicht, installiere es:
   - Windows: `winget install Python.Python.3.12`
   - Warte bis die Installation abgeschlossen ist und pruefe erneut

2. **Google Chrome**: Pruefe ob Chrome installiert ist. Falls nicht, weise den Nutzer an Chrome von https://google.com/chrome zu installieren.

3. **pip Dependencies**: `pip install -r requirements.txt`

4. **Playwright Browser**: `playwright install chromium`

Erst NACHDEM alle Voraussetzungen installiert sind, fahre mit dem Setup in `SETUP.md` fort (API Keys abfragen, config.json erstellen, etc.).

---

## Workspace Structure

```
.
├── CLAUDE.md              # This file
├── SETUP.md               # Setup-Anleitung fuer Claude Code
├── config.json            # Persoenliche Config (gitignored)
├── config.example.json    # Template mit Platzhaltern
├── requirements.txt       # Python Dependencies
├── server.py              # FastAPI: Routen, WS-Endpoint (Origin/Token, Stopp-Handling), Settings-/Dashboard-/Command-API — dispatcht alle wirkenden Pfade ueber rt.capabilities
├── runtime.py             # Composition Root (RFC-0002): Runtime besitzt Config/Clients/State,
│                         #   create_app(runtime), Lifespan aopen/aclose; haelt den einen
│                         #   Capability-Coordinator und den TargetGuard
├── assistant_core.py      # Gespraechsfluss: System-Prompt (build_system_prompt), LLM-Calls, Verlauf, Action-Orchestrierung
├── capability/            # Capability-/Policy-Kernel als deep module (RFC-0007 + Amendment 2):
│                         #   Contract (Taxonomie/Vertraege) · Policy (reiner decide) · Coordinator
│                         #   (validate→…→verify) · SSRF-TargetGuard · Legacy-Adapter ([ACTION:…]→Capability).
│                         #   ALLE 22 Voice-Actions + 9/10 mutierende REST-Routen laufen hierueber
├── conversation/          # ConversationSession/TurnContext (RFC-0006): Turn-/Queue-/Cancel-Besitz,
│                         #   reiner Transitionskern; loest die Session-Globals ab
├── wire_protocol/         # Typisierte, versionierte Wire-Contracts (RFC-0005): Legacy- + V1-Codec,
│                         #   ConversationChannel/EventSink; kein Wire-Dict im App-Code
├── configuration.py       # Configuration als deep module (RFC-0003): Runtime-eigener
│                         #   Single Writer — snapshot()/settings_view()/mutate(intent),
│                         #   schema_version v1 + Migration, atomarer Austausch, Rollback
├── config_loader.py       # Leaf: Config laden/validieren (Settings-Whitelist, apps-Registry)
├── obslog.py              # Strukturierte Betriebslogs als deep module (RFC-0004): einziges
│                         #   Emit-Interface event(name, **fields) mit geschlossener Feld-
│                         #   Allowlist + fail-closed Redaction; install_protection() als
│                         #   Schutznetz fuer uvicorn/httpx/… — rohe private Inhalte auf keinem Level
├── actions.py             # Action als deep module: Registry (ActionSpec) mit Metadaten,
│                         #   Ausfuehrung (execute) + Prompt-Selbstbeschreibung (describe)
│                         #   je Action; Parsing + URL/Origin-Policies + Stop-Woerter
├── app_launcher.py        # Allowlist-App-Launcher (config.apps) — Sprach-Aktion APP_OPEN + UI-Klick
├── tts.py                 # ElevenLabs-TTS (Chunking, Retries) — pur und testbar
├── memory.py              # Tages-Inbox, Vault-Helfer + Langzeit-Gedaechtnis ("Jarvis Memory.md")
├── monitors.py            # Monitor-Erkennung (ctypes) fuer die Monitor-Map — GET /launcher/monitors
├── health.py              # /health-Report (Key-/Browser-/Vault-Checks, passiv)
├── browser_tools.py       # Playwright Browser-Steuerung + HTML-Fallback fuer Quellensuche
├── screen_capture.py      # Screenshot + Claude Vision (optionale Kontextfrage)
├── clipboard_tools.py     # Windows-Zwischenablage lesen (PowerShell Get-Clipboard)
├── jarvis-launcher.pyw    # Natives pywebview-Fenster + Tray + Panel-/Fokus-Modus
├── frontend/
│   ├── index.html         # Jarvis Web-UI
│   ├── main.js            # Speech Recognition + WebSocket + Audio + Orb + Seiten-Nav + Command Center
│   ├── settings.js        # Einstellungen im Kontrollzentrum (GET/POST /settings)
│   ├── music.js           # Musik-Sub-View: MP3-Auswahl fuer den Sessionstart (GET/POST /music/*)
│   └── style.css          # Dark Theme mit Orb-Animation, Panel-/Fokus-Layouts + Command Center
├── tests/                 # unittest-Suite (python -m unittest discover -s tests)
└── scripts/
    ├── clap-trigger.py    # Doppelklatschen-Erkennung
    └── launch-session.ps1 # Startet alle Apps + Jarvis
```

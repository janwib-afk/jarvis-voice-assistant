# CLAUDE.md

Dieses Workspace ist **Jarvis** — ein persoenlicher KI-Assistent mit Sprachsteuerung, Browser-Kontrolle und Doppelklatschen-Trigger.

---

## Fuer Claude Code: Setup-Modus

Wenn der Nutzer nach dem Setup fragt oder "Richte Jarvis ein" sagt, folge den Anweisungen in `SETUP.md`. Frage den Nutzer nach seinem Namen, seiner Taetigkeit, und wie er angesprochen werden moechte — diese Infos gehoeren in `config.json` (`user_name`, `user_role`, `user_address`). Der Systemprompt in `server.py` liest sie automatisch aus der Config; im Code muss nichts ersetzt werden. Spaeter sind sie auch im Jarvis-UI ueber die Einstellungen (Zahnrad-Symbol) aenderbar.

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
├── server.py              # FastAPI: Routen, WS-Endpoint (Origin/Token, Stopp-Handling), Settings-API
├── assistant_core.py      # Gespraechsfluss: System-Prompt, LLM-Calls, Verlauf, Action-Ausfuehrung
├── config_loader.py       # Config laden/validieren/speichern (Settings-Whitelist)
├── actions.py             # Action-Registry (ActionSpec) + Parsing + URL/Origin-Policies + Stop-Woerter
├── tts.py                 # ElevenLabs-TTS (Chunking, Retries) — pur und testbar
├── memory.py              # Tages-Inbox, Vault-Helfer + Langzeit-Gedaechtnis ("Jarvis Memory.md")
├── health.py              # /health-Report (Key-/Browser-/Vault-Checks, passiv)
├── browser_tools.py       # Playwright Browser-Steuerung + HTML-Fallback fuer Quellensuche
├── screen_capture.py      # Screenshot + Claude Vision (optionale Kontextfrage)
├── clipboard_tools.py     # Windows-Zwischenablage lesen (PowerShell Get-Clipboard)
├── jarvis-launcher.pyw    # Natives pywebview-Fenster + Tray + Panel-/Fokus-Modus
├── frontend/
│   ├── index.html         # Jarvis Web-UI
│   ├── main.js            # Speech Recognition + WebSocket + Audio + Orb-Zustaende
│   ├── settings.js        # Einstellungen-Overlay (GET/POST /settings)
│   └── style.css          # Dark Theme mit Orb-Animation, Panel-/Fokus-Layouts
├── tests/                 # unittest-Suite (python -m unittest discover -s tests)
└── scripts/
    ├── clap-trigger.py    # Doppelklatschen-Erkennung
    └── launch-session.ps1 # Startet alle Apps + Jarvis
```

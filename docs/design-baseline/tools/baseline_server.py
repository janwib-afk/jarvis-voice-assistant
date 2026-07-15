"""Phase-0-Baseline-Harness: startet den ECHTEN Jarvis-Server gefahrlos auf Port 8341.

Zweck: Die UI fuer die visuelle Baseline (und spaetere Redesign-Vergleiche) in einem
Browser inspizieren, ohne dass je ein kostenpflichtiger API-Call ausgeloest werden
kann. Hintergrund: Das Frontend sendet beim ersten WS-Connect automatisch die
Begruessung 'Jarvis activate' (frontend/main.js) — gegen einen Server mit echter
config.json waere allein das OEffnen der Seite ein Anthropic- + ElevenLabs-Call.

Sicherheitsmassnahmen (alle Stubs greifen VOR dem ersten Connect):
  - Temp-config.json mit Dummy-Keys — die echte config.json wird NIE geladen.
  - LLM gestubbt: deterministische deutsche Antworten (zyklisch), kein Netz.
  - TTS gestubbt: (b"", None) — Antwort erscheint als Text, kein Fehlerbanner.
  - assistant_core.refresh_data gestubbt — kein wttr.in-Call beim 'activate'.
  - JARVIS_SKIP_STARTUP_REFRESH=1 — kein Startup-Refresh.
  - app_launcher._start_url/_start_process gestubbt — 'OEffnen'-Klicks starten
    nichts, liefern aber den normalen Erfolgs-Flow fuer die UI.
  - server.CONFIG_PATH -> Temp-Config — alle POST-Schreibzugriffe (Settings,
    Musik, Launcher/Profile) landen im Tempordner, nie in der echten Config.

Nutzung:  python docs/design-baseline/tools/baseline_server.py [--port 8341]
Stoppen:  Ctrl+C. Es wird keine bestehende Projektdatei veraendert.
"""

import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

# Muss vor dem server-Import gesetzt sein (server registriert den Startup-Hook).
os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)

PORT = 8341
if "--port" in sys.argv:
    PORT = int(sys.argv[sys.argv.index("--port") + 1])

# ── 1) Temp-Umgebung: Inbox, Vault, Musikordner, Dummy-Apps ─────────────────
# Fester Pfad statt mkdtemp: Die Settings-/Musik-Views rendern diese Pfade —
# ein zufaelliger Suffix wuerde Screenshot-Vergleiche zwischen Laeufen
# nichtdeterministisch machen. Der Ordner gehoert ausschliesslich dem Harness.
TMP = os.path.join(tempfile.gettempdir(), "jarvis-baseline-fixed")
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)
INBOX = os.path.join(TMP, "inbox")
VAULT = os.path.join(TMP, "vault")
MUSIC = os.path.join(TMP, "music")
for d in (INBOX, VAULT, MUSIC):
    os.makedirs(d, exist_ok=True)
for name in ("Ambient Start.mp3", "Deep Focus.mp3", "Morning Drive.mp3"):
    open(os.path.join(MUSIC, name), "wb").close()

# Kommandos zeigen auf nicht existente Pfade — selbst ein ungestubbter Launch
# koennte nichts starten (doppelter Boden zusaetzlich zu den _start_*-Stubs).
MISSING_EXE = os.path.join(TMP, "does-not-exist", "app.exe")

BASELINE_CONFIG = {
    "anthropic_api_key": "baseline-dummy-anthropic-key",
    "elevenlabs_api_key": "baseline-dummy-elevenlabs-key",
    "elevenlabs_voice_id": "baseline-voice",
    "user_name": "Jan",
    "user_address": "Jan",
    "user_role": "Baseline-Aufnahme",
    "city": "Hamburg",
    "workspace_path": TMP,
    "obsidian_inbox_path": VAULT,
    "obsidian_inbox_folder": INBOX,
    "music_folder": MUSIC,
    "selected_music_file": "",
    "music_volume": 0.25,
    "apps": [
        {"id": "obsidian", "name": "Obsidian", "command": MISSING_EXE,
         "type": "process", "process_name": "baseline-none"},
        {"id": "vscode", "name": "VS Code", "command": MISSING_EXE,
         "type": "process", "process_name": "baseline-none"},
        {"id": "kalender", "name": "Kalender", "command": "https://example.invalid/kalender",
         "type": "url", "process_name": "baseline-none"},
        {"id": "steam", "name": "Steam", "command": MISSING_EXE,
         "type": "process", "process_name": "baseline-none"},
    ],
    "launcher": {
        "active_profile": "coding",
        "profiles": [
            {"id": "coding", "name": "Coding", "apps": {
                "vscode": {"autostart": True, "placement": {"monitor": "left", "zone": "left_half"}},
                "obsidian": {"autostart": True, "placement": {"monitor": "left", "zone": "right_half"}},
                "kalender": {"autostart": False},
            }},
            {"id": "research", "name": "Research", "apps": {
                "obsidian": {"autostart": True, "placement": {"monitor": "left", "zone": "fullscreen"}},
                "kalender": {"autostart": True, "placement": {"monitor": "right", "zone": "fullscreen"}},
                "vscode": {"autostart": False},
            }},
        ],
    },
}

CONFIG_PATH = os.path.join(TMP, "config.json")
with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump(BASELINE_CONFIG, f, indent=2)

# ── 2) Server importieren (Amendment 1: Import laedt nichts, erzeugt nichts) ─
import server  # noqa: E402
import runtime as runtime_mod  # noqa: E402

# ── 3) Stubs: LLM, TTS, refresh_data, App-Starts ─────────────────────────────
import app_launcher  # noqa: E402
import assistant_core  # noqa: E402

REPLIES = [
    "Guten Morgen, Jan. Alle Systeme laufen stabil — die Baseline-Aufnahme kann beginnen.",
    "Die visuelle Bestandsaufnahme laeuft. Ich dokumentiere Farben, Typografie und Komponenten.",
    "Der Orb kennt sechs Zustaende: idle, listening, thinking, speaking, muted und error.",
    "Notiert. Die Screenshots landen unter docs/design-baseline/screenshots.",
    "Verstanden. Diese Antwort stammt aus dem Baseline-Stub, nicht von der echten API.",
]


class _FakeMessages:
    """Wie tests/test_integration_research.py, aber zyklisch statt endlich."""

    def __init__(self, replies):
        self._replies = list(replies)
        self._i = 0

    async def create(self, **kwargs):
        text = self._replies[self._i % len(self._replies)]
        self._i += 1
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class _FakeAI:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


async def _fake_synthesize_speech(text):
    return b"", None  # kein Audio, kein Fehler -> Client geht sauber auf idle


assistant_core.synthesize_speech = _fake_synthesize_speech
assistant_core.refresh_data = lambda: None  # 'activate' loest sonst wttr.in aus
app_launcher._start_url = lambda command: None
app_launcher._start_process = lambda command: None

# Runtime mit EXPLIZITER Temp-Config + injiziertem Fake-LLM (BORROWED — wird vom
# Root nie geschlossen); Config/Clients oeffnen im Lifespan. environ={} umgeht ein
# evtl. geerbtes JARVIS_CONFIG_PATH. Alle Save-Endpunkte schreiben in die Temp-Config.
_rt = runtime_mod.Runtime.for_production(
    config_path=CONFIG_PATH, environ={}, ai=_FakeAI(REPLIES))
app = server.create_app(_rt)

# ── 4) Start ─────────────────────────────────────────────────────────────────
import uvicorn  # noqa: E402

if __name__ == "__main__":
    print(f"[baseline] Temp-Umgebung: {TMP}")
    print(f"[baseline] Server: http://127.0.0.1:{PORT}  (Dummy-Keys, LLM/TTS/Apps gestubbt)")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")

"""E2E-Harness-Server: startet den ECHTEN Jarvis-Server gefahrlos auf einem
frei waehlbaren Loopback-Port — mit kontrollierbaren Provider-/Desktop-Adaptern.

Erweitert die Idee von docs/design-baseline/tools/baseline_server.py:
  - alle externen Grenzen (LLM, TTS, Wetter/refresh, Browser, Clipboard, Screen,
    App-Start, Monitor-Hardware) sind gestubbt — 0 echte Provider-/Netzaufrufe,
    0 echte Desktopwirkung, 0 API-Kosten;
  - synthetische Temp-Config mit Dummy-Keys (die echte config.json wird nie
    geladen);
  - ein Test-Steuerkanal ``/__e2e__/scenario`` erlaubt es dem Browsertest, die
    naechsten LLM-Antworten, eine kuenstliche Aktions-Dauer (fuer Stop-Tests) und
    Provider-Fehler deterministisch vorzugeben.

Der Steuerkanal ist reine Test-Infrastruktur (nur auf 127.0.0.1, ephemerer Port)
und beruehrt keinen Produktionscode.

Nutzung:  python tests/browser/e2e_server.py --port <PORT> [--tmp <DIR>]
Readiness: GET /health liefert 200. Stoppen: SIGTERM/kill.
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
from collections import deque
from types import SimpleNamespace

# Muss vor dem server-Import gesetzt sein (server registriert den Startup-Hook).
os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

PORT = 8399
if "--port" in sys.argv:
    PORT = int(sys.argv[sys.argv.index("--port") + 1])
TMP = None
if "--tmp" in sys.argv:
    TMP = os.path.abspath(sys.argv[sys.argv.index("--tmp") + 1])
if not TMP:
    TMP = os.path.join(tempfile.gettempdir(), f"jarvis-e2e-{PORT}")
shutil.rmtree(TMP, ignore_errors=True)
INBOX = os.path.join(TMP, "inbox")
VAULT = os.path.join(TMP, "vault")
MUSIC = os.path.join(TMP, "music")
for d in (INBOX, VAULT, MUSIC):
    os.makedirs(d, exist_ok=True)
for name in ("Ambient Start.mp3", "Deep Focus.mp3", "Morning Drive.mp3"):
    open(os.path.join(MUSIC, name), "wb").close()

MISSING_EXE = os.path.join(TMP, "does-not-exist", "app.exe")

E2E_CONFIG = {
    "schema_version": 1,
    "anthropic_api_key": "e2e-dummy-anthropic-key",
    "elevenlabs_api_key": "e2e-dummy-elevenlabs-key",
    "elevenlabs_voice_id": "e2e-voice",
    "user_name": "Testnutzer",
    "user_address": "Chef",
    "user_role": "E2E-Testlauf",
    "city": "Hamburg",
    "workspace_path": TMP,
    "obsidian_inbox_path": VAULT,
    "obsidian_inbox_folder": INBOX,
    "music_folder": MUSIC,
    "selected_music_file": "",
    "music_volume": 0.25,
    "apps": [
        {"id": "obsidian", "name": "Obsidian", "command": MISSING_EXE,
         "type": "process", "process_name": "e2e-none"},
        {"id": "vscode", "name": "VS Code", "command": MISSING_EXE,
         "type": "process", "process_name": "e2e-none"},
        {"id": "kalender", "name": "Kalender", "command": "https://example.invalid/kalender",
         "type": "url", "process_name": "e2e-none"},
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
    json.dump(E2E_CONFIG, f, indent=2)

# Amendment 1 (voll-lazy Import): der Import laedt nichts und erzeugt keine
# Clients — die Runtime bekommt die E2E-Temp-Config spaeter explizit. Kein
# load_config-Monkeypatch mehr noetig.
import server  # noqa: E402
import runtime as runtime_mod  # noqa: E402

import app_launcher  # noqa: E402
import assistant_core  # noqa: E402
import browser_tools  # noqa: E402
import clipboard_tools  # noqa: E402
import monitors  # noqa: E402
import screen_capture  # noqa: E402

# ── Steuerbarer LLM-Adapter ─────────────────────────────────────────────────
# Der Browsertest legt die naechsten Antworten ueber /__e2e__/scenario ab.
# Ist die Queue leer (z.B. die Auto-Begruessung 'Jarvis activate'), wird eine
# unverfaengliche Standardantwort geliefert.
_SCENARIO = {
    "replies": deque(),
    "llm_delay": 0.0,     # kuenstliche LLM-Latenz (s)
    "action_delay": 0.0,  # kuenstliche Aktions-Dauer (s) fuer Stop-Tests
}
_DEFAULT_REPLY = "Alles bereit, Chef. Diese Antwort stammt aus dem E2E-Stub."


class _FakeMessages:
    async def create(self, **kwargs):
        if _SCENARIO["llm_delay"]:
            await asyncio.sleep(_SCENARIO["llm_delay"])
        item = _SCENARIO["replies"].popleft() if _SCENARIO["replies"] else _DEFAULT_REPLY
        if isinstance(item, dict) and item.get("raise"):
            raise RuntimeError("e2e-stub-provider-fehler")
        text = item if isinstance(item, str) else str(item.get("text", _DEFAULT_REPLY))
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class _FakeAI:
    def __init__(self):
        self.messages = _FakeMessages()


async def _fake_synth(text):
    return b"", None  # kein Audio -> Client geht sauber auf idle (kein TTS-Netz)


async def _fake_search_links(query, limit=5):
    # Kuenstliche Dauer fuer Stop-Tests; asyncio.sleep ist abbrechbar (CancelledError).
    if _SCENARIO["action_delay"]:
        await asyncio.sleep(_SCENARIO["action_delay"])
    return [
        {"title": "E2E Quelle 1", "url": "https://example.invalid/eins"},
        {"title": "E2E Quelle 2", "url": "https://example.invalid/zwei"},
        {"title": "E2E Quelle 3", "url": "https://example.invalid/drei"},
    ]


async def _fake_visit(url, max_chars=1500):
    return {"title": f"Titel {url}", "url": url, "content": "E2E-Inhalt ohne Netz."}


async def _fake_search_and_read(query):
    if _SCENARIO["action_delay"]:
        await asyncio.sleep(_SCENARIO["action_delay"])
    return {"title": "E2E-Treffer", "url": "https://example.invalid/treffer",
            "content": "Kurzer E2E-Trefferinhalt."}


async def _fake_fetch_news():
    return "E2E-Nachrichten: nichts Echtes, rein synthetisch."


assistant_core.synthesize_speech = _fake_synth
assistant_core.refresh_data = lambda: None
browser_tools.search_links = _fake_search_links
browser_tools.visit = _fake_visit
browser_tools.search_and_read = _fake_search_and_read
browser_tools.fetch_news = _fake_fetch_news
browser_tools.open_url = lambda url: None
app_launcher._start_url = lambda command: None
app_launcher._start_process = lambda command: None
clipboard_tools.get_clipboard_text = lambda: "E2E-Zwischenablageninhalt (synthetisch)."
monitors.detect_monitors = lambda: [
    {"id": "left", "label": "Linker Monitor", "x": 0, "y": 0,
     "width": 1920, "height": 1080, "primary": True},
    {"id": "right", "label": "Rechter Monitor", "x": 1920, "y": 0,
     "width": 1920, "height": 1080, "primary": False},
]
screen_capture.describe_screen = lambda ai, question="": "E2E-Bildschirmbeschreibung (synthetisch)."

# ── Test-Steuerkanal (nur Test-Infra) ───────────────────────────────────────
from fastapi import Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

# Runtime mit EXPLIZITER E2E-Temp-Config + injiziertem Fake-LLM (BORROWED — wird
# vom Root nie geschlossen). environ={} umgeht ein evtl. geerbtes
# JARVIS_CONFIG_PATH der Testsuite; Config/Clients oeffnen im Lifespan.
_rt = runtime_mod.Runtime.for_production(config_path=CONFIG_PATH, environ={}, ai=_FakeAI())
app = server.create_app(_rt)


@app.post("/__e2e__/scenario")
async def _e2e_scenario(request: Request):
    body = await request.json()
    _SCENARIO["replies"].clear()
    for item in body.get("replies", []):
        _SCENARIO["replies"].append(item)
    _SCENARIO["llm_delay"] = float(body.get("llm_delay", 0.0))
    _SCENARIO["action_delay"] = float(body.get("action_delay", 0.0))
    return JSONResponse({"ok": True, "queued": len(_SCENARIO["replies"])})


@app.post("/__e2e__/reset")
async def _e2e_reset():
    _SCENARIO["replies"].clear()
    _SCENARIO["llm_delay"] = 0.0
    _SCENARIO["action_delay"] = 0.0
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn
    print(f"[e2e] Temp: {TMP}")
    print(f"[e2e] Server: http://127.0.0.1:{PORT}  (Dummy-Keys, alle Provider gestubbt)")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")

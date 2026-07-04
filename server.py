"""
Jarvis V2 — Voice AI Server

Reine HTTP-/WebSocket-Schicht: FastAPI-App, Routen (/,, /health, /settings),
WS-Endpoint mit Origin-/Token-Gate. Der Gesprächsfluss (LLM, Aktionen, TTS)
liegt in assistant_core.py, Diagnose in health.py, Obsidian/Memory in memory.py.
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import asyncio
import json
import logging
import os
import secrets

import anthropic
import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

import actions
import assistant_core
import config_loader
import memory

# Logging: Betriebs-Logs auf INFO, private Inhalte nur auf DEBUG (Default aus).
# Level per Umgebungsvariable JARVIS_LOG_LEVEL ueberschreibbar.
logging.basicConfig(
    level=os.environ.get("JARVIS_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jarvis")

# Lokales Session-Token: schuetzt /ws zusaetzlich zum Origin-Check. Wird beim
# Start erzeugt und nur in die ausgelieferte Seite injiziert (Same-Origin).
SESSION_TOKEN = secrets.token_urlsafe(24)

# Load config (zentrale Validierung mit verständlichen Fehlermeldungen)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
try:
    config = config_loader.load_config(CONFIG_PATH)
except config_loader.ConfigError as e:
    logger.error("Konfigurationsfehler:\n%s", e)
    sys.exit(1)

# Optionale Voraussetzungen pruefen (Obsidian-Pfade, Playwright/Chromium).
# Warnungen brechen den Start NICHT ab — betroffene Features degradieren nur.
STARTUP_WARNINGS = config_loader.check_runtime_environment(config)
for _warning in STARTUP_WARNINGS:
    logger.warning("Startup-Check: %s", _warning)

# Timeout + Retries SDK-nativ — gilt fuer alle Claude-Calls inkl. Vision.
ai = anthropic.AsyncAnthropic(api_key=config["anthropic_api_key"], timeout=30.0, max_retries=2)
http = httpx.AsyncClient(timeout=30)

# Module verdrahten: Obsidian-Pfade, Persona/TTS-Werte, API-Clients.
memory.configure(
    vault_path=config.get("obsidian_inbox_path", ""),
    inbox_path=config.get("obsidian_inbox_folder", ""),
)
assistant_core.configure(config)
assistant_core.init_clients(ai, http)

app = FastAPI()

import browser_tools
import health

# Chromium beim Server-Stopp mit beenden.
app.router.on_shutdown.append(browser_tools.close)


async def _startup_refresh():
    # Kontextdaten (Wetter/Tasks/Vault) im Hintergrund laden — der Server nimmt
    # sofort Verbindungen an. build_system_prompt toleriert noch fehlende Daten.
    # Tests/Smoke-Test setzen JARVIS_SKIP_STARTUP_REFRESH, um echte Netz-/
    # Dateisystemzugriffe zu vermeiden.
    if os.environ.get("JARVIS_SKIP_STARTUP_REFRESH"):
        return
    asyncio.get_running_loop().create_task(asyncio.to_thread(assistant_core.refresh_data))

app.router.on_startup.append(_startup_refresh)

# Verbundene WS-Clients — fuer Push-Updates (z.B. frische Warnings nach Settings-Save).
ws_clients: set[WebSocket] = set()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Token zuerst bestimmen — die Origin-Policy braucht es fuer den 'null'-Sonderfall.
    # Als bytes vergleichen — compare_digest auf str wirft bei Nicht-ASCII.
    origin = ws.headers.get("origin")
    token = ws.query_params.get("token", "")
    token_valid = secrets.compare_digest(token.encode("utf-8"), SESSION_TOKEN.encode("utf-8"))

    # 1. Origin-Policy: lokale Origins immer; 'null' nur mit gueltigem Token
    #    (pywebview/WebView2-Sandbox); fremde/fehlende Origins abgelehnt.
    if not actions.is_origin_acceptable(origin, token_valid):
        logger.warning("WS-Verbindung mit unzulaessigem Origin abgelehnt: %r", origin)
        await ws.close(code=1008)
        return

    # 2. Session-Token hart pruefen (schuetzt auch lokale Origins).
    if not token_valid:
        logger.warning("WS-Verbindung mit ungueltigem Token abgelehnt")
        await ws.close(code=1008)
        return

    await ws.accept()
    session_id = str(id(ws))
    ws_clients.add(ws)
    logger.info("Client verbunden")

    # Startup-Warnungen ans Status-Center melden.
    await ws.send_json({"type": "health", "warnings": STARTUP_WARNINGS})

    # Nachrichten laufen als Task neben der Receive-Loop — so kommt ein "Stopp"
    # auch WÄHREND einer langen Aktion (z.B. 3-Minuten-Recherche) durch.
    # Ein Worker arbeitet die Queue strikt sequenziell ab (wie bisher).
    queue: asyncio.Queue[str] = asyncio.Queue()
    current: dict = {"task": None}

    async def worker():
        while True:
            text = await queue.get()
            task = asyncio.create_task(assistant_core.process_message(session_id, text, ws))
            current["task"] = task
            try:
                await task
            except asyncio.CancelledError:
                if not task.cancelled():
                    # Der Worker selbst wurde beendet (Disconnect) — Task mitnehmen.
                    task.cancel()
                    raise
                # Task wurde per "Stopp" abgebrochen — weiter mit der naechsten Nachricht.
            except Exception:
                # Unerwartete Fehler beenden nie die Verbindung.
                logger.exception("Nachrichtenverarbeitung fehlgeschlagen")
                try:
                    await assistant_core.send_error(ws, "llm", "Interner Fehler bei der Verarbeitung.")
                except Exception:
                    pass
            finally:
                current["task"] = None

    worker_task = asyncio.create_task(worker())

    try:
        while True:
            data = await ws.receive_json()
            user_text = data.get("text", "").strip()

            # Stopp: laufende Verarbeitung/Aktion abbrechen, Queue leeren,
            # Frontend stoppt die Audio-Wiedergabe (Frame type=stop).
            if data.get("type") == "stop" or actions.is_stop_command(user_text):
                task = current["task"]
                was_busy = task is not None and not task.done()
                if was_busy:
                    task.cancel()
                while not queue.empty():
                    queue.get_nowait()
                assistant_core.pending_confirm.pop(session_id, None)
                logger.info("Stopp empfangen (Task aktiv: %s)", was_busy)
                await ws.send_json({"type": "stop"})
                if was_busy:
                    await ws.send_json({"type": "response", "text": "Okay, gestoppt.", "audio": ""})
                continue

            if not user_text:
                continue

            logger.debug("You: %s", user_text)
            await queue.put(user_text)

    except WebSocketDisconnect:
        pass
    finally:
        worker_task.cancel()
        ws_clients.discard(ws)
        assistant_core.end_session(session_id)


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")), name="static")


INDEX_PATH = os.path.join(os.path.dirname(__file__), "frontend", "index.html")


@app.get("/health")
async def health_endpoint():
    """Passive Statusuebersicht fuer Launcher, Tests und Smoke-Test.

    'ok' heisst: der Server nimmt Verbindungen an. Einzeldienste stehen in
    'services'; es werden keine bezahlten APIs angefragt (kein Quota-Verbrauch).
    """
    return health.build_report(
        config, STARTUP_WARNINGS, assistant_core.DATA_LOADED, assistant_core.LAST_REFRESH
    )


# ── Settings-API ─────────────────────────────────────────────────────────────
# Editierbar ist nur die Whitelist aus config_loader.UI_EDITABLE_KEYS.
# API-Keys verlassen den Server nie und werden nie angenommen.

def _settings_token_ok(request: Request) -> bool:
    token = request.headers.get("x-jarvis-token", "")
    return secrets.compare_digest(token.encode("utf-8"), SESSION_TOKEN.encode("utf-8"))


def _public_settings() -> dict:
    return {
        key: config.get(key, [] if key == "apps" else "")
        for key in sorted(config_loader.UI_EDITABLE_KEYS)
    }


async def broadcast_health():
    """Frische Warnings an alle verbundenen Clients pushen."""
    for client in list(ws_clients):
        try:
            await client.send_json({"type": "health", "warnings": STARTUP_WARNINGS})
        except Exception:
            ws_clients.discard(client)


async def apply_settings(merged: dict):
    """Gespeicherte Settings ohne Neustart uebernehmen. System-Prompt und
    Voice-ID werden pro Anfrage gelesen und greifen damit sofort."""
    global config, STARTUP_WARNINGS

    needs_refresh = (
        merged.get("city", assistant_core.CITY) != assistant_core.CITY
        or merged.get("obsidian_inbox_path", memory.VAULT_PATH) != memory.VAULT_PATH
        or merged.get("obsidian_inbox_folder", memory.INBOX_PATH) != memory.INBOX_PATH
    )
    config = merged
    assistant_core.configure(config)
    memory.configure(
        vault_path=config.get("obsidian_inbox_path", ""),
        inbox_path=config.get("obsidian_inbox_folder", ""),
    )
    STARTUP_WARNINGS = config_loader.check_runtime_environment(config)
    if needs_refresh:
        # wttr.in/Vault-Scan blockieren bis ~5s — nicht auf der Event-Loop laufen lassen.
        await asyncio.to_thread(assistant_core.refresh_data)
    await broadcast_health()


@app.get("/settings")
async def get_settings(request: Request):
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    return {"ok": True, "settings": _public_settings(), "warnings": STARTUP_WARNINGS}


@app.post("/settings")
async def post_settings(request: Request):
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    try:
        updates = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "errors": ["Ungültiges JSON."]}, status_code=400)
    errors = config_loader.validate_settings_update(updates)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)
    try:
        merged = config_loader.save_settings(CONFIG_PATH, updates)
    except config_loader.ConfigError as e:
        # ConfigError-Meldungen nennen nur Schluesselnamen, nie Werte.
        return JSONResponse({"ok": False, "errors": [str(e)]}, status_code=500)
    await apply_settings(merged)
    logger.info("Settings aktualisiert: %s", ", ".join(sorted(updates.keys())))
    return {"ok": True, "applied": sorted(updates.keys()), "warnings": STARTUP_WARNINGS}


@app.get("/")
async def serve_index():
    # Session-Token in die ausgelieferte Seite injizieren. Dank Same-Origin-Policy
    # kann nur diese Seite das Token lesen — fremde Origins nicht.
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    token_script = f'<script>window.JARVIS_TOKEN={json.dumps(SESSION_TOKEN)};</script>'
    if "</head>" in html:
        html = html.replace("</head>", token_script + "</head>", 1)
    else:
        html = token_script + html
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn
    print("=" * 50, flush=True)
    print("  J.A.R.V.I.S. V2 Server", flush=True)
    print(f"  http://localhost:8340", flush=True)
    print("=" * 50, flush=True)
    for _warning in STARTUP_WARNINGS:
        print(f"  WARNUNG: {_warning}", flush=True)
    # Nur lokal binden — nicht im LAN erreichbar.
    uvicorn.run(app, host="127.0.0.1", port=8340)

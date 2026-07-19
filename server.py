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
import contextlib
import json
import os
import re
import secrets

import anthropic
import httpx
from fastapi import APIRouter, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

import actions
import app_launcher
import capability
import monitors
import assistant_core
import config_loader
import conversation
import configuration
import memory
import obslog
import runtime as runtime_mod
import wire_protocol as wp

# Logging: strukturierte Operational Events mit zentraler Redaction (RFC-0004).
# Der Import konfiguriert NICHTS (Import-Sicherheit, D9) — die Verdrahtung passiert
# einmalig am expliziten Startpfad (_configure_logging), fuer beide Entry Points:
#   - python server.py  -> vor dem Config-Load
#   - uvicorn server:app -> im Lifespan-Start (nicht beim Import)


def _configure_logging() -> None:
    """Einmalig am Startpfad: produktiver stderr-Sink + Format-/Level-Schalter.

    Idempotent (obslog.configure ist idempotent). JARVIS_LOG_LEVEL (Default INFO)
    und JARVIS_LOG_FORMAT=text|jsonl (Default text, ungueltig -> text) steuern die
    Ausgabe. Kein FileHandler, keine neue Dependency (D10)."""
    obslog.configure(
        fmt=obslog.format_from_env(),
        level=os.environ.get("JARVIS_LOG_LEVEL", "INFO"),
    )
    # Schutznetz fuer Legacy-/Drittanbieter-Records (uvicorn/httpx/anthropic/…).
    obslog.install_protection()

import browser_tools
import health

# ── Composition Root (RFC-0002 + Amendment 1): import-sicher ────────────────
# Der Import erzeugt NUR eine ungeöffnete Runtime — kein Config-Load, keine
# Provider-Clients, kein Prozess, kein sys.exit. Config + OWNED-Clients öffnen
# ausschließlich im FastAPI-Lifespan (runtime.aopen) und schließen in aclose.
runtime = runtime_mod.Runtime.for_production()

# Read-Spiegel der Produktions-Runtime fuer Bestandsaufrufer/Launcher.
# Config, Config-Pfad und Warnungen leben AUSSCHLIESSLICH in der Runtime bzw.
# ihrer Configuration (RFC-0003 Slice 5: A6-Cleanup) — es gibt keine zweite,
# veraenderbare Wahrheit mehr.
SESSION_TOKEN = runtime.session_token
# Verbundene WS-Clients werden jetzt in der Runtime-ConnectionRegistry gehalten
# (RFC-0005 §12) — kein Modul-Global mehr; Broadcasts laufen über rt.connections.

# Routen werden auf einem APIRouter registriert, damit create_app(runtime) sie
# auf einer frischen, isolierten App montieren kann.
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Token zuerst bestimmen — die Origin-Policy braucht es fuer den 'null'-Sonderfall.
    # Als bytes vergleichen — compare_digest auf str wirft bei Nicht-ASCII.
    # E2-Zugriff (RFC-0002): Token/ws_clients/Warnings kommen aus der App-Runtime.
    rt = ws.app.state.runtime
    origin = ws.headers.get("origin")
    token = ws.query_params.get("token", "")
    token_valid = secrets.compare_digest(token.encode("utf-8"), rt.session_token.encode("utf-8"))

    # 1. Origin-Policy: lokale Origins immer; 'null' nur mit gueltigem Token
    #    (pywebview/WebView2-Sandbox); fremde/fehlende Origins abgelehnt.
    if not actions.is_origin_acceptable(origin, token_valid):
        obslog.event("ws.rejected", reason="bad_origin")
        await ws.close(code=1008)
        return

    # 2. Session-Token hart pruefen (schuetzt auch lokale Origins).
    if not token_valid:
        obslog.event("ws.rejected", reason="bad_token")
        await ws.close(code=1008)
        return

    # 3. Versionsaushandlung (RFC-0005 D4): angebotene Subprotokolle bestimmen den
    #    Protocol Context. Nur nicht unterstütztes jarvis.vN -> Ablehnung VOR accept
    #    (dort ist kein Error-Frame möglich, A1.C). Fehlt jarvis.v1 -> exakt Legacy.
    offered = ws.scope.get("subprotocols", [])
    neg = wp.negotiate_ws(offered)
    if neg.rejected:
        obslog.event("ws.rejected", reason="unsupported_version")
        await ws.close(code=1002)
        return

    await ws.accept(subprotocol=neg.accepted_subprotocol)
    # Verbindung in der Runtime-Registry anmelden: opake Session-ID statt str(id(ws));
    # Sendepfad via ConversationChannel (Send-Lock).
    channel, _accepted = rt.connections.register(ws.send_json, offered)
    session_id = channel.session_id
    obslog.event("ws.connected")

    # Sofortiger Health-Frame (spontan -> frische Server-Correlation-ID).
    await channel.emit(wp.Health(warnings=tuple(rt.startup_warnings)),
                       correlation_id=rt.wire_protocol.new_correlation_id())

    # Conversation-Zustand liegt seit RFC-0006 (Phase 4J) im runtime-eigenen
    # Session-Aggregat: Queue, aktiver Turn, Verlauf, offene Bestaetigung und der
    # Cancellation-Lifecycle sind PRIVATE Implementierung der Session. Dieser
    # Endpunkt ist nur noch Adapter — er kennt weder Queue noch Task noch Worker.
    # Origin/Token/Handshake/Frame-Groesse/Decode/ProtocolError bleiben hier
    # (RFC-0005-Transportgrenze, Praezisierung 8).
    async def _run_turn(ctx, text, correlation_id, sink):
        await assistant_core.process_message(
            ctx, text, sink, mutate_launcher=_launcher_hook(rt),
            capabilities=rt.capabilities)

    session = rt.conversation_manager.open(channel, run_turn=_run_turn)

    async def _v1_fault(code, message, close_code):
        if channel.ctx.is_v1:
            await channel.emit(
                wp.ErrorEvent(component="protocol", message=message, code=code),
                correlation_id=rt.wire_protocol.new_correlation_id())
        await ws.close(code=close_code)

    try:
        while True:
            raw = await ws.receive_text()
            # Frame-Größenvertrag (A1.C): 64 KiB eingehend, VOR dem JSON-Decoding.
            if len(raw.encode("utf-8")) > _MAX_WS_FRAME_BYTES:
                await _v1_fault("too_large", "Frame zu groß.", 1009)
                break
            try:
                data = json.loads(raw)
            except Exception:
                await _v1_fault("malformed_json", "Ungültiges JSON.", 1007)
                break
            cmd = rt.wire_protocol.decode_command(data, channel.ctx)

            # V1-Validierungsfehler: strukturierter Fehler; bei close_code die
            # Verbindung schließen, sonst offen bleiben (korrigierbarer Fehler).
            if isinstance(cmd, wp.ProtocolError):
                await channel.emit(
                    wp.ErrorEvent(component="protocol", message=cmd.message, hint=cmd.hint,
                                  code=cmd.code, retryable=cmd.retryable),
                    correlation_id=rt.wire_protocol.new_correlation_id())
                if cmd.close_code is not None:
                    await ws.close(code=cmd.close_code)
                    break
                continue

            # Stopp: explizites Stop-Command ODER ein Stop-Wort als SayText.
            is_stop = isinstance(cmd, wp.Stop) or (
                isinstance(cmd, wp.SayText) and actions.is_stop_command(cmd.text))
            if is_stop:
                obslog.event("message.stopped",
                             was_busy=not session.snapshot()["ready"])
                await session.submit(conversation.StopReceived(cmd.correlation_id))
                continue

            if not isinstance(cmd, wp.SayText):
                continue  # None (Legacy ignoriert) — kein Fehlerframe

            obslog.event("message.received", text_len=len(cmd.text))
            await session.submit(
                conversation.SayTextReceived(cmd.text, cmd.correlation_id))

    except WebSocketDisconnect:
        pass
    finally:
        # Disconnect: die Session bricht eine laufende Verarbeitung garantiert ab
        # und gibt ihre Ressourcen frei (kein Task-Leak pro Verbindung).
        await rt.conversation_manager.close(session)
        rt.connections.unregister(channel)


INDEX_PATH = os.path.join(os.path.dirname(__file__), "frontend", "index.html")


@router.get("/health")
async def health_endpoint(request: Request):
    """Passive Statusuebersicht fuer Launcher, Tests und Smoke-Test.

    'ok' heisst: der Server nimmt Verbindungen an. Einzeldienste stehen in
    'services'; es werden keine bezahlten APIs angefragt (kein Quota-Verbrauch).
    """
    rt = request.app.state.runtime
    return health.build_report(
        rt.configuration.snapshot().as_dict(), rt.startup_warnings,
        assistant_core.DATA_LOADED, assistant_core.LAST_REFRESH
    )


# ── REST-V1-Presentation (RFC-0005 §10, Slice 7) ─────────────────────────────
# Gemeinsamer REST-Seam als Response-Middleware: Legacy passiert byte-exakt (kein
# V1-Accept -> keine Umhüllung); V1 (Accept: application/vnd.jarvis.v1+json) wird in
# die V1-Envelope gehüllt + Correlation-Header gespiegelt; unbekannte Vendor-Version
# -> 406. HTTP-Status bleibt maßgeblich. session_id ist bei REST immer null.

_VENDOR_V1 = "application/vnd.jarvis.v1+json"
_MAX_WS_FRAME_BYTES = 64 * 1024      # A1.C: eingehender WS-JSON-Frame
_MAX_REST_BODY_BYTES = 1024 * 1024   # A1.C: V1-REST-Body
_CORR_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _rest_family(path: str):
    """Route-Familie -> (result_type, sensitivity) oder None (nicht abgedeckt)."""
    if path == "/health":
        return ("health", "public")
    if path == "/settings":
        return ("settings", "personal")
    if path == "/music/files":
        return ("music_files", "local")
    if path == "/music/selection":
        return ("music_selection", "local")
    if path == "/dashboard/state":
        return ("dashboard", "personal")
    if path == "/commands/app/open":
        return ("app_open", "local")
    if path.startswith("/launcher/"):
        return ("launcher", "local")
    return None


def _rest_correlation(request: Request):
    """Correlation pro Request: gültige Client-ID spiegeln, sonst serverseitig; auf
    request.state cachen, damit Broadcast-Route und Response-Envelope dieselbe nutzen."""
    existing = getattr(request.state, "correlation_id", None)
    if existing:
        return existing
    rt = request.app.state.runtime
    h = request.headers.get("x-jarvis-correlation-id")
    corr = h if (h and _CORR_RE.match(h)) else rt.wire_protocol.new_correlation_id()
    request.state.correlation_id = corr
    return corr


def _redact_health_v1(payload):
    """Öffentliche V1-Health-Projektion (D9): keine lokalen Pfade."""
    if not isinstance(payload, dict):
        return payload
    p = json.loads(json.dumps(payload))
    warnings = p.get("warnings", [])
    p["warnings_count"] = len(warnings) if isinstance(warnings, list) else 0
    p["warnings"] = []  # Warnungstexte können den Vault-Pfad enthalten
    services = p.get("services")
    if isinstance(services, dict) and isinstance(services.get("vault"), dict):
        vault = services["vault"]
        vault["detail"] = ("Vault erreichbar" if vault.get("ok")
                           else "Vault nicht erreichbar oder nicht konfiguriert")
    return p


class RestV1Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rt = request.app.state.runtime
        family = _rest_family(request.url.path)
        neg = wp.negotiate_rest(request.headers.get("accept", ""))
        corr = _rest_correlation(request)
        if family and neg.not_acceptable:
            env = rt.wire_protocol.rest_error(
                "not_acceptable", "Nicht unterstützte Protokoll-Repräsentation.",
                correlation_id=corr)
            return JSONResponse(env, status_code=406,
                                headers={"X-Jarvis-Correlation-ID": corr,
                                         "Content-Type": _VENDOR_V1})
        # Größenvertrag (A1.C): V1-Body > 1 MiB -> 413, VOR dem Route-Decoding.
        if family and neg.context.is_v1:
            try:
                clen = int(request.headers.get("content-length") or 0)
            except ValueError:
                clen = 0
            if clen > _MAX_REST_BODY_BYTES:
                env = rt.wire_protocol.rest_error(
                    "too_large", "Anfrage zu groß.", correlation_id=corr)
                return JSONResponse(env, status_code=413,
                                    headers={"X-Jarvis-Correlation-ID": corr,
                                             "Content-Type": _VENDOR_V1})
        response = await call_next(request)
        if not family or not neg.context.is_v1:
            return response  # Legacy exakt (keine Umhüllung)
        raw = b""
        async for chunk in response.body_iterator:
            raw += chunk
        try:
            payload = json.loads(raw) if raw else None
        except Exception:
            payload = None
        result_type, sensitivity = family
        if result_type == "health":
            payload = _redact_health_v1(payload)
        env = rt.wire_protocol.rest_envelope(result_type, sensitivity, payload,
                                             correlation_id=corr)
        return JSONResponse(env, status_code=response.status_code,
                            headers={"X-Jarvis-Correlation-ID": corr,
                                     "Content-Type": _VENDOR_V1})


# ── Settings-API ─────────────────────────────────────────────────────────────
# Editierbar ist nur die Whitelist aus config_loader.UI_EDITABLE_KEYS.
# API-Keys verlassen den Server nie und werden nie angenommen.

def _settings_token_ok(request: Request) -> bool:
    # E2-Zugriff (RFC-0002): Dep aus der App-Runtime, nicht aus einem Modul-Global —
    # damit ist die Token-Pruefung pro App-Instanz korrekt.
    token = request.headers.get("x-jarvis-token", "")
    expected = request.app.state.runtime.session_token
    return secrets.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))


def _configuration(request: Request):
    """Die Configuration der KONKRETEN App-Instanz (RFC-0003 D2) — nie ein Global."""
    return request.app.state.runtime.configuration


async def broadcast_health(rt):
    """Frische Warnings der App-Runtime an alle Clients — semantisches Health-Event,
    versionsabhängig pro Empfänger encodiert (RFC-0005 §20)."""
    await rt.connections.broadcast(wp.Health(warnings=tuple(rt.startup_warnings)))


def _live_apply(rt, merged: dict) -> bool:
    """NOTWENDIGES Live-Apply (RFC-0003 D9): deterministisch, ohne Netz/Broadcast.

    Laeuft INNERHALB der Transaktion — wirft es, stellt der Writer Datei und
    Snapshot wieder her. Gibt zurueck, ob ein Post-Commit-Refresh noetig ist.
    """
    needs_refresh = (
        merged.get("city", assistant_core.CITY) != assistant_core.CITY
        or merged.get("obsidian_inbox_path", memory.VAULT_PATH) != memory.VAULT_PATH
        or merged.get("obsidian_inbox_folder", memory.INBOX_PATH) != memory.INBOX_PATH
    )
    assistant_core.configure(merged)
    memory.configure(
        vault_path=merged.get("obsidian_inbox_path", ""),
        inbox_path=merged.get("obsidian_inbox_folder", ""),
    )
    app_launcher.configure(merged.get("apps", []), merged.get("launcher"))
    rt.startup_warnings = config_loader.check_runtime_environment(merged)
    return needs_refresh


async def _post_commit(rt, needs_refresh: bool) -> list[str]:
    """POST-COMMIT-Effekte (RFC-0003 D9): duerfen eine gueltig persistierte
    Configuration NIE zurueckrollen — ihr Fehler erzeugt einen Degraded-Zustand."""
    degraded: list[str] = []
    if needs_refresh:
        try:
            # wttr.in/Vault-Scan blockieren bis ~5s — nicht auf der Event-Loop.
            await asyncio.to_thread(assistant_core.refresh_data)
        except Exception as e:
            obslog.event("context.refresh_failed", stage="settings",
                         error_type=type(e).__name__)
            degraded.append("Kontextdaten (Wetter/Vault) konnten nicht neu geladen "
                            "werden — die Einstellungen sind gespeichert.")
    try:
        await broadcast_health(rt)
    except Exception as e:
        obslog.event("health.broadcast_failed", error_type=type(e).__name__)
    return degraded


@router.get("/settings")
async def get_settings(request: Request):
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    rt = request.app.state.runtime
    view = rt.configuration.settings_view()
    # Bestandsfelder unveraendert; 'revision' ist additiv (RFC-0003 §32).
    return {"ok": True, "settings": view["settings"], "warnings": rt.startup_warnings,
            "revision": view["revision"]}


@router.post("/settings")
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

    rt = request.app.state.runtime
    # If-Match ist OPTIONAL (Kompatibilitaet): fehlt er, wird gegen die frisch
    # gelesene Basis gearbeitet. Ist er vorhanden und ueberholt -> 409 (D6).
    expected = request.headers.get("if-match") or None
    needs_refresh = False

    def _apply(document):
        nonlocal needs_refresh
        needs_refresh = _live_apply(rt, document)

    try:
        await rt.configuration.mutate(
            configuration.SetSettings(updates), expected_revision=expected, apply=_apply)
    except configuration.ConfigConflict as e:
        return JSONResponse({"ok": False, "errors": [str(e)], "conflict": True},
                            status_code=409)
    except config_loader.ConfigError as e:
        # ConfigError-Meldungen nennen nur Schluesselnamen, nie Werte.
        return JSONResponse({"ok": False, "errors": [str(e)]}, status_code=500)

    degraded = await _post_commit(rt, needs_refresh)
    obslog.event("settings.saved", changed=len(updates))
    body = {"ok": True, "applied": sorted(updates.keys()),
            "warnings": rt.startup_warnings,
            "revision": rt.configuration.snapshot().revision}
    if degraded:
        body["degraded"] = degraded
    return body


# ── Musik-API ────────────────────────────────────────────────────────────────
# Gleiche Token-Sicherung wie /settings. Gespeichert wird NUR der Dateiname
# (config.selected_music_file); abgespielt wird ausschliesslich aus dem
# konfigurierten music_folder — launch-session.ps1 prueft beim Sessionstart
# nochmal Dateiname + .mp3 + Existenz (Defense-in-Depth).

def _scan_music_folder(folder: str) -> dict:
    """Listet ``.mp3``-Dateien im Musikordner, stabil alphabetisch (casefold).

    Kein Ordner konfiguriert -> ok mit leerer Liste (das UI zeigt den Hinweis);
    Ordner fehlt/nicht lesbar -> kontrollierter Fehler statt Crash. Pfade sind
    keine Secrets und duerfen in Meldungen genannt werden.
    """
    if not folder:
        return {"ok": True, "files": [], "error": ""}
    if not os.path.isdir(folder):
        return {"ok": False, "files": [], "error": f"Musikordner nicht gefunden: {folder}"}
    files = []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if not entry.is_file() or not entry.name.lower().endswith(".mp3"):
                    continue
                try:
                    stat = entry.stat()
                    files.append({"name": entry.name, "size": stat.st_size,
                                  "modified": stat.st_mtime})
                except OSError:
                    files.append({"name": entry.name, "size": None, "modified": None})
    except OSError as e:
        return {"ok": False, "files": [], "error": f"Musikordner konnte nicht gelesen werden: {e}"}
    files.sort(key=lambda f: f["name"].casefold())
    return {"ok": True, "files": files, "error": ""}


@router.get("/music/files")
async def music_files(request: Request):
    """MP3-Liste fuers Kontrollzentrum. HTTP 200 auch bei fehlendem Ordner —
    die Antwort ist ein Zustandsbericht (ok/error), kein Crash."""
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    document = _configuration(request).snapshot().as_dict()
    folder = document.get("music_folder", "")
    result = await asyncio.to_thread(_scan_music_folder, folder)
    return {
        "ok": result["ok"],
        "folder": folder,
        "selected": document.get("selected_music_file", ""),
        "files": result["files"],
        "error": result["error"],
    }


@router.post("/music/selection")
async def music_selection(request: Request):
    """MP3 fuer den naechsten Sessionstart waehlen ('' = abwaehlen).

    Validiert den Dateinamen (config_loader) UND die Existenz im Musikordner,
    speichert dann nur den Dateinamen und uebernimmt die Config live.
    """
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "errors": ["Ungültiges JSON."]}, status_code=400)
    file = body.get("file") if isinstance(body, dict) else None
    if not isinstance(file, str):
        return JSONResponse({"ok": False, "errors": ["Feld 'file' fehlt."]}, status_code=400)
    file = file.strip()
    # Format-Vorpruefung bleibt hier, damit ein reiner Formatfehler weiterhin 400
    # liefert. Die inhaltliche Pruefung (Ordner + Existenz) passiert INNERHALB der
    # Transaktion gegen denselben frisch gelesenen Snapshot (RFC-0003 Slice 3).
    errors = config_loader.validate_music_file_value(file)
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)

    rt = request.app.state.runtime
    needs_refresh = False

    def _apply(document):
        nonlocal needs_refresh
        needs_refresh = _live_apply(rt, document)

    try:
        await rt.configuration.mutate(configuration.SelectMusic(file), apply=_apply)
    except config_loader.ConfigError as e:
        # Ordner fehlt/Datei nicht gefunden -> wie bisher 400 (Nutzerfehler).
        message = str(e)
        status = 400 if ("Musikordner" in message or "Datei nicht" in message) else 500
        return JSONResponse({"ok": False, "errors": [message]}, status_code=status)
    await _post_commit(rt, needs_refresh)
    # Alle verbundenen Clients nachziehen (Muster: launcher_changed) —
    # Musikliste und "Nächste Musik"-Status bleiben ueberall synchron.
    await rt.connections.broadcast(wp.MusicChanged(selected=file),
                                   correlation_id=_rest_correlation(request))
    obslog.event("settings.saved", changed=1)
    return {"ok": True, "selected": file}


# ── Dashboard-/Command-API ───────────────────────────────────────────────────
# Gleiche Sicherheitslogik wie /settings: Session-Token im x-jarvis-token-Header.
# UI-Klicks und Sprach-Aktion (APP_OPEN) laufen beide ueber app_launcher.

@router.get("/dashboard/state")
def dashboard_state(request: Request):
    """Daten fuer das Command Center (Fokus-Modus). Sync def → Threadpool,
    da health.build_report Datei-/Pfad-Checks macht. Nutzt die gecachten
    Kontextdaten aus assistant_core (kein Vault-Scan pro Aufruf)."""
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    return {
        "ok": True,
        "health": health.build_report(
            request.app.state.runtime.configuration.snapshot().as_dict(),
            request.app.state.runtime.startup_warnings,
            assistant_core.DATA_LOADED, assistant_core.LAST_REFRESH
        ),
        "tasks": assistant_core.TASKS_INFO,
        "today_inbox": assistant_core.TODAY_INBOX,
        "vault": assistant_core.VAULT_SUMMARY,
        "apps": app_launcher.list_apps(),
        "data_loaded": assistant_core.DATA_LOADED,
        "last_refresh": assistant_core.LAST_REFRESH,
    }


@router.post("/commands/app/open")
async def command_app_open(request: Request):
    """App aus der Registry starten (UI-Klick) — dieselbe Allowlist wie APP_OPEN."""
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "errors": ["Ungültiges JSON."]}, status_code=400)
    app_query = body.get("app") if isinstance(body, dict) else None
    if not isinstance(app_query, str) or not app_query.strip():
        return JSONResponse({"ok": False, "errors": ["Feld 'app' fehlt."]}, status_code=400)

    result = await asyncio.to_thread(app_launcher.launch, app_query)
    await request.app.state.runtime.connections.broadcast(
        wp.AppEvent(ok=result["ok"], app=result["app"], name=result["name"],
                    message=result["message"]),
        correlation_id=_rest_correlation(request))
    status_code = 200 if result["ok"] else (404 if result["app"] is None else 500)
    return JSONResponse(result, status_code=status_code)


# ── Launcher-API ─────────────────────────────────────────────────────────────
# Session-Profile: autostart/placement pro App leben im aktiven Profil
# (config.launcher); launch-session.ps1 startet das aktive Profil.
# Gleiche Token-Sicherung wie /settings; ``command`` verlaesst den Server nie.

async def persist_launcher_intent(rt, intent, kind: str, correlation_id=None) -> list[str]:
    """Kern-Persistenz fuer Endpunkte UND Sprach-Aktionen (RFC-0003 Slice 4).

    Nimmt eine SEMANTISCHE Aenderungsabsicht (kein vorberechneter Voll-Block) und
    laesst sie vom Single Writer gegen die FRISCHE Basis anwenden: live anwenden →
    WS-Event ``launcher_changed`` (Fokus-UI zieht Profile/Toggles/Map nach).
    Leere Liste = ok, sonst lesbare deutsche Fehler.
    """
    needs_refresh = False

    def _apply(document):
        nonlocal needs_refresh
        needs_refresh = _live_apply(rt, document)

    try:
        await rt.configuration.mutate(intent, apply=_apply)
    except configuration.ConfigConflict as e:
        return [str(e)]
    except config_loader.ConfigError as e:
        return [str(e)]
    await _post_commit(rt, needs_refresh)
    await rt.connections.broadcast(
        wp.LauncherChanged(kind=kind, active_profile=app_launcher.ACTIVE_PROFILE),
        correlation_id=correlation_id)
    return []


def _launcher_hook(rt):
    """Request-spezifischer semantischer Mutationshook fuer den ActionContext.

    Wird pro WS-Nachricht aus der Runtime der KONKRETEN App erzeugt (RFC-0003):
    ``actions``/``assistant_core`` bleiben dadurch frei von Runtime-/Server-
    Abhaengigkeiten.
    """
    async def _mutate(intent, kind: str) -> list[str]:
        return await persist_launcher_intent(rt, intent, kind)
    return _mutate


async def _persist_launcher(rt, intent, kind: str, correlation_id=None):
    """Endpunkt-Wrapper: Fehler des Persist-Kerns als JSONResponse (500)."""
    errors = await persist_launcher_intent(rt, intent, kind, correlation_id)
    if errors:
        return None, JSONResponse({"ok": False, "errors": errors}, status_code=500)
    return True, None


def _profiles_response() -> dict:
    """Einheitliche Antwort der Profil-Endpunkte: Profile + effective Apps."""
    return {
        "ok": True,
        "active_profile": app_launcher.ACTIVE_PROFILE,
        "profiles": app_launcher.serialize_launcher()["profiles"],
        "apps": app_launcher.list_apps(),
    }


@router.get("/launcher/apps")
async def launcher_list_apps(request: Request):
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    return {"ok": True, "active_profile": app_launcher.ACTIVE_PROFILE,
            "apps": app_launcher.list_apps()}


@router.post("/launcher/apps/{app_id}/toggle")
async def launcher_toggle_autostart(app_id: str, request: Request):
    """Autostart einer bekannten App setzen — expliziter Boolean statt Flip,
    damit wiederholte Requests idempotent sind (kein Lost-Update)."""
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "errors": ["Ungültiges JSON."]}, status_code=400)
    value = body.get("autostart") if isinstance(body, dict) else None
    if not isinstance(value, bool):
        return JSONResponse(
            {"ok": False, "errors": ["Feld 'autostart' muss true oder false sein."]},
            status_code=400,
        )

    if app_launcher.find_app(app_id) is None:
        return JSONResponse({"ok": False, "errors": ["Unbekannte App."]}, status_code=404)
    _merged, err = await _persist_launcher(
        request.app.state.runtime, configuration.SetAutostart(app_id, value), "autostart", _rest_correlation(request))
    if err is not None:
        return err
    obslog.event("autostart.changed", app=app_id, enabled=value)
    return {"ok": True, "apps": app_launcher.list_apps()}


@router.get("/launcher/monitors")
async def launcher_list_monitors(request: Request):
    """Physische Monitore fuer die Monitor-Map. Leere Liste = Erkennung
    fehlgeschlagen -> das Frontend zeigt die virtuelle Standardansicht."""
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    return {"ok": True, "monitors": monitors.detect_monitors()}


@router.post("/launcher/apps/{app_id}/placement")
async def launcher_set_placement(app_id: str, request: Request):
    """Monitor/Zone einer bekannten App setzen — beide Felder sind Pflicht,
    damit wiederholte Requests idempotent sind (kein Lost-Update).
    launch-session.ps1 wendet die Platzierung beim naechsten Sessionstart an."""
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "errors": ["Ungültiges JSON."]}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "errors": ["'placement' muss ein Objekt sein."]},
                            status_code=400)
    errors = [f"Feld '{field}' fehlt." for field in ("monitor", "zone") if field not in body]
    errors.extend(config_loader.validate_placement_value(body))
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=400)

    if app_launcher.find_app(app_id) is None:
        return JSONResponse({"ok": False, "errors": ["Unbekannte App."]}, status_code=404)
    _merged, err = await _persist_launcher(
        request.app.state.runtime,
        configuration.SetPlacement(app_id, body["monitor"], body["zone"]), "placement", _rest_correlation(request))
    if err is not None:
        return err
    # Zu diesem Zeitpunkt sind monitor/zone Allowlist-Konstanten, keine Nutzerdaten.
    obslog.event("placement.changed", app=app_id,
                 monitor=body["monitor"], zone=body["zone"])
    return {"ok": True, "apps": app_launcher.list_apps()}


# ── Profil-API ───────────────────────────────────────────────────────────────
# Session-Profile verwalten. Antworten einheitlich via _profiles_response().

async def _read_body(request: Request):
    """JSON-Body lesen; (body, fehler_response)."""
    try:
        body = await request.json()
    except Exception:
        return None, JSONResponse({"ok": False, "errors": ["Ungültiges JSON."]}, status_code=400)
    if not isinstance(body, dict):
        return None, JSONResponse({"ok": False, "errors": ["Body muss ein Objekt sein."]},
                                  status_code=400)
    return body, None


def _profile_name_from(body: dict):
    """(name, fehler_response) — 'name' ist bei allen Profil-Mutationen Pflicht."""
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, JSONResponse({"ok": False, "errors": ["Feld 'name' fehlt."]}, status_code=400)
    return name.strip(), None


@router.get("/launcher/profiles")
async def launcher_list_profiles(request: Request):
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    return _profiles_response()


@router.post("/launcher/profiles")
async def launcher_create_profile(request: Request):
    """Neues Profil mit Defaults (alle Apps autostart:true, keine Placements).
    Aktiviert bewusst NICHT — anlegen ist nicht wechseln."""
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    body, err = await _read_body(request)
    if err is not None:
        return err
    name, err = _profile_name_from(body)
    if err is not None:
        return err
    intent = configuration.CreateProfile(body.get("id"), name)
    if intent.validate(request.app.state.runtime.configuration.snapshot().as_dict()):
        return JSONResponse({"ok": False, "errors": ["Profil-ID bereits vergeben oder ungültig."]},
                            status_code=400)
    _merged, err = await _persist_launcher(request.app.state.runtime, intent, "profile", _rest_correlation(request))
    if err is not None:
        return err
    obslog.event("profile.changed", kind="created", active=app_launcher.ACTIVE_PROFILE)
    return _profiles_response()


@router.post("/launcher/profiles/{profile_id}/activate")
async def launcher_activate_profile(profile_id: str, request: Request):
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    if app_launcher.find_profile(profile_id) is None:
        return JSONResponse({"ok": False, "errors": ["Unbekanntes Profil."]}, status_code=404)
    _merged, err = await _persist_launcher(
        request.app.state.runtime, configuration.ActivateProfile(profile_id), "profile", _rest_correlation(request))
    if err is not None:
        return err
    obslog.event("profile.changed", kind="activated", active=app_launcher.ACTIVE_PROFILE)
    return _profiles_response()


@router.post("/launcher/profiles/{profile_id}/duplicate")
async def launcher_duplicate_profile(profile_id: str, request: Request):
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    if not app_launcher.profile_exists(profile_id):
        return JSONResponse({"ok": False, "errors": ["Unbekanntes Profil."]}, status_code=404)
    body, err = await _read_body(request)
    if err is not None:
        return err
    name, err = _profile_name_from(body)
    if err is not None:
        return err
    intent = configuration.DuplicateProfile(profile_id, body.get("id"), name)
    if intent.validate(request.app.state.runtime.configuration.snapshot().as_dict()):
        return JSONResponse({"ok": False, "errors": ["Profil-ID bereits vergeben oder ungültig."]},
                            status_code=400)
    _merged, err = await _persist_launcher(request.app.state.runtime, intent, "profile", _rest_correlation(request))
    if err is not None:
        return err
    obslog.event("profile.changed", kind="duplicated", active=app_launcher.ACTIVE_PROFILE)
    return _profiles_response()


@router.post("/launcher/profiles/{profile_id}/rename")
async def launcher_rename_profile(profile_id: str, request: Request):
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    body, err = await _read_body(request)
    if err is not None:
        return err
    name, err = _profile_name_from(body)
    if err is not None:
        return err
    if app_launcher.find_profile(profile_id) is None:
        return JSONResponse({"ok": False, "errors": ["Unbekanntes Profil."]}, status_code=404)
    # REST-Pilot (RFC-0007 Slice 8): ueber DENSELBEN Coordinator, Provenance operator.
    # Keine direkte Mutationsumgehung — die Persistenz laeuft im Capability-Execute
    # ausschliesslich ueber configuration.mutate (einziger Writer). Status/Body/Broadcast
    # bleiben byte-/shape-identisch.
    rt = request.app.state.runtime
    outcome = await rt.capabilities.attempt(
        capability.CapabilityRequest(
            "launcher.profile.rename", capability.Provenance.OPERATOR,
            {"profile_id": profile_id, "name": name}),
        capability.Evidence(),
        meta={"correlation_id": _rest_correlation(request)})
    if outcome.status is not capability.OutcomeStatus.OK:
        return JSONResponse({"ok": False, "errors": ["Profil-Aktion fehlgeschlagen."]},
                            status_code=500)
    errors = list(outcome.value["errors"])
    if errors:
        return JSONResponse({"ok": False, "errors": errors}, status_code=500)
    obslog.event("profile.changed", kind="renamed", active=app_launcher.ACTIVE_PROFILE)
    return _profiles_response()


@router.delete("/launcher/profiles/{profile_id}")
async def launcher_delete_profile(profile_id: str, request: Request):
    if not _settings_token_ok(request):
        return JSONResponse({"ok": False, "errors": ["Nicht autorisiert."]}, status_code=403)
    if app_launcher.find_profile(profile_id) is None:
        return JSONResponse({"ok": False, "errors": ["Unbekanntes Profil."]}, status_code=404)
    intent = configuration.DeleteProfile(profile_id)
    guards = intent.validate(request.app.state.runtime.configuration.snapshot().as_dict())
    if guards:
        return JSONResponse({"ok": False, "errors": guards}, status_code=400)
    _merged, err = await _persist_launcher(request.app.state.runtime, intent, "profile", _rest_correlation(request))
    if err is not None:
        return err
    obslog.event("profile.changed", kind="deleted", active=app_launcher.ACTIVE_PROFILE)
    return _profiles_response()


@router.get("/")
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


# ── App-Factory + Lifespan (Composition Root) ───────────────────────────────

@contextlib.asynccontextmanager
async def _server_lifespan(app):
    """Öffnet/schließt die Ressourcen der App-Runtime und spiegelt die
    A6-Residual-Modul-Globals (config/CONFIG_PATH/STARTUP_WARNINGS) + per-App
    session_token/ws_clients aus der aktiven Runtime — Routen/Helfer lesen diese."""
    _configure_logging()   # uvicorn-Weg: erst hier, nicht beim Import (D9)
    rt = app.state.runtime
    await rt.aopen()
    global SESSION_TOKEN
    SESSION_TOKEN = rt.session_token
    if rt.startup_warnings:
        # Warnungstexte enthalten lokale Pfade -> nur die Anzahl loggen (D3).
        obslog.event("config.startup_degraded", count=len(rt.startup_warnings))
    try:
        yield
    finally:
        await rt.aclose()


def create_app(rt: runtime_mod.Runtime) -> FastAPI:
    """Reine, seiteneffektfreie Verdrahtung: App + Lifespan + Routen + Static.
    Config/Clients öffnen erst im Lifespan (rt.aopen)."""
    app = FastAPI(lifespan=_server_lifespan)
    app.state.runtime = rt
    # Launcher-Persist in die Runtime injizieren (RFC-0007 §17, Slice 8): der
    # Capability-Kernel fuehrt REST-Wirkungen ueber DIESE Orchestrierung aus, ohne
    # dass ``capability`` ``server`` importiert (keine Zyklus-/Locator-Kopplung).
    rt.configure_launcher_persist(persist_launcher_intent)
    app.add_middleware(RestV1Middleware)   # REST-V1-Presentation (Legacy passiert exakt)
    app.include_router(router)
    app.mount("/static", StaticFiles(
        directory=os.path.join(os.path.dirname(__file__), "frontend")), name="static")
    return app


# Produktions-App (import-sicher: die Runtime ist ungeöffnet — keine Config/Clients).
app = create_app(runtime)


if __name__ == "__main__":
    import uvicorn
    _configure_logging()   # direkter Startweg: VOR Config-Load/moeglichem Fehler
    # Fail-fast: ohne gültige Config gar nicht starten (Launcher-„exited"-Signal
    # bleibt erhalten). Dieser Config-Load ist der explizite Produktions-Check;
    # der Lifespan (aopen) lädt sie dann nicht erneut.
    try:
        runtime.load_config()
    except config_loader.ConfigError as e:
        obslog.event("config.startup_failed", error_type=type(e).__name__)
        print("  Konfigurationsfehler — bitte config.json pruefen.", flush=True)
        sys.exit(1)
    print("=" * 50, flush=True)
    print("  J.A.R.V.I.S. V2 Server", flush=True)
    print(f"  http://localhost:8340", flush=True)
    print("=" * 50, flush=True)
    if runtime.startup_warnings:
        # Details stehen im Kontrollzentrum; hier keine (pfadhaltigen) Rohtexte in
        # das von jarvis-launcher.log erfasste stdout schreiben (D3).
        print(f"  {len(runtime.startup_warnings)} Startup-Warnung(en) — "
              "Details im Kontrollzentrum.", flush=True)
    # Nur lokal binden — nicht im LAN erreichbar.
    # log_config=None: uvicorn installiert KEINE eigene Logging-Konfiguration und
    # ueberschreibt damit unsere Sinks nicht (Slice 5 schuetzt uvicorns Logger).
    uvicorn.run(app, host="127.0.0.1", port=8340, log_config=None)

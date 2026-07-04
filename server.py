"""
Jarvis V2 — Voice AI Server
FastAPI backend: receives speech text, thinks with Claude Haiku,
speaks with ElevenLabs, controls browser with Playwright.
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import asyncio
import base64
import json
import logging
import os
import re
import secrets
import time

import anthropic
import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

import actions
import config_loader

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

ANTHROPIC_API_KEY = config["anthropic_api_key"]
ELEVENLABS_API_KEY = config["elevenlabs_api_key"]
ELEVENLABS_VOICE_ID = config.get("elevenlabs_voice_id", "rDmv3mOhK6TnhYWckFaD")
USER_NAME = config.get("user_name", "Jan")
USER_ADDRESS = config.get("user_address", USER_NAME)
USER_ROLE = config.get("user_role", "")
CITY = config.get("city", "Hamburg")
TASKS_FILE = config.get("obsidian_inbox_path", "")
INBOX_PATH = config.get("obsidian_inbox_folder", "")

# Timeout + Retries SDK-nativ — gilt fuer alle Claude-Calls inkl. Vision.
ai = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, timeout=30.0, max_retries=2)
http = httpx.AsyncClient(timeout=30)

app = FastAPI()

import browser_tools
import clipboard_tools
import screen_capture

# Chromium beim Server-Stopp mit beenden.
app.router.on_shutdown.append(browser_tools.close)


def get_weather_sync():
    """Fetch raw weather data (2 Versuche, je 5s Timeout)."""
    import urllib.request
    for attempt in range(2):
        try:
            req = urllib.request.Request(f"https://wttr.in/{CITY}?format=j1", headers={"User-Agent": "curl"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            c = data["current_condition"][0]
            return {
                "temp": c["temp_C"],
                "feels_like": c["FeelsLikeC"],
                "description": c["weatherDesc"][0]["value"],
                "humidity": c["humidity"],
                "wind_kmh": c["windspeedKmph"],
            }
        except Exception:
            if attempt == 0:
                logger.warning("Wetterabruf fehlgeschlagen — zweiter Versuch")
                time.sleep(1)
            else:
                logger.warning("Wetterabruf fehlgeschlagen", exc_info=True)
    return None


def get_tasks_sync():
    """Read open tasks from Obsidian (sync)."""
    if not TASKS_FILE:
        return []
    try:
        tasks_path = os.path.join(TASKS_FILE, "Tasks.md")
        with open(tasks_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.strip().replace("- [ ]", "").strip() for l in lines if l.strip().startswith("- [ ]")]
    except Exception:
        logger.warning("Tasks konnten nicht gelesen werden", exc_info=True)
        return []


def _today_inbox_file() -> str:
    """Pfad der heutigen Brain-Dump-Datei (Inbox)."""
    return os.path.join(INBOX_PATH, f"{time.strftime('%Y-%m-%d')} Brain Dump.md")


def read_today_inbox_sync(max_chars: int = 3000) -> str | None:
    """Heutige Inbox-Einträge lesen; None wenn nicht konfiguriert oder noch leer."""
    if not INBOX_PATH or not os.path.isdir(INBOX_PATH):
        return None
    file_path = _today_inbox_file()
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()[:max_chars]
    except OSError:
        logger.warning("Inbox konnte nicht gelesen werden", exc_info=True)
        return None


def _walk_vault_md(vault_path: str) -> list[tuple[float, str, str]]:
    """Alle .md-Dateien im Vault als (mtime, pfad, name) — versteckte Ordner ausgenommen."""
    results = []
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.endswith('.md'):
                path = os.path.join(root, f)
                results.append((os.path.getmtime(path), path, f[:-3]))
    return results


def get_vault_summary_sync():
    """Scan Obsidian vault: note count by folder + recently modified notes."""
    vault_path = config.get("obsidian_inbox_path", "")
    if not vault_path or not os.path.isdir(vault_path):
        return None
    try:
        entries = _walk_vault_md(vault_path)
        folder_counts = {}
        for _, path, _ in entries:
            parts = os.path.relpath(path, vault_path).split(os.sep)
            if len(parts) > 1:
                folder_counts[parts[0]] = folder_counts.get(parts[0], 0) + 1
        entries.sort(reverse=True)
        return {
            "total": sum(folder_counts.values()),
            "by_folder": dict(sorted(folder_counts.items(), key=lambda x: x[1], reverse=True)),
            "recent": [name for _, _, name in entries[:5]],
        }
    except Exception:
        logger.warning("Vault-Zusammenfassung fehlgeschlagen", exc_info=True)
        return None


def read_recent_notes_sync(n: int = 5, chars_per_note: int = 1500) -> str:
    """Inhalt der zuletzt geänderten Notizen — Grundlage für 'Fasse meine letzten Notizen zusammen'."""
    vault_path = config.get("obsidian_inbox_path", "")
    if not vault_path or not os.path.isdir(vault_path):
        return ""
    try:
        entries = _walk_vault_md(vault_path)
    except Exception:
        logger.warning("Vault-Scan fehlgeschlagen", exc_info=True)
        return ""
    entries.sort(reverse=True)
    parts = []
    for mtime, path, name in entries[:n]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()[:chars_per_note]
        except OSError:
            continue
        datum = time.strftime("%d.%m.%Y %H:%M", time.localtime(mtime))
        parts.append(f"Notiz: {name} (geändert {datum})\n{content}")
    return "\n\n---\n\n".join(parts)


def refresh_data():
    """Refresh weather, tasks, vault summary and today's inbox."""
    global WEATHER_INFO, TASKS_INFO, VAULT_SUMMARY, TODAY_INBOX, DATA_LOADED, LAST_REFRESH
    WEATHER_INFO = get_weather_sync()
    TASKS_INFO = get_tasks_sync()
    VAULT_SUMMARY = get_vault_summary_sync()
    TODAY_INBOX = read_today_inbox_sync(max_chars=800)
    DATA_LOADED = True
    LAST_REFRESH = time.time()
    logger.info("Wetter geladen: %s", "ja" if WEATHER_INFO else "nein")
    logger.info("Tasks geladen: %d", len(TASKS_INFO))
    logger.info("Vault: %s Notizen", VAULT_SUMMARY['total'] if VAULT_SUMMARY else "n/a")
    logger.info("Heutige Inbox: %s", "vorhanden" if TODAY_INBOX else "leer")

WEATHER_INFO = ""
TASKS_INFO = []
VAULT_SUMMARY = None
TODAY_INBOX = None
DATA_LOADED = False
LAST_REFRESH: float | None = None


async def _startup_refresh():
    # Kontextdaten (Wetter/Tasks/Vault) im Hintergrund laden — der Server nimmt
    # sofort Verbindungen an. build_system_prompt toleriert noch fehlende Daten.
    # Tests/Smoke-Test setzen JARVIS_SKIP_STARTUP_REFRESH, um echte Netz-/
    # Dateisystemzugriffe zu vermeiden.
    if os.environ.get("JARVIS_SKIP_STARTUP_REFRESH"):
        return
    asyncio.get_running_loop().create_task(asyncio.to_thread(refresh_data))

app.router.on_startup.append(_startup_refresh)

conversations: dict[str, list] = {}

# Riskante Aktionen (actions.CONFIRM_ACTIONS), die auf ein mündliches Ja warten.
pending_confirm: dict[str, actions.Action] = {}

# Verbundene WS-Clients — fuer Push-Updates (z.B. frische Warnings nach Settings-Save).
ws_clients: set[WebSocket] = set()

def build_system_prompt():
    weather_block = ""
    if WEATHER_INFO:
        w = WEATHER_INFO
        weather_block = f"\nWetter {CITY}: {w['temp']}°C, gefuehlt {w['feels_like']}°C, {w['description']}"

    task_block = ""
    if TASKS_INFO:
        task_block = f"\nOffene Aufgaben ({len(TASKS_INFO)}): " + ", ".join(TASKS_INFO[:5])

    vault_block = ""
    if VAULT_SUMMARY:
        v = VAULT_SUMMARY
        top_folders = ", ".join(f"{k} ({n})" for k, n in list(v["by_folder"].items())[:4])
        recent_notes = ", ".join(v["recent"][:3])
        vault_block = f"\nObsidian-Vault: {v['total']} Notizen. Bereiche: {top_folders}. Zuletzt bearbeitet: {recent_notes}"

    inbox_block = ""
    if TODAY_INBOX:
        inbox_block = f"\nHeutige Inbox-Eintraege:\n{TODAY_INBOX}"

    role_part = f", {USER_ROLE}" if USER_ROLE else ""
    return f"""Du bist Jarvis, der persoenliche KI-Assistent von {USER_NAME}{role_part}. Du sprichst ausschliesslich Deutsch. {USER_NAME} moechte geduzt und mit "{USER_ADDRESS}" angesprochen werden — nutze "du" als Pronomen (z.B. "Klar, {USER_ADDRESS}, ich schau mir das an."). Du bist ein kompetenter Kollege und Gespraechspartner auf Augenhoehe: freundlich, direkt, professionell und assistenzorientiert — wie ein smarter Arbeitskollege oder persoenlicher Mitarbeiter. Du redest klar und ohne Umschweife, denkst mit und bringst eigene Vorschlaege ein, ohne belehrend zu wirken. Kein Sarkasmus, keine Butler-Attituede, keine gekuenstelte Foermlichkeit. Du bist effizient und einen Schritt voraus, aber immer auf Augenhoehe. Halte deine Antworten kurz — maximal 3 Saetze (einzige Ausnahme: der Tagesueberblick bei "Jarvis activate"). Wiederhole NIEMALS etwas, das bereits in diesem Gespraech gesagt wurde, es sei denn, {USER_ADDRESS} fragt explizit danach. Vault-Inhalte oder fruehere Antworten fasst du NUR zusammen wenn {USER_ADDRESS} ausdruecklich danach fragt.

WICHTIG: Schreibe NIEMALS Regieanweisungen, Emotionen oder Tags in eckigen Klammern wie [freundlich] [formal] [amused] oder aehnliches. Alles was du schreibst wird laut vorgelesen — dein Ton entsteht rein durch die Wortwahl.

Du hast die volle Kontrolle ueber den Browser von {USER_NAME}. Du kannst im Internet suchen, Webseiten oeffnen und den Bildschirm sehen. Wenn {USER_ADDRESS} dich bittet etwas nachzuschauen, zu recherchieren, zu googeln, eine Seite zu oeffnen, oder irgendetwas im Internet zu tun — nutze IMMER eine Aktion. Frag nicht ob du es tun sollst, tu es einfach.

AKTIONEN - Schreibe die passende Aktion ans ENDE deiner Antwort. Der Text VOR der Aktion wird vorgelesen, die Aktion selbst wird still ausgefuehrt. Maximal EINE Aktion pro Antwort.
[ACTION:SEARCH] suchbegriff - Schnelle Websuche: erstes Ergebnis lesen und zusammenfassen. Fuer einfache Fakten.
[ACTION:RESEARCH] thema - Gruendliche Recherche: liest 3-5 Quellen und liefert eine Zusammenfassung mit Quellenliste. Nutze wenn {USER_ADDRESS} "recherchiere" sagt oder eine fundierte Antwort mit mehreren Quellen sinnvoll ist.
[ACTION:OPEN] url - URL im Browser oeffnen
[ACTION:SCREEN] optionale frage - Bildschirm ansehen. Ohne Frage: kurz beschreiben. Mit Frage (z.B. "Was ist das Problem?", "Fasse diese Seite zusammen", "Was soll ich als naechstes tun?"): die Frage anhand des Bildschirms beantworten. WICHTIG: Bei SCREEN schreibe KEINEN Text vor die Aktion.
[ACTION:NEWS] - Aktuelle Weltnachrichten abrufen. Nutze diese Aktion wenn nach News, Nachrichten, was in der Welt passiert, aktuelle Lage oder Weltgeschehen gefragt wird. Schreibe einen kurzen Satz davor wie "Ich schaue nach den aktuellen Nachrichten."
[ACTION:INBOX_READ] - Liest die heutigen Eintraege aus der Obsidian-Inbox. Nutze wenn {USER_ADDRESS} fragt was heute notiert wurde oder einen Tagesrueckblick moechte.
[ACTION:INBOX_WRITE] [Kategorie] text - Schreibt einen Eintrag in die heutige Inbox-Datei. Kategorie ist GENAU EINE von: Idee, Aufgabe, Termin, Recherche, Erinnerung — waehle die passendste. Beispiel: [ACTION:INBOX_WRITE] [Termin] Zahnarzt Dienstag 9 Uhr. Nutze IMMER wenn {USER_ADDRESS} etwas festhalten, notieren, aufschreiben oder merken moechte. Frag nicht ob, tu es einfach. Formuliere den Text klar und strukturiert.
[ACTION:NOTES_RECENT] - Fasst die zuletzt bearbeiteten Notizen aus dem Vault zusammen. Nutze wenn {USER_ADDRESS} z.B. "Fasse meine letzten Notizen zusammen" sagt oder wissen will woran er zuletzt gearbeitet hat.
[ACTION:CLIPBOARD] auftrag - Verarbeitet den Text in der Zwischenablage (auftrag z.B. "zusammenfassen", "uebersetzen", "erklaeren"). Nutze wenn {USER_ADDRESS} von Zwischenablage, Clipboard oder "das Kopierte" spricht.
[ACTION:CLIPBOARD_NOTE] - Speichert den Text aus der Zwischenablage als Inbox-Notiz. Nutze wenn {USER_ADDRESS} aus der Zwischenablage eine Notiz machen moechte.
[ACTION:SESSION_SUMMARY] - Fasst zusammen was in dieser Sitzung besprochen und erledigt wurde. Nutze bei "Was haben wir heute gemacht?" oder am Sitzungsende. Moechte {USER_ADDRESS} das Fazit danach speichern, nutze INBOX_WRITE.

WENN {USER_NAME} "Jarvis activate" sagt, liefere den Tagesueberblick (maximal 6 Saetze):
- Begruesse ihn kreativ und passend zur Tageszeit (aktuelle Zeit: {{time}}).
- Wetter in einem Satz: Temperatur, ob Sonne/klar/bewoelkt/Regen, und wie es sich anfuehlt. Keine Luftfeuchtigkeit.
- Falls heute schon Inbox-Eintraege existieren: nenne sie knapp nach Kategorien gruppiert.
- Fasse die offenen Aufgaben als Ueberblick in einem Satz zusammen, ohne jede einzelne vorzulesen.
- Nenne in einem Satz die zuletzt bearbeiteten Notizen als Hinweis, woran {USER_ADDRESS} zuletzt gearbeitet hat.

=== AKTUELLE DATEN ==={weather_block}{task_block}{vault_block}{inbox_block}
==="""


def get_system_prompt():
    return build_system_prompt().replace("{time}", time.strftime("%H:%M"))


def strip_action(text: str) -> str:
    """Entfernt einen etwaigen Action-Tag aus Text (z.B. aus Zusammenfassungen)."""
    spoken, _, _ = actions.parse_action(text)
    return spoken


async def synthesize_speech(text: str) -> tuple[bytes, str | None]:
    """Erzeugt TTS-Audio. Gibt (audio, fehlergrund) zurück — fehlergrund ist ein
    kurzer, nutzertauglicher Hinweis wenn KEIN Audio erzeugt werden konnte."""
    if not text.strip():
        return b"", None

    # Split long text into chunks at sentence boundaries to avoid ElevenLabs cutoff
    chunks = []
    if len(text) > 250:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        current = ""
        for s in sentences:
            if len(current) + len(s) > 250 and current:
                chunks.append(current.strip())
                current = s
            else:
                current = (current + " " + s).strip()
        if current:
            chunks.append(current.strip())
    else:
        chunks = [text]

    audio_parts = []
    error: str | None = None
    # Eigener Timeout pro Request (statt Client-Default 30s); 1 Retry pro Chunk,
    # aber nur bei Netzwerkfehlern/5xx — 4xx (Key/Voice/Quota) ist nicht transient.
    tts_timeout = httpx.Timeout(20.0, connect=5.0)
    for chunk in chunks:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        for attempt in range(2):
            try:
                resp = await http.post(url, headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                }, json={
                    "text": chunk,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.85},
                }, timeout=tts_timeout)
            except Exception:
                logger.warning("TTS-Aufruf fehlgeschlagen (Versuch %d)", attempt + 1, exc_info=True)
                error = "Netzwerkfehler zu ElevenLabs."
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                break
            logger.debug("TTS chunk status: %s, size: %d", resp.status_code, len(resp.content))
            if resp.status_code == 200:
                audio_parts.append(resp.content)
                break
            logger.warning("TTS-Fehler (Status %s): %s", resp.status_code, resp.text[:200])
            if resp.status_code in (401, 403):
                error = f"ElevenLabs-Status {resp.status_code} — API-Key prüfen."
                break
            elif resp.status_code == 404:
                error = "ElevenLabs-Status 404 — Voice-ID prüfen."
                break
            elif resp.status_code == 429:
                error = "ElevenLabs-Kontingent oder Rate-Limit erreicht."
                break
            else:
                error = f"ElevenLabs-Status {resp.status_code}."
                if attempt == 0 and resp.status_code >= 500:
                    await asyncio.sleep(0.5)
                    continue
                break

    audio = b"".join(audio_parts)
    if audio:
        error = None  # Teil-Erfolg reicht — kein Fehler melden
    return audio, error


async def send_error(ws: WebSocket, component: str, text: str, hint: str = ""):
    """Strukturierter Fehler ans Frontend: component ∈ {llm, tts, browser, action, config}."""
    await ws.send_json({"type": "error", "component": component, "text": text, "hint": hint})


async def send_spoken_response(ws: WebSocket, text: str, display_text: str | None = None):
    """Antwort mit TTS senden; bei komplettem TTS-Ausfall zusätzlich einen tts-Fehler melden.

    ``display_text`` erlaubt eine längere Anzeige-Version (z.B. mit Quellen-URLs),
    während nur ``text`` vorgelesen wird.
    """
    audio, tts_err = await synthesize_speech(text)
    logger.debug("Audio bytes: %d", len(audio))
    await ws.send_json({
        "type": "response",
        "text": display_text or text,
        "audio": base64.b64encode(audio).decode("utf-8") if audio else "",
    })
    if not audio and tts_err:
        await send_error(ws, "tts", "Sprachausgabe fehlgeschlagen — Antwort wird nur als Text angezeigt.", tts_err)


ACTION_LABELS = {
    "SEARCH": "Websuche",
    "BROWSE": "Seite lesen",
    "OPEN": "Browser öffnen",
    "SCREEN": "Bildschirm ansehen",
    "NEWS": "Nachrichten",
    "INBOX_READ": "Inbox lesen",
    "INBOX_WRITE": "Inbox-Eintrag",
    "RESEARCH": "Recherche",
    "CLIPBOARD": "Zwischenablage",
    "CLIPBOARD_NOTE": "Clipboard-Notiz",
    "NOTES_RECENT": "Letzte Notizen",
    "SESSION_SUMMARY": "Sitzungsfazit",
}

BROWSER_ACTIONS = {"SEARCH", "BROWSE", "OPEN", "NEWS", "RESEARCH"}

# Gesamt-Timeout pro Aktion (Sekunden) — Recherche liest mehrere Seiten.
ACTION_TIMEOUTS = {"RESEARCH": 180}
DEFAULT_ACTION_TIMEOUT = 60

# Aktionsspezifische Aufgaben für den Zusammenfassungs-Schritt; Default bleibt
# die generische Kurz-Zusammenfassung.
SUMMARY_TASKS = {
    "INBOX_READ": (
        "Gib einen kurzen, strukturierten Tagesrueckblick ueber die heutigen Notizen: "
        "gruppiere nach Kategorie (Idee, Aufgabe, Termin, Recherche, Erinnerung, Notiz) "
        "und fasse knapp zusammen. Maximal 5 Saetze."
    ),
    "NOTES_RECENT": (
        "Fasse die zuletzt bearbeiteten Notizen kurz zusammen und nenne dabei die "
        "Notiznamen, damit klar ist woran zuletzt gearbeitet wurde. Maximal 5 Saetze."
    ),
    "RESEARCH": (
        "Fasse die Rechercheergebnisse aus den Quellen zu einer praezisen Antwort "
        "zusammen. Maximal 5 Saetze. Nenne KEINE URLs im Text."
    ),
    "CLIPBOARD": (
        "Fuehre den genannten Auftrag auf dem Inhalt der Zwischenablage aus. "
        "Antworte kurz und praezise."
    ),
    "SESSION_SUMMARY": (
        "Fasse kurz zusammen, was in dieser Sitzung besprochen und erledigt wurde. "
        "Maximal 5 Saetze."
    ),
}
DEFAULT_SUMMARY_TASK = "Fasse die folgenden Informationen KURZ zusammen, maximal 3 Saetze."

SUMMARY_MAX_TOKENS = {"RESEARCH": 350, "SESSION_SUMMARY": 350, "INBOX_READ": 350, "NOTES_RECENT": 350}
DEFAULT_SUMMARY_MAX_TOKENS = 250


def summary_system_prompt(action_type: str) -> str:
    task = SUMMARY_TASKS.get(action_type, DEFAULT_SUMMARY_TASK)
    return (
        f"Du bist Jarvis. {task} Antworte auf Deutsch im Jarvis-Stil: freundlich, "
        f"direkt und professionell, wie ein kompetenter Kollege auf Augenhoehe. "
        f"Duze den Nutzer und sprich ihn als {USER_ADDRESS} an. "
        "Deine Antwort wird laut vorgelesen: reiner Fliesstext, KEIN Markdown, "
        "keine Aufzaehlungszeichen, KEINE Tags in eckigen Klammern, KEINE ACTION-Tags."
    )


async def send_action_event(ws: WebSocket, phase: str, action_type: str, detail: str = ""):
    """Aktionshistorie-Event: phase ∈ {start, done, error}."""
    await ws.send_json({
        "type": "action",
        "phase": phase,
        "action": action_type,
        "label": ACTION_LABELS.get(action_type, action_type),
        "detail": detail,
        "ts": time.time(),
    })


def _llm_error_hint(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Anthropic-API-Key ungültig — in config.json prüfen."
    if isinstance(e, anthropic.RateLimitError):
        return "Rate-Limit erreicht — einen Moment warten."
    if isinstance(e, anthropic.APIConnectionError):
        return "Keine Verbindung zur Anthropic-API — Internetverbindung prüfen."
    return ""


async def write_inbox_entry(text: str, kategorie: str, dedup: bool = True) -> str:
    """Hängt einen kategorisierten Eintrag an die heutige Brain-Dump-Datei an.

    ``dedup=True`` prüft vorher per Haiku auf semantische Duplikate (wie bisher
    bei INBOX_WRITE); Autosaves (z.B. Recherche) überspringen das.
    """
    if not INBOX_PATH:
        return "Inbox-Ordner nicht konfiguriert."
    os.makedirs(INBOX_PATH, exist_ok=True)
    file_path = _today_inbox_file()
    existing = ""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing = f.read()
    if dedup and existing.strip():
        dedup_resp = await ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            system="Antworte NUR mit 'DUPLIKAT: [kurzer Ausschnitt des Originals]' oder 'NEU'. Pruefe ob der neue Eintrag semantisch das Gleiche aussagt wie ein bereits vorhandener Eintrag.",
            messages=[{"role": "user", "content": f"Vorhandene Eintraege:\n{existing[:2000]}\n\nNeuer Eintrag:\n{text.strip()}"}],
        )
        verdict = dedup_resp.content[0].text.strip()
        if verdict.upper().startswith("DUPLIKAT"):
            excerpt = verdict[9:].strip(": ").strip()
            return f"Aehnlicher Eintrag existiert bereits: {excerpt}. Nicht neu gespeichert. Bisherige heutige Eintraege:\n{existing[:1500]}"
    tag = "#" + kategorie.lower()
    entry = f"\n## {time.strftime('%H:%M')} · {kategorie}\n{tag}\n{text.strip()}\n"
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(entry)
    updated = existing + entry
    return f"Eintrag gespeichert (Kategorie: {kategorie}). Bisherige heutige Eintraege:\n{updated[:1500]}"


# Erfolgreiche Recherche-Ergebnisse enthalten pro Quelle eine solche Zeile —
# daraus baut process_message die Quellenliste fürs Transcript und den Autosave.
RESEARCH_SOURCE_PREFIX = "QUELLE: "


async def run_research(topic: str) -> str:
    """Recherche-Modus: 3–5 Quellen lesen statt nur des ersten Treffers."""
    links = await browser_tools.search_links(topic, limit=5)
    if not links:
        return "Recherche fehlgeschlagen: keine Suchergebnisse gefunden."
    parts = [f"Recherche zu: {topic}"]
    gelesen = 0
    for link in links:
        if gelesen >= 4:
            break
        result = await browser_tools.visit(link["url"], max_chars=1500)
        if "error" in result:
            logger.info("Recherche-Quelle übersprungen: %s", link["url"])
            continue
        gelesen += 1
        title = (result.get("title") or link["title"]).strip()
        parts.append(f"{RESEARCH_SOURCE_PREFIX}{title} — {link['url']}\n{result.get('content', '')}")
    if gelesen == 0:
        return "Recherche fehlgeschlagen: keine der Quellen war lesbar."
    return "\n\n".join(parts)


async def execute_action(action: actions.Action, session_id: str) -> str:
    t = action.type
    p = action.payload

    if t == "SEARCH":
        result = await browser_tools.search_and_read(p)
        if "error" not in result:
            return f"Seite: {result.get('title', '')}\nURL: {result.get('url', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Suche fehlgeschlagen: {result.get('error', '')}"

    elif t == "BROWSE":
        result = await browser_tools.visit(p)
        if "error" not in result:
            return f"Seite: {result.get('title', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Seite nicht erreichbar: {result.get('error', '')}"

    elif t == "OPEN":
        await browser_tools.open_url(p)
        return f"Geoeffnet: {p}"

    elif t == "SCREEN":
        return await screen_capture.describe_screen(ai, question=p)

    elif t == "NEWS":
        result = await browser_tools.fetch_news()
        return result

    elif t == "RESEARCH":
        return await run_research(p)

    elif t == "INBOX_READ":
        if not INBOX_PATH or not os.path.isdir(INBOX_PATH):
            return "Inbox-Ordner nicht konfiguriert oder nicht gefunden."
        content = await asyncio.to_thread(read_today_inbox_sync)
        if content is None:
            return f"Noch keine Eintraege fuer heute ({time.strftime('%Y-%m-%d')})."
        return content

    elif t == "INBOX_WRITE":
        kategorie, text = actions.split_inbox_category(p)
        return await write_inbox_entry(text, kategorie)

    elif t == "NOTES_RECENT":
        notes = await asyncio.to_thread(read_recent_notes_sync)
        if not notes:
            return "Keine Notizen gefunden — Vault nicht konfiguriert oder leer."
        return notes

    elif t == "CLIPBOARD":
        clip = await asyncio.to_thread(clipboard_tools.get_clipboard_text)
        if not clip:
            return "Die Zwischenablage ist leer oder enthaelt keinen Text."
        auftrag = p or "Fasse den Inhalt kurz zusammen."
        return f"Auftrag: {auftrag}\n\nInhalt der Zwischenablage:\n{clip}"

    elif t == "CLIPBOARD_NOTE":
        clip = await asyncio.to_thread(clipboard_tools.get_clipboard_text)
        if not clip:
            return "Die Zwischenablage ist leer oder enthaelt keinen Text."
        return await write_inbox_entry(clip, actions.INBOX_FALLBACK_CATEGORY)

    elif t == "SESSION_SUMMARY":
        history = conversations.get(session_id, [])
        lines = [
            f"{'Du' if msg['role'] == 'user' else 'Jarvis'}: {msg['content']}"
            for msg in history[-40:]
        ]
        log = "\n".join(lines)[-6000:]
        if not log.strip():
            return "Diese Sitzung hat noch keinen nennenswerten Verlauf."
        return f"Sitzungsprotokoll:\n{log}"

    return ""


async def _finish_research(summary: str, action_result: str) -> str | None:
    """Quellenliste für die Anzeige anhängen und das Ergebnis in den Brain Dump sichern."""
    sources = [
        line[len(RESEARCH_SOURCE_PREFIX):].strip()
        for line in action_result.splitlines()
        if line.startswith(RESEARCH_SOURCE_PREFIX)
    ]
    if not sources:
        return None
    quellen_block = "Quellen:\n" + "\n".join(f"- {s}" for s in sources)
    # Autosave: Obsidian sortiert die Inbox am Tagesende selbst ein.
    try:
        await write_inbox_entry(f"{summary}\n\n{quellen_block}", "Recherche", dedup=False)
    except Exception:
        logger.warning("Recherche-Autosave in die Inbox fehlgeschlagen", exc_info=True)
    return f"{summary}\n\n{quellen_block}"


async def run_action_and_respond(session_id: str, action: actions.Action, ws: WebSocket):
    """Aktion ausführen, Ergebnis zusammenfassen und sprechen (inkl. Historie-Events)."""
    logger.info("Action: %s", action.type)
    logger.debug("Action payload: %s", action.payload)

    # Quick voice feedback for SCREEN so user knows Jarvis is working
    if action.type == "SCREEN":
        await send_spoken_response(ws, "Ich werfe kurz einen Blick auf deinen Bildschirm.")

    await send_action_event(ws, "start", action.type, (action.payload or "")[:80])
    try:
        # Gesamt-Cap: ein haengender Browser blockiert die WS-Loop nie laenger.
        timeout = ACTION_TIMEOUTS.get(action.type, DEFAULT_ACTION_TIMEOUT)
        action_result = await asyncio.wait_for(execute_action(action, session_id), timeout=timeout)
        logger.info("Action %s lieferte %d Zeichen", action.type, len(action_result))
        logger.debug("Action-Ergebnis: %s", action_result)
        await send_action_event(ws, "done", action.type)
    except Exception as e:
        logger.warning("Action %s fehlgeschlagen", action.type, exc_info=True)
        label = ACTION_LABELS.get(action.type, action.type)
        component = "browser" if action.type in BROWSER_ACTIONS else "action"
        await send_action_event(ws, "error", action.type, type(e).__name__)
        await send_error(ws, component, f"Aktion '{label}' fehlgeschlagen.", type(e).__name__)
        action_result = f"Fehler: {e}"

    if action.type == "OPEN":
        # Just opened browser, nothing to summarize
        return

    # Ergebnis zusammenfassen — Aufgabe und Länge sind aktionsspezifisch.
    display_text = None
    if action_result and "fehlgeschlagen" not in action_result:
        try:
            summary_resp = await ai.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=SUMMARY_MAX_TOKENS.get(action.type, DEFAULT_SUMMARY_MAX_TOKENS),
                system=summary_system_prompt(action.type),
                messages=[{"role": "user", "content": action_result}],
            )
            summary = strip_action(summary_resp.content[0].text)
            if action.type == "RESEARCH":
                # Quellen nur anzeigen (nicht vorlesen) + Autosave in die Inbox.
                display_text = await _finish_research(summary, action_result)
        except Exception as e:
            logger.error("KI-Zusammenfassung fehlgeschlagen", exc_info=True)
            await send_error(ws, "llm", "KI-Anfrage fehlgeschlagen.", _llm_error_hint(e))
            summary = f"Das hat leider nicht funktioniert, {USER_ADDRESS}."
    else:
        summary = f"Das hat leider nicht funktioniert, {USER_ADDRESS}."

    # Anzeige-Version (mit Quellen) in die Historie — so funktionieren Folgefragen
    # wie "Öffne die zweite Quelle".
    conversations[session_id].append({"role": "assistant", "content": display_text or summary})
    await send_spoken_response(ws, summary, display_text)


async def process_message(session_id: str, user_text: str, ws: WebSocket):
    """Process message and send responses via WebSocket."""
    if session_id not in conversations:
        conversations[session_id] = []

    # Wartet eine riskante Aktion auf Bestätigung? Ja => ausführen, Nein => verwerfen,
    # alles andere => Aktion verfällt und die Nachricht wird normal verarbeitet.
    pending = pending_confirm.pop(session_id, None)
    if pending is not None:
        verdict = actions.is_confirmation(user_text)
        if verdict is not None:
            conversations[session_id].append({"role": "user", "content": user_text})
            if verdict:
                await run_action_and_respond(session_id, pending, ws)
            else:
                msg = f"Verstanden, {USER_ADDRESS} — ich lasse es bleiben."
                conversations[session_id].append({"role": "assistant", "content": msg})
                await send_spoken_response(ws, msg)
            return

    # Refresh weather + tasks on activate — blockiert die Event-Loop nicht.
    if "activate" in user_text.lower():
        await asyncio.to_thread(refresh_data)

    conversations[session_id].append({"role": "user", "content": user_text})
    history = conversations[session_id][-16:]

    # LLM call — Fehler duerfen die WS-Receive-Loop nicht beenden.
    try:
        response = await ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=get_system_prompt(),
            messages=history,
        )
    except Exception as e:
        logger.error("KI-Anfrage fehlgeschlagen", exc_info=True)
        await send_error(ws, "llm", "KI-Anfrage fehlgeschlagen.", _llm_error_hint(e))
        return
    reply = response.content[0].text
    logger.debug("LLM raw: %s", reply[:200])
    spoken_text, action, action_err = actions.parse_action(reply)
    if action_err:
        # Tag war vorhanden, aber ungueltig: nicht ausfuehren, nur Text sprechen.
        logger.warning("Ungueltige Aktion verworfen: %s", action_err)

    # Speak the main response immediately
    if spoken_text:
        logger.debug("Jarvis: %s", spoken_text[:80])
        conversations[session_id].append({"role": "assistant", "content": spoken_text})
        await send_spoken_response(ws, spoken_text)

    # Execute action if any
    if action:
        if action.type in actions.CONFIRM_ACTIONS:
            # Riskante Aktion: erst merken und mündlich rückfragen.
            pending_confirm[session_id] = action
            label = ACTION_LABELS.get(action.type, action.type)
            detail = f" ({action.payload[:60]})" if action.payload else ""
            frage = f"Soll ich das wirklich ausführen: {label}{detail}? Ja oder Nein, {USER_ADDRESS}."
            conversations[session_id].append({"role": "assistant", "content": frage})
            await send_spoken_response(ws, frage)
            return
        await run_action_and_respond(session_id, action, ws)


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

    try:
        while True:
            data = await ws.receive_json()
            user_text = data.get("text", "").strip()
            if not user_text:
                continue

            logger.debug("You: %s", user_text)
            await process_message(session_id, user_text, ws)

    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)
        conversations.pop(session_id, None)
        pending_confirm.pop(session_id, None)


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")), name="static")


INDEX_PATH = os.path.join(os.path.dirname(__file__), "frontend", "index.html")


def _key_status(value: str) -> dict:
    """Passiver Key-Check: vorhanden und kein Platzhalter (kein API-Aufruf)."""
    if not value or not value.strip():
        return {"ok": False, "detail": "API-Key fehlt in config.json."}
    if config_loader._looks_like_placeholder(value):
        return {"ok": False, "detail": "API-Key ist noch der Platzhalterwert."}
    return {"ok": True, "detail": "API-Key vorhanden"}


def _browser_status() -> dict:
    state = browser_tools.status()
    if state["connected"]:
        return {"ok": True, "detail": "Browser läuft"}
    if config_loader.find_chromium_executable() is not None:
        return {"ok": True, "detail": "Chromium gefunden, nicht gestartet"}
    return {"ok": False, "detail": "Chromium nicht gefunden — python -m playwright install chromium"}


def _vault_status() -> dict:
    vault_path = config.get("obsidian_inbox_path", "")
    if not vault_path:
        return {"ok": False, "detail": "Kein Vault-Pfad konfiguriert (obsidian_inbox_path)."}
    if not os.path.isdir(vault_path):
        return {"ok": False, "detail": f"Pfad nicht erreichbar: {vault_path}"}
    return {"ok": True, "detail": "Vault erreichbar"}


@app.get("/health")
async def health():
    """Passive Statusuebersicht fuer Launcher, Tests und Smoke-Test.

    'ok' heisst: der Server nimmt Verbindungen an. Einzeldienste stehen in
    'services'; es werden keine bezahlten APIs angefragt (kein Quota-Verbrauch).
    """
    return {
        "ok": True,
        "warnings": STARTUP_WARNINGS,
        "services": {
            "config": {"ok": True},
            "llm": _key_status(config.get("anthropic_api_key", "")),
            "tts": _key_status(config.get("elevenlabs_api_key", "")),
            "browser": _browser_status(),
            "vault": _vault_status(),
        },
        "startup": {"data_loaded": DATA_LOADED, "last_refresh": LAST_REFRESH},
    }


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
    global config, USER_NAME, USER_ADDRESS, USER_ROLE, CITY, TASKS_FILE, INBOX_PATH
    global ELEVENLABS_VOICE_ID, STARTUP_WARNINGS

    needs_refresh = (
        merged.get("city", CITY) != CITY
        or merged.get("obsidian_inbox_path", TASKS_FILE) != TASKS_FILE
        or merged.get("obsidian_inbox_folder", INBOX_PATH) != INBOX_PATH
    )
    config = merged
    USER_NAME = config.get("user_name", "Jan")
    USER_ADDRESS = config.get("user_address", USER_NAME)
    USER_ROLE = config.get("user_role", "")
    CITY = config.get("city", "Hamburg")
    TASKS_FILE = config.get("obsidian_inbox_path", "")
    INBOX_PATH = config.get("obsidian_inbox_folder", "")
    ELEVENLABS_VOICE_ID = config.get("elevenlabs_voice_id", "rDmv3mOhK6TnhYWckFaD")
    STARTUP_WARNINGS = config_loader.check_runtime_environment(config)
    if needs_refresh:
        # wttr.in/Vault-Scan blockieren bis ~5s — nicht auf der Event-Loop laufen lassen.
        await asyncio.to_thread(refresh_data)
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

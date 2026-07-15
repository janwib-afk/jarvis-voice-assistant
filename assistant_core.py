"""
Jarvis V2 — Gesprächskern

Der komplette Gesprächsfluss, unabhängig von FastAPI-Routen:
LLM-Aufrufe, System-Prompt, Session-Verlauf, Bestätigungs-Flow,
Action-Ausführung inkl. Zusammenfassung und WS-Frames (response/error/action).

Modul-State (Persona/City/TTS-Werte, Kontextdaten, Sessions) wird von
``configure``/``init_clients`` gesetzt — beim Serverstart und nach jedem
Settings-Save. server.py bleibt damit die reine HTTP-/WS-Schicht.
"""

import asyncio
import base64
import json
import logging
import time

import anthropic

import actions
import app_launcher
import browser_tools
import clipboard_tools
import memory
import screen_capture
import tts

logger = logging.getLogger("jarvis.core")

LLM_MODEL = "claude-haiku-4-5-20251001"

# Verlauf pro Session hart kappen — der LLM sieht ohnehin nur die letzten 16.
MAX_HISTORY = 60

# ── Konfigurierbarer Modul-State (configure/init_clients) ───────────────────
USER_NAME = "Jan"
USER_ADDRESS = "Jan"
USER_ROLE = ""
CITY = "Hamburg"
ELEVENLABS_API_KEY = ""
ELEVENLABS_VOICE_ID = ""

ai = None    # anthropic.AsyncAnthropic — von init_clients gesetzt
http = None  # httpx.AsyncClient — von init_clients gesetzt

# Vom Server injiziert (Composition Root, vermeidet Zirkular-Import):
# async (new_launcher: dict, kind: str) -> list[str] — persistiert einen
# launcher-Block (validate + save + live-apply + WS-Broadcast). Leere Liste = ok.
# None = keine Persistenz moeglich (Standalone/Tests ohne Server).
PERSIST_LAUNCHER = None

# Kontextdaten fuer den System-Prompt (refresh_data)
WEATHER_INFO = ""
TASKS_INFO = []
VAULT_SUMMARY = None
TODAY_INBOX = None
DATA_LOADED = False
LAST_REFRESH: float | None = None

# Session-Verlauf + riskante Aktionen, die auf ein muendliches Ja warten.
conversations: dict[str, list] = {}
pending_confirm: dict[str, actions.Action] = {}


def configure(cfg: dict) -> None:
    """Persona-/City-/TTS-Werte aus der Config uebernehmen (Start + Settings-Save)."""
    global USER_NAME, USER_ADDRESS, USER_ROLE, CITY
    global ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
    USER_NAME = cfg.get("user_name", "Jan")
    USER_ADDRESS = cfg.get("user_address", USER_NAME)
    USER_ROLE = cfg.get("user_role", "")
    CITY = cfg.get("city", "Hamburg")
    ELEVENLABS_API_KEY = cfg.get("elevenlabs_api_key", "")
    ELEVENLABS_VOICE_ID = cfg.get("elevenlabs_voice_id", "rDmv3mOhK6TnhYWckFaD")


def init_clients(ai_client, http_client) -> None:
    """API-Clients injizieren — Besitz bleibt beim Server (Composition Root)."""
    global ai, http
    ai = ai_client
    http = http_client


def _remember(session_id: str, role: str, content: str) -> None:
    """Verlauf anhaengen und hart kappen (kein unbegrenztes Wachstum)."""
    conv = conversations.setdefault(session_id, [])
    conv.append({"role": role, "content": content})
    del conv[:-MAX_HISTORY]


def end_session(session_id: str) -> None:
    """Session-Zustand aufraeumen (WS-Disconnect)."""
    conversations.pop(session_id, None)
    pending_confirm.pop(session_id, None)


# ── Kontextdaten (Wetter/Tasks/Vault/Inbox) ─────────────────────────────────

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


def refresh_data():
    """Refresh weather, tasks, vault summary and today's inbox."""
    global WEATHER_INFO, TASKS_INFO, VAULT_SUMMARY, TODAY_INBOX, DATA_LOADED, LAST_REFRESH
    WEATHER_INFO = get_weather_sync()
    TASKS_INFO = memory.get_tasks_sync()
    VAULT_SUMMARY = memory.get_vault_summary_sync()
    TODAY_INBOX = memory.read_today_inbox_sync(max_chars=800)
    DATA_LOADED = True
    LAST_REFRESH = time.time()
    logger.info("Wetter geladen: %s", "ja" if WEATHER_INFO else "nein")
    logger.info("Tasks geladen: %d", len(TASKS_INFO))
    logger.info("Vault: %s Notizen", VAULT_SUMMARY['total'] if VAULT_SUMMARY else "n/a")
    logger.info("Heutige Inbox: %s", "vorhanden" if TODAY_INBOX else "leer")


# ── System-Prompt ────────────────────────────────────────────────────────────

def build_system_prompt():
    weather_block = ""
    if WEATHER_INFO:
        w = WEATHER_INFO
        weather_block = f"\nWetter {CITY}: {w['temp']}°C, gefühlt {w['feels_like']}°C, {w['description']}"

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
        inbox_block = f"\nHeutige Inbox-Einträge:\n{TODAY_INBOX}"

    apps_line = ""
    app_names = ", ".join(a["name"] for a in app_launcher.list_apps())
    if app_names:
        profile_names = ", ".join(pr["name"] for pr in app_launcher.PROFILES)
        apps_line = (
            f"\n[ACTION:APP_OPEN] app-name - Öffnet eine konfigurierte lokale App, z.B. Obsidian, "
            f"VS Code oder Chrome. Nutze diese Aktion, wenn {USER_ADDRESS} dich bittet, eine lokale App "
            f"oder ein Programm zu öffnen. Es können NUR konfigurierte Apps geöffnet werden. "
            f"Schreibe KEINEN Text vor die Aktion. Verfügbare Apps: {app_names}"
            f"\n[ACTION:PROFILE_ACTIVATE] profilname - Aktiviert ein vorhandenes Session-Profil für den "
            f"Clap-Start. Nutze es bei Aussagen wie \"aktiviere Coding-Modus\" oder \"wechsle ins "
            f"Research-Profil\". Verfügbare Profile: {profile_names}"
            f"\n[ACTION:PROFILE_STATUS] optionaler profilname - Sagt, welches Profil aktiv ist und welche "
            f"Apps beim Clap starten. Ohne Payload: das aktive Profil. Nutze bei \"Welches Profil ist "
            f"aktiv?\" oder \"Welche Apps starten im Research-Profil?\"."
            f"\n[ACTION:APP_AUTOSTART_ON] app-name - Nimmt eine konfigurierte App im aktiven Profil in den "
            f"Clap-Start auf. Nutze bei \"starte X beim nächsten Clap mit\"."
            f"\n[ACTION:APP_AUTOSTART_OFF] app-name - Nimmt eine konfigurierte App im aktiven Profil aus "
            f"dem Clap-Start. Nutze bei \"nimm X aus dem Clap-Start\"."
            f"\n[ACTION:APP_PLACE] app-name | monitor | zone - Setzt die Startposition einer konfigurierten "
            f"App im aktiven Profil. monitor: primary, left, right, leftmost, rightmost. zone: fullscreen, "
            f"left_half, right_half, top_half, bottom_half, top_left, top_right, bottom_left, bottom_right, "
            f"center. Beispiel: [ACTION:APP_PLACE] Obsidian | left | right_half"
            f"\nLauncher-Regeln: Nur konfigurierte Apps und vorhandene Profile verwenden. Ist ein App- oder "
            f"Profilname unklar, frag nach statt zu raten. Persistente Änderungen (Autostart, Platzierung, "
            f"Profilwechsel) nur bei klarer Absicht von {USER_ADDRESS}. Profile löschen, anlegen oder "
            f"überschreiben geht NICHT per Sprache — verweise dafür auf das Jarvis-Fenster."
        )

    memory_block = ""
    memory_content = memory.read_memory_sync()
    if memory_content:
        memory_block = (
            f"\nLangzeit-Gedächtnis (aus '{memory.MEMORY_FILENAME}', vom Nutzer editierbar):\n"
            f"{memory_content}"
        )

    role_part = f", {USER_ROLE}" if USER_ROLE else ""
    return f"""Du bist Jarvis, der persönliche KI-Assistent von {USER_NAME}{role_part}. Du sprichst ausschließlich Deutsch. {USER_NAME} möchte geduzt und mit "{USER_ADDRESS}" angesprochen werden — nutze "du" als Pronomen (z.B. "Klar, {USER_ADDRESS}, ich schau mir das an."). Du bist ein kompetenter Kollege und Gesprächspartner auf Augenhöhe: freundlich, direkt, professionell und assistenzorientiert — wie ein smarter Arbeitskollege oder persönlicher Mitarbeiter. Du redest klar und ohne Umschweife, denkst mit und bringst eigene Vorschläge ein, ohne belehrend zu wirken. Kein Sarkasmus, keine Butler-Attitüde, keine gekünstelte Förmlichkeit. Du bist effizient und einen Schritt voraus, aber immer auf Augenhöhe. Halte deine Antworten kurz — maximal 3 Sätze (einzige Ausnahme: der Tagesüberblick bei "Jarvis activate"). Wiederhole NIEMALS etwas, das bereits in diesem Gespräch gesagt wurde, es sei denn, {USER_ADDRESS} fragt explizit danach. Vault-Inhalte oder frühere Antworten fasst du NUR zusammen wenn {USER_ADDRESS} ausdrücklich danach fragt.

WICHTIG: Schreibe NIEMALS Regieanweisungen, Emotionen oder Tags in eckigen Klammern wie [freundlich] [formal] [amused] oder ähnliches. Alles was du schreibst wird laut vorgelesen — dein Ton entsteht rein durch die Wortwahl.

Du hast die volle Kontrolle über den Browser von {USER_NAME}. Du kannst im Internet suchen, Webseiten öffnen und den Bildschirm sehen. Wenn {USER_ADDRESS} dich bittet etwas nachzuschauen, zu recherchieren, zu googeln, eine Seite zu öffnen, oder irgendetwas im Internet zu tun — nutze IMMER eine Aktion. Frag nicht ob du es tun sollst, tu es einfach.

AKTIONEN - Schreibe die passende Aktion ans ENDE deiner Antwort. Der Text VOR der Aktion wird vorgelesen, die Aktion selbst wird still ausgeführt. Maximal EINE Aktion pro Antwort.
[ACTION:SEARCH] suchbegriff - Schnelle Websuche: erstes Ergebnis lesen und zusammenfassen. Für einfache Fakten.
[ACTION:RESEARCH] thema - Gründliche Recherche: liest 3-5 Quellen und liefert eine Zusammenfassung mit Quellenliste. Nutze wenn {USER_ADDRESS} "recherchiere" sagt oder eine fundierte Antwort mit mehreren Quellen sinnvoll ist.
[ACTION:OPEN] url - URL im Browser öffnen
[ACTION:SCREEN] optionale frage - Bildschirm ansehen. Ohne Frage: kurz beschreiben. Mit Frage (z.B. "Was ist das Problem?", "Fasse diese Seite zusammen", "Was soll ich als nächstes tun?"): die Frage anhand des Bildschirms beantworten. WICHTIG: Bei SCREEN schreibe KEINEN Text vor die Aktion.
[ACTION:NEWS] - Aktuelle Weltnachrichten abrufen. Nutze diese Aktion wenn nach News, Nachrichten, was in der Welt passiert, aktuelle Lage oder Weltgeschehen gefragt wird. Schreibe einen kurzen Satz davor wie "Ich schaue nach den aktuellen Nachrichten."
[ACTION:INBOX_READ] - Liest die heutigen Einträge aus der Obsidian-Inbox. Nutze wenn {USER_ADDRESS} fragt was heute notiert wurde oder einen Tagesrückblick möchte.
[ACTION:INBOX_WRITE] [Kategorie] text - Schreibt einen Eintrag in die heutige Inbox-Datei. Kategorie ist GENAU EINE von: Idee, Aufgabe, Termin, Recherche, Erinnerung — wähle die passendste. Beispiel: [ACTION:INBOX_WRITE] [Termin] Zahnarzt Dienstag 9 Uhr. Nutze IMMER wenn {USER_ADDRESS} etwas festhalten, notieren, aufschreiben oder merken möchte. Frag nicht ob, tu es einfach. Formuliere den Text klar und strukturiert.
[ACTION:MEMORY_WRITE] text - Speichert eine Information DAUERHAFT im Langzeit-Gedächtnis (Präferenzen, laufende Projekte, offene Loops). Nutze NUR wenn {USER_ADDRESS} ausdrücklich sagt, dass du dir etwas dauerhaft/für die Zukunft merken sollst (z.B. "merk dir dauerhaft", "vergiss nie"). Tagesnotizen gehören in INBOX_WRITE. Speichere NIEMALS sensible Inhalte (Passwörter, Gesundheit, Finanzen) ohne ausdrückliche Aufforderung.
[ACTION:MEMORY_READ] - Zeigt bzw. fasst zusammen, was du dauerhaft über {USER_NAME} gespeichert hast. Nutze wenn {USER_ADDRESS} fragt "Was weißt du über mich?", "Was hast du dir gemerkt?" oder Ähnliches.
[ACTION:MEMORY_FORGET] stichwort - Löscht einen passenden Eintrag DAUERHAFT aus dem Langzeit-Gedächtnis. Nutze wenn {USER_ADDRESS} sagt "vergiss ..." o.Ä. Gib als Payload knapp das Thema/Stichwort an, das vergessen werden soll (nicht das Wort "vergiss" selbst). Diese Aktion wird vor der Ausführung sicherheitshalber noch einmal mündlich bestätigt.
[ACTION:NOTES_RECENT] - Fasst die zuletzt bearbeiteten Notizen aus dem Vault zusammen. Nutze wenn {USER_ADDRESS} z.B. "Fasse meine letzten Notizen zusammen" sagt oder wissen will woran er zuletzt gearbeitet hat.
[ACTION:PROJECT_CONTEXT] frage oder projektname - Durchsucht den Obsidian-Vault lokal nach passenden Notizen und antwortet mit deren Kontext. Nutze wenn {USER_ADDRESS} nach dem Stand, den nächsten Schritten oder offenen Punkten eines Projekts fragt, Kontext zu einem Thema aus seinen Notizen möchte oder fragt "was weißt du über mein Projekt ...".
[ACTION:CLIPBOARD] auftrag - Verarbeitet den Text in der Zwischenablage (auftrag z.B. "zusammenfassen", "übersetzen", "erklären"). Nutze wenn {USER_ADDRESS} von Zwischenablage, Clipboard oder "das Kopierte" spricht.
[ACTION:CLIPBOARD_NOTE] - Speichert den Text aus der Zwischenablage als Inbox-Notiz. Nutze wenn {USER_ADDRESS} aus der Zwischenablage eine Notiz machen möchte.
[ACTION:SESSION_SUMMARY] - Fasst zusammen was in dieser Sitzung besprochen und erledigt wurde. Nutze bei "Was haben wir heute gemacht?" oder am Sitzungsende. Möchte {USER_ADDRESS} das Fazit danach speichern, nutze INBOX_WRITE.{apps_line}

WENN {USER_NAME} "Jarvis activate" sagt, liefere den Tagesüberblick (maximal 6 Sätze):
- Begrüße ihn kreativ und passend zur Tageszeit (aktuelle Zeit: {{time}}).
- Wetter in einem Satz: Temperatur, ob Sonne/klar/bewölkt/Regen, und wie es sich anfühlt. Keine Luftfeuchtigkeit.
- Falls heute schon Inbox-Einträge existieren: nenne sie knapp nach Kategorien gruppiert.
- Fasse die offenen Aufgaben als Überblick in einem Satz zusammen, ohne jede einzelne vorzulesen.
- Nenne in einem Satz die zuletzt bearbeiteten Notizen als Hinweis, woran {USER_ADDRESS} zuletzt gearbeitet hat.

=== AKTUELLE DATEN ==={weather_block}{task_block}{vault_block}{inbox_block}{memory_block}
==="""


def get_system_prompt():
    return build_system_prompt().replace("{time}", time.strftime("%H:%M"))


def strip_action(text: str) -> str:
    """Entfernt einen etwaigen Action-Tag aus Text (z.B. aus Zusammenfassungen)."""
    spoken, _, _ = actions.parse_action(text)
    return spoken


# ── WS-Frames + TTS ──────────────────────────────────────────────────────────

async def synthesize_speech(text: str) -> tuple[bytes, str | None]:
    """TTS mit den aktuellen Config-Werten — Logik liegt in tts.py."""
    return await tts.synthesize_speech(
        text, api_key=ELEVENLABS_API_KEY, voice_id=ELEVENLABS_VOICE_ID, client=http
    )


async def send_error(ws, component: str, text: str, hint: str = ""):
    """Strukturierter Fehler ans Frontend: component ∈ {llm, tts, browser, action, config}."""
    await ws.send_json({"type": "error", "component": component, "text": text, "hint": hint})


async def send_spoken_response(ws, text: str, display_text: str | None = None):
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


async def send_action_event(ws, phase: str, action_type: str, detail: str = ""):
    """Aktionshistorie-Event: phase ∈ {start, done, error}."""
    await ws.send_json({
        "type": "action",
        "phase": phase,
        "action": action_type,
        "label": actions.label_for(action_type),
        "detail": detail,
        "ts": time.time(),
    })


def summary_system_prompt(action_type: str) -> str:
    task = actions.spec_for(action_type).summary_task or actions.DEFAULT_SUMMARY_TASK
    return (
        f"Du bist Jarvis. {task} Antworte auf Deutsch im Jarvis-Stil: freundlich, "
        f"direkt und professionell, wie ein kompetenter Kollege auf Augenhöhe. "
        f"Duze den Nutzer und sprich ihn als {USER_ADDRESS} an. "
        "Deine Antwort wird laut vorgelesen: reiner Fließtext, KEIN Markdown, "
        "keine Aufzählungszeichen, KEINE Tags in eckigen Klammern, KEINE ACTION-Tags."
    )


def _llm_error_hint(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Anthropic-API-Key ungültig — in config.json prüfen."
    if isinstance(e, anthropic.RateLimitError):
        return "Rate-Limit erreicht — einen Moment warten."
    if isinstance(e, anthropic.APIConnectionError):
        return "Keine Verbindung zur Anthropic-API — Internetverbindung prüfen."
    return ""


# ── Aktionen ─────────────────────────────────────────────────────────────────

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
    if gelesen < 3:
        # Duenne Quellenlage ehrlich benennen statt Scheinsicherheit vorzulesen.
        parts.append(
            f"HINWEIS AN JARVIS: Nur {gelesen} Quelle(n) waren lesbar — sag ehrlich dazu, "
            "dass die Quellenlage dünn ist und die Antwort entsprechend vorsichtig zu werten ist."
        )
    return "\n\n".join(parts)


# ── Launcher-Sprachsteuerung (Phase 5) ──────────────────────────────────────
# Antworten sind fertige deutsche Saetze (speaks_result) — kein Zusammenfassungs-LLM.

_MONITOR_SPEECH = {
    "primary": "auf dem Hauptmonitor", "left": "auf dem linken Monitor",
    "right": "auf dem rechten Monitor", "leftmost": "ganz links",
    "rightmost": "ganz rechts",
}
_ZONE_SPEECH = {
    "fullscreen": "im Vollbild", "left_half": "in der linken Hälfte",
    "right_half": "in der rechten Hälfte", "top_half": "in der oberen Hälfte",
    "bottom_half": "in der unteren Hälfte", "top_left": "oben links",
    "top_right": "oben rechts", "bottom_left": "unten links",
    "bottom_right": "unten rechts", "center": "zentriert",
}


def _available_apps() -> str:
    return ", ".join(a["name"] for a in app_launcher.APPS)


def _available_profiles() -> str:
    return ", ".join(p["name"] for p in app_launcher.PROFILES)


def _unknown_app_message(query: str) -> str:
    available = _available_apps()
    if not available:
        return "Es sind keine Apps konfiguriert — trage Apps in den Einstellungen ein."
    return f"Die App '{(query or '').strip()}' ist nicht konfiguriert. Verfügbar: {available}."


async def _persist_launcher_or_error(new_launcher: dict, kind: str) -> str | None:
    """Persist via injizierten Server-Hook; None = ok, sonst sprechbarer Fehler."""
    if PERSIST_LAUNCHER is None:
        return "Profil-Änderungen sind gerade nicht möglich."
    errors = await PERSIST_LAUNCHER(new_launcher, kind)
    if errors:
        return "Das konnte ich nicht speichern: " + " ".join(errors)
    return None


async def _voice_activate_profile(payload: str) -> str:
    profile = app_launcher.find_profile(payload)
    if profile is None:
        return (f"Das Profil '{(payload or '').strip()}' kenne ich nicht. "
                f"Verfügbar: {_available_profiles()}.")
    if profile["id"] == app_launcher.ACTIVE_PROFILE:
        return f"{profile['name']} ist bereits aktiv."
    new_launcher = app_launcher.launcher_with_active(profile["id"])
    error = await _persist_launcher_or_error(new_launcher, "profile")
    if error:
        return error
    return f"{profile['name']} ist jetzt aktiv."


def _voice_profile_status(payload: str) -> str:
    if payload.strip():
        profile = app_launcher.find_profile(payload)
        if profile is None:
            return (f"Das Profil '{payload.strip()}' kenne ich nicht. "
                    f"Verfügbar: {_available_profiles()}.")
    else:
        profile = app_launcher.find_profile(app_launcher.ACTIVE_PROFILE)
        if profile is None:
            return "Es ist kein Profil konfiguriert."
    enabled = [a["name"] for a in app_launcher.effective_apps(profile["id"]) if a["autostart"]]
    is_active = profile["id"] == app_launcher.ACTIVE_PROFILE
    prefix = f"Aktiv ist '{profile['name']}'." if is_active else f"Im Profil '{profile['name']}':"
    if not enabled:
        return f"{prefix} Beim Clap startet nichts automatisch."
    return f"{prefix} Beim Clap starten: {', '.join(enabled)}."


async def _voice_set_autostart(payload: str, enabled: bool) -> str:
    app = app_launcher.find_app(payload)
    if app is None:
        return _unknown_app_message(payload)
    new_launcher = app_launcher.launcher_with_app_state(app["id"], autostart=enabled)
    if new_launcher is None:
        return _unknown_app_message(payload)
    error = await _persist_launcher_or_error(new_launcher, "autostart")
    if error:
        return error
    if enabled:
        return f"{app['name']} startet beim nächsten Clap mit."
    return f"{app['name']} ist aus dem Clap-Start raus."


async def _voice_place_app(payload: str) -> str:
    parsed, parse_error = actions.parse_place_payload(payload)
    if parse_error:
        return parse_error
    app_query, monitor, zone = parsed
    app = app_launcher.find_app(app_query)
    if app is None:
        return _unknown_app_message(app_query)
    new_launcher = app_launcher.launcher_with_app_state(
        app["id"], placement={"monitor": monitor, "zone": zone}
    )
    if new_launcher is None:
        return _unknown_app_message(app_query)
    error = await _persist_launcher_or_error(new_launcher, "placement")
    if error:
        return error
    return f"{app['name']} liegt jetzt {_ZONE_SPEECH[zone]} {_MONITOR_SPEECH[monitor]}."


def _action_context(session_id: str) -> actions.ActionContext:
    """Request-scoped Kontext aus dem AKTUELLEN Prozesszustand bauen (RFC-0001).

    Der Verlauf wird als unveraenderlicher Snapshot uebergeben — die Action sieht
    weder ``session_id`` noch das ``conversations``-Dict.
    """
    return actions.ActionContext(
        ai=ai,
        history=tuple(dict(msg) for msg in conversations.get(session_id, [])),
        persist_launcher=PERSIST_LAUNCHER,
    )


async def execute_action(action: actions.Action, session_id: str) -> str:
    """Thin Dispatcher: Kontext bauen, Registry-Lookup, ausfuehren.

    TEMPORAERER SHIM (RFC-0001 Kompatibilitaetsadapter): migrierte Actions laufen
    ueber ``spec.execute``; noch nicht migrierte fallen auf den Legacy-``if/elif``
    zurueck. Der Shim faellt in Slice C, sobald alle 22 Actions migriert sind.
    """
    spec = actions.REGISTRY.get(action.type)
    if spec is not None and spec.execute is not None:
        return await spec.execute(action.payload, _action_context(session_id))
    return await _execute_action_legacy(action, session_id)


async def _execute_action_legacy(action: actions.Action, session_id: str) -> str:
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
        return f"Geöffnet: {p}"

    elif t == "APP_OPEN":
        result = await asyncio.to_thread(app_launcher.launch, p)
        return result["message"]

    elif t == "PROFILE_ACTIVATE":
        return await _voice_activate_profile(p)

    elif t == "PROFILE_STATUS":
        return _voice_profile_status(p)

    elif t == "APP_AUTOSTART_ON":
        return await _voice_set_autostart(p, True)

    elif t == "APP_AUTOSTART_OFF":
        return await _voice_set_autostart(p, False)

    elif t == "APP_PLACE":
        return await _voice_place_app(p)

    elif t == "SCREEN":
        return await screen_capture.describe_screen(ai, question=p)

    elif t == "NEWS":
        result = await browser_tools.fetch_news()
        return result

    elif t == "RESEARCH":
        return await run_research(p)

    elif t == "INBOX_READ":
        if not memory.inbox_available():
            return "Inbox-Ordner nicht konfiguriert oder nicht gefunden."
        content = await asyncio.to_thread(memory.read_today_inbox_sync)
        if content is None:
            return f"Noch keine Einträge für heute ({time.strftime('%Y-%m-%d')})."
        return content

    elif t == "INBOX_WRITE":
        kategorie, text = actions.split_inbox_category(p)
        return await memory.write_inbox_entry(text, kategorie, ai=ai)

    elif t == "MEMORY_WRITE":
        return await asyncio.to_thread(memory.append_memory, p)

    elif t == "MEMORY_READ":
        content = await asyncio.to_thread(memory.read_memory_sync)
        if not content.strip():
            return "Ich habe mir dauerhaft noch nichts gemerkt."
        return f"Langzeit-Gedächtnis (dauerhaft gespeichert):\n{content}"

    elif t == "MEMORY_FORGET":
        return await asyncio.to_thread(memory.forget_memory, p)

    elif t == "NOTES_RECENT":
        notes = await asyncio.to_thread(memory.read_recent_notes_sync)
        if not notes:
            return "Keine Notizen gefunden — Vault nicht konfiguriert oder leer."
        return notes

    elif t == "PROJECT_CONTEXT":
        if not memory.vault_available():
            return "Kein Obsidian-Vault konfiguriert — bitte den Vault-Pfad in den Einstellungen hinterlegen."
        context = await asyncio.to_thread(memory.get_project_context_sync, p)
        if not context:
            return f'Im Vault habe ich zu "{p}" nichts Passendes gefunden.'
        return f'Frage: "{p}"\n\n{context}'

    elif t == "CLIPBOARD":
        clip = await asyncio.to_thread(clipboard_tools.get_clipboard_text)
        if not clip:
            return "Die Zwischenablage ist leer oder enthält keinen Text."
        auftrag = p or "Fasse den Inhalt kurz zusammen."
        return f"Auftrag: {auftrag}\n\nInhalt der Zwischenablage:\n{clip}"

    elif t == "CLIPBOARD_NOTE":
        clip = await asyncio.to_thread(clipboard_tools.get_clipboard_text)
        if not clip:
            return "Die Zwischenablage ist leer oder enthält keinen Text."
        return await memory.write_inbox_entry(clip, actions.INBOX_FALLBACK_CATEGORY, ai=ai)

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
        await memory.write_inbox_entry(f"{summary}\n\n{quellen_block}", "Recherche", dedup=False)
    except Exception:
        logger.warning("Recherche-Autosave in die Inbox fehlgeschlagen", exc_info=True)
    return f"{summary}\n\n{quellen_block}"


async def run_action_and_respond(session_id: str, action: actions.Action, ws):
    """Aktion ausführen, Ergebnis zusammenfassen und sprechen (inkl. Historie-Events)."""
    logger.info("Action: %s", action.type)
    logger.debug("Action payload: %s", action.payload)

    # Quick voice feedback for SCREEN so user knows Jarvis is working
    if action.type == "SCREEN":
        await send_spoken_response(ws, "Ich werfe kurz einen Blick auf deinen Bildschirm.")

    spec = actions.spec_for(action.type)
    await send_action_event(ws, "start", action.type, (action.payload or "")[:80])
    try:
        # Gesamt-Cap: ein haengender Browser blockiert die WS-Loop nie laenger.
        action_result = await asyncio.wait_for(execute_action(action, session_id), timeout=spec.timeout)
        logger.info("Action %s lieferte %d Zeichen", action.type, len(action_result))
        logger.debug("Action-Ergebnis: %s", action_result)
        await send_action_event(ws, "done", action.type)
    except asyncio.CancelledError:
        # Nutzer hat "Stopp" gesagt: Historie markieren, Abbruch weiterreichen.
        logger.info("Action %s abgebrochen (Stopp)", action.type)
        await send_action_event(ws, "error", action.type, "abgebrochen")
        raise
    except Exception as e:
        logger.warning("Action %s fehlgeschlagen", action.type, exc_info=True)
        component = "browser" if spec.is_browser else "action"
        await send_action_event(ws, "error", action.type, type(e).__name__)
        await send_error(ws, component, f"Aktion '{spec.label}' fehlgeschlagen.", type(e).__name__)
        action_result = f"Fehler: {e}"

    if action.type == "OPEN":
        # Just opened browser, nothing to summarize
        return

    if action.type in actions.SPEAK_RESULT_ACTIONS:
        # Launcher-Meldungen sind bereits kurz und deutsch — keine LLM-Zusammenfassung.
        msg = action_result
        if not msg or msg.startswith("Fehler:"):
            msg = f"Das hat leider nicht funktioniert, {USER_ADDRESS}."
        _remember(session_id, "assistant", msg)
        await send_spoken_response(ws, msg)
        return

    # Ergebnis zusammenfassen — Aufgabe und Länge sind aktionsspezifisch.
    display_text = None
    if action_result and "fehlgeschlagen" not in action_result:
        try:
            summary_resp = await ai.messages.create(
                model=LLM_MODEL,
                max_tokens=spec.summary_max_tokens,
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
    _remember(session_id, "assistant", display_text or summary)
    await send_spoken_response(ws, summary, display_text)


async def process_message(session_id: str, user_text: str, ws):
    """Process message and send responses via WebSocket."""
    if session_id not in conversations:
        conversations[session_id] = []

    # Wartet eine riskante Aktion auf Bestätigung? Ja => ausführen, Nein => verwerfen,
    # alles andere => Aktion verfällt und die Nachricht wird normal verarbeitet.
    pending = pending_confirm.pop(session_id, None)
    if pending is not None:
        verdict = actions.is_confirmation(user_text)
        if verdict is not None:
            _remember(session_id, "user", user_text)
            if verdict:
                await run_action_and_respond(session_id, pending, ws)
            else:
                msg = f"Verstanden, {USER_ADDRESS} — ich lasse es bleiben."
                _remember(session_id, "assistant", msg)
                await send_spoken_response(ws, msg)
            return

    # Refresh weather + tasks on activate — blockiert die Event-Loop nicht.
    if "activate" in user_text.lower():
        await asyncio.to_thread(refresh_data)

    _remember(session_id, "user", user_text)
    history = conversations[session_id][-16:]

    # LLM call — Fehler duerfen die WS-Receive-Loop nicht beenden.
    try:
        response = await ai.messages.create(
            model=LLM_MODEL,
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
        _remember(session_id, "assistant", spoken_text)
        await send_spoken_response(ws, spoken_text)

    # Execute action if any
    if action:
        if action.type in actions.CONFIRM_ACTIONS:
            # Riskante Aktion: erst merken und mündlich rückfragen.
            pending_confirm[session_id] = action
            label = actions.label_for(action.type)
            detail = f" ({action.payload[:60]})" if action.payload else ""
            frage = f"Soll ich das wirklich ausführen: {label}{detail}? Ja oder Nein, {USER_ADDRESS}."
            _remember(session_id, "assistant", frage)
            await send_spoken_response(ws, frage)
            return
        await run_action_and_respond(session_id, action, ws)

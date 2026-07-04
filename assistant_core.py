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

    memory_block = ""
    memory_content = memory.read_memory_sync()
    if memory_content:
        memory_block = (
            f"\nLangzeit-Gedaechtnis (aus '{memory.MEMORY_FILENAME}', vom Nutzer editierbar):\n"
            f"{memory_content}"
        )

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
[ACTION:MEMORY_WRITE] text - Speichert eine Information DAUERHAFT im Langzeit-Gedaechtnis (Praeferenzen, laufende Projekte, offene Loops). Nutze NUR wenn {USER_ADDRESS} ausdruecklich sagt, dass du dir etwas dauerhaft/fuer die Zukunft merken sollst (z.B. "merk dir dauerhaft", "vergiss nie"). Tagesnotizen gehoeren in INBOX_WRITE. Speichere NIEMALS sensible Inhalte (Passwoerter, Gesundheit, Finanzen) ohne ausdrueckliche Aufforderung.
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
        f"direkt und professionell, wie ein kompetenter Kollege auf Augenhoehe. "
        f"Duze den Nutzer und sprich ihn als {USER_ADDRESS} an. "
        "Deine Antwort wird laut vorgelesen: reiner Fliesstext, KEIN Markdown, "
        "keine Aufzaehlungszeichen, KEINE Tags in eckigen Klammern, KEINE ACTION-Tags."
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
        if not memory.inbox_available():
            return "Inbox-Ordner nicht konfiguriert oder nicht gefunden."
        content = await asyncio.to_thread(memory.read_today_inbox_sync)
        if content is None:
            return f"Noch keine Eintraege fuer heute ({time.strftime('%Y-%m-%d')})."
        return content

    elif t == "INBOX_WRITE":
        kategorie, text = actions.split_inbox_category(p)
        return await memory.write_inbox_entry(text, kategorie, ai=ai)

    elif t == "MEMORY_WRITE":
        return await asyncio.to_thread(memory.append_memory, p)

    elif t == "NOTES_RECENT":
        notes = await asyncio.to_thread(memory.read_recent_notes_sync)
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
    except Exception as e:
        logger.warning("Action %s fehlgeschlagen", action.type, exc_info=True)
        component = "browser" if spec.is_browser else "action"
        await send_action_event(ws, "error", action.type, type(e).__name__)
        await send_error(ws, component, f"Aktion '{spec.label}' fehlgeschlagen.", type(e).__name__)
        action_result = f"Fehler: {e}"

    if action.type == "OPEN":
        # Just opened browser, nothing to summarize
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

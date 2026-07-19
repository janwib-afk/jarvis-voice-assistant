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
import time

import anthropic

import actions
import capability
import obslog
import wire_protocol as wp
import app_launcher
import browser_tools
import clipboard_tools
import memory
import screen_capture
import tts

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

# Session-Verlauf und offene Bestaetigung liegen seit RFC-0006 (Phase 4J) im
# Session-Aggregat (``conversation.ConversationSession``) und werden ueber einen
# expliziten ``TurnContext`` uebergeben — hier gibt es KEINE Session-Globals mehr.


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
                obslog.event("context.refresh_failed", stage="weather")
                time.sleep(1)
            else:
                obslog.event("context.refresh_failed", stage="weather")
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
    obslog.event("context.refreshed",
                 weather_ok=bool(WEATHER_INFO), tasks=len(TASKS_INFO),
                 notes=(VAULT_SUMMARY["total"] if VAULT_SUMMARY else 0),
                 inbox_present=bool(TODAY_INBOX))


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

    # Action-Beschreibungen kommen aus der Registry (RFC-0001): eine Quelle der
    # Wahrheit. Die Launcher-Gruppe erscheint nur mit konfigurierten Apps.
    action_block = actions.render_action_block(actions.PromptContext(
        user_name=USER_NAME,
        user_address=USER_ADDRESS,
        app_names=", ".join(a["name"] for a in app_launcher.list_apps()),
        profile_names=", ".join(pr["name"] for pr in app_launcher.PROFILES),
    ))

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
{action_block}

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


_RETRYABLE_COMPONENTS = ("llm", "tts", "browser")


def _error_code(component: str) -> str:
    return f"{component}_failed"


async def send_error(sink, component: str, text: str, hint: str = ""):
    """Strukturierter Fehler ans Frontend: component ∈ {llm, tts, browser, action, config}.

    Emittiert ein semantisches ErrorEvent; die Wire-Projektion (Legacy: text/hint,
    V1: zusätzlich code/retryable) erledigt der Codec. Kein Wire-Dict im App-Code.
    """
    await sink.emit(wp.ErrorEvent(
        component=component, message=text, hint=hint,
        code=_error_code(component), retryable=component in _RETRYABLE_COMPONENTS))


async def send_spoken_response(sink, text: str, display_text: str | None = None):
    """Antwort mit TTS senden; bei komplettem TTS-Ausfall zusätzlich einen tts-Fehler melden.

    ``display_text`` erlaubt eine längere Anzeige-Version (z.B. mit Quellen-URLs),
    während nur ``text`` vorgelesen wird.
    """
    audio, tts_err = await synthesize_speech(text)
    await sink.emit(wp.SpokenResponse(
        text=display_text or text,
        audio=base64.b64encode(audio).decode("utf-8") if audio else ""))
    if not audio and tts_err:
        await send_error(sink, "tts", "Sprachausgabe fehlgeschlagen — Antwort wird nur als Text angezeigt.", tts_err)


async def send_action_event(sink, phase: str, action_type: str, detail: str = ""):
    """Aktionshistorie-Event: phase ∈ {start, done, error}. Legacy-`ts` setzt der Codec."""
    await sink.emit(wp.ActionLifecycle(
        phase=phase, action=action_type,
        label=actions.label_for(action_type), detail=detail))


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
# Die Ausfuehrung liegt seit RFC-0001 je Action am Registry-Eintrag (actions.py);
# hier bleibt nur die Orchestrierung (Timeout/Cancel/Summary/TTS/WS/Autosave).


def _action_context(ctx, mutate_launcher=None) -> actions.ActionContext:
    """Request-scoped Kontext aus dem AKTUELLEN Prozesszustand bauen (RFC-0001).

    Der Verlauf wird als unveraenderlicher Snapshot uebergeben — die Action sieht
    weder eine Session-ID noch ein Verlaufs-Dict. ``mutate_launcher`` wird
    vom Aufrufer (WS-Endpoint) aus der Runtime der konkreten App injiziert
    (RFC-0003) — assistant_core kennt weder Runtime noch server.
    """
    return actions.ActionContext(
        ai=ai,
        history=ctx.history_snapshot(),
        mutate_launcher=mutate_launcher,
    )


async def execute_action(action: actions.Action, ctx,
                         mutate_launcher=None) -> str:
    """Thin Dispatcher (RFC-0001): Kontext bauen, Registry-Lookup, ausfuehren.

    Die Action beschreibt und fuehrt sich selbst aus; hier bleibt nur die
    Uebersetzung von (action, TurnContext) in einen request-scoped Kontext.
    Nur validierte Actions erreichen diesen Punkt (parse_action ist der Adapter).
    ``mutate_launcher`` reicht der Aufrufer aus der App-Runtime durch (RFC-0003).
    """
    return await actions.spec_for(action.type).execute(
        action.payload, _action_context(ctx, mutate_launcher))


async def _finish_research(summary: str, action_result: str) -> str | None:
    """Quellenliste für die Anzeige anhängen und das Ergebnis in den Brain Dump sichern."""
    sources = [
        line[len(actions.RESEARCH_SOURCE_PREFIX):].strip()
        for line in action_result.splitlines()
        if line.startswith(actions.RESEARCH_SOURCE_PREFIX)
    ]
    if not sources:
        return None
    quellen_block = "Quellen:\n" + "\n".join(f"- {s}" for s in sources)
    # Autosave: Obsidian sortiert die Inbox am Tagesende selbst ein.
    try:
        await memory.write_inbox_entry(f"{summary}\n\n{quellen_block}", "Recherche", dedup=False)
    except Exception as e:
        obslog.event("inbox.autosave_failed", error_type=type(e).__name__)
    return f"{summary}\n\n{quellen_block}"


async def run_action_and_respond(ctx, action: actions.Action, sink,
                                 mutate_launcher=None, capabilities=None):
    """Aktion ausführen, Ergebnis zusammenfassen und sprechen (inkl. Historie-Events).

    ``capabilities``: der runtime-eigene Coordinator (RFC-0007 §17). In der Pilotphase
    dispatchen die migrierten Pfade (Slices 5/7) hierueber; nicht migrierte Actions
    laufen unveraendert ueber ``execute_action``.
    """
    obslog.event("action.started", action=action.type)

    # Quick voice feedback for SCREEN so user knows Jarvis is working
    if action.type == "SCREEN":
        await send_spoken_response(sink, "Ich werfe kurz einen Blick auf deinen Bildschirm.")

    spec = actions.spec_for(action.type)
    await send_action_event(sink, "start", action.type, (action.payload or "")[:80])
    try:
        if capabilities is not None and capability.is_migrated(action.type):
            # Migrierter Pilot-Pfad (RFC-0007): der Coordinator ist der EINZIGE
            # Timeout-Owner (Amendment 1 §A1.6 F1) — daher hier KEIN wait_for.
            # CancelledError reicht der Coordinator unveraendert durch.
            action_result = await capability.run_migrated(capabilities, action, ctx)
        else:
            # Gesamt-Cap: ein haengender Browser blockiert die WS-Loop nie laenger.
            action_result = await asyncio.wait_for(
                execute_action(action, ctx, mutate_launcher), timeout=spec.timeout)
        obslog.event("action.finished", action=action.type, result_len=len(action_result))
        await send_action_event(sink, "done", action.type)
    except asyncio.CancelledError:
        # Nutzer hat "Stopp" gesagt: Historie markieren, Abbruch weiterreichen.
        obslog.event("action.cancelled", action=action.type)
        await send_action_event(sink, "error", action.type, "abgebrochen")
        raise
    except Exception as e:
        component = "browser" if spec.is_browser else "action"
        obslog.event("action.failed", action=action.type,
                     error_type=type(e).__name__, component=component)
        await send_action_event(sink, "error", action.type, type(e).__name__)
        await send_error(sink, component, f"Aktion '{spec.label}' fehlgeschlagen.", type(e).__name__)
        action_result = f"Fehler: {e}"

    if action.type == "OPEN":
        # Just opened browser, nothing to summarize
        return

    if action.type in actions.SPEAK_RESULT_ACTIONS:
        # Launcher-Meldungen sind bereits kurz und deutsch — keine LLM-Zusammenfassung.
        msg = action_result
        if not msg or msg.startswith("Fehler:"):
            msg = f"Das hat leider nicht funktioniert, {USER_ADDRESS}."
        ctx.remember("assistant", msg)
        await send_spoken_response(sink, msg)
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
            obslog.event("llm.request_failed", error_type=type(e).__name__)
            await send_error(sink, "llm", "KI-Anfrage fehlgeschlagen.", _llm_error_hint(e))
            summary = f"Das hat leider nicht funktioniert, {USER_ADDRESS}."
    else:
        summary = f"Das hat leider nicht funktioniert, {USER_ADDRESS}."

    # Anzeige-Version (mit Quellen) in die Historie — so funktionieren Folgefragen
    # wie "Öffne die zweite Quelle".
    ctx.remember("assistant", display_text or summary)
    await send_spoken_response(sink, summary, display_text)


async def process_message(ctx, user_text: str, sink, mutate_launcher=None,
                          capabilities=None):
    """Process message and send responses via WebSocket.

    ``mutate_launcher``: semantischer Launcher-Hook der KONKRETEN App-Runtime,
    vom WS-Endpoint injiziert (RFC-0003) — keine Runtime-/server-Abhaengigkeit hier.
    ``capabilities``: der runtime-eigene Capability-Coordinator (RFC-0007 §17),
    identisch vom WS-Endpoint injiziert. In der Pilotphase reichen wir ihn nur an die
    Ausfuehrung durch; die Piloten (Slices 5/7) dispatchen migrierte Pfade darueber.
    ``assistant_core`` haelt keine Rueckreferenz auf ``server`` oder eine globale Runtime.
    """
    # Wartet eine riskante Aktion auf Bestätigung? Ja => ausführen, Nein => verwerfen,
    # alles andere => Aktion verfällt und die Nachricht wird normal verarbeitet.
    # Die offene Bestaetigung wurde beim Turn-Start vom Session-Kern KONSUMIERT und
    # liegt hier als ``ctx.pending`` — identisch zum frueheren ``pop()``.
    pending = ctx.pending
    if pending is not None:
        verdict = actions.is_confirmation(user_text)
        if verdict is not None:
            ctx.remember("user", user_text)
            if verdict:
                await run_action_and_respond(ctx, pending, sink, mutate_launcher,
                                             capabilities=capabilities)
            else:
                msg = f"Verstanden, {USER_ADDRESS} — ich lasse es bleiben."
                ctx.remember("assistant", msg)
                await send_spoken_response(sink, msg)
            return

    # Refresh weather + tasks on activate — blockiert die Event-Loop nicht.
    if "activate" in user_text.lower():
        await asyncio.to_thread(refresh_data)

    ctx.remember("user", user_text)
    history = ctx.recent()

    # LLM call — Fehler duerfen die WS-Receive-Loop nicht beenden.
    try:
        response = await ai.messages.create(
            model=LLM_MODEL,
            max_tokens=500,
            system=get_system_prompt(),
            messages=history,
        )
    except Exception as e:
        obslog.event("llm.request_failed", error_type=type(e).__name__)
        await send_error(sink, "llm", "KI-Anfrage fehlgeschlagen.", _llm_error_hint(e))
        return
    reply = response.content[0].text
    obslog.event("llm.response_received", reply_len=len(reply))
    spoken_text, action, action_err = actions.parse_action(reply)
    if action_err:
        # Tag war vorhanden, aber ungueltig: nicht ausfuehren, nur Text sprechen.
        obslog.event("action.rejected")

    # Speak the main response immediately
    if spoken_text:
        ctx.remember("assistant", spoken_text)
        await send_spoken_response(sink, spoken_text)

    # Execute action if any
    if action:
        if action.type in actions.CONFIRM_ACTIONS:
            # Riskante Aktion: erst merken und mündlich rückfragen.
            ctx.request_confirmation(action)
            label = actions.label_for(action.type)
            detail = f" ({action.payload[:60]})" if action.payload else ""
            frage = f"Soll ich das wirklich ausführen: {label}{detail}? Ja oder Nein, {USER_ADDRESS}."
            ctx.remember("assistant", frage)
            await send_spoken_response(sink, frage)
            return
        await run_action_and_respond(ctx, action, sink, mutate_launcher,
                                     capabilities=capabilities)

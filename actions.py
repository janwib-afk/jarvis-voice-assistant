"""
Jarvis V2 — Action-Parsing & Validierung

Kapselt die fragile `[ACTION:...]`-Textauswertung der LLM-Antwort in eine
validierte, testbare Struktur. Bewusst ohne Netzwerk-/Config-Seiteneffekte,
damit es isoliert (ohne Serverstart) getestet werden kann.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

import app_launcher
import browser_tools
import clipboard_tools
import memory
import screen_capture

logger = logging.getLogger("jarvis.actions")

# Gleiche Regex wie bisher: [ACTION:TYP] optionaler payload bis Zeilenende.
ACTION_PATTERN = re.compile(r'\[ACTION:(\w+)\]\s*(.*?)$', re.DOTALL | re.MULTILINE)


@dataclass(frozen=True)
class ActionContext:
    """Request-scoped Ausfuehrungskontext einer Aktion (RFC-0001).

    Bewusst winzig und unveraenderlich: nur die querschnittlichen Abhaengigkeiten,
    die eine Action nicht selbst besitzen darf. Die stabilen Capability-Module
    (``browser_tools``/``memory``/``app_launcher``/``screen_capture``/
    ``clipboard_tools``) sind **direkte** Abhaengigkeiten der Implementation und
    stehen absichtlich NICHT im Kontext.

    - ``ai``: LLM-Client (prod: Anthropic, test: Fake) — der einzige echte Seam.
    - ``history``: unveraenderlicher Snapshot des Sitzungsverlaufs (kein
      ``session_id``, kein ``conversations``-Dict, keine ``Runtime``).
    - ``persist_launcher``: optionaler async Hook fuer Launcher-Persistenz;
      fehlt er, liefert die Action denselben sprechbaren Fehler wie bisher.
    """
    ai: Any = None
    history: tuple[dict, ...] = ()
    persist_launcher: Callable | None = None


@dataclass(frozen=True)
class PromptContext:
    """Kontext der Prompt-Selbstbeschreibung — nur Anzeige-/Persona-Werte."""
    user_name: str = ""
    user_address: str = ""
    app_names: str = ""
    profile_names: str = ""


@dataclass(frozen=True)
class ActionSpec:
    """Alle Metadaten, die Ausfuehrung UND die Selbstbeschreibung einer Aktion
    an einer Stelle (Registry-Eintrag, RFC-0001 Variant A).

    - ``payload``: "required" | "optional" | "none"
    - ``is_url``: Payload muss eine gueltige http(s)-URL sein
    - ``risk``: "low" | "confirm" — confirm-Aktionen brauchen ein muendliches Ja
    - ``timeout``: Gesamt-Cap in Sekunden fuer die Ausfuehrung
    - ``is_browser``: Fehler werden dem Frontend als Browser-Problem gemeldet
    - ``speaks_result``: Ergebnis ist bereits ein kurzer deutscher Satz und wird
      direkt gesprochen (keine LLM-Zusammenfassung)
    - ``summary_task``: aktionsspezifische Aufgabe fuer den Zusammenfassungs-Schritt
      (None = generische Kurz-Zusammenfassung)
    - ``execute``: ``async (payload, ctx) -> str`` — fuehrt die Aktion aus und gibt
      das ROHE Ergebnis zurueck. Timeout/Cancel/Zusammenfassung/TTS/WS-Events
      bleiben Sache der Orchestrierung.
    - ``describe``: ``(PromptContext) -> str`` — der Prompt-Absatz dieser Aktion.
      ``None`` = bewusst nicht im System-Prompt beworben (heute: BROWSE).
    - ``prompt_order``/``prompt_group``: deklarative Reihenfolge/Gruppe fuer den
      generierten Prompt ("core" immer, "launcher" nur bei konfigurierten Apps).
    """
    type: str
    label: str
    payload: str = "required"
    is_url: bool = False
    risk: str = "low"
    timeout: int = 60
    is_browser: bool = False
    speaks_result: bool = False
    summary_task: str | None = None
    summary_max_tokens: int = 250
    execute: Callable | None = None
    describe: Callable | None = None
    prompt_order: int | None = None
    prompt_group: str = "core"


DEFAULT_SUMMARY_TASK = "Fasse die folgenden Informationen KURZ zusammen, maximal 3 Sätze."


# ── Ausfuehrung (RFC-0001) ──────────────────────────────────────────────────
# Je Action eine ``execute``-Funktion, direkt am Registry-Eintrag referenziert.
# Sie geben das ROHE Ergebnis zurueck; Orchestrierung bleibt in assistant_core.

# Erfolgreiche Recherche-Ergebnisse enthalten pro Quelle eine solche Zeile —
# daraus baut die Orchestrierung die Quellenliste fuers Transcript und den Autosave.
RESEARCH_SOURCE_PREFIX = "QUELLE: "


async def _exec_search(payload: str, ctx: ActionContext) -> str:
    result = await browser_tools.search_and_read(payload)
    if "error" not in result:
        return (f"Seite: {result.get('title', '')}\nURL: {result.get('url', '')}"
                f"\n\n{result.get('content', '')[:2000]}")
    return f"Suche fehlgeschlagen: {result.get('error', '')}"


async def _exec_browse(payload: str, ctx: ActionContext) -> str:
    result = await browser_tools.visit(payload)
    if "error" not in result:
        return f"Seite: {result.get('title', '')}\n\n{result.get('content', '')[:2000]}"
    return f"Seite nicht erreichbar: {result.get('error', '')}"


async def _exec_open(payload: str, ctx: ActionContext) -> str:
    await browser_tools.open_url(payload)
    return f"Geöffnet: {payload}"


async def _exec_news(payload: str, ctx: ActionContext) -> str:
    result = await browser_tools.fetch_news()
    return result


async def _exec_research(payload: str, ctx: ActionContext) -> str:
    """Recherche-Modus: 3–5 Quellen lesen statt nur des ersten Treffers."""
    links = await browser_tools.search_links(payload, limit=5)
    if not links:
        return "Recherche fehlgeschlagen: keine Suchergebnisse gefunden."
    parts = [f"Recherche zu: {payload}"]
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
        parts.append(f"{RESEARCH_SOURCE_PREFIX}{title} — {link['url']}\n"
                     f"{result.get('content', '')}")
    if gelesen == 0:
        return "Recherche fehlgeschlagen: keine der Quellen war lesbar."
    if gelesen < 3:
        # Duenne Quellenlage ehrlich benennen statt Scheinsicherheit vorzulesen.
        parts.append(
            f"HINWEIS AN JARVIS: Nur {gelesen} Quelle(n) waren lesbar — sag ehrlich dazu, "
            "dass die Quellenlage dünn ist und die Antwort entsprechend vorsichtig zu werten ist."
        )
    return "\n\n".join(parts)


# ── Launcher-Sprachsteuerung ────────────────────────────────────────────────
# Wirkt ausschliesslich ueber die Profil-Schicht in app_launcher — nie ueber
# freie Kommandos. Antworten sind fertige deutsche Saetze (speaks_result).

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


async def _persist_launcher_or_error(ctx: ActionContext, new_launcher: dict,
                                     kind: str) -> str | None:
    """Persist ausschliesslich ueber ctx.persist_launcher; None = ok."""
    if ctx.persist_launcher is None:
        return "Profil-Änderungen sind gerade nicht möglich."
    errors = await ctx.persist_launcher(new_launcher, kind)
    if errors:
        return "Das konnte ich nicht speichern: " + " ".join(errors)
    return None


async def _exec_app_open(payload: str, ctx: ActionContext) -> str:
    result = await asyncio.to_thread(app_launcher.launch, payload)
    return result["message"]


async def _exec_profile_activate(payload: str, ctx: ActionContext) -> str:
    profile = app_launcher.find_profile(payload)
    if profile is None:
        return (f"Das Profil '{(payload or '').strip()}' kenne ich nicht. "
                f"Verfügbar: {_available_profiles()}.")
    if profile["id"] == app_launcher.ACTIVE_PROFILE:
        return f"{profile['name']} ist bereits aktiv."
    new_launcher = app_launcher.launcher_with_active(profile["id"])
    error = await _persist_launcher_or_error(ctx, new_launcher, "profile")
    if error:
        return error
    return f"{profile['name']} ist jetzt aktiv."


async def _exec_profile_status(payload: str, ctx: ActionContext) -> str:
    if payload.strip():
        profile = app_launcher.find_profile(payload)
        if profile is None:
            return (f"Das Profil '{payload.strip()}' kenne ich nicht. "
                    f"Verfügbar: {_available_profiles()}.")
    else:
        profile = app_launcher.find_profile(app_launcher.ACTIVE_PROFILE)
        if profile is None:
            return "Es ist kein Profil konfiguriert."
    enabled = [a["name"] for a in app_launcher.effective_apps(profile["id"])
               if a["autostart"]]
    is_active = profile["id"] == app_launcher.ACTIVE_PROFILE
    prefix = (f"Aktiv ist '{profile['name']}'." if is_active
              else f"Im Profil '{profile['name']}':")
    if not enabled:
        return f"{prefix} Beim Clap startet nichts automatisch."
    return f"{prefix} Beim Clap starten: {', '.join(enabled)}."


async def _set_autostart(payload: str, ctx: ActionContext, enabled: bool) -> str:
    app = app_launcher.find_app(payload)
    if app is None:
        return _unknown_app_message(payload)
    new_launcher = app_launcher.launcher_with_app_state(app["id"], autostart=enabled)
    if new_launcher is None:
        return _unknown_app_message(payload)
    error = await _persist_launcher_or_error(ctx, new_launcher, "autostart")
    if error:
        return error
    if enabled:
        return f"{app['name']} startet beim nächsten Clap mit."
    return f"{app['name']} ist aus dem Clap-Start raus."


async def _exec_autostart_on(payload: str, ctx: ActionContext) -> str:
    return await _set_autostart(payload, ctx, True)


async def _exec_autostart_off(payload: str, ctx: ActionContext) -> str:
    return await _set_autostart(payload, ctx, False)


async def _exec_app_place(payload: str, ctx: ActionContext) -> str:
    parsed, parse_error = parse_place_payload(payload)
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
    error = await _persist_launcher_or_error(ctx, new_launcher, "placement")
    if error:
        return error
    return f"{app['name']} liegt jetzt {_ZONE_SPEECH[zone]} {_MONITOR_SPEECH[monitor]}."


async def _exec_inbox_read(payload: str, ctx: ActionContext) -> str:
    if not memory.inbox_available():
        return "Inbox-Ordner nicht konfiguriert oder nicht gefunden."
    content = await asyncio.to_thread(memory.read_today_inbox_sync)
    if content is None:
        return f"Noch keine Einträge für heute ({time.strftime('%Y-%m-%d')})."
    return content


async def _exec_inbox_write(payload: str, ctx: ActionContext) -> str:
    kategorie, text = split_inbox_category(payload)
    return await memory.write_inbox_entry(text, kategorie, ai=ctx.ai)


async def _exec_memory_write(payload: str, ctx: ActionContext) -> str:
    return await asyncio.to_thread(memory.append_memory, payload)


async def _exec_memory_read(payload: str, ctx: ActionContext) -> str:
    content = await asyncio.to_thread(memory.read_memory_sync)
    if not content.strip():
        return "Ich habe mir dauerhaft noch nichts gemerkt."
    return f"Langzeit-Gedächtnis (dauerhaft gespeichert):\n{content}"


async def _exec_memory_forget(payload: str, ctx: ActionContext) -> str:
    return await asyncio.to_thread(memory.forget_memory, payload)


async def _exec_notes_recent(payload: str, ctx: ActionContext) -> str:
    notes = await asyncio.to_thread(memory.read_recent_notes_sync)
    if not notes:
        return "Keine Notizen gefunden — Vault nicht konfiguriert oder leer."
    return notes


async def _exec_project_context(payload: str, ctx: ActionContext) -> str:
    if not memory.vault_available():
        return ("Kein Obsidian-Vault konfiguriert — bitte den Vault-Pfad in den "
                "Einstellungen hinterlegen.")
    context = await asyncio.to_thread(memory.get_project_context_sync, payload)
    if not context:
        return f'Im Vault habe ich zu "{payload}" nichts Passendes gefunden.'
    return f'Frage: "{payload}"\n\n{context}'


async def _exec_screen(payload: str, ctx: ActionContext) -> str:
    return await screen_capture.describe_screen(ctx.ai, question=payload)


async def _exec_clipboard(payload: str, ctx: ActionContext) -> str:
    clip = await asyncio.to_thread(clipboard_tools.get_clipboard_text)
    if not clip:
        return "Die Zwischenablage ist leer oder enthält keinen Text."
    auftrag = payload or "Fasse den Inhalt kurz zusammen."
    return f"Auftrag: {auftrag}\n\nInhalt der Zwischenablage:\n{clip}"


async def _exec_clipboard_note(payload: str, ctx: ActionContext) -> str:
    clip = await asyncio.to_thread(clipboard_tools.get_clipboard_text)
    if not clip:
        return "Die Zwischenablage ist leer oder enthält keinen Text."
    return await memory.write_inbox_entry(clip, INBOX_FALLBACK_CATEGORY, ai=ctx.ai)


async def _exec_session_summary(payload: str, ctx: ActionContext) -> str:
    lines = [
        f"{'Du' if msg['role'] == 'user' else 'Jarvis'}: {msg['content']}"
        for msg in ctx.history[-40:]
    ]
    log = "\n".join(lines)[-6000:]
    if not log.strip():
        return "Diese Sitzung hat noch keinen nennenswerten Verlauf."
    return f"Sitzungsprotokoll:\n{log}"


# ── Selbstbeschreibung (RFC-0001 Slice P) ───────────────────────────────────
# Je Action der Prompt-Absatz, den bisher build_system_prompt hardcodiert hat —
# Text WOERTLICH uebernommen (byte-genaue Goldens schuetzen das). ``describe=None``
# heisst: bewusst nicht beworben (BROWSE ist registriert + ausfuehrbar, aber der
# System-Prompt hat sie noch nie erwaehnt).

# Gemeinsamer Suffix der Launcher-Gruppe — erscheint nur mit konfigurierten Apps.
def _describe_launcher_rules(c: PromptContext) -> str:
    return (
        f"Launcher-Regeln: Nur konfigurierte Apps und vorhandene Profile verwenden. Ist ein App- oder "
        f"Profilname unklar, frag nach statt zu raten. Persistente Änderungen (Autostart, Platzierung, "
        f"Profilwechsel) nur bei klarer Absicht von {c.user_address}. Profile löschen, anlegen oder "
        f"überschreiben geht NICHT per Sprache — verweise dafür auf das Jarvis-Fenster."
    )


def _d_search(c: PromptContext) -> str:
    return ("[ACTION:SEARCH] suchbegriff - Schnelle Websuche: erstes Ergebnis lesen und "
            "zusammenfassen. Für einfache Fakten.")


def _d_research(c: PromptContext) -> str:
    return (f"[ACTION:RESEARCH] thema - Gründliche Recherche: liest 3-5 Quellen und liefert eine "
            f"Zusammenfassung mit Quellenliste. Nutze wenn {c.user_address} \"recherchiere\" sagt "
            f"oder eine fundierte Antwort mit mehreren Quellen sinnvoll ist.")


def _d_open(c: PromptContext) -> str:
    return "[ACTION:OPEN] url - URL im Browser öffnen"


def _d_screen(c: PromptContext) -> str:
    return ("[ACTION:SCREEN] optionale frage - Bildschirm ansehen. Ohne Frage: kurz beschreiben. "
            "Mit Frage (z.B. \"Was ist das Problem?\", \"Fasse diese Seite zusammen\", \"Was soll "
            "ich als nächstes tun?\"): die Frage anhand des Bildschirms beantworten. WICHTIG: Bei "
            "SCREEN schreibe KEINEN Text vor die Aktion.")


def _d_news(c: PromptContext) -> str:
    return ("[ACTION:NEWS] - Aktuelle Weltnachrichten abrufen. Nutze diese Aktion wenn nach News, "
            "Nachrichten, was in der Welt passiert, aktuelle Lage oder Weltgeschehen gefragt wird. "
            "Schreibe einen kurzen Satz davor wie \"Ich schaue nach den aktuellen Nachrichten.\"")


def _d_inbox_read(c: PromptContext) -> str:
    return (f"[ACTION:INBOX_READ] - Liest die heutigen Einträge aus der Obsidian-Inbox. Nutze wenn "
            f"{c.user_address} fragt was heute notiert wurde oder einen Tagesrückblick möchte.")


def _d_inbox_write(c: PromptContext) -> str:
    return (f"[ACTION:INBOX_WRITE] [Kategorie] text - Schreibt einen Eintrag in die heutige "
            f"Inbox-Datei. Kategorie ist GENAU EINE von: Idee, Aufgabe, Termin, Recherche, "
            f"Erinnerung — wähle die passendste. Beispiel: [ACTION:INBOX_WRITE] [Termin] Zahnarzt "
            f"Dienstag 9 Uhr. Nutze IMMER wenn {c.user_address} etwas festhalten, notieren, "
            f"aufschreiben oder merken möchte. Frag nicht ob, tu es einfach. Formuliere den Text "
            f"klar und strukturiert.")


def _d_memory_write(c: PromptContext) -> str:
    return (f"[ACTION:MEMORY_WRITE] text - Speichert eine Information DAUERHAFT im "
            f"Langzeit-Gedächtnis (Präferenzen, laufende Projekte, offene Loops). Nutze NUR wenn "
            f"{c.user_address} ausdrücklich sagt, dass du dir etwas dauerhaft/für die Zukunft merken "
            f"sollst (z.B. \"merk dir dauerhaft\", \"vergiss nie\"). Tagesnotizen gehören in "
            f"INBOX_WRITE. Speichere NIEMALS sensible Inhalte (Passwörter, Gesundheit, Finanzen) "
            f"ohne ausdrückliche Aufforderung.")


def _d_memory_read(c: PromptContext) -> str:
    return (f"[ACTION:MEMORY_READ] - Zeigt bzw. fasst zusammen, was du dauerhaft über {c.user_name} "
            f"gespeichert hast. Nutze wenn {c.user_address} fragt \"Was weißt du über mich?\", \"Was "
            f"hast du dir gemerkt?\" oder Ähnliches.")


def _d_memory_forget(c: PromptContext) -> str:
    return (f"[ACTION:MEMORY_FORGET] stichwort - Löscht einen passenden Eintrag DAUERHAFT aus dem "
            f"Langzeit-Gedächtnis. Nutze wenn {c.user_address} sagt \"vergiss ...\" o.Ä. Gib als "
            f"Payload knapp das Thema/Stichwort an, das vergessen werden soll (nicht das Wort "
            f"\"vergiss\" selbst). Diese Aktion wird vor der Ausführung sicherheitshalber noch einmal "
            f"mündlich bestätigt.")


def _d_notes_recent(c: PromptContext) -> str:
    return (f"[ACTION:NOTES_RECENT] - Fasst die zuletzt bearbeiteten Notizen aus dem Vault zusammen. "
            f"Nutze wenn {c.user_address} z.B. \"Fasse meine letzten Notizen zusammen\" sagt oder "
            f"wissen will woran er zuletzt gearbeitet hat.")


def _d_project_context(c: PromptContext) -> str:
    return (f"[ACTION:PROJECT_CONTEXT] frage oder projektname - Durchsucht den Obsidian-Vault lokal "
            f"nach passenden Notizen und antwortet mit deren Kontext. Nutze wenn {c.user_address} "
            f"nach dem Stand, den nächsten Schritten oder offenen Punkten eines Projekts fragt, "
            f"Kontext zu einem Thema aus seinen Notizen möchte oder fragt \"was weißt du über mein "
            f"Projekt ...\".")


def _d_clipboard(c: PromptContext) -> str:
    return (f"[ACTION:CLIPBOARD] auftrag - Verarbeitet den Text in der Zwischenablage (auftrag z.B. "
            f"\"zusammenfassen\", \"übersetzen\", \"erklären\"). Nutze wenn {c.user_address} von "
            f"Zwischenablage, Clipboard oder \"das Kopierte\" spricht.")


def _d_clipboard_note(c: PromptContext) -> str:
    return (f"[ACTION:CLIPBOARD_NOTE] - Speichert den Text aus der Zwischenablage als Inbox-Notiz. "
            f"Nutze wenn {c.user_address} aus der Zwischenablage eine Notiz machen möchte.")


def _d_session_summary(c: PromptContext) -> str:
    return (f"[ACTION:SESSION_SUMMARY] - Fasst zusammen was in dieser Sitzung besprochen und erledigt "
            f"wurde. Nutze bei \"Was haben wir heute gemacht?\" oder am Sitzungsende. Möchte "
            f"{c.user_address} das Fazit danach speichern, nutze INBOX_WRITE.")


def _d_app_open(c: PromptContext) -> str:
    return (f"[ACTION:APP_OPEN] app-name - Öffnet eine konfigurierte lokale App, z.B. Obsidian, "
            f"VS Code oder Chrome. Nutze diese Aktion, wenn {c.user_address} dich bittet, eine lokale App "
            f"oder ein Programm zu öffnen. Es können NUR konfigurierte Apps geöffnet werden. "
            f"Schreibe KEINEN Text vor die Aktion. Verfügbare Apps: {c.app_names}")


def _d_profile_activate(c: PromptContext) -> str:
    return (f"[ACTION:PROFILE_ACTIVATE] profilname - Aktiviert ein vorhandenes Session-Profil für den "
            f"Clap-Start. Nutze es bei Aussagen wie \"aktiviere Coding-Modus\" oder \"wechsle ins "
            f"Research-Profil\". Verfügbare Profile: {c.profile_names}")


def _d_profile_status(c: PromptContext) -> str:
    return ("[ACTION:PROFILE_STATUS] optionaler profilname - Sagt, welches Profil aktiv ist und welche "
            "Apps beim Clap starten. Ohne Payload: das aktive Profil. Nutze bei \"Welches Profil ist "
            "aktiv?\" oder \"Welche Apps starten im Research-Profil?\".")


def _d_autostart_on(c: PromptContext) -> str:
    return ("[ACTION:APP_AUTOSTART_ON] app-name - Nimmt eine konfigurierte App im aktiven Profil in den "
            "Clap-Start auf. Nutze bei \"starte X beim nächsten Clap mit\".")


def _d_autostart_off(c: PromptContext) -> str:
    return ("[ACTION:APP_AUTOSTART_OFF] app-name - Nimmt eine konfigurierte App im aktiven Profil aus "
            "dem Clap-Start. Nutze bei \"nimm X aus dem Clap-Start\".")


def _d_app_place(c: PromptContext) -> str:
    return ("[ACTION:APP_PLACE] app-name | monitor | zone - Setzt die Startposition einer konfigurierten "
            "App im aktiven Profil. monitor: primary, left, right, leftmost, rightmost. zone: fullscreen, "
            "left_half, right_half, top_half, bottom_half, top_left, top_right, bottom_left, bottom_right, "
            "center. Beispiel: [ACTION:APP_PLACE] Obsidian | left | right_half")


# Zentrale Registry: nur hier eingetragene Aktionen werden geparst/ausgefuehrt.
REGISTRY: dict[str, ActionSpec] = {spec.type: spec for spec in (
    ActionSpec("SEARCH", "Websuche", is_browser=True, execute=_exec_search,
               describe=_d_search, prompt_order=1),
    ActionSpec("BROWSE", "Seite lesen", is_url=True, is_browser=True,
               execute=_exec_browse),  # describe=None: bewusst nicht beworben
    ActionSpec("OPEN", "Browser öffnen", is_url=True, is_browser=True,
               execute=_exec_open, describe=_d_open, prompt_order=3),
    ActionSpec("APP_OPEN", "App öffnen", timeout=15, speaks_result=True,
               execute=_exec_app_open,
               describe=_d_app_open, prompt_order=16, prompt_group="launcher"),
    # Launcher-Sprachsteuerung (Phase 5): wirkt ueber die Profil-Schicht in
    # app_launcher — nie ueber freie Kommandos. Antworten sind fertige Saetze.
    ActionSpec("PROFILE_ACTIVATE", "Profil aktivieren", timeout=15, speaks_result=True,
               execute=_exec_profile_activate,
               describe=_d_profile_activate, prompt_order=17, prompt_group="launcher"),
    ActionSpec("PROFILE_STATUS", "Profil-Status", payload="optional", timeout=15,
               speaks_result=True, execute=_exec_profile_status,
               describe=_d_profile_status, prompt_order=18, prompt_group="launcher"),
    ActionSpec("APP_AUTOSTART_ON", "Clap-Start an", timeout=15, speaks_result=True,
               execute=_exec_autostart_on,
               describe=_d_autostart_on, prompt_order=19, prompt_group="launcher"),
    ActionSpec("APP_AUTOSTART_OFF", "Clap-Start aus", timeout=15, speaks_result=True,
               execute=_exec_autostart_off,
               describe=_d_autostart_off, prompt_order=20, prompt_group="launcher"),
    ActionSpec("APP_PLACE", "App platzieren", timeout=15, speaks_result=True,
               execute=_exec_app_place,
               describe=_d_app_place, prompt_order=21, prompt_group="launcher"),
    ActionSpec("SCREEN", "Bildschirm ansehen", payload="optional",
               execute=_exec_screen, describe=_d_screen, prompt_order=4),
    ActionSpec("NEWS", "Nachrichten", payload="none", is_browser=True,
               execute=_exec_news, describe=_d_news, prompt_order=5),
    ActionSpec(
        "INBOX_READ", "Inbox lesen", payload="none", summary_max_tokens=350,
        summary_task=(
            "Gib einen kurzen, strukturierten Tagesrückblick über die heutigen Notizen: "
            "gruppiere nach Kategorie (Idee, Aufgabe, Termin, Recherche, Erinnerung, Notiz) "
            "und fasse knapp zusammen. Maximal 5 Sätze."
        ),
        execute=_exec_inbox_read, describe=_d_inbox_read, prompt_order=6,
    ),
    ActionSpec("INBOX_WRITE", "Inbox-Eintrag", execute=_exec_inbox_write,
               describe=_d_inbox_write, prompt_order=7),
    ActionSpec("MEMORY_WRITE", "Merken", execute=_exec_memory_write,
               describe=_d_memory_write, prompt_order=8),
    ActionSpec(
        "MEMORY_READ", "Gedächtnis lesen", payload="none", summary_max_tokens=350,
        summary_task=(
            "Fasse zusammen, was du dauerhaft über den Nutzer weißt (Präferenzen, "
            "Projekte, offene Loops). Ordne es knapp und nenne die Punkte. Maximal 5 Sätze. "
            "Steht dort nichts, sag das ehrlich."
        ),
        execute=_exec_memory_read, describe=_d_memory_read, prompt_order=9,
    ),
    ActionSpec(
        "MEMORY_FORGET", "Vergessen", risk="confirm",
        summary_task=(
            "Bestätige kurz und freundlich, was du aus dem Langzeit-Gedächtnis gelöscht "
            "hast (oder dass es nichts Passendes gab). Maximal 2 Sätze."
        ),
        execute=_exec_memory_forget, describe=_d_memory_forget, prompt_order=10,
    ),
    ActionSpec(
        "RESEARCH", "Recherche", is_browser=True, timeout=180, summary_max_tokens=350,
        summary_task=(
            "Fasse die Rechercheergebnisse aus den Quellen zu einer präzisen Antwort "
            "zusammen. Maximal 5 Sätze. Nenne KEINE URLs im Text."
        ),
        execute=_exec_research, describe=_d_research, prompt_order=2,
    ),
    ActionSpec(
        "CLIPBOARD", "Zwischenablage", payload="optional",
        summary_task=(
            "Führe den genannten Auftrag auf dem Inhalt der Zwischenablage aus. "
            "Antworte kurz und präzise."
        ),
        execute=_exec_clipboard, describe=_d_clipboard, prompt_order=13,
    ),
    ActionSpec("CLIPBOARD_NOTE", "Clipboard-Notiz", payload="none",
               execute=_exec_clipboard_note,
               describe=_d_clipboard_note, prompt_order=14),
    ActionSpec(
        "NOTES_RECENT", "Letzte Notizen", payload="none", summary_max_tokens=350,
        summary_task=(
            "Fasse die zuletzt bearbeiteten Notizen kurz zusammen und nenne dabei die "
            "Notiznamen, damit klar ist woran zuletzt gearbeitet wurde. Maximal 5 Sätze."
        ),
        execute=_exec_notes_recent, describe=_d_notes_recent, prompt_order=11,
    ),
    ActionSpec(
        "PROJECT_CONTEXT", "Projekt-Kontext", summary_max_tokens=350,
        summary_task=(
            "Nutze den folgenden Vault-Kontext, um die Frage projektbezogen zu "
            "beantworten. Wenn der Kontext nicht reicht, sag das ehrlich. Maximal 5 Sätze."
        ),
        execute=_exec_project_context, describe=_d_project_context, prompt_order=12,
    ),
    ActionSpec(
        "SESSION_SUMMARY", "Sitzungsfazit", payload="none", summary_max_tokens=350,
        summary_task=(
            "Fasse kurz zusammen, was in dieser Sitzung besprochen und erledigt wurde. "
            "Maximal 5 Sätze."
        ),
        execute=_exec_session_summary, describe=_d_session_summary, prompt_order=15,
    ),
)}

# Abgeleitete Views — bestehende Aufrufer/Tests arbeiten weiter mit Sets.
ALLOWED_ACTIONS = frozenset(REGISTRY)
PAYLOAD_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.payload == "required")
NO_PAYLOAD_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.payload == "none")
OPTIONAL_PAYLOAD_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.payload == "optional")
URL_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.is_url)
BROWSER_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.is_browser)

# Aktionen, die erst nach muendlicher Bestaetigung ausgefuehrt werden.
# Aktuell: MEMORY_FORGET (loescht dauerhaft). Weitere riskante Aktionen bekommen
# einfach risk="confirm" in der Registry und sind damit automatisch abgesichert.
CONFIRM_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.risk == "confirm")

# Aktionen, deren Ergebnis direkt gesprochen wird (kein Zusammenfassungs-LLM).
SPEAK_RESULT_ACTIONS = frozenset(t for t, s in REGISTRY.items() if s.speaks_result)


def _described(group: str) -> list[ActionSpec]:
    """Beworbene Actions einer Gruppe in deklarativer Prompt-Reihenfolge."""
    specs = [sp for sp in REGISTRY.values()
             if sp.describe is not None and sp.prompt_group == group]
    return sorted(specs, key=lambda sp: sp.prompt_order)


def render_action_block(c: PromptContext) -> str:
    """Den Action-Block des System-Prompts aus den Selbstbeschreibungen erzeugen.

    Eine Quelle der Wahrheit: der Text kommt aus den Registry-Eintraegen selbst.
    Die Launcher-Gruppe (inkl. gemeinsamem Regel-Suffix) erscheint nur, wenn Apps
    konfiguriert sind — genau wie bisher.
    """
    block = "\n".join(sp.describe(c) for sp in _described("core"))
    if c.app_names:
        launcher = [sp.describe(c) for sp in _described("launcher")]
        launcher.append(_describe_launcher_rules(c))
        block += "\n" + "\n".join(launcher)
    return block


def spec_for(action_type: str) -> ActionSpec:
    """Registry-Eintrag einer (bereits validierten) Aktion."""
    return REGISTRY[action_type]


def label_for(action_type: str) -> str:
    """Anzeige-Label; unbekannte Typen fallen auf den Typnamen zurueck."""
    spec = REGISTRY.get(action_type)
    return spec.label if spec else action_type

# Kategorien fuer Inbox-Eintraege; unbekannte/fehlende Kategorie => "Notiz".
INBOX_CATEGORIES = ("Idee", "Aufgabe", "Termin", "Recherche", "Erinnerung")
INBOX_FALLBACK_CATEGORY = "Notiz"

# Hosts, die als lokaler Origin fuer den WebSocket erlaubt sind
_ALLOWED_ORIGIN_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Erfasst ein fuehrendes "schema:" (mit oder ohne //). Wird genutzt, um
# gefaehrliche Schemata (javascript:, data:, file: ...) sicher zu erkennen.
_SCHEME_RE = re.compile(r'^([a-zA-Z][a-zA-Z0-9+.\-]*):(.*)$', re.DOTALL)


@dataclass(frozen=True)
class Action:
    """Eine validierte, ausfuehrbare Aktion."""
    type: str
    payload: str = ""


def normalize_url(raw: str) -> str | None:
    """Normalisiert und validiert eine URL.

    - Fehlt das Schema, wird ``https://`` vorangestellt (LLM liefert oft bare Domains).
    - Erlaubt sind ausschliesslich ``http`` und ``https`` (blockt ``javascript:``,
      ``file:``, ``data:`` u.ae.).
    - Gibt die normalisierte URL zurueck oder ``None``, wenn sie ungueltig ist.
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    m = _SCHEME_RE.match(raw)
    if m:
        scheme = m.group(1).lower()
        rest = m.group(2)
        if scheme in ("http", "https"):
            # Vollstaendige URL — Authority (netloc) muss vorhanden sein.
            try:
                parsed = urlparse(raw)
            except ValueError:
                return None
            return raw if parsed.netloc else None
        # Kein echtes Schema, sondern "host:port" (rest = nur Ziffern)?
        # Dann unten https:// voranstellen. Sonst ist es ein fremdes Schema
        # (javascript:, data:, file:, mailto: ...) und wird abgelehnt.
        if not rest.isdigit():
            return None

    raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if not parsed.netloc:
        return None
    return raw


def parse_action(text: str) -> tuple[str, Action | None, str | None]:
    """Trennt gesprochenen Text und Aktion aus einer LLM-Antwort.

    Rueckgabe: ``(spoken_text, action_or_None, error_or_None)``.

    - ``spoken_text`` ist die Antwort ohne den Action-Tag.
    - Ist kein Tag vorhanden, sind ``action`` und ``error`` ``None``.
    - Ist der Tag vorhanden aber ungueltig (unbekannter Typ, fehlender Payload,
      ungueltige URL), ist ``action`` ``None`` und ``error`` enthaelt den Grund.
      Der Aufrufer spricht dann nur ``spoken_text`` und fuehrt nichts aus.
    """
    match = ACTION_PATTERN.search(text)
    if not match:
        return text.strip(), None, None

    spoken = text[:match.start()].strip()
    action_type = match.group(1).upper()
    payload = match.group(2).strip()

    if action_type not in ALLOWED_ACTIONS:
        return spoken, None, f"unbekannter Action-Typ: {action_type}"

    if action_type in NO_PAYLOAD_ACTIONS:
        payload = ""
    elif action_type in OPTIONAL_PAYLOAD_ACTIONS:
        pass  # Payload darf leer sein (z.B. SCREEN ohne Kontextfrage)
    elif not payload:
        return spoken, None, f"fehlender Payload fuer {action_type}"

    if action_type in URL_ACTIONS:
        url = normalize_url(payload)
        if url is None:
            return spoken, None, f"ungueltige URL fuer {action_type}"
        payload = url

    return spoken, Action(action_type, payload), None


# ── APP_PLACE: "app | monitor | zone" ───────────────────────────────────────
# Bewusste Kopie der Placement-Allowlists (Entkopplungs-Muster wie zwischen
# config_loader und app_launcher) — ein Sync-Test verhindert Drift.
PLACE_MONITORS = ("primary", "left", "right", "leftmost", "rightmost")
PLACE_ZONES = ("fullscreen", "left_half", "right_half", "top_half", "bottom_half",
               "top_left", "top_right", "bottom_left", "bottom_right", "center")

# Deutsche Aliasse — das LLM soll kanonische Werte liefern, aber gesprochene
# Formen ("linke Haelfte", "Vollbild") werden tolerant angenommen.
_MONITOR_ALIASES = {
    "links": "left", "linker monitor": "left",
    "rechts": "right", "rechter monitor": "right",
    "primär": "primary", "primaer": "primary", "haupt": "primary",
    "hauptmonitor": "primary", "primärer monitor": "primary",
    "primaerer monitor": "primary",
    "ganz links": "leftmost", "ganz rechts": "rightmost",
}
_ZONE_ALIASES = {
    "vollbild": "fullscreen", "fullscreen": "fullscreen", "maximiert": "fullscreen",
    "linke hälfte": "left_half", "linke haelfte": "left_half",
    "rechte hälfte": "right_half", "rechte haelfte": "right_half",
    "obere hälfte": "top_half", "obere haelfte": "top_half", "oben": "top_half",
    "untere hälfte": "bottom_half", "untere haelfte": "bottom_half", "unten": "bottom_half",
    "oben links": "top_left", "oben rechts": "top_right",
    "unten links": "bottom_left", "unten rechts": "bottom_right",
    "mitte": "center", "zentriert": "center", "zentrum": "center",
}

_PLACE_FORMAT_HINT = "Format: app | monitor | zone (z.B. Obsidian | left | right_half)"


def _normalize_place_token(raw: str, canonical: tuple, aliases: dict) -> str | None:
    token = re.sub(r"\s+", " ", (raw or "").strip().casefold())
    if token in canonical:
        return token
    return aliases.get(token)


def parse_place_payload(payload: str) -> tuple[tuple[str, str, str] | None, str | None]:
    """Zerlegt einen APP_PLACE-Payload ``app | monitor | zone``.

    Rueckgabe: ``((app_query, monitor, zone), None)`` bei Erfolg, sonst
    ``(None, fehlertext)`` — der Fehlertext ist deutsch und direkt sprechbar.
    Monitor/Zone werden gegen die Allowlists geprueft; deutsche Aliasse
    ("linke Haelfte", "Vollbild") werden auf kanonische Werte gemappt.
    """
    parts = [s.strip() for s in (payload or "").split("|")]
    if len(parts) != 3 or not all(parts):
        return None, f"Ich brauche App, Monitor und Zone. {_PLACE_FORMAT_HINT}"
    app_query = parts[0]
    monitor = _normalize_place_token(parts[1], PLACE_MONITORS, _MONITOR_ALIASES)
    if monitor is None:
        return None, ("Den Monitor kenne ich nicht — erlaubt: "
                      + ", ".join(PLACE_MONITORS) + ".")
    zone = _normalize_place_token(parts[2], PLACE_ZONES, _ZONE_ALIASES)
    if zone is None:
        return None, ("Die Zone kenne ich nicht — erlaubt: "
                      + ", ".join(PLACE_ZONES) + ".")
    return (app_query, monitor, zone), None


# Fuehrendes "[Kategorie]" am Anfang eines INBOX_WRITE-Payloads.
_CATEGORY_RE = re.compile(r'^\[([^\]]{1,30})\]\s*(.*)$', re.DOTALL)


def split_inbox_category(payload: str) -> tuple[str, str]:
    """Trennt ein fuehrendes ``[Kategorie]`` vom Eintragstext.

    Rueckgabe: ``(kategorie, text)``. Die Kategorie wird case-insensitiv gegen
    ``INBOX_CATEGORIES`` geprueft; bei unbekannter/fehlender Kategorie oder
    leerem Resttext bleibt der Payload unveraendert und die Kategorie ist
    ``INBOX_FALLBACK_CATEGORY`` — es geht nie Text verloren.
    """
    text = (payload or "").strip()
    m = _CATEGORY_RE.match(text)
    if m:
        candidate = m.group(1).strip()
        rest = m.group(2).strip()
        if rest:
            for cat in INBOX_CATEGORIES:
                if candidate.lower() == cat.lower():
                    return cat, rest
    return INBOX_FALLBACK_CATEGORY, text


# Ja/Nein-Erkennung fuer den Bestaetigungs-Dialog riskanter Aktionen.
_YES_WORDS = frozenset({
    "ja", "jawohl", "jep", "jup", "yes", "genau", "gerne", "bestaetige",
    "bestätige", "einverstanden", "natuerlich", "natürlich", "sicher",
    "ok", "okay", "mach", "tu", "los",
})
_NO_WORDS = frozenset({
    "nein", "ne", "nö", "noe", "nicht", "niemals", "abbrechen", "abbruch",
    "stopp", "stop", "lass", "vergiss", "no", "kein", "keine",
})


def is_confirmation(text: str) -> bool | None:
    """Deutet eine Nutzerantwort als Bestaetigung.

    Rueckgabe: ``True`` (Ja), ``False`` (Nein) oder ``None`` (weder — der
    Aufrufer behandelt die Nachricht dann als normale Anfrage). Verneinungen
    gewinnen: "Nein, mach das nicht" ist ein Nein, obwohl "mach" vorkommt.
    """
    words = re.findall(r"\w+", (text or "").lower())
    if not words:
        return None
    if any(w in _NO_WORDS for w in words[:6]):
        return False
    if words[0] in _YES_WORDS:
        return True
    if len(words) <= 6 and any(w in _YES_WORDS for w in words):
        return True
    return None


# Stopp-Erkennung: Woerter, die fuer sich genommen "hoer auf" bedeuten …
_STOP_WORDS = frozenset({
    "stopp", "stop", "stoppe", "stoppen", "halt", "abbrechen", "abbruch",
    "aufhoeren", "aufhören", "still", "ruhe", "leise", "cancel",
})
# … plus Fuellwoerter, die eine Stopp-Aeusserung nicht entkraeften ("Jarvis, bitte stopp!").
_STOP_FILLER = frozenset({
    "jarvis", "bitte", "mal", "jetzt", "sofort", "das", "es", "sei", "hoer",
    "hör", "auf", "damit", "ok", "okay", "danke",
})
# Mehrwort-Formen, deren Einzelwoerter allein zu schwach sind.
_STOP_PHRASES = ("hoer auf", "hör auf", "sei still", "sei ruhig")


def is_stop_command(text: str) -> bool:
    """Erkennt eine reine Stopp-Aeusserung ("Stopp", "Jarvis, hör auf", "abbrechen").

    Bewusst konservativ: kurze Nachricht (max. 5 Woerter), mindestens ein
    Stop-Wort/-Ausdruck und KEIN inhaltliches Wort — "Wie stoppe ich einen
    Container?" ist eine normale Frage, kein Stopp.
    """
    words = re.findall(r"\w+", (text or "").lower())
    if not words or len(words) > 5:
        return False
    joined = " ".join(words)
    has_stop = any(w in _STOP_WORDS for w in words) or any(p in joined for p in _STOP_PHRASES)
    if not has_stop:
        return False
    return all(w in _STOP_WORDS or w in _STOP_FILLER for w in words)


def is_allowed_origin(origin: str | None) -> bool:
    """Prueft, ob ein WebSocket-``Origin``-Header lokal (erlaubt) ist.

    Erlaubt nur ``http``/``https`` mit Hostname localhost/127.0.0.1/::1.
    Fehlt der Origin oder ist er fremd, wird ``False`` zurueckgegeben.
    """
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if host is None:
        return False
    return host.lower() in _ALLOWED_ORIGIN_HOSTS


def is_origin_acceptable(origin: str | None, token_valid: bool) -> bool:
    """Origin-Policy fuer den WebSocket-Handshake.

    - Lokale Origins (localhost/127.0.0.1/::1) sind erlaubt (``is_allowed_origin``).
    - Der literale Origin ``"null"`` wird **ausschliesslich** mit gueltigem Token
      akzeptiert. Grund: manche pywebview/WebView2-Sandbox-Kontexte senden ``null``
      statt eines echten Origins; ohne diese Ausnahme koennte sich das Fenster nicht
      verbinden. Das Token (Same-Origin-Secret) verhindert Missbrauch durch Fremde.
    - Ein komplett fehlender Origin (``None``) sowie fremde Hosts bleiben abgelehnt
      (Browser senden bei WebSockets immer einen Origin-Header).
    """
    if is_allowed_origin(origin):
        return True
    if origin == "null" and token_valid:
        return True
    return False

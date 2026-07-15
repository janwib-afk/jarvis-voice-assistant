"""
Jarvis V2 — App-Launcher

Sichere Command-Schicht zum Starten lokaler Apps: Es koennen ausschliesslich
Apps aus der konfigurierten Registry (``config.apps``) gestartet werden —
niemals freie Shell-Kommandos. Sprach-Aktion (APP_OPEN) und UI-Klick
(POST /commands/app/open) nutzen beide ``launch()``.

Seit Phase 4 ist die Registry nur noch fuer App-IDENTITAET zustaendig
({"id", "name", "command", "type", "process_name"}); der ZUSTAND
(``autostart`` + ``placement``) lebt pro Session-Profil im
``launcher``-Block: {"active_profile", "profiles": [{"id", "name",
"apps": {app_id: {"autostart", "placement"?}}}]}. Fehlt der Block,
wird ein "default"-Profil aus den alten App-Level-Feldern abgeleitet
(Rueckwaertskompatibilitaet) — die erste Mutation materialisiert ihn.

Registry-Eintraege sind rueckwaerts-kompatibel: einfache Strings
("obsidian://open") oder strukturierte Objekte. Apps ohne Eintrag im
Profil gelten als ``autostart: true`` ohne Placement. launch-session.ps1
wendet nur EXPLIZIT im Profil gespeicherte Placements an; der
normalisierte Default (primary/fullscreen) dient nur der UI-Anzeige.
``process_name`` hilft der Fensterfindung (noetig fuer http/https-URLs)
und bleibt wie ``command`` serverseitig.
"""

import logging
import os
import re
import shutil
import subprocess

logger = logging.getLogger("jarvis.apps")

APP_TYPES = ("url", "process")

# Bewusste Duplikation der config_loader-Konstanten (wie APP_TYPES) —
# die Module bleiben entkoppelt, config_loader ist ein Leaf-Modul.
PLACEMENT_MONITORS = ("primary", "left", "right", "leftmost", "rightmost")
PLACEMENT_ZONES = ("fullscreen", "left_half", "right_half", "top_half", "bottom_half",
                   "top_left", "top_right", "bottom_left", "bottom_right", "center")
DEFAULT_PLACEMENT = {"monitor": "primary", "zone": "fullscreen"}

# Normalisierter Zustand — gesetzt via configure(): Registry (Identitaet)
# + Session-Profile (autostart/placement pro App, pro Profil) + aktives Profil.
APPS: list[dict] = []
PROFILES: list[dict] = []
ACTIVE_PROFILE: str = "default"


def _slugify(text: str) -> str:
    """Lesbarer Kleinbuchstaben-Slug fuer App-IDs (z.B. "VS Code" -> "vs-code")."""
    slug = re.sub(r"[^a-z0-9_-]+", "-", text.strip().casefold()).strip("-")
    return slug or "app"


def _derive_id_and_name(command: str, app_type: str) -> tuple[str, str]:
    """ID/Name aus dem Befehl ableiten: URL-Schema bzw. Dateiname ohne Endung."""
    if app_type == "url":
        base = command.split("://", 1)[0]
    else:
        base = os.path.splitext(os.path.basename(command.rstrip("\\/")))[0] or command
    return _slugify(base), base.capitalize() if base.islower() else base


def _normalize_placement(raw) -> dict:
    """Placement tolerant normalisieren: Defaults primary/fullscreen, Teilobjekte
    auffuellen, Unbrauchbares faellt mit Warnung auf den Default zurueck — die
    harte Ablehnung passiert beim Settings-Save in config_loader."""
    placement = dict(DEFAULT_PLACEMENT)
    if raw is None:
        return placement
    if not isinstance(raw, dict):
        logger.warning("Ungueltiges placement-Objekt — Standard (primary/fullscreen) verwendet.")
        return placement
    if raw.get("monitor") in PLACEMENT_MONITORS:
        placement["monitor"] = raw["monitor"]
    elif "monitor" in raw:
        logger.warning("Ungueltiger placement.monitor — Standard 'primary' verwendet.")
    if raw.get("zone") in PLACEMENT_ZONES:
        placement["zone"] = raw["zone"]
    elif "zone" in raw:
        logger.warning("Ungueltige placement.zone — Standard 'fullscreen' verwendet.")
    return placement


def normalize_app_entry(entry) -> dict | None:
    """Einen Registry-Eintrag (String oder Objekt) auf die Objektform bringen.

    Gibt ``None`` fuer unbrauchbare Eintraege zurueck (fehlender Befehl) —
    die harte Ablehnung passiert bereits beim Settings-Save in config_loader.
    """
    if isinstance(entry, str):
        command = entry.strip()
        if not command:
            return None
        app_type = "url" if "://" in command else "process"
        app_id, name = _derive_id_and_name(command, app_type)
        return {"id": app_id, "name": name, "command": command,
                "type": app_type, "autostart": True,
                "placement": dict(DEFAULT_PLACEMENT)}

    if isinstance(entry, dict):
        command = str(entry.get("command", "") or "").strip()
        if not command:
            return None
        app_type = entry.get("type") or ("url" if "://" in command else "process")
        if app_type not in APP_TYPES:
            return None
        derived_id, derived_name = _derive_id_and_name(command, app_type)
        name = str(entry.get("name", "") or "").strip() or derived_name
        app_id = _slugify(str(entry.get("id", "") or "").strip() or name) or derived_id
        app = {"id": app_id, "name": name, "command": command,
               "type": app_type, "autostart": bool(entry.get("autostart", True)),
               "placement": _normalize_placement(entry.get("placement"))}
        process_name = str(entry.get("process_name", "") or "").strip()
        if process_name:
            app["process_name"] = process_name
        return app

    return None


def normalize_apps(raw) -> list[dict]:
    """Rohe Config-Liste normalisieren; unbrauchbare Eintraege ueberspringen."""
    normalized = []
    for i, entry in enumerate(raw or []):
        app = normalize_app_entry(entry)
        if app is None:
            logger.warning("apps-Eintrag %d ist unbrauchbar und wird uebersprungen.", i)
            continue
        normalized.append(app)
    return normalized


def _derive_default_launcher(raw_apps) -> dict:
    """Default-Profil aus den alten App-Level-Feldern ableiten (Migration).

    ``autostart`` kommt vom Eintrag; ``placement`` wird NUR uebernommen, wenn
    es explizit am Roh-Eintrag steht — die Explizit-Semantik der
    Placement-Engine bleibt so ueber die Migration hinweg erhalten.
    """
    states: dict[str, dict] = {}
    for entry in raw_apps or []:
        normalized = normalize_app_entry(entry)
        if normalized is None:
            continue
        state = {"autostart": normalized["autostart"]}
        if isinstance(entry, dict) and isinstance(entry.get("placement"), dict):
            state["placement"] = _normalize_placement(entry.get("placement"))
        states[normalized["id"]] = state
    return {"active_profile": "default",
            "profiles": [{"id": "default", "name": "Default", "apps": states}]}


def normalize_launcher(raw_apps, raw_launcher) -> dict:
    """``launcher``-Block normalisieren — tolerant, wirft nie.

    Fehlt der Block (Alt-Config), wird das Default-Profil abgeleitet.
    Unbekannte Profil-App-Keys werden mit Warnung entfernt (die harte
    Ablehnung passiert beim Settings-Save in config_loader); ein unbekanntes
    ``active_profile`` faellt auf das erste Profil zurueck.
    """
    if not isinstance(raw_launcher, dict) or not raw_launcher.get("profiles"):
        return _derive_default_launcher(raw_apps)

    ids_by_fold = {a["id"].casefold(): a["id"] for a in normalize_apps(raw_apps)}
    profiles: list[dict] = []
    seen: set[str] = set()
    for raw_profile in raw_launcher.get("profiles") or []:
        if not isinstance(raw_profile, dict):
            logger.warning("Ungueltiges Profil uebersprungen (kein Objekt).")
            continue
        pid = _slugify(str(raw_profile.get("id", "") or "").strip())
        if not pid or pid in seen:
            logger.warning("Profil ohne/mit doppelter ID uebersprungen.")
            continue
        seen.add(pid)
        name = str(raw_profile.get("name", "") or "").strip() or pid.capitalize()
        states: dict[str, dict] = {}
        raw_states = raw_profile.get("apps")
        if isinstance(raw_states, dict):
            for app_key, raw_state in raw_states.items():
                app_id = ids_by_fold.get(str(app_key).strip().casefold())
                if app_id is None:
                    logger.warning("Profil '%s': App-Eintrag '%s' ist keiner App "
                                   "zugeordnet — entfernt.", pid, app_key)
                    continue
                if not isinstance(raw_state, dict):
                    logger.warning("Profil '%s': App-Eintrag '%s' ist kein Objekt "
                                   "— entfernt.", pid, app_key)
                    continue
                state = {"autostart": bool(raw_state.get("autostart", True))}
                if isinstance(raw_state.get("placement"), dict):
                    # dict-Placement gilt als explizit; Teilobjekte werden gefuellt.
                    state["placement"] = _normalize_placement(raw_state["placement"])
                elif "placement" in raw_state:
                    logger.warning("Profil '%s', App '%s': ungueltiges placement "
                                   "entfernt.", pid, app_id)
                states[app_id] = state
        profiles.append({"id": pid, "name": name, "apps": states})

    if not profiles:
        return _derive_default_launcher(raw_apps)
    active = _slugify(str(raw_launcher.get("active_profile", "") or "").strip())
    if active not in {p["id"] for p in profiles}:
        logger.warning("Unbekanntes active_profile — erstes Profil verwendet.")
        active = profiles[0]["id"]
    return {"active_profile": active, "profiles": profiles}


def configure(raw_apps, raw_launcher=None) -> None:
    """Registry + Profile aus der Config uebernehmen (Serverstart + Settings-Save)."""
    global APPS, PROFILES, ACTIVE_PROFILE
    APPS = normalize_apps(raw_apps)
    launcher = normalize_launcher(raw_apps, raw_launcher)
    PROFILES = launcher["profiles"]
    ACTIVE_PROFILE = launcher["active_profile"]
    logger.info("App-Registry: %d App(s), %d Profil(e), aktiv: '%s'.",
                len(APPS), len(PROFILES), ACTIVE_PROFILE)


def _profile_by_id(profile_id) -> dict | None:
    pid = _slugify(str(profile_id or "").strip())
    for profile in PROFILES:
        if profile["id"] == pid:
            return profile
    return None


def profile_exists(profile_id) -> bool:
    """Existenz-Check fuer die Profil-API (404- vs. 400-Unterscheidung)."""
    return _profile_by_id(profile_id) is not None


def find_profile(query) -> dict | None:
    """Profil per ID oder Name finden — case-insensitiv, Whitespace-tolerant.

    Zusaetzlich matcht die geslugte Eingabe die ID ("Deep Work" -> deep-work).
    Kein Fuzzy-Raten: unbekannt = None, das Nachfragen uebernimmt der Aufrufer.
    """
    needle = str(query or "").strip().casefold()
    if not needle:
        return None
    for profile in PROFILES:
        if needle in (profile["id"].casefold(), profile["name"].casefold()):
            return profile
    return _profile_by_id(query)


def effective_apps(profile_id=None) -> list[dict]:
    """Registry + Profil-Zustand gemerged — die oeffentliche App-Sicht.

    Form wie seit Phase 1: {"id","name","type","autostart","placement"},
    ohne ``command``/``process_name``. Apps ohne Profil-Eintrag gelten als
    autostart:true; fehlendes Placement wird fuer die Anzeige mit dem
    Default gefuellt (die Engine wendet nur explizite Placements an).
    """
    profile = _profile_by_id(profile_id if profile_id is not None else ACTIVE_PROFILE)
    if profile is None and PROFILES:
        profile = PROFILES[0]
    states = profile["apps"] if profile else {}
    result = []
    for a in APPS:
        state = states.get(a["id"], {})
        placement = state.get("placement")
        result.append({
            "id": a["id"], "name": a["name"], "type": a["type"],
            "autostart": bool(state.get("autostart", True)),
            "placement": dict(placement) if placement else dict(DEFAULT_PLACEMENT),
        })
    return result


def list_apps() -> list[dict]:
    """Oeffentliche Sicht fuer UI/Dashboard — effective Apps des aktiven Profils."""
    return effective_apps()


def find_app(query: str) -> dict | None:
    """App per ID oder Name finden — case-insensitiv, Whitespace-tolerant."""
    needle = (query or "").strip().casefold()
    if not needle:
        return None
    for app in APPS:
        if needle in (app["id"].casefold(), app["name"].casefold()):
            return app
    return None


# Beim Konvertieren eines Legacy-Strings in die Objektform werden NUR diese
# Kernfelder gepinnt. Das placement stammt bei der Normalisierung aus dem
# Default und darf hier NICHT auf Platte landen — sonst wuerde
# launch-session.ps1 es als explizite Platzierung anwenden
# (primary/fullscreen-Maximierung). Placements leben in den Profilen.
_LEGACY_CONVERT_KEYS = ("id", "name", "command", "type", "autostart")


def pin_app_ids(raw_apps) -> list:
    """Explizite IDs in die ROHE apps-Liste pinnen (neue Liste, Eingabe bleibt).

    Wird beim Persistieren des launcher-Blocks mitgespeichert, damit
    launch-session.ps1 Profil-Keys sicher ueber ``id`` matchen kann.
    Legacy-Strings werden in die Objektform ueberfuehrt (``command`` bleibt
    woertlich erhalten, KEIN placement gepinnt); unbrauchbare Eintraege
    bleiben unangetastet.
    """
    entries = []
    for entry in raw_apps or []:
        normalized = normalize_app_entry(entry)
        if normalized is None:
            entries.append(entry)
        elif isinstance(entry, dict):
            if isinstance(entry.get("id"), str) and entry["id"].strip():
                entries.append(entry)
            else:
                updated = dict(entry)
                updated["id"] = normalized["id"]
                entries.append(updated)
        else:
            entries.append({k: normalized[k] for k in _LEGACY_CONVERT_KEYS})
    return entries


# ── Profil-Persistenz: pure Helfer, liefern den zu speichernden launcher-Block ──

def _copy_state(state: dict) -> dict:
    copied = {"autostart": state.get("autostart", True)}
    if "placement" in state:
        copied["placement"] = dict(state["placement"])
    return copied


def _copy_profiles() -> list[dict]:
    return [
        {"id": p["id"], "name": p["name"],
         "apps": {aid: _copy_state(st) for aid, st in p["apps"].items()}}
        for p in PROFILES
    ]


def serialize_launcher() -> dict:
    """Aktuellen Profil-Zustand als speicherbaren launcher-Block ausgeben."""
    return {"active_profile": ACTIVE_PROFILE, "profiles": _copy_profiles()}


def launcher_with_app_state(app_id, autostart=None, placement=None) -> dict | None:
    """Toggle/Placement einer App im AKTIVEN Profil setzen.

    ``placement`` = {"monitor", "zone"} wird explizit gespeichert (ab dann
    wendet launch-session.ps1 es an). ``None`` bei unbekannter App.
    """
    needle = (app_id or "").strip().casefold()
    app = next((a for a in APPS if a["id"].casefold() == needle), None)
    if app is None:
        return None
    profiles = _copy_profiles()
    profile = next((p for p in profiles if p["id"] == ACTIVE_PROFILE), None)
    if profile is None:
        return None
    state = profile["apps"].setdefault(app["id"], {"autostart": True})
    if autostart is not None:
        state["autostart"] = bool(autostart)
    if placement is not None:
        state["placement"] = {"monitor": placement["monitor"], "zone": placement["zone"]}
    return {"active_profile": ACTIVE_PROFILE, "profiles": profiles}


def launcher_with_active(profile_id) -> dict | None:
    """Aktives Profil wechseln. ``None`` bei unbekanntem Profil."""
    profile = _profile_by_id(profile_id)
    if profile is None:
        return None
    return {"active_profile": profile["id"], "profiles": _copy_profiles()}


def launcher_with_new_profile(profile_id, name, copy_from=None) -> dict | None:
    """Neues Profil anlegen — Defaults (alle Apps autostart:true, ohne
    Placement) oder Kopie von ``copy_from`` (Duplizieren). ``None`` bei
    ID-Kollision, leerem Namen oder unbekannter Kopierquelle."""
    name = str(name or "").strip()
    pid = _slugify(str(profile_id or "").strip() or name)
    if not pid or not name:
        return None
    if _profile_by_id(pid) is not None:
        return None
    profiles = _copy_profiles()
    if copy_from is not None:
        source = next((p for p in profiles if p["id"] == _slugify(str(copy_from).strip())), None)
        if source is None:
            return None
        states = {aid: _copy_state(st) for aid, st in source["apps"].items()}
    else:
        states = {a["id"]: {"autostart": True} for a in APPS}
    profiles.append({"id": pid, "name": name, "apps": states})
    return {"active_profile": ACTIVE_PROFILE, "profiles": profiles}


def launcher_with_renamed(profile_id, name) -> dict | None:
    """Profil umbenennen (ID bleibt stabil). ``None`` bei unbekanntem Profil
    oder leerem Namen."""
    name = str(name or "").strip()
    if not name or _profile_by_id(profile_id) is None:
        return None
    pid = _slugify(str(profile_id or "").strip())
    profiles = _copy_profiles()
    for profile in profiles:
        if profile["id"] == pid:
            profile["name"] = name
    return {"active_profile": ACTIVE_PROFILE, "profiles": profiles}


def launcher_without_profile(profile_id) -> tuple[dict | None, str | None]:
    """Profil loeschen. Rueckgabe ``(launcher, fehlertext)``:
    unbekanntes Profil → (None, None); Schutzregeln → (None, Meldung)."""
    profile = _profile_by_id(profile_id)
    if profile is None:
        return None, None
    if len(PROFILES) <= 1:
        return None, "Das letzte Profil kann nicht gelöscht werden."
    if profile["id"] == ACTIVE_PROFILE:
        return None, "Das aktive Profil kann nicht gelöscht werden — erst ein anderes aktivieren."
    profiles = [p for p in _copy_profiles() if p["id"] != profile["id"]]
    return {"active_profile": ACTIVE_PROFILE, "profiles": profiles}, None


# VS Codes PATH-Eintrag ist auf Windows der Shim ``...\bin\code.cmd`` (Batch),
# NICHT ``code.exe``. ``subprocess.Popen(["code"])`` kann den Shim nicht starten,
# weil CreateProcess nur ``.exe`` aufloest -> FileNotFoundError. Darum wird das
# bekannte Token ``code`` auf die echte ``Code.exe`` gemappt. Ausschliesslich
# dieses eine Token wird aufgeloest — keine generische PATH-Suche, damit die
# Allowlist dicht bleibt.
_VSCODE_WELL_KNOWN = (
    r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
    r"%ProgramFiles%\Microsoft VS Code\Code.exe",
    r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe",
)


def _resolve_vscode() -> str | None:
    """Konkreten ``Code.exe``-Pfad finden: zuerst aus dem ``code``-Shim im PATH
    ableiten (``...\\bin\\code.cmd`` -> eine Ebene hoeher ``Code.exe``), sonst die
    typischen Windows-Installationspfade pruefen. ``None`` wenn nichts existiert."""
    shim = shutil.which("code")
    if shim:
        # ...\Microsoft VS Code\bin\code.cmd  ->  ...\Microsoft VS Code\Code.exe
        exe = os.path.join(os.path.dirname(os.path.dirname(shim)), "Code.exe")
        if os.path.isfile(exe):
            return exe
    for raw in _VSCODE_WELL_KNOWN:
        path = os.path.expandvars(raw)
        if "%" not in path and os.path.isfile(path):
            return path
    return None


def _resolve_command(command: str) -> str:
    """Launch-Command aufloesen. Nur das Sonder-Token ``code`` (VS-Code-CLI-Shim)
    wird auf ``Code.exe`` gemappt; jeder andere Command bleibt unveraendert."""
    if command.strip().casefold() == "code":
        resolved = _resolve_vscode()
        if resolved:
            return resolved
    return command


def _start_url(command: str) -> None:
    """URL/Protokoll ueber den registrierten Windows-Handler oeffnen."""
    os.startfile(command)  # noqa: S606 — bewusst: nur Allowlist-Befehle


def _start_process(command: str) -> None:
    """Erlaubtes Programm starten — nur der Executable-Pfad, keine Shell,
    keine Argument-Zerlegung (haelt die Allowlist dicht). ``code`` wird auf die
    echte ``Code.exe`` aufgeloest (siehe ``_resolve_command``)."""
    subprocess.Popen([_resolve_command(command)],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def launch(query: str) -> dict:
    """App aus der Registry starten. Blockiert kurz — via ``asyncio.to_thread`` aufrufen.

    Ergebnis immer strukturiert: {"ok", "app", "name", "message"} — die Meldung
    ist deutsch und direkt vorlesbar (Erfolg wie Fehler).
    """
    if not APPS:
        return {"ok": False, "app": None, "name": None,
                "message": "Es sind keine Apps konfiguriert — trage Apps in den Einstellungen ein."}

    app = find_app(query)
    if app is None:
        available = ", ".join(a["name"] for a in APPS)
        return {"ok": False, "app": None, "name": None,
                "message": f"Die App '{(query or '').strip()}' ist nicht konfiguriert. Verfügbar: {available}."}

    try:
        if app["type"] == "url":
            _start_url(app["command"])
        else:
            _start_process(app["command"])
    except Exception as e:
        logger.warning("App '%s' konnte nicht gestartet werden", app["id"], exc_info=True)
        return {"ok": False, "app": app["id"], "name": app["name"],
                "message": f"'{app['name']}' konnte nicht gestartet werden ({type(e).__name__})."}

    logger.info("App gestartet: %s (%s)", app["id"], app["type"])
    return {"ok": True, "app": app["id"], "name": app["name"],
            "message": f"{app['name']} wird geöffnet."}

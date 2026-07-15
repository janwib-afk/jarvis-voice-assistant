"""
Jarvis V2 — Config-Loader & Validierung

Zentrale, testbare Stelle zum Laden und Prüfen von ``config.json``. Liefert
verständliche Fehlermeldungen statt roher Tracebacks. Es werden **niemals**
Config-Werte (Secrets) in Meldungen/Logs ausgegeben — nur Schlüsselnamen.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import os

# Ohne diese Felder kann der Server nicht arbeiten.
REQUIRED_KEYS = ("anthropic_api_key", "elevenlabs_api_key")

# Ueber die Settings-UI editierbare Felder (strikte Whitelist).
UI_EDITABLE_KEYS = frozenset({
    "user_name",
    "user_address",
    "user_role",
    "city",
    "elevenlabs_voice_id",
    "obsidian_inbox_path",
    "obsidian_inbox_folder",
    "apps",
    "launcher",
    "music_folder",
    "selected_music_file",
    "music_volume",
})

# Secrets: duerfen NIE ueber die UI gelesen oder geschrieben werden.
PROTECTED_KEYS = frozenset({"anthropic_api_key", "elevenlabs_api_key"})

# Marker, die auf einen unausgefüllten Platzhalter aus config.example.json hindeuten.
_PLACEHOLDER_MARKERS = ("YOUR_", "DEIN_")

# Erlaubte Felder eines strukturierten apps-Eintrags (strikte Whitelist).
_APP_ENTRY_KEYS = frozenset({"id", "name", "command", "type", "autostart",
                             "placement", "process_name"})
_APP_TYPES = ("url", "process")
_PLACEMENT_MONITORS = ("primary", "left", "right", "leftmost", "rightmost")
_PLACEMENT_ZONES = ("fullscreen", "left_half", "right_half", "top_half", "bottom_half",
                    "top_left", "top_right", "bottom_left", "bottom_right", "center")
_PLACEMENT_KEYS = frozenset({"monitor", "zone"})

# Session-Profile: launcher-Block mit aktivem Profil + Profil-Liste.
_LAUNCHER_KEYS = frozenset({"active_profile", "profiles"})
_PROFILE_KEYS = frozenset({"id", "name", "apps"})
_PROFILE_APP_KEYS = frozenset({"autostart", "placement"})


class ConfigError(Exception):
    """Wird bei fehlender/ungültiger Konfiguration mit lesbarer Meldung geworfen."""


def _looks_like_placeholder(value: str) -> bool:
    return any(marker in value for marker in _PLACEHOLDER_MARKERS)


def validate_config(cfg: dict) -> list[str]:
    """Prüft eine bereits geparste Config und gibt eine Liste lesbarer Fehler zurück.

    Meldungen nennen ausschliesslich Schlüsselnamen, nie Werte (keine Secrets).
    Leere Liste = gültig.
    """
    errors: list[str] = []

    if not isinstance(cfg, dict):
        return ["config.json muss ein JSON-Objekt sein (geschweifte Klammern)."]

    for key in REQUIRED_KEYS:
        if key not in cfg:
            errors.append(f"Pflichtfeld '{key}' fehlt in config.json.")
            continue
        value = cfg[key]
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Pflichtfeld '{key}' ist leer oder kein Text.")
        elif _looks_like_placeholder(value):
            errors.append(
                f"Feld '{key}' enthält noch den Platzhalterwert — trage deinen echten Wert ein."
            )

    return errors


def load_config(path: str) -> dict:
    """Lädt und validiert ``config.json`` von ``path``.

    Wirft ``ConfigError`` mit einer verständlichen, secret-freien Meldung, wenn die
    Datei fehlt, kein gültiges JSON ist oder Pflichtfelder fehlen/Platzhalter enthalten.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        raise ConfigError(
            f"config.json nicht gefunden ({path}). "
            "Kopiere config.example.json nach config.json und trage deine Keys ein."
        )
    except OSError as e:
        raise ConfigError(f"config.json konnte nicht gelesen werden: {e}")

    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(
            f"config.json ist kein gültiges JSON (Zeile {e.lineno}, Spalte {e.colno}): {e.msg}."
        )

    errors = validate_config(cfg)
    if errors:
        raise ConfigError("Ungültige config.json:\n- " + "\n- ".join(errors))

    return cfg


def resolve_config_path(environ, default: str) -> str:
    """Wählt den Config-Pfad: expliziter ``JARVIS_CONFIG_PATH``-Override, sonst Default.

    Nur für kontrollierte Starts und Tests gedacht (eine eingecheckte, synthetische
    Test-Fixture wird über die Variable ausdrücklich ausgewählt). Ein leerer oder
    reiner Whitespace-Override wird ignoriert und fällt auf den Default zurück. Die
    Produktion setzt die Variable nicht und nutzt damit immer ihre echte
    ``config.json`` — es gibt keinen stillen Rückfall auf eine Testconfig.
    """
    override = (environ.get("JARVIS_CONFIG_PATH") or "").strip()
    return override or default


def validate_placement_value(value) -> list[str]:
    """Prüft ein ``placement``-Objekt. Leere Liste = gültig.

    ``monitor``/``zone`` sind optional (Defaults setzt die Normalisierung in
    app_launcher); wenn vorhanden, müssen sie erlaubte Werte sein. Meldungen
    nennen die erlaubten Werte, nie den fehlerhaften Wert.
    """
    if not isinstance(value, dict):
        return ["'placement' muss ein Objekt sein."]
    errors: list[str] = []
    for key in value:
        if key not in _PLACEMENT_KEYS:
            errors.append(f"'placement': unbekanntes Feld '{key}'.")
    if "monitor" in value and value["monitor"] not in _PLACEMENT_MONITORS:
        errors.append("'placement.monitor' ist ungültig — erlaubt: "
                      + ", ".join(_PLACEMENT_MONITORS) + ".")
    if "zone" in value and value["zone"] not in _PLACEMENT_ZONES:
        errors.append("'placement.zone' ist ungültig — erlaubt: "
                      + ", ".join(_PLACEMENT_ZONES) + ".")
    return errors


def validate_launcher_value(value, app_ids=None) -> list[str]:
    """Prüft den ``launcher``-Block (Session-Profile). Leere Liste = gültig.

    Struktur: ``{"active_profile": str, "profiles": [{"id","name","apps"}]}``.
    Profil-IDs müssen eindeutig sein (case-insensitiv), ``active_profile``
    muss auf ein vorhandenes Profil zeigen. Profil-App-States erlauben nur
    ``autostart`` (bool) und ``placement`` (siehe ``validate_placement_value``).
    Der Cross-Check gegen die App-Registry läuft nur, wenn ``app_ids``
    übergeben wird (die Profil-Endpunkte tun das; die Settings-UI schickt
    nie einen launcher-Block). Meldungen nennen nur Schlüssel, nie Secrets.
    """
    if not isinstance(value, dict):
        return ["'launcher' muss ein Objekt sein."]
    errors: list[str] = []
    for key in value:
        if key not in _LAUNCHER_KEYS:
            errors.append(f"'launcher': unbekanntes Feld '{key}'.")

    profiles = value.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        errors.append("'launcher.profiles' muss eine Liste mit mindestens einem Profil sein.")
        return errors

    known_app_ids = None
    if app_ids is not None:
        known_app_ids = {str(a).casefold() for a in app_ids}

    seen_ids: dict[str, int] = {}
    for i, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            errors.append(f"'launcher.profiles' Eintrag {i} muss ein Objekt sein.")
            continue
        for key in profile:
            if key not in _PROFILE_KEYS:
                errors.append(f"Profil {i}: unbekanntes Feld '{key}'.")
        profile_id = profile.get("id")
        if not isinstance(profile_id, str) or not profile_id.strip():
            errors.append(f"Profil {i}: 'id' fehlt oder ist kein Text.")
        else:
            key = profile_id.strip().casefold()
            if key in seen_ids:
                errors.append(
                    f"Profil {i}: 'id' ist bereits vergeben (gleiche ID wie Profil {seen_ids[key]})."
                )
            else:
                seen_ids[key] = i
        name = profile.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"Profil {i}: 'name' fehlt oder ist kein Text.")
        apps = profile.get("apps", {})
        if not isinstance(apps, dict):
            errors.append(f"Profil {i}: 'apps' muss ein Objekt sein.")
            continue
        for app_key, state in apps.items():
            if known_app_ids is not None and str(app_key).casefold() not in known_app_ids:
                errors.append(f"Profil {i}: App-Eintrag '{app_key}' ist keiner App zugeordnet.")
            if not isinstance(state, dict):
                errors.append(f"Profil {i}: App-Eintrag '{app_key}' muss ein Objekt sein.")
                continue
            for key in state:
                if key not in _PROFILE_APP_KEYS:
                    errors.append(f"Profil {i}, App '{app_key}': unbekanntes Feld '{key}'.")
            if "autostart" in state and not isinstance(state["autostart"], bool):
                errors.append(f"Profil {i}, App '{app_key}': 'autostart' muss true oder false sein.")
            if "placement" in state:
                errors.extend(f"Profil {i}, App '{app_key}': {msg}"
                              for msg in validate_placement_value(state["placement"]))

    active = value.get("active_profile")
    if not isinstance(active, str) or not active.strip():
        errors.append("'launcher.active_profile' fehlt oder ist kein Text.")
    elif active.strip().casefold() not in seen_ids:
        errors.append("'launcher.active_profile' verweist auf kein vorhandenes Profil.")
    return errors


def validate_apps_value(value) -> list[str]:
    """Prüft den ``apps``-Wert: Liste aus Strings (Legacy) und/oder Objekten.

    Objektform: ``command`` ist Pflicht; optional ``id``/``name`` (Text),
    ``type`` ("url"/"process"), ``autostart`` (bool), ``placement``
    (monitor/zone, siehe ``validate_placement_value``) und ``process_name``
    (Text, nur für die Fensterfindung in launch-session.ps1). Explizite IDs
    müssen eindeutig sein (case-insensitiv). Unbekannte Felder werden
    abgelehnt. Meldungen nennen nur Index/Schlüssel, nie Werte.
    """
    if not isinstance(value, list):
        return ["'apps' muss eine Liste sein."]

    errors: list[str] = []
    # Nur EXPLIZITE IDs auf Eindeutigkeit prüfen — abgeleitete IDs (Legacy-
    # Strings, Objekte ohne id) entstehen erst in app_launcher und bleiben
    # dort first-match-wins, wie bisher bei launch().
    seen_ids: dict[str, int] = {}
    for i, entry in enumerate(value):
        if isinstance(entry, str):
            if not entry.strip():
                errors.append(f"'apps' Eintrag {i} darf nicht leer sein.")
        elif isinstance(entry, dict):
            for key in entry:
                if key not in _APP_ENTRY_KEYS:
                    errors.append(f"'apps' Eintrag {i}: unbekanntes Feld '{key}'.")
            command = entry.get("command")
            if not isinstance(command, str) or not command.strip():
                errors.append(f"'apps' Eintrag {i}: 'command' fehlt oder ist kein Text.")
            for field in ("id", "name"):
                if field in entry and (not isinstance(entry[field], str) or not entry[field].strip()):
                    errors.append(f"'apps' Eintrag {i}: '{field}' muss Text sein.")
            entry_id = entry.get("id")
            if isinstance(entry_id, str) and entry_id.strip():
                key = entry_id.strip().casefold()
                if key in seen_ids:
                    errors.append(
                        f"'apps' Eintrag {i}: 'id' ist bereits vergeben (gleiche ID wie Eintrag {seen_ids[key]})."
                    )
                else:
                    seen_ids[key] = i
            if "type" in entry and entry["type"] not in _APP_TYPES:
                errors.append(f"'apps' Eintrag {i}: 'type' muss 'url' oder 'process' sein.")
            if "autostart" in entry and not isinstance(entry["autostart"], bool):
                errors.append(f"'apps' Eintrag {i}: 'autostart' muss true oder false sein.")
            if "placement" in entry:
                errors.extend(f"'apps' Eintrag {i}: {msg}"
                              for msg in validate_placement_value(entry["placement"]))
            if "process_name" in entry and (
                    not isinstance(entry["process_name"], str) or not entry["process_name"].strip()):
                errors.append(f"'apps' Eintrag {i}: 'process_name' muss Text sein.")
        else:
            errors.append(f"'apps' Eintrag {i} muss Text oder Objekt sein.")
    return errors


def validate_music_file_value(value) -> list[str]:
    """Prüft ``selected_music_file``. Leere Liste = gültig.

    Leer = keine Musik gewählt. Sonst muss der Wert ein REINER ``.mp3``-
    Dateiname sein: keine Pfadseparatoren, keine absoluten Pfade, keine
    Laufwerks-/Stream-Doppelpunkte, kein ``..`` — abgespielt wird nur aus dem
    konfigurierten Musikordner. Meldungen nennen nie den fehlerhaften Wert.
    """
    if not isinstance(value, str):
        return ["'selected_music_file' muss Text sein."]
    name = value.strip()
    if not name:
        return []
    if ("/" in name or "\\" in name or ":" in name
            or os.path.isabs(name) or os.path.basename(name) != name
            or name in (".", "..")):
        return ["'selected_music_file' muss ein reiner Dateiname sein (kein Pfad)."]
    if not name.lower().endswith(".mp3"):
        return ["'selected_music_file' muss eine .mp3-Datei sein."]
    return []


def validate_music_volume_value(value) -> list[str]:
    """Prüft ``music_volume``: Zahl (oder numerischer String mit Punkt) in [0, 1].

    Leerer String = nicht gesetzt (Launcher nutzt seinen Default). Bewusst
    KEIN Dezimal-Komma: der Wert wird von launch-session.ps1 invariant geparst.
    """
    if isinstance(value, str):
        if not value.strip():
            return []
        try:
            value = float(value.strip())
        except ValueError:
            return ["'music_volume' muss eine Zahl zwischen 0 und 1 sein (z.B. 0.25)."]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ["'music_volume' muss eine Zahl zwischen 0 und 1 sein (z.B. 0.25)."]
    if not (0.0 <= float(value) <= 1.0):
        return ["'music_volume' muss eine Zahl zwischen 0 und 1 sein (z.B. 0.25)."]
    return []


def validate_settings_update(updates: dict) -> list[str]:
    """Prüft ein Settings-Update aus der UI. Gibt lesbare Fehler zurück (leer = ok).

    Erlaubt sind nur Keys aus ``UI_EDITABLE_KEYS``; geschützte Keys (API-Keys)
    werden explizit abgelehnt. Meldungen nennen nur Schlüsselnamen, nie Werte.
    """
    if not isinstance(updates, dict):
        return ["Einstellungen müssen ein JSON-Objekt sein."]

    errors: list[str] = []
    for key, value in updates.items():
        if key in PROTECTED_KEYS:
            errors.append(f"'{key}' kann nur direkt in config.json geändert werden.")
        elif key not in UI_EDITABLE_KEYS:
            errors.append(f"Unbekannte Einstellung: '{key}'.")
        elif key == "apps":
            errors.extend(validate_apps_value(value))
        elif key == "launcher":
            # Cross-Check gegen App-IDs nur, wenn apps im selben Update stecken —
            # die Profil-Endpunkte validieren zusaetzlich explizit mit app_ids.
            app_ids = None
            if isinstance(updates.get("apps"), list):
                app_ids = [
                    entry.get("id") for entry in updates["apps"]
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str)
                ]
            errors.extend(validate_launcher_value(value, app_ids=app_ids))
        elif key == "selected_music_file":
            errors.extend(validate_music_file_value(value))
        elif key == "music_volume":
            errors.extend(validate_music_volume_value(value))
        elif not isinstance(value, str):
            errors.append(f"'{key}' muss Text sein.")
    return errors


def save_settings(path: str, updates: dict) -> dict:
    """Merged UI-editierbare Felder in ``config.json`` und schreibt atomar zurück.

    Liest die Datei frisch von Platte (nie eine In-Memory-Config zurückschreiben),
    damit Secrets, unbekannte Felder und manuelle Edits erhalten bleiben.
    Gibt die gemergte Config zurück. Wirft ``ConfigError`` bei Problemen.
    """
    errors = validate_settings_update(updates)
    if errors:
        raise ConfigError("Ungültige Einstellungen:\n- " + "\n- ".join(errors))

    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"config.json nicht gefunden ({path}).")
    except json.JSONDecodeError as e:
        raise ConfigError(f"config.json ist kein gültiges JSON (Zeile {e.lineno}): {e.msg}.")
    except OSError as e:
        raise ConfigError(f"config.json konnte nicht gelesen werden: {e}")

    if not isinstance(cfg, dict):
        raise ConfigError("config.json muss ein JSON-Objekt sein (geschweifte Klammern).")

    for key in UI_EDITABLE_KEYS & updates.keys():
        cfg[key] = updates[key]

    # Atomar: erst .tmp im selben Verzeichnis schreiben, dann os.replace
    # (same-volume rename ist auf Windows atomar).
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except OSError as e:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise ConfigError(f"config.json konnte nicht geschrieben werden: {e}")

    return cfg


def check_obsidian_paths(cfg: dict) -> list[str]:
    """Prüft die Obsidian-Pfade und gibt Warnungen zurück (kein Abbruch).

    Pfade sind keine Secrets und dürfen in Meldungen genannt werden.
    """
    warnings: list[str] = []

    vault_path = cfg.get("obsidian_inbox_path", "")
    if not vault_path:
        warnings.append(
            "'obsidian_inbox_path' ist nicht konfiguriert — Obsidian-Funktionen "
            "(Tasks, Vault-Übersicht) sind deaktiviert."
        )
    elif not os.path.isdir(vault_path):
        warnings.append(
            f"'obsidian_inbox_path' zeigt auf ein nicht existierendes Verzeichnis: {vault_path} "
            "(Tipp: Backslashes in JSON als \\\\ schreiben)."
        )

    # INBOX_WRITE legt den Ordner selbst an (os.makedirs) — nur der Parent muss existieren.
    inbox_folder = cfg.get("obsidian_inbox_folder", "")
    if inbox_folder and not os.path.isdir(inbox_folder):
        parent = os.path.dirname(inbox_folder.rstrip("\\/"))
        if not parent or not os.path.isdir(parent):
            warnings.append(
                f"'obsidian_inbox_folder' und sein übergeordnetes Verzeichnis existieren nicht: {inbox_folder} "
                "(Tipp: Backslashes in JSON als \\\\ schreiben)."
            )

    return warnings


def find_chromium_executable(browsers_dir: str | None = None) -> str | None:
    """Sucht das Playwright-Chromium-Executable, ohne einen Browser zu starten.

    Auflösung des Browser-Verzeichnisses: Parameter → PLAYWRIGHT_BROWSERS_PATH →
    Standard %LOCALAPPDATA%\\ms-playwright. Der Sonderwert "0" der Env-Variable
    bedeutet: Browser liegen in site-packages neben dem playwright-Paket.
    """
    root = browsers_dir
    if root is None:
        env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
        if env_path == "0":
            spec = importlib.util.find_spec("playwright")
            if spec is None or not spec.origin:
                return None
            root = os.path.join(os.path.dirname(spec.origin), "driver", "package", ".local-browsers")
        elif env_path:
            root = env_path
        else:
            root = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")

    # chrome-win64 (aktuell) und chrome-win (ältere Playwright-Versionen)
    matches = glob.glob(os.path.join(root, "chromium-*", "chrome-win*", "chrome.exe"))
    return matches[0] if matches else None


def check_playwright_chromium(browsers_dir: str | None = None) -> list[str]:
    """Prüft, ob Playwright samt Chromium nutzbar ist. Gibt Warnungen zurück."""
    if importlib.util.find_spec("playwright") is None:
        return [
            "Python-Paket 'playwright' ist nicht installiert — Browser-Aktionen "
            "(Suche, News, URLs öffnen) werden fehlschlagen. "
            "Installiere es mit: pip install -r requirements.txt"
        ]

    if find_chromium_executable(browsers_dir) is None:
        return [
            "Playwright-Chromium ist nicht installiert — Browser-Aktionen "
            "(Suche, News, URLs öffnen) werden fehlschlagen. "
            "Installiere es mit: python -m playwright install chromium"
        ]

    return []


def check_runtime_environment(cfg: dict) -> list[str]:
    """Prüft optionale Laufzeit-Voraussetzungen. Gibt WARNUNGEN zurück (kein Abbruch).

    Der Server startet trotz Warnungen — betroffene Features degradieren nur.
    """
    warnings: list[str] = []
    warnings += check_obsidian_paths(cfg)
    warnings += check_playwright_chromium()
    return warnings

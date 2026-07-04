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
})

# Secrets: duerfen NIE ueber die UI gelesen oder geschrieben werden.
PROTECTED_KEYS = frozenset({"anthropic_api_key", "elevenlabs_api_key"})

# Marker, die auf einen unausgefüllten Platzhalter aus config.example.json hindeuten.
_PLACEHOLDER_MARKERS = ("YOUR_", "DEIN_")


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
            if not isinstance(value, list) or not all(isinstance(a, str) for a in value):
                errors.append("'apps' muss eine Liste von Texten sein.")
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

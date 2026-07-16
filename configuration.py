"""Configuration — versionierte Konfiguration mit genau einem Schreibweg (RFC-0003).

Die **Configuration** ist das vollstaendige persistierte Dokument (`config.json`)
inklusive Secrets und unbekannter Felder; die **Settings** sind die UI-editierbare
Projektion daraus (siehe CONTEXT.md).

Dieses Modul ist ein deep module mit kleinem Interface:

- ``snapshot()``                       — unveraenderliche kanonische Sicht
- ``settings_view()``                  — UI-Projektion (nie Secrets) + Revision
- ``mutate(intent, expected_revision)`` — der EINZIGE Schreibweg, serialisiert

Verborgen bleiben: Fresh-Read, Migration, Vollvalidierung, atomarer Austausch,
Live-Apply, Kompensation, Revisionsbildung und der Lock.

Abhaengigkeitsrichtung: ``configuration`` -> ``config_loader`` (Leaf: Datei-/
Validierungsgrundlagen). ``config_loader`` importiert dieses Modul NIE.
Import-Sicherheit (RFC-0002): der Import macht keine I/O und erzeugt nichts.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from types import MappingProxyType

import config_loader

logger = logging.getLogger("jarvis.configuration")

# Aktuelle Zielversion des persistierten Formats. Fehlender Marker = Legacy v0.
SCHEMA_VERSION = 1

# Feldname des Formatmarkers. NICHT zu verwechseln mit der Revision: der Marker ist
# die persistierte Formatversion (Migration), die Revision ein opakes, NICHT
# persistiertes Concurrency-Token (Konflikterkennung) — RFC-0003 D5.
SCHEMA_VERSION_KEY = "schema_version"


def schema_version_of(document: dict) -> int:
    """Formatversion eines Dokuments. Fehlender/ungueltiger Marker = 0 (Legacy)."""
    value = document.get(SCHEMA_VERSION_KEY)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def migrate_document(document: dict) -> dict:
    """Ein Dokument rein auf ``SCHEMA_VERSION`` bringen (Eingabe bleibt unberuehrt).

    **v0 -> v1 ergaenzt ausschliesslich den Versionsmarker.** Reihenfolge, unbekannte
    Felder, Secrets, Legacy-App-Strings und Mischformen bleiben unveraendert — die
    Versionierung ist kein Vorwand fuer Normalisierung (RFC-0003 §19).

    Eine unbekannte zukuenftige Version ist **fails-closed**: ``ConfigError``, damit
    eine neuere Datei nie stillschweigend herabgestuft oder ueberschrieben wird.
    """
    version = schema_version_of(document)
    if version > SCHEMA_VERSION:
        raise config_loader.ConfigError(
            f"config.json hat die unbekannte Version {version}; diese Jarvis-Version "
            f"unterstuetzt hoechstens Version {SCHEMA_VERSION}. Die Datei wurde nicht "
            "veraendert — bitte Jarvis aktualisieren."
        )
    if version == SCHEMA_VERSION:
        return document
    # v0 -> v1: nur den Marker anhaengen, sonst nichts anfassen.
    migrated = copy.deepcopy(document)
    migrated[SCHEMA_VERSION_KEY] = SCHEMA_VERSION
    return migrated


def read_document(path: str) -> dict:
    """Das rohe Dokument lesen — fails-closed, ohne die Datei je zu veraendern.

    Meldungen nennen nur Position/Grund, nie Config-Werte (keine Secrets).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        raise config_loader.ConfigError(
            f"config.json nicht gefunden ({path}). "
            "Kopiere config.example.json nach config.json und trage deine Keys ein."
        )
    except OSError as e:
        raise config_loader.ConfigError(f"config.json konnte nicht gelesen werden: {e}")

    try:
        document = json.loads(raw)
    except json.JSONDecodeError as e:
        raise config_loader.ConfigError(
            f"config.json ist kein gültiges JSON (Zeile {e.lineno}, Spalte {e.colno}): {e.msg}."
        )
    if not isinstance(document, dict):
        raise config_loader.ConfigError(
            "config.json muss ein JSON-Objekt sein (geschweifte Klammern)."
        )
    return document


# Suffix des einzigen Pre-Migration-Backups. Traegt Klartext-Secrets — die
# .gitignore-Regel ``config.json.*`` deckt es ab (RFC-0003 D10/§29).
BACKUP_SUFFIX = ".pre-v1.bak"
# Temp-Datei fuer den atomaren Austausch (gleiches Verzeichnis => same-volume).
TEMP_SUFFIX = ".tmp"


def _dump(document: dict) -> str:
    """Kanonische Serialisierung — identisch zum bisherigen save_settings-Format."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def _revision_of(document: dict) -> str:
    """Opakes Concurrency-Token des Inhalts.

    Bewusst KEIN Schemafeld und nicht persistiert (RFC-0003 D5/§20): rein
    abgeleitet, damit auch eine manuelle Dateiaenderung eine neue Revision ergibt.
    """
    payload = json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def _freeze(value):
    """Tiefe, nur-lesbare Sicht — Aufrufer koennen den kanonischen Zustand nicht mutieren."""
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class ConfigSnapshot:
    """Unveraenderliche kanonische Sicht auf die Configuration.

    - ``document``: das vollstaendige Dokument (inkl. Secrets/unbekannte Felder),
      nur lesbar.
    - ``schema_version``: persistierte Formatversion.
    - ``revision``: opakes Concurrency-Token (nicht persistiert).
    """
    document: MappingProxyType
    schema_version: int
    revision: str

    def as_dict(self) -> dict:
        """Veraenderbare tiefe Kopie — Aenderungen daran treffen den Kern nie."""
        return copy.deepcopy(_thaw(self.document))


def _thaw(value):
    if isinstance(value, MappingProxyType):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


class ConfigConflict(Exception):
    """Die erwartete Revision ist ueberholt — es wurde NICHTS geschrieben."""


class Configuration:
    """Runtime-eigener, transaktionaler Besitzer der Configuration (RFC-0003 D1).

    Genau ein serialisierter Schreibweg (``mutate``) unter einem per-Instanz-Lock.
    Kein Actor, kein Hintergrund-Writer, kein OS-weites Lock — In-Process-
    Serialisierung, wie in D4 entschieden.
    """

    def __init__(self, path: str):
        self.path = path
        self._snapshot: ConfigSnapshot | None = None
        self._lock = asyncio.Lock()

    # ── Lesen ───────────────────────────────────────────────────────────────
    @property
    def backup_path(self) -> str:
        return self.path + BACKUP_SUFFIX

    @property
    def temp_path(self) -> str:
        return self.path + TEMP_SUFFIX

    def snapshot(self) -> ConfigSnapshot:
        """Die kanonische Sicht. ``load()`` muss vorher gelaufen sein."""
        if self._snapshot is None:
            raise config_loader.ConfigError(
                "Configuration ist nicht geladen — load() gehoert in den Runtime-Lifecycle."
            )
        return self._snapshot

    def settings_view(self) -> dict:
        """UI-Projektion: ausschliesslich UI_EDITABLE_KEYS, nie Secrets, + Revision."""
        snap = self.snapshot()
        document = snap.as_dict()
        defaults = {"apps": [], "launcher": {}}
        settings = {
            key: document.get(key, defaults.get(key, ""))
            for key in sorted(config_loader.UI_EDITABLE_KEYS)
        }
        return {"settings": settings, "revision": snap.revision}

    # ── Laden/Migrieren ─────────────────────────────────────────────────────
    def load(self) -> ConfigSnapshot:
        """Fresh-Read → Version bestimmen → migrieren (mit Backup) → validieren.

        Fails-closed: fehlende/beschaedigte/zukuenftige/ungueltige Datei wird NIE
        ueberschrieben. Idempotent: ein zweiter Aufruf ohne Dateiaenderung liefert
        dieselbe Revision.
        """
        document = read_document(self.path)
        version = schema_version_of(document)
        if version != SCHEMA_VERSION:
            # migrate_document wirft bei zukuenftiger Version, BEVOR irgendetwas
            # geschrieben oder gesichert wird.
            migrated = migrate_document(document)
            errors = config_loader.validate_config(migrated)
            if errors:
                raise config_loader.ConfigError(
                    "Ungültige config.json:\n- " + "\n- ".join(errors))
            self._backup_once()
            self._atomic_write(migrated)
            logger.info("config.json von Version %d auf %d migriert", version, SCHEMA_VERSION)
            document = migrated
        else:
            errors = config_loader.validate_config(document)
            if errors:
                raise config_loader.ConfigError(
                    "Ungültige config.json:\n- " + "\n- ".join(errors))
        self._publish(document)
        return self._snapshot

    def _publish(self, document: dict) -> None:
        self._snapshot = ConfigSnapshot(
            document=_freeze(copy.deepcopy(document)),
            schema_version=schema_version_of(document),
            revision=_revision_of(document),
        )

    def _backup_once(self) -> None:
        """Bytegenaues Pre-Migration-Backup + Verifikation. Nur das letzte bleibt."""
        try:
            with open(self.path, "rb") as f:
                original = f.read()
            with open(self.backup_path, "wb") as f:
                f.write(original)
            with open(self.backup_path, "rb") as f:
                written = f.read()
        except OSError as e:
            raise config_loader.ConfigError(
                f"Sicherungskopie vor der Migration konnte nicht angelegt werden: {e}")
        if written != original:
            raise config_loader.ConfigError(
                "Sicherungskopie vor der Migration ist nicht bytegleich — Migration abgebrochen.")

    def _atomic_write(self, document: dict) -> None:
        """.tmp schreiben + os.replace — der Linearization Point (RFC-0003 §22)."""
        try:
            with open(self.temp_path, "w", encoding="utf-8") as f:
                f.write(_dump(document))
            os.replace(self.temp_path, self.path)
        except OSError as e:
            try:
                os.remove(self.temp_path)
            except OSError:
                pass
            raise config_loader.ConfigError(f"config.json konnte nicht geschrieben werden: {e}")

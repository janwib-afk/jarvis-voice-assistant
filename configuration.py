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

import copy
import json
import os

import config_loader

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

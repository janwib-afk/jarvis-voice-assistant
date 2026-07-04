"""
Jarvis V2 — Memory & Obsidian-Helfer

Alles, was Jarvis liest/schreibt, um sich Dinge zu merken:
- Tages-Inbox (Brain Dump) lesen/schreiben, Tasks.md, Vault-Zusammenfassung
- Langzeit-Gedaechtnis: eine transparente Markdown-Datei ("Jarvis Memory.md"
  im Vault, sonst memory.md im Workspace), die der Nutzer jederzeit selbst
  einsehen und bearbeiten kann. Es wird NUR auf ausdruecklichen Wunsch
  gespeichert (Action MEMORY_WRITE) — keine heimliche Speicherung.

Modul-State (VAULT_PATH/INBOX_PATH) wird von ``configure`` gesetzt — beim
Serverstart und nach jedem Settings-Save.
"""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("jarvis.memory")

# Wird von configure() gesetzt (server-Start + Settings-Save).
VAULT_PATH = ""   # Obsidian-Vault (config: obsidian_inbox_path)
INBOX_PATH = ""   # Brain-Dump-Ordner (config: obsidian_inbox_folder)

MEMORY_FILENAME = "Jarvis Memory.md"
FALLBACK_MEMORY_FILENAME = "memory.md"  # im Workspace, wenn kein Vault konfiguriert

_MEMORY_HEADER = (
    "# Jarvis Memory\n\n"
    "Langzeit-Gedaechtnis von Jarvis: Praeferenzen, Projekte, offene Loops.\n"
    "Diese Datei gehoert dir — bearbeite oder loesche Eintraege jederzeit.\n"
    "Jarvis speichert hier nur auf ausdrueckliche Aufforderung.\n"
)


def configure(vault_path: str, inbox_path: str) -> None:
    """Pfade setzen — einzige Stelle, an der der Modul-State veraendert wird."""
    global VAULT_PATH, INBOX_PATH
    VAULT_PATH = vault_path or ""
    INBOX_PATH = inbox_path or ""


# ── Tages-Inbox (Brain Dump) ─────────────────────────────────────────────────

def _today_inbox_file() -> str:
    """Pfad der heutigen Brain-Dump-Datei (Inbox)."""
    return os.path.join(INBOX_PATH, f"{time.strftime('%Y-%m-%d')} Brain Dump.md")


def inbox_available() -> bool:
    return bool(INBOX_PATH) and os.path.isdir(INBOX_PATH)


def read_today_inbox_sync(max_chars: int = 3000) -> str | None:
    """Heutige Inbox-Einträge lesen; None wenn nicht konfiguriert oder noch leer."""
    if not inbox_available():
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


async def write_inbox_entry(text: str, kategorie: str, ai=None, dedup: bool = True) -> str:
    """Hängt einen kategorisierten Eintrag an die heutige Brain-Dump-Datei an.

    ``dedup=True`` prüft vorher per Haiku (``ai``-Client) auf semantische
    Duplikate; Autosaves (z.B. Recherche) überspringen das mit ``dedup=False``.
    """
    if not INBOX_PATH:
        return "Inbox-Ordner nicht konfiguriert."
    os.makedirs(INBOX_PATH, exist_ok=True)
    file_path = _today_inbox_file()
    existing = ""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing = f.read()
    if dedup and ai is not None and existing.strip():
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


# ── Obsidian-Vault (Tasks, Zusammenfassung, letzte Notizen) ─────────────────

def get_tasks_sync() -> list[str]:
    """Read open tasks from Obsidian (sync)."""
    if not VAULT_PATH:
        return []
    try:
        tasks_path = os.path.join(VAULT_PATH, "Tasks.md")
        with open(tasks_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.strip().replace("- [ ]", "").strip() for l in lines if l.strip().startswith("- [ ]")]
    except Exception:
        logger.warning("Tasks konnten nicht gelesen werden", exc_info=True)
        return []


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
    if not VAULT_PATH or not os.path.isdir(VAULT_PATH):
        return None
    try:
        entries = _walk_vault_md(VAULT_PATH)
        folder_counts = {}
        for _, path, _ in entries:
            parts = os.path.relpath(path, VAULT_PATH).split(os.sep)
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
    if not VAULT_PATH or not os.path.isdir(VAULT_PATH):
        return ""
    try:
        entries = _walk_vault_md(VAULT_PATH)
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


# ── Langzeit-Gedaechtnis (transparent, nutzer-editierbar) ────────────────────

def memory_file_path() -> str:
    """Pfad der Memory-Datei: im Vault sichtbar, sonst Workspace-Fallback."""
    if VAULT_PATH and os.path.isdir(VAULT_PATH):
        return os.path.join(VAULT_PATH, MEMORY_FILENAME)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), FALLBACK_MEMORY_FILENAME)


def read_memory_sync(max_chars: int = 1500) -> str:
    """Inhalt des Langzeit-Gedaechtnisses (ohne Header), gekappt; "" wenn leer.

    Bei Uebergroesse wird der ANFANG gekappt — die neuesten Eintraege (unten)
    bleiben im Prompt.
    """
    path = memory_file_path()
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        logger.warning("Memory-Datei konnte nicht gelesen werden", exc_info=True)
        return ""
    body = content[len(_MEMORY_HEADER):] if content.startswith(_MEMORY_HEADER) else content
    body = body.strip()
    if len(body) > max_chars:
        body = "…" + body[-max_chars:]
    return body


def append_memory(text: str) -> str:
    """Haengt einen datierten Eintrag ans Langzeit-Gedaechtnis an (legt Datei an)."""
    text = (text or "").strip()
    if not text:
        return "Kein Inhalt zum Merken angegeben."
    path = memory_file_path()
    entry = f"- {time.strftime('%Y-%m-%d')}: {text}\n"
    try:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(_MEMORY_HEADER + "\n")
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
    except OSError as e:
        logger.warning("Memory-Datei konnte nicht geschrieben werden", exc_info=True)
        return f"Konnte mir das nicht merken (Dateifehler: {type(e).__name__})."
    return f"Dauerhaft gemerkt: {text}"

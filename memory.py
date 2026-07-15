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
import re
import time

logger = logging.getLogger("jarvis.memory")

# Wird von configure() gesetzt (server-Start + Settings-Save).
VAULT_PATH = ""   # Obsidian-Vault (config: obsidian_inbox_path)
INBOX_PATH = ""   # Brain-Dump-Ordner (config: obsidian_inbox_folder)

MEMORY_FILENAME = "Jarvis Memory.md"
FALLBACK_MEMORY_FILENAME = "memory.md"  # im Workspace, wenn kein Vault konfiguriert

# Bewusst in ASCII belassen: read_memory_sync() schneidet diesen Header per
# exaktem startswith() ab, er landet also NIE in Prompt/TTS. Eine Umlaut-Fassung
# wuerde bei bestehenden 'Jarvis Memory.md'-Dateien (alter Header) das Strippen
# brechen — dann leakt der alte Header in den Prompt. Darum unveraendert.
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
            system="Antworte NUR mit 'DUPLIKAT: [kurzer Ausschnitt des Originals]' oder 'NEU'. Prüfe ob der neue Eintrag semantisch das Gleiche aussagt wie ein bereits vorhandener Eintrag.",
            messages=[{"role": "user", "content": f"Vorhandene Einträge:\n{existing[:2000]}\n\nNeuer Eintrag:\n{text.strip()}"}],
        )
        verdict = dedup_resp.content[0].text.strip()
        if verdict.upper().startswith("DUPLIKAT"):
            excerpt = verdict[9:].strip(": ").strip()
            return f"Ähnlicher Eintrag existiert bereits: {excerpt}. Nicht neu gespeichert. Bisherige heutige Einträge:\n{existing[:1500]}"
    tag = "#" + kategorie.lower()
    entry = f"\n## {time.strftime('%H:%M')} · {kategorie}\n{tag}\n{text.strip()}\n"
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(entry)
    updated = existing + entry
    return f"Eintrag gespeichert (Kategorie: {kategorie}). Bisherige heutige Einträge:\n{updated[:1500]}"


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
            # Alle .md zaehlen — inkl. Root-Level-Notizen (by_folder deckt nur
            # Unterordner ab, wuerde total sonst verfaelschen).
            "total": len(entries),
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


# ── Projekt-Kontext (lokale Vault-Suche, token-sparsam) ─────────────────────

def vault_available() -> bool:
    return bool(VAULT_PATH) and os.path.isdir(VAULT_PATH)


# Woerter ohne Suchwert — werden aus der Query gefiltert. Bleibt danach nichts
# uebrig (z.B. "mein Projekt"), wird auf die ungefilterten Woerter zurueckgefallen.
_CONTEXT_STOPWORDS = frozenset({
    "was", "wie", "wer", "ist", "sind", "war", "der", "die", "das",
    "den", "dem", "des", "ein", "eine", "einem", "einen", "und", "oder",
    "mit", "von", "zum", "zur", "ueber", "über", "fuer", "für", "bei", "beim",
    "mein", "meine", "meinem", "meinen", "meiner", "mir", "ich", "gerade",
    "projekt", "projekte", "project", "notiz", "notizen", "note", "notes",
    "stand", "status", "aktuell", "aktuelle", "aktueller", "bitte",
    "the", "for", "and", "what", "about",
})

# Kleiner Bonus, wenn eine bereits relevante Notiz Projekt-/Aufgaben-Tags traegt.
_CONTEXT_BONUS_TAGS = ("#projekt", "#project", "#todo", "#aufgabe", "#jarvis")

# Dateien, deren Pfad nach Secrets aussieht, werden komplett uebersprungen.
_SECRET_PATH_RE = re.compile(
    r"(?i)(secret|passwor[dt]|passphrase|credential|zugangsdaten|token|"
    r"api[-_ ]?key|\.env|config\.json)"
)

# Zeilen, die nach Secrets aussehen, fliegen aus Ausschnitten raus (skippen,
# nicht redigieren). False Positives kuerzen nur den Ausschnitt — leaken nie.
_SECRET_LINE_RE = re.compile(
    r"(?i)(passwor[dt]|passphrase|secret|credential|token|bearer|authorization|"
    r"api[-_ ]?key|private[-_ ]?key|BEGIN [A-Z ]*PRIVATE KEY|"
    r"(sk-|ghp_|xoxb-|AKIA)[A-Za-z0-9_\-]{8,}|[A-Za-z0-9+/_\-]{40,}=*)"
)


def _context_excerpt(content: str, tokens: list[str], budget: int) -> str:
    """Kurzer relevanter Ausschnitt: ab der ersten Trefferzeile (Ueberschriften
    bevorzugt), YAML-Frontmatter und Secret-verdaechtige Zeilen ausgenommen."""
    if budget <= 0:
        return ""
    lines = content.splitlines()
    if lines and lines[0].strip() == "---":  # YAML-Frontmatter ueberspringen
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1:]
                break
    lines = [l for l in lines if not _SECRET_LINE_RE.search(l)]
    if not lines:
        return ""
    heading_hit = body_hit = None
    for i, line in enumerate(lines):
        line_cf = line.casefold()
        if any(t in line_cf for t in tokens):
            if line.lstrip().startswith("#"):
                heading_hit = i
                break
            if body_hit is None:
                body_hit = i
    anchor = heading_hit if heading_hit is not None else (body_hit or 0)
    chunk = "\n".join(lines[max(0, anchor - 1):]).strip()
    if len(chunk) > budget:
        chunk = chunk[:budget].rstrip() + "…"
    return chunk


def get_project_context_sync(query: str, limit: int = 5, max_chars: int = 3000) -> str:
    """Lokale, token-sparende Vault-Suche: relevante Notiz-Ausschnitte zur Query.

    Nur .md-Dateien, keine versteckten Ordner, nie der ganze Vault: pro Treffer
    ein kurzer Ausschnitt (Name, relativer Pfad, Aenderungsdatum), Gesamtausgabe
    auf ``max_chars`` gekappt. Secret-verdaechtige Dateien/Zeilen werden
    uebersprungen; die Memory-Datei laeuft weiter ueber read_memory_sync().
    Ein Walk plus ein gecappter Read pro Kandidat — kein Index/Cache in v1.
    """
    if not vault_available():
        return ""
    raw = [w for w in re.findall(r"\w+", (query or "").casefold()) if len(w) > 2]
    tokens = [w for w in raw if w not in _CONTEXT_STOPWORDS] or raw
    if not tokens:
        return ""

    try:
        entries = _walk_vault_md(VAULT_PATH)
    except Exception:
        logger.warning("Vault-Scan fehlgeschlagen", exc_info=True)
        return ""

    now = time.time()
    scored = []
    for mtime, path, name in entries:
        if os.path.basename(path) == MEMORY_FILENAME:
            continue  # Langzeit-Gedaechtnis soll die Treffer nicht dominieren
        rel = os.path.relpath(path, VAULT_PATH).replace(os.sep, "/")
        if _SECRET_PATH_RE.search(rel):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read(50_000)
        except OSError:
            continue
        body_cf = content.casefold()
        name_cf = name.casefold()
        dir_cf = os.path.dirname(rel).casefold()
        headings_cf = " ".join(
            l for l in body_cf.splitlines() if l.lstrip().startswith("#")
        )
        score = 0
        for tok in tokens:
            if tok in name_cf:
                score += 10   # Dateiname: stark
            if tok in headings_cf:
                score += 8    # Ueberschrift: stark
            if tok in dir_cf:
                score += 4    # Ordnername: mittel
            score += min(body_cf.count(tok), 5)  # Fliesstext: schwach, gedeckelt
        if score == 0:
            continue  # Boni allein qualifizieren nie
        if any(t in body_cf for t in _CONTEXT_BONUS_TAGS):
            score += 3
        age = now - mtime
        if age < 7 * 86400:
            score += 3
        elif age < 30 * 86400:
            score += 1
        scored.append((score, mtime, name, rel, content))

    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    per_hit = max(200, max_chars // max(1, limit))
    sep = "\n\n---\n\n"
    blocks = []
    used = 0
    for _score, mtime, name, rel, content in scored[:limit]:
        datum = time.strftime("%d.%m.%Y %H:%M", time.localtime(mtime))
        header = f"Notiz: {name} ({rel}, geändert {datum})"
        excerpt = _context_excerpt(content, tokens, per_hit - len(header) - 1)
        block = f"{header}\n{excerpt}" if excerpt else header
        extra = (len(sep) if blocks else 0) + len(block)
        if blocks and used + extra > max_chars:
            break
        blocks.append(block)
        used += extra
    return sep.join(blocks)[:max_chars]


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


def forget_memory(query: str) -> str:
    """Loescht passende Eintragszeilen aus dem Langzeit-Gedaechtnis (hartes Loeschen).

    Konservativ: nur zeilenbasierte Eintraege ('- '-Praefix, wie von
    ``append_memory`` geschrieben) werden betrachtet — Header und handschriftlicher
    Freitext des Nutzers bleiben unangetastet. Eine Zeile passt, wenn sie den
    Suchtext als Substring enthaelt ODER alle signifikanten Woerter (>2 Zeichen)
    des Suchtexts enthaelt. Kein Treffer => es wird nichts geloescht.
    """
    query = (query or "").strip()
    if not query:
        return "Kein Suchbegriff angegeben — es wurde nichts vergessen."
    path = memory_file_path()
    if not os.path.exists(path):
        return "Es ist noch nichts im Langzeit-Gedächtnis gespeichert."
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        logger.warning("Memory-Datei konnte nicht gelesen werden", exc_info=True)
        return "Konnte das Gedächtnis nicht lesen (Dateifehler)."

    q_lower = query.lower()
    q_words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 2]

    def _matches(line: str) -> bool:
        stripped = line.strip()
        if not stripped.startswith("- "):
            return False  # Header/Freitext nie anfassen
        low = stripped.lower()
        if q_lower in low:
            return True
        return bool(q_words) and all(w in low for w in q_words)

    kept, removed = [], []
    for line in lines:
        (removed if _matches(line) else kept).append(line)

    if not removed:
        return f"Dazu habe ich nichts gespeichert — es wurde nichts gelöscht ({query})."

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(kept)
    except OSError as e:
        logger.warning("Memory-Datei konnte nicht geschrieben werden", exc_info=True)
        return f"Konnte den Eintrag nicht löschen (Dateifehler: {type(e).__name__})."

    excerpts = "; ".join(l.strip().lstrip("- ").strip() for l in removed)[:300]
    return f"Vergessen ({len(removed)} Eintrag/Einträge gelöscht): {excerpts}"

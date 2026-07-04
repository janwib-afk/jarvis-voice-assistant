"""
Jarvis V2 — Clipboard Tools
Liest die Windows-Zwischenablage ohne Zusatzpakete (PowerShell Get-Clipboard).
"""

import logging
import subprocess

logger = logging.getLogger("jarvis.clipboard")

MAX_CLIPBOARD_CHARS = 4000


def get_clipboard_text(max_chars: int = MAX_CLIPBOARD_CHARS) -> str:
    """Text aus der Zwischenablage; "" bei leer, Nicht-Text-Inhalt oder Fehler.

    Blockiert bis ~5s — im Server via ``asyncio.to_thread`` aufrufen.
    """
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Clipboard -Raw",
            ],
            capture_output=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        logger.warning("Zwischenablage konnte nicht gelesen werden", exc_info=True)
        return ""
    if result.returncode != 0:
        logger.warning("Get-Clipboard Exit-Code %s", result.returncode)
        return ""
    text = result.stdout.decode("utf-8", errors="replace").strip()
    return text[:max_chars]

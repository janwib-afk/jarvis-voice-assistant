"""
Jarvis V2 — Status- und Diagnosefunktionen

Baut den /health-Report: passiv (keine bezahlten API-Aufrufe, kein
Browserstart) — nur Config-Checks, Dateisystem und Playwright-Zustand.
"""

import os

import browser_tools
import config_loader


def _key_status(value: str) -> dict:
    """Passiver Key-Check: vorhanden und kein Platzhalter (kein API-Aufruf)."""
    if not value or not value.strip():
        return {"ok": False, "detail": "API-Key fehlt in config.json."}
    if config_loader._looks_like_placeholder(value):
        return {"ok": False, "detail": "API-Key ist noch der Platzhalterwert."}
    return {"ok": True, "detail": "API-Key vorhanden"}


def _browser_status() -> dict:
    state = browser_tools.status()
    if state["connected"]:
        return {"ok": True, "detail": "Browser läuft"}
    if config_loader.find_chromium_executable() is not None:
        return {"ok": True, "detail": "Chromium gefunden, nicht gestartet"}
    return {"ok": False, "detail": "Chromium nicht gefunden — python -m playwright install chromium"}


def _vault_status(config: dict) -> dict:
    vault_path = config.get("obsidian_inbox_path", "")
    if not vault_path:
        return {"ok": False, "detail": "Kein Vault-Pfad konfiguriert (obsidian_inbox_path)."}
    if not os.path.isdir(vault_path):
        return {"ok": False, "detail": f"Pfad nicht erreichbar: {vault_path}"}
    return {"ok": True, "detail": "Vault erreichbar"}


def build_report(config: dict, warnings: list[str], data_loaded: bool, last_refresh: float | None) -> dict:
    """Kompletter /health-Payload — 'ok' heisst: der Server nimmt Verbindungen an."""
    return {
        "ok": True,
        "warnings": warnings,
        "services": {
            "config": {"ok": True},
            "llm": _key_status(config.get("anthropic_api_key", "")),
            "tts": _key_status(config.get("elevenlabs_api_key", "")),
            "browser": _browser_status(),
            "vault": _vault_status(config),
        },
        "startup": {"data_loaded": data_loaded, "last_refresh": last_refresh},
    }

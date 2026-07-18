"""Private Decode-Logik für eingehende Client Commands (Legacy + V1, RFC-0005 A1.B/A1.C).

Rein: keine Netz-/Transport-Nebenwirkungen. Server-IDs (correlation für Legacy bzw.
fehlende/ungültige V1-correlation) kommen aus dem injizierten idgen.
"""
from __future__ import annotations

import re

from ._model import ProtocolError, SayText, Stop

_MAX_TEXT_BYTES = 16 * 1024
_RESERVED = ("event_id", "session_id", "timestamp", "sensitivity")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def decode_legacy(raw, idgen):
    """Legacy: `{text}`→SayText, `{type:"stop"}`→Stop, sonst None (ignoriert, kein Fehler)."""
    if not isinstance(raw, dict):
        return None
    if raw.get("type") == "stop":
        return Stop(correlation_id=idgen.new_id())
    text = raw.get("text", "")
    if isinstance(text, str) and text.strip():
        return SayText(text=text.strip(), correlation_id=idgen.new_id())
    return None


def decode_v1(raw, idgen):
    """V1: strikte Command-Envelope; Server-Felder abgelehnt, additive ignoriert."""
    if not isinstance(raw, dict):
        return ProtocolError("bad_root", "Erwartet ein JSON-Objekt.", close_code=None)
    for field in _RESERVED:
        if field in raw:
            return ProtocolError("reserved_field",
                                 "Server-Felder dürfen nicht gesetzt werden.")
    if raw.get("protocol_version") != 1:
        return ProtocolError("unsupported_version",
                             "Nicht unterstützte Protokoll-Hauptversion.",
                             close_code=1002)
    ctype = raw.get("type")
    corr = raw.get("correlation_id")
    correlation_id = corr if isinstance(corr, str) and _UUID_RE.match(corr) else idgen.new_id()
    payload = raw.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return ProtocolError("invalid_command", "payload muss ein Objekt sein.")

    if ctype == "say_text":
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return ProtocolError("invalid_command", "payload.text fehlt.")
        norm = text.strip()
        if len(norm.encode("utf-8")) > _MAX_TEXT_BYTES:
            return ProtocolError("too_large", "Text überschreitet das Limit.",
                                 close_code=1009)
        return SayText(text=norm, correlation_id=correlation_id)
    if ctype == "stop":
        return Stop(correlation_id=correlation_id)
    return ProtocolError("unknown_command", "Unbekannter Command-Typ.")

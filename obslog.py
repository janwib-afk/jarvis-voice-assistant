"""obslog — strukturierte Operational Log Events mit zentraler, fail-closed Redaction.

RFC-0004 (Variante C). Das EINZIGE Emit-Interface des Anwendungscodes ist
``event(name, **fields)``. Jedes Event hat eine geschlossene Feld-Allowlist mit
festen Typen und Transformationen; alles andere wird verworfen (ohne ``str()``/
``repr()`` darauf aufzurufen). Es gibt kein Freitextfeld.

Sicherheitsgarantien:
- Rohe private Inhalte erscheinen auf KEINEM Level (D3): es gibt schlicht kein Feld
  dafuer.
- Unbekannte Event-Namen werden nie ausgegeben (sie koennten Daten tragen); nur ein
  neutraler Marker (D5).
- URLs werden auf ``schema://host`` reduziert (D7).
- Redaction/Formatierung/Sink koennen nie den Rohwert ausgeben; bei Fehler ein
  statischer, datenfreier Fallback (D8). ``event()`` wirft nie.
- Import-sicher (D9): der Import installiert keinen Handler, erzeugt keine Datei und
  aendert die Root-Logger-Konfiguration nicht. Logging ist prozessweit, kein
  Runtime-Zustand.
- Keine neue Dependency (D10).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from urllib.parse import urlsplit

# ── Feldtransformationen ─────────────────────────────────────────────────────
# Jede gibt einen SICHEREN Wert zurueck oder wirft/gibt _DROP, damit das Feld
# verworfen wird. Sie rufen NIE str()/repr() auf nicht vertrauenswuerdigen Werten.

_DROP = object()


def _as_int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else _DROP


def _as_bool(v):
    return v if isinstance(v, bool) else _DROP


def _as_id(v):
    """Stabile, kurze Bezeichner (Action-Typ, App-/Profil-ID, Reason-Code, Zone).

    Nur ASCII-Wortzeichen plus einige unbedenkliche Trenner; harte Laengengrenze.
    Freitext/Inhalt faellt damit strukturell raus (kein Leerzeichen erlaubt).
    """
    if not isinstance(v, str) or not v or len(v) > 64:
        return _DROP
    if not all(c.isalnum() or c in "._-:/" for c in v):
        return _DROP
    return v


def _as_host(v):
    """URL auf ``schema://host`` reduzieren — Pfad/Query/Fragment/Userinfo entfallen."""
    if not isinstance(v, str) or not v:
        return _DROP
    try:
        parts = urlsplit(v)
    except ValueError:
        return _DROP
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return _DROP
    host = parts.hostname
    return f"{parts.scheme}://{host}"


def _as_loc(v):
    """Sicherer Codeort (D6): hoechstens der Basename, nie Verzeichnis/Nutzerpfad.

    Ein voller Pfad wie ``C:\\Users\\Jan\\browser_tools.py`` wird auf
    ``browser_tools.py`` reduziert; eine optionale ``:Zeile`` bleibt erhalten.
    """
    if not isinstance(v, str) or not v:
        return _DROP
    base = os.path.basename(v.replace("\\", "/"))
    if not base or len(base) > 64:
        return _DROP
    if not all(c.isalnum() or c in "._-:" for c in base):
        return _DROP
    return base


# ── Eventkatalog (geschlossen) ───────────────────────────────────────────────
# name -> (level, {feld: transform}). Nur diese Felder erscheinen je Event.

_CATALOG: dict[str, tuple[int, dict]] = {
    # WebSocket / Nachrichten
    "ws.connected":        (logging.INFO,    {}),
    "ws.rejected":         (logging.WARNING, {"reason": _as_id}),
    "message.received":    (logging.DEBUG,   {"text_len": _as_int}),
    "message.stopped":     (logging.INFO,    {"was_busy": _as_bool}),
    "message.failed":      (logging.WARNING, {"error_type": _as_id, "where": _as_id}),
    # Settings / Config
    "settings.saved":      (logging.INFO,    {"changed": _as_int}),
    "settings.refresh_failed": (logging.WARNING, {"error_type": _as_id}),
    "settings.conflict":   (logging.INFO,    {}),
    "config.migrated":     (logging.INFO,    {"from_version": _as_int, "to_version": _as_int}),
    "config.restore_failed": (logging.ERROR, {"error_type": _as_id, "location": _as_loc}),
    "config.startup_failed": (logging.ERROR, {"error_type": _as_id}),
    "config.startup_degraded": (logging.WARNING, {"count": _as_int}),
    # Kontextdaten-Refresh
    "context.refreshed":   (logging.INFO,    {"weather_ok": _as_bool, "tasks": _as_int,
                                              "notes": _as_int, "inbox_present": _as_bool}),
    "context.refresh_failed": (logging.WARNING, {"stage": _as_id, "error_type": _as_id}),
    # Actions
    "action.started":      (logging.INFO,    {"action": _as_id}),
    "action.finished":     (logging.INFO,    {"action": _as_id, "result_len": _as_int}),
    "action.cancelled":    (logging.INFO,    {"action": _as_id}),
    "action.failed":       (logging.WARNING, {"action": _as_id, "error_type": _as_id,
                                              "component": _as_id, "where": _as_id,
                                              "location": _as_loc}),
    "action.rejected":     (logging.INFO,    {"reason": _as_id}),
    # LLM / TTS
    "llm.request_failed":  (logging.WARNING, {"error_type": _as_id}),
    "llm.response_received": (logging.DEBUG, {"reply_len": _as_int}),
    "tts.request_failed":  (logging.WARNING, {"error_type": _as_id, "status": _as_int}),
    "tts.chunk_received":  (logging.DEBUG,   {"status": _as_int, "size": _as_int}),
    "tts.synthesis_failed": (logging.WARNING, {"error_type": _as_id}),
    # Browser
    "browser.fallback":    (logging.INFO,    {"url": _as_host, "reason": _as_id}),
    "browser.request_failed": (logging.WARNING, {"url": _as_host, "status": _as_int,
                                                 "error_type": _as_id}),
    "browser.source_skipped": (logging.INFO, {"url": _as_host}),
    "browser.foreground_failed": (logging.DEBUG, {"error_type": _as_id}),
    "browser.reconnecting": (logging.WARNING, {"error_type": _as_id}),
    # Memory / Vault
    "memory.read_failed":  (logging.WARNING, {"error_type": _as_id}),
    "memory.write_failed": (logging.WARNING, {"error_type": _as_id}),
    "vault.scan_failed":   (logging.WARNING, {"error_type": _as_id}),
    "inbox.autosave_failed": (logging.WARNING, {"error_type": _as_id}),
    "clipboard.read_failed": (logging.WARNING, {"error_type": _as_id, "code": _as_int}),
    # Launcher / Apps / Monitors
    "launcher.configured": (logging.INFO,    {"apps": _as_int, "profiles": _as_int,
                                              "active": _as_id}),
    "launcher.normalize_warning": (logging.WARNING, {"reason": _as_id}),
    "app.launched":        (logging.INFO,    {"app": _as_id, "kind": _as_id}),
    "app.launch_failed":   (logging.WARNING, {"app": _as_id, "error_type": _as_id}),
    "autostart.changed":   (logging.INFO,    {"app": _as_id, "enabled": _as_bool}),
    "placement.changed":   (logging.INFO,    {"app": _as_id, "monitor": _as_id, "zone": _as_id}),
    "profile.changed":     (logging.INFO,    {"kind": _as_id, "active": _as_id}),
    "monitor.detect_failed": (logging.WARNING, {"error_type": _as_id}),
    # Capability-Audit (RFC-0007 §20, Amendment 1 §A1.6) — ausschliesslich
    # Metadaten. Payloads, Inhalte, URLs, Preview-Hashes und Secrets sind hier
    # strukturell nicht nennbar, weil es schlicht kein Feld dafuer gibt.
    "capability.attempted": (logging.INFO,   {"capability": _as_id, "version": _as_int,
                                              "outcome": _as_id, "duration_ms": _as_int,
                                              "effects": _as_id, "reason": _as_id}),
    "capability.unverified": (logging.INFO,  {"capability": _as_id, "version": _as_int}),
    # Server-Lifecycle
    "server.started":      (logging.INFO,    {}),
    "health.broadcast_failed": (logging.WARNING, {"error_type": _as_id}),
}

_LEVEL_NAMES = {logging.DEBUG: "DEBUG", logging.INFO: "INFO",
                logging.WARNING: "WARNING", logging.ERROR: "ERROR",
                logging.CRITICAL: "CRITICAL"}


# ── Sinks ────────────────────────────────────────────────────────────────────

class MemorySink:
    """Test-Sink: sammelt die fertig gerenderten Zeilen (D12)."""

    def __init__(self):
        self.lines: list[str] = []

    def write_line(self, line: str) -> None:
        self.lines.append(line)


class _StderrSink:
    """Produktiver Sink: eine Zeile pro Event nach stderr. Kein FileHandler (D10)."""

    def write_line(self, line: str) -> None:
        stream = sys.stderr
        stream.write(line + "\n")
        stream.flush()


# ── Modulzustand (prozessweit, kein Runtime-State) ───────────────────────────

_sink = None            # None => noch nicht konfiguriert: Events werden verworfen
_sink_explicit = False  # True => Sink wurde explizit gesetzt (Test) — nie ungefragt ersetzen
_fmt = "text"
_min_level = logging.INFO


def configure(sink=None, fmt: str = "text", level=None) -> None:
    """Einmalig am Startpfad aufrufen. Idempotent; ungueltiges fmt -> 'text'.

    Ein explizit uebergebener ``sink`` (Tests) wird gesetzt und als *explizit*
    markiert. Ein spaeterer Produktionsstart ruft ``configure(sink=None)`` — das
    setzt den stderr-Sink NUR, wenn noch keiner existiert, und ersetzt einen bereits
    (explizit oder produktiv) gesetzten Sink NICHT (verhindert das stille
    Ueberschreiben eines Test-Sinks im Lifespan). KEINE Datei, KEIN Root-Handler.
    """
    global _sink, _sink_explicit, _fmt, _min_level
    if sink is not None:
        _sink = sink
        _sink_explicit = True
    elif _sink is None:
        _sink = _StderrSink()
        _sink_explicit = False
    # sonst: vorhandenen Sink behalten (idempotent; kein Ueberschreiben)
    _fmt = fmt if fmt in ("text", "jsonl") else "text"
    if level is not None:
        resolved = getattr(logging, str(level).upper(), None) if isinstance(level, str) else level
        _min_level = resolved if isinstance(resolved, int) else logging.INFO


def reset() -> None:
    """Testhilfe: Konfiguration zuruecksetzen (kein Sink)."""
    global _sink, _sink_explicit, _fmt, _min_level
    _sink = None
    _sink_explicit = False
    _fmt = "text"
    _min_level = logging.INFO


# ── Redaction + Formatierung ─────────────────────────────────────────────────

def _redact(name: str, fields: dict) -> tuple[dict, int]:
    """Nur erlaubte, korrekt transformierbare Felder behalten. Rueckgabe
    ``(safe_fields, dropped_count)``. Ruft nie str()/repr() auf Rohwerten auf."""
    allowed = _CATALOG[name][1]
    safe: dict = {}
    dropped = 0
    for key, value in fields.items():
        transform = allowed.get(key)
        if transform is None:
            dropped += 1
            continue
        try:
            out = transform(value)
        except Exception:
            out = _DROP
        if out is _DROP:
            dropped += 1
        else:
            safe[key] = out
    return safe, dropped


def _timestamp() -> str:
    """UTC-ISO-8601 auf Sekunden (kein Korrelations-/Protokoll-ID-Zusatz)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _render(name: str, level: int, safe: dict, dropped: int) -> str:
    if dropped:
        safe = {**safe, "dropped_fields": dropped}
    lvl = _LEVEL_NAMES.get(level, "INFO")
    ts = _timestamp()
    logger = name.split(".", 1)[0]  # Namespace als Logger (z.B. 'action', 'config')
    if _fmt == "jsonl":
        record = {"ts": ts, "logger": logger, "level": lvl, "event": name, **safe}
        return json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    parts = " ".join(f"{k}={v}" for k, v in safe.items())
    return f"{ts} {logger} [{lvl}] {name}" + (f" {parts}" if parts else "")


def _fallback_line() -> str:
    """Statischer, datenfreier Fallback (D8): keine Quelldaten, keine Namen."""
    if _fmt == "jsonl":
        return '{"event":"logging.error","level":"ERROR"}'
    return "[ERROR] logging.error"


# ── Emit ─────────────────────────────────────────────────────────────────────

def event(name: str, **fields) -> None:
    """Das EINZIGE Emit-Interface. Wirft nie; bricht den Ablauf nie ab (D8)."""
    sink = _sink
    if sink is None:
        return
    try:
        spec = _CATALOG.get(name)
        if spec is None:
            # Unbekannter Name koennte Daten tragen -> nie ausgeben, nur Marker.
            line = ('{"event":"unknown_event","level":"WARNING"}'
                    if _fmt == "jsonl" else "[WARNING] unknown_event")
            sink.write_line(line)
            return
        level, _ = spec
        if level < _min_level:
            return
        safe, dropped = _redact(name, fields)
        sink.write_line(_render(name, level, safe, dropped))
    except Exception:
        # Fail-closed, keine Rekursion: statische, datenfreie Zeile — und selbst
        # deren Fehler wird sicher verschluckt.
        try:
            sink.write_line(_fallback_line())
        except Exception:
            pass


# ── Startverdrahtung (Slice 2 nutzt dies) ────────────────────────────────────

def format_from_env(environ=None) -> str:
    """JARVIS_LOG_FORMAT=text|jsonl; ungueltig -> 'text'."""
    environ = os.environ if environ is None else environ
    value = (environ.get("JARVIS_LOG_FORMAT") or "text").strip().lower()
    return value if value in ("text", "jsonl") else "text"


# ── Legacy-/Drittanbieter-Schutznetz (RFC-0004 §17, Slice 5) ─────────────────
# Ein zentraler, sanitierender Root-Handler fuer Records, die NICHT ueber
# obslog.event() laufen (uvicorn/uvicorn.access/httpx/anthropic/playwright und
# jeder noch nicht migrierte jarvis.*-Aufruf). Er ist ein NETZ, keine Garantie:
# die harte Garantie liefern die Allowlist-Events. Kein FileHandler, keine
# neue Dependency (D10). Wird am Startpfad installiert, NICHT beim Import (D9).

_PROTECTION_TAG = "obslog.protection"
# Drittanbieter-Logger, deren INFO-Zeilen (Request-/Access-Zeilen mit URLs bzw.
# dem Session-Token) konservativ auf WARNING gehoben werden (§25).
_NOISY_THIRD_PARTY = ("uvicorn.access", "httpx", "httpcore", "anthropic", "playwright")

_URL_RE = re.compile(r"https?://\S+")
# Sensible Query-Parameter in bloßen Pfaden (z.B. uvicorn.access: GET /ws?token=…).
_QUERY_SECRET_RE = re.compile(
    r"([?&](?:token|key|api[_-]?key|password|passwd|secret|access_token|auth)=)[^\s&\"'<>]+",
    re.IGNORECASE)
# Secret-/Token-Muster (Anthropic-Keys, Bearer-Header, JWTs).
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9\-_]{6,}|Bearer\s+\S+|eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)")


def _url_to_host(match) -> str:
    url = match.group(0)
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<url>"
    if parts.scheme in ("http", "https") and parts.hostname:
        return f"{parts.scheme}://{parts.hostname}"
    return "<url>"


def _sanitize_text(text: str) -> str:
    """URLs auf Schema+Host kuerzen, sensible Query-Werte und Secret-Muster maskieren."""
    text = _URL_RE.sub(_url_to_host, text)
    text = _QUERY_SECRET_RE.sub(r"\1<redacted>", text)
    text = _SECRET_RE.sub("<redacted>", text)
    return text


class _SanitizingFilter(logging.Filter):
    """Neutralisiert einen Record IN-PLACE, damit ihn KEIN Handler mehr roh ausgeben
    kann (auch ein bereits vorhandener, nicht-propagierender oder ueber handleError):
    Nachricht sanitiert, Args geleert, Traceback/exc_text/Stack entfernt. Gibt immer
    True zurueck (verwirft nichts — nur Redaction)."""

    _obslog_tag = _PROTECTION_TAG

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = "<unrenderable>"
        record.msg = _sanitize_text(msg)
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class _ProtectionFormatter(logging.Formatter):
    """Rendert Drittanbieter-Records fail-closed: Timestamp, Logger, Level und
    sanitierte Nachricht — nie Traceback/exc_text/rohe Args. Wirft NIE (Fallback).
    In JSONL als eine gueltige JSON-Zeile (durchgaengiges JSONL, D4)."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            try:
                msg = record.getMessage()
            except Exception:
                msg = "<unrenderable>"
            safe = _sanitize_text(msg)
            ts = _timestamp()
            if _fmt == "jsonl":
                return json.dumps(
                    {"ts": ts, "logger": record.name, "level": record.levelname,
                     "event": "thirdparty.log", "message": safe},
                    ensure_ascii=False, separators=(",", ":"))
            return f"{ts} {record.name} [{record.levelname}] {safe}"
        except Exception:
            return _fallback_line()


class _ProtectionHandler(logging.StreamHandler):
    """Wie StreamHandler, aber ``handleError`` gibt NIE den Rohrecord, rohe Args oder
    einen Traceback aus — auch nicht bei ``logging.raiseExceptions=True``. Hoechstens
    eine statische, datenfreie Fallback-Zeile auf den echten stderr."""

    def handleError(self, record: logging.LogRecord) -> None:
        try:
            sys.stderr.write(_fallback_line() + "\n")
            sys.stderr.flush()
        except Exception:
            pass


def _iter_all_loggers():
    root = logging.getLogger()
    yield root
    for obj in list(root.manager.loggerDict.values()):
        if isinstance(obj, logging.Logger):
            yield obj


def _neutralize_existing_handlers(filt: logging.Filter) -> None:
    """Den sanitierenden Filter an ALLE bereits vorhandenen Handler haengen (Root +
    jeder benannte Logger, auch ``propagate=False``), damit sie denselben Record nicht
    mehr roh ausgeben. Ein zusaetzlicher sicherer Handler allein genuegt nicht."""
    for logger in _iter_all_loggers():
        for h in list(logger.handlers):
            if getattr(h, "_obslog_tag", None) == _PROTECTION_TAG:
                continue
            if not any(getattr(f, "_obslog_tag", None) == _PROTECTION_TAG
                       for f in h.filters):
                h.addFilter(filt)


def install_protection(stream=None) -> None:
    """Zentrales Schutznetz installieren (idempotent).

    (1) Bereits vorhandene Handler werden mit dem sanitierenden Filter neutralisiert;
    (2) ein eigener fail-closed Handler wird an den Root gehaengt. ``stream`` erlaubt
    Tests, den formatierten Output abzugreifen; Default stderr.
    """
    root = logging.getLogger()
    for h in root.handlers:
        if getattr(h, "_obslog_tag", None) == _PROTECTION_TAG:
            return  # bereits installiert
    filt = _SanitizingFilter()
    _neutralize_existing_handlers(filt)
    handler = _ProtectionHandler(stream if stream is not None else sys.stderr)
    handler._obslog_tag = _PROTECTION_TAG
    handler.setLevel(logging.DEBUG)
    handler.addFilter(filt)
    handler.setFormatter(_ProtectionFormatter())
    root.addHandler(handler)
    # Root mindestens auf WARNING lassen (Default), damit WARNING+ das Netz erreicht.
    if root.level == logging.NOTSET:
        root.setLevel(logging.WARNING)
    # Laute INFO-Logger konservativ daempfen (Request-/Access-Zeilen).
    for name in _NOISY_THIRD_PARTY:
        logging.getLogger(name).setLevel(logging.WARNING)


def uninstall_protection() -> None:
    """Testhilfe: Schutz-Handler entfernen UND die sanitierenden Filter von allen
    (weiterhin vorhandenen) Handlern loesen."""
    for logger in _iter_all_loggers():
        for h in list(logger.handlers):
            if getattr(h, "_obslog_tag", None) == _PROTECTION_TAG:
                logger.removeHandler(h)
            else:
                for f in list(h.filters):
                    if getattr(f, "_obslog_tag", None) == _PROTECTION_TAG:
                        h.removeFilter(f)

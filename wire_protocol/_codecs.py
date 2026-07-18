"""Private Codecs: LegacyCodec (byte-/shape-exakt) und V1Codec (nested Envelope).

Die Projektionsregistry `_PROJECTIONS` bildet je Event-Typ auf eine `_Proj` ab:
legacy_type, legacy_fields(event)->dict, has_legacy_ts, sensitivity, v1_fields(event)->dict.
Anwendungscode sieht diese Interna nie.

Legacy-`ts` ist ein Epoch-Float (`clock.now_epoch()`) und steht — wie heute — als
LETZTES Feld im Frame. Im V1-Envelope gibt es keinen Legacy-Epoch; die Zeit steckt im
Envelope-`timestamp` (RFC3339).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ._model import (ActionLifecycle, AppEvent, ErrorEvent, Health, LauncherChanged,
                     MusicChanged, Sensitivity, SpokenResponse, StopAck)


# Actions, deren `detail` (Screen-/Clipboard-/Vault-Ausschnitt, Rohtext) unter V1
# minimiert wird (A1.D). Legacy bleibt byte-exakt.
_SENSITIVE_ACTIONS = frozenset({"SCREEN", "CLIPBOARD", "PROJECT_CONTEXT", "RESEARCH"})


@dataclass(frozen=True)
class _Proj:
    legacy_type: str
    legacy_fields: Callable[[object], dict]
    has_legacy_ts: bool
    sensitivity: Sensitivity
    v1_fields: Callable[[object], dict]


_PROJECTIONS = {
    Health: _Proj(
        "health", lambda e: {"warnings": list(e.warnings)}, False,
        # V1-Health ist eine redigierte OEFFENTLICHE Projektion (D9): Warnungstexte
        # koennen lokale Pfade enthalten -> nur die Anzahl auf dem Wire.
        Sensitivity.PUBLIC, lambda e: {"warnings_count": len(e.warnings)}),
    SpokenResponse: _Proj(
        "response", lambda e: {"text": e.text, "audio": e.audio}, False,
        Sensitivity.PERSONAL, lambda e: {"text": e.text, "audio": e.audio}),
    ActionLifecycle: _Proj(
        "action",
        lambda e: {"phase": e.phase, "action": e.action, "label": e.label, "detail": e.detail},
        True, Sensitivity.PERSONAL,
        # V1-Projektion: bei sensiblen Actions (Screen/Clipboard/Vault) wird `detail`
        # minimiert — es kann Ausschnitte sensibler Inhalte tragen (A1.D). Legacy
        # bleibt exakt (roher detail).
        lambda e: {"phase": e.phase, "action": e.action, "label": e.label,
                   "detail": "" if e.action in _SENSITIVE_ACTIONS else e.detail}),
    ErrorEvent: _Proj(
        "error",
        lambda e: {"component": e.component, "text": e.message, "hint": e.hint}, False,
        Sensitivity.LOCAL,
        lambda e: {"component": e.component, "code": e.code, "message": e.message,
                   "hint": e.hint, "retryable": e.retryable}),
    StopAck: _Proj(
        "stop", lambda e: {}, False, Sensitivity.PUBLIC, lambda e: {}),
    MusicChanged: _Proj(
        "music_changed", lambda e: {"selected": e.selected}, True,
        Sensitivity.LOCAL, lambda e: {"selected": e.selected}),
    AppEvent: _Proj(
        "app_event",
        lambda e: {"ok": e.ok, "app": e.app, "name": e.name, "message": e.message}, True,
        Sensitivity.LOCAL,
        lambda e: {"ok": e.ok, "app": e.app, "name": e.name, "message": e.message}),
    LauncherChanged: _Proj(
        "launcher_changed",
        lambda e: {"kind": e.kind, "active_profile": e.active_profile}, True,
        Sensitivity.LOCAL,
        lambda e: {"kind": e.kind, "active_profile": e.active_profile}),
}


class LegacyCodec:
    def __init__(self, clock) -> None:
        self._clock = clock

    def encode(self, event) -> dict:
        proj = _PROJECTIONS[type(event)]
        frame = {"type": proj.legacy_type, **proj.legacy_fields(event)}
        if proj.has_legacy_ts:
            frame["ts"] = self._clock.now_epoch()  # Epoch-Float, als LETZTES Feld
        return frame


class V1Codec:
    def __init__(self, clock, idgen) -> None:
        self._clock = clock
        self._idgen = idgen

    def encode(self, event, ctx, correlation_id, *, event_id=None, timestamp=None) -> dict:
        proj = _PROJECTIONS[type(event)]
        return {
            "protocol_version": 1,
            "type": proj.legacy_type,
            "event_id": event_id if event_id is not None else self._idgen.new_id(),
            "correlation_id": correlation_id,
            "session_id": ctx.session_id,
            "timestamp": timestamp if timestamp is not None else self._clock.now_iso(),
            "sensitivity": proj.sensitivity.value,
            "payload": proj.v1_fields(event),
        }

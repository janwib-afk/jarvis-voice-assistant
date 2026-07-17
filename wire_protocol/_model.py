"""Transportneutrales Typmodell (immutable stdlib-Dataclasses) — kein Pydantic."""
from __future__ import annotations

import enum
from dataclasses import dataclass


class Sensitivity(enum.Enum):
    PUBLIC = "public"
    LOCAL = "local"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


_LEGACY = "legacy"
_V1 = "v1"


@dataclass(frozen=True)
class ProtocolContext:
    """Ausgehandelter Kontext pro Verbindung (WS) bzw. Request (REST)."""
    version: str
    session_id: str | None = None

    @classmethod
    def legacy(cls) -> "ProtocolContext":
        return cls(_LEGACY, None)

    @classmethod
    def v1(cls, session_id: str | None = None) -> "ProtocolContext":
        return cls(_V1, session_id)

    @property
    def is_v1(self) -> bool:
        return self.version == _V1


# ── Server Events (semantisch; Wire-Projektion + Sensitivität in _codecs) ─────

@dataclass(frozen=True)
class Health:
    warnings: tuple = ()


@dataclass(frozen=True)
class SpokenResponse:
    text: str
    audio: str = ""


@dataclass(frozen=True)
class ActionLifecycle:
    phase: str            # start | done | error
    action: str
    label: str
    detail: str = ""


@dataclass(frozen=True)
class ErrorEvent:
    component: str        # llm | tts | browser | action | config
    message: str          # sichere Nachricht (Legacy-Feld "text")
    hint: str = ""
    code: str = "error"   # maschinenlesbarer Code (V1)
    retryable: bool = False


@dataclass(frozen=True)
class StopAck:
    pass


@dataclass(frozen=True)
class MusicChanged:
    selected: str


@dataclass(frozen=True)
class AppEvent:
    ok: bool
    app: str | None
    name: str
    message: str


@dataclass(frozen=True)
class LauncherChanged:
    kind: str
    active_profile: str


# ── Client Commands (decodiert) ───────────────────────────────────────────────

@dataclass(frozen=True)
class SayText:
    text: str
    correlation_id: str


@dataclass(frozen=True)
class Stop:
    correlation_id: str


# ── Fehler (Decode-Ergebnis und/oder V1-Fehler-Event) ─────────────────────────

@dataclass(frozen=True)
class ProtocolError:
    code: str                 # maschinenlesbar (invalid_command, unknown_command, …)
    message: str              # sichere Nachricht, nie Rohwert/repr/Pfad
    hint: str = ""
    retryable: bool = False
    close_code: int | None = None  # WS-Close-Code (None = Verbindung bleibt offen)

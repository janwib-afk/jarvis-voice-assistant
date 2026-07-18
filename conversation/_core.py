"""Reiner Transitionskern der Conversation (RFC-0006 §9/§10/§15, D12).

``step(state, event) -> (state, effects)`` ist deterministisch, synchron und
**I/O-frei**: kein Task, kein Lock, keine Queue-Implementierung, kein Wire-Codec,
kein Netz. Effekte werden nur BESCHRIEBEN; ausgefuehrt werden sie ausserhalb
(``conversation._session``). Ungueltige Uebergaenge sind **totale No-Ops** (§19) —
der Kern wirft nie, damit ein Race nie die Verbindung beendet.

Zustaende (D5):
  Session : open -> closing -> closed
  Turn    : queued | processing | awaiting-confirmation | executing-action | cancelling
``completed``/``failed``/``cancelled`` sind ERGEBNISSE, keine verweilenden Zustaende;
``ready`` ist abgeleitet; die Queue-Laenge ist Daten.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

# ── Ereignisse (§17) ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SayTextReceived:
    text: str
    correlation_id: str


@dataclass(frozen=True)
class StopReceived:
    correlation_id: str


@dataclass(frozen=True)
class ConfirmationOpened:
    """Die Verarbeitung hat eine riskante Aktion zurueckgestellt (Rueckfrage laeuft)."""
    action: Any
    origin_correlation_id: str


@dataclass(frozen=True)
class TurnFinished:
    """Die Turn-Verarbeitung endete normal (Ergebnis ``completed``)."""


@dataclass(frozen=True)
class TurnFailed:
    """Die Turn-Verarbeitung endete mit einem Fehler (Ergebnis ``failed``)."""


@dataclass(frozen=True)
class ExecutionEnded:
    """Eine abgebrochene Verarbeitung ist vollstaendig ausgelaufen."""


@dataclass(frozen=True)
class Disconnected:
    """Verbindung beendet bzw. Runtime-Shutdown."""


# ── Effekte (§18) ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StartTurn:
    text: str
    correlation_id: str


@dataclass(frozen=True)
class CancelActive:
    """Laufende Verarbeitung abbrechen (Anforderung, nicht Abschluss — D7)."""


@dataclass(frozen=True)
class EmitStopAck:
    correlation_id: str


@dataclass(frozen=True)
class EmitStopped:
    """Gesprochene Bestaetigung 'Okay, gestoppt.' — nur wenn wirklich etwas lief."""
    correlation_id: str


@dataclass(frozen=True)
class CloseSession:
    """Ressourcen der Session freigeben (Kanal abmelden, Verlauf verwerfen)."""


# ── Zustand ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Turn:
    state: str
    text: str
    correlation_id: str


@dataclass(frozen=True)
class Suspended:
    """Offene Bestaetigung = suspendierter Turn im Session-Aggregat (D6)."""
    action: Any
    origin_correlation_id: str


@dataclass(frozen=True)
class SessionState:
    lifecycle: str = "open"
    active: Turn | None = None
    queue: tuple[SayTextReceived, ...] = ()
    suspended: Suspended | None = None

    @property
    def is_ready(self) -> bool:
        """Abgeleitet (D5): offen und kein aktiver Turn — KEIN eigener Zustand."""
        return self.lifecycle == "open" and self.active is None

    def view(self) -> dict:
        """Unveraenderliche, semantische Projektion — nie Tasks/Locks/Queue-Interna."""
        return {
            "lifecycle": self.lifecycle,
            "turn": self.active.state if self.active is not None else None,
            "queued": len(self.queue),
            "awaiting_confirmation": self.suspended is not None,
            "ready": self.is_ready,
        }


def initial_session_state() -> SessionState:
    return SessionState()


# ── Transitionen (§15.1/§15.2) ──────────────────────────────────────────────

_NOOP: tuple = ()


def _start_next(state: SessionState) -> tuple[SessionState, tuple]:
    """Naechsten wartenden Turn starten — oder in den abgeleiteten Ready-Zustand."""
    if not state.queue:
        return replace(state, active=None), _NOOP
    nxt, rest = state.queue[0], state.queue[1:]
    turn = Turn(state="processing", text=nxt.text, correlation_id=nxt.correlation_id)
    return (replace(state, active=turn, queue=rest),
            (StartTurn(text=nxt.text, correlation_id=nxt.correlation_id),))


def step(state: SessionState, event: Any) -> tuple[SessionState, tuple]:
    """Gesamte Transitionsfunktion. Unbekannte/ungueltige Kombinationen: No-Op."""
    # I4: closing/closed nehmen keine Commands mehr an.
    if state.lifecycle != "open":
        if isinstance(event, ExecutionEnded) and state.lifecycle == "closing":
            return replace(state, lifecycle="closed", active=None), _NOOP
        return state, _NOOP

    if isinstance(event, SayTextReceived):
        # Aktiver Turn (auch waehrend cancelling, Praezisierung 5) -> einreihen.
        if state.active is not None:
            return replace(state, queue=state.queue + (event,)), _NOOP
        turn = Turn(state="processing", text=event.text, correlation_id=event.correlation_id)
        return (replace(state, active=turn),
                (StartTurn(text=event.text, correlation_id=event.correlation_id),))

    if isinstance(event, StopReceived):
        effects: tuple = ()
        active = state.active
        # 'was_busy' nur, wenn wirklich etwas laeuft: ein bereits abbrechender Turn
        # zaehlt nicht erneut (wiederholter Stop bleibt idempotent).
        was_busy = active is not None and active.state != "cancelling"
        if was_busy:
            effects += (CancelActive(),)
            active = replace(active, state="cancelling")
        effects += (EmitStopAck(correlation_id=event.correlation_id),)
        if was_busy:
            effects += (EmitStopped(correlation_id=event.correlation_id),)
        return replace(state, active=active, queue=(), suspended=None), effects

    if isinstance(event, ConfirmationOpened):
        return replace(state, suspended=Suspended(
            action=event.action,
            origin_correlation_id=event.origin_correlation_id)), _NOOP

    if isinstance(event, (TurnFinished, TurnFailed, ExecutionEnded)):
        if state.active is None:
            return state, _NOOP
        return _start_next(state)

    if isinstance(event, Disconnected):
        effects = ()
        if state.active is not None and state.active.state != "cancelling":
            effects += (CancelActive(),)
        effects += (CloseSession(),)
        return replace(state, lifecycle="closing", queue=(), suspended=None), effects

    return state, _NOOP

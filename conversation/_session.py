"""Runtime-eigener Conversation-Manager und Sessions (RFC-0006 D4, §23).

Der Manager erzeugt und **besitzt** die Sessions; eine Session besitzt Verlauf,
offene Bestaetigung, Turn-Queue, aktiven Turn und den Worker-/Cancellation-Lifecycle
als **private** Implementierung. Nach aussen sichtbar sind nur ``open``/``close``,
``submit``/``on`` und die unveraenderliche ``snapshot()``-Projektion — niemals Tasks,
Locks oder Queue-Interna (§24).

Die Entscheidungen trifft ausschliesslich der reine Kern (``_core.step``); hier
werden nur die zurueckgegebenen Effekte ausgefuehrt (D12: I/O ausserhalb des Kerns).

``ConversationChannel``/``ConnectionRegistry`` bleiben unveraenderte
RFC-0005-Transportmodule — dieses Modul besitzt Conversation-Zustand, nicht den Codec.
"""
from __future__ import annotations

import asyncio
import contextlib

import obslog
import wire_protocol as wp

from ._core import (
    CancelActive, CloseSession, ConfirmationOpened, EmitStopAck, EmitStopped,
    ExecutionEnded, SayTextReceived, StopReceived, TurnFailed, TurnFinished,
    initial_session_state, step,
)

STOPPED_TEXT = "Okay, gestoppt."
# Verlaufsgrenzen unveraendert aus assistant_core uebernommen (Verhaltenskompatibilitaet).
MAX_HISTORY = 60
LLM_HISTORY = 16


class TurnContext:
    """Expliziter Session-/Turn-Kontext statt Modul-Globals (RFC-0006 §8).

    Traegt den session-eigenen Verlauf und die beim Turn-Start KONSUMIERTE offene
    Bestaetigung. ``request_confirmation`` meldet eine neue Rueckfrage an den
    Session-Zustand zurueck — der Kern bleibt die einzige Wahrheit.
    """

    def __init__(self, history: list, pending, request_confirmation, correlation_id: str):
        self._history = history
        self.pending = pending
        self._request_confirmation = request_confirmation
        self.correlation_id = correlation_id

    def remember(self, role: str, content: str) -> None:
        """Verlauf anhaengen und hart kappen (kein unbegrenztes Wachstum)."""
        self._history.append({"role": role, "content": content})
        del self._history[:-MAX_HISTORY]

    def recent(self, limit: int = LLM_HISTORY) -> list:
        """Die juengsten Nachrichten fuer den LLM-Kontext."""
        return self._history[-limit:]

    def history_snapshot(self) -> tuple:
        """Unveraenderlicher Verlaufs-Snapshot fuer den ActionContext."""
        return tuple(dict(msg) for msg in self._history)

    def request_confirmation(self, action) -> None:
        self._request_confirmation(action)


class ConversationSession:
    """Eine Conversation Session: lebt von Accept bis Disconnect."""

    def __init__(self, manager: "ConversationManager", channel, run_turn):
        self._manager = manager
        self._channel = channel
        self._run_turn = run_turn
        self._state = initial_session_state()
        # Session-eigener Verlauf (Daten, kein Zustandsautomat) — ersetzt das
        # fruehere Modul-Global ``assistant_core.conversations``.
        self._history: list = []
        # Private Implementierung — nie Teil der oeffentlichen Oberflaeche.
        self._task: asyncio.Task | None = None

    # ── oeffentliche Oberflaeche (§24) ──────────────────────────────────────
    @property
    def session_id(self):
        return getattr(self._channel, "session_id", None)

    def snapshot(self) -> dict:
        """Unveraenderliche, semantische Projektion des Zustands."""
        return self._state.view()

    async def submit(self, command) -> None:
        """Einen Client Command verarbeiten (SayText/Stop)."""
        await self._apply(command)

    async def on(self, event) -> None:
        """Ein internes Ereignis verarbeiten (Turn-Ergebnis, Disconnect, ...)."""
        await self._apply(event)

    # ── Effekt-Ausfuehrung (ausserhalb des reinen Kerns) ────────────────────
    async def _apply(self, event) -> None:
        before = self._state
        self._state, effects = step(self._state, event)
        if self._state is before and not effects:
            # Totaler No-Op (§19): zaehlbar machen, ohne Inhalte/Correlation.
            if isinstance(event, (SayTextReceived, StopReceived)):
                obslog.event("conversation.command_ignored",
                             reason=type(event).__name__)
            return
        for effect in effects:
            await self._perform(effect)

    async def _perform(self, effect) -> None:
        if isinstance(effect, type(None)):
            return
        name = type(effect).__name__
        if name == "StartTurn":
            self._start(effect)
        elif name == "CancelActive":
            task = self._task
            if task is not None and not task.done():
                task.cancel()
        elif name == "EmitStopAck":
            await self._channel.emit(wp.StopAck(), correlation_id=effect.correlation_id)
        elif name == "EmitStopped":
            await self._channel.emit(wp.SpokenResponse(text=STOPPED_TEXT, audio=""),
                                     correlation_id=effect.correlation_id)
        elif name == "CloseSession":
            await self._cleanup()

    def _start(self, effect) -> None:
        """Turn-Verarbeitung als Task starten; das Ergebnis meldet sich selbst zurueck."""
        sink = self._channel.event_sink(effect.correlation_id)
        ctx = TurnContext(
            history=self._history,
            pending=effect.pending,
            request_confirmation=self._request_confirmation,
            correlation_id=effect.correlation_id,
        )
        self._task = asyncio.create_task(
            self._run_and_report(ctx, effect.text, effect.correlation_id, sink))

    def _request_confirmation(self, action) -> None:
        """Eine riskante Aktion wartet auf muendliche Bestaetigung (D6)."""
        self._state, _ = step(self._state, ConfirmationOpened(
            action=action, origin_correlation_id=self._state.active.correlation_id
            if self._state.active is not None else ""))

    async def _run_and_report(self, ctx, text, correlation_id, sink) -> None:
        try:
            await self._run_turn(ctx, text, correlation_id, sink)
        except asyncio.CancelledError:
            # Abbruch vollstaendig ausgelaufen -> der Kern darf weiterschalten.
            self._task = None
            with contextlib.suppress(Exception):
                await self._apply(ExecutionEnded())
            raise
        except Exception as e:
            obslog.event("conversation.turn_failed", error_type=type(e).__name__)
            self._task = None
            await self._apply(TurnFailed())
            return
        self._task = None
        await self._apply(TurnFinished())

    async def _cleanup(self) -> None:
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._task = None
        self._history.clear()
        self._manager._forget(self)

    async def aclose(self) -> None:
        """Session deterministisch beenden (auch bei Runtime-Shutdown)."""
        from ._core import Disconnected
        await self._apply(Disconnected())
        # Cleanup abschliessen -> lifecycle 'closed'.
        self._state, _ = step(self._state, ExecutionEnded())


class ConversationManager:
    """Runtime-eigener Besitzer aller Sessions (D4). Konstruktion ist I/O-frei."""

    def __init__(self):
        self._sessions: list[ConversationSession] = []

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    def open(self, channel, *, run_turn) -> ConversationSession:
        session = ConversationSession(self, channel, run_turn)
        self._sessions.append(session)
        return session

    async def close(self, session: ConversationSession) -> None:
        await session.aclose()
        self._forget(session)

    async def aclose(self) -> None:
        """Alle aktiven Sessions schliessen (Runtime-Shutdown, §8)."""
        for session in list(self._sessions):
            with contextlib.suppress(Exception):
                await session.aclose()
        self._sessions.clear()

    def _forget(self, session: ConversationSession) -> None:
        if session in self._sessions:
            self._sessions.remove(session)

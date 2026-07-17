"""ConversationChannel / EventSink / ConnectionRegistry (RFC-0005 §12, Slice 3).

Der Sendepfad ist gekapselt und pro Verbindung durch einen asyncio-Send-Lock
serialisiert (Worker vs. REST-Broadcast). Der EventSink emittiert AUSSCHLIESSLICH
semantische Server Events (kennt keine JSON-Dicts). Die Registry encodiert Broadcasts
pro Empfänger; ein semantischer Broadcast hat EINE gemeinsame Event-ID + EINEN
Timestamp, aber je Empfänger dessen eigene Session-ID.
"""
from __future__ import annotations

import asyncio

from ._model import ProtocolContext
from ._negotiation import negotiate_ws
from ._seams import UuidGen


class EventSink:
    """An eine Correlation-ID gebundene Emit-Schnittstelle für process_message."""

    def __init__(self, channel: "ConversationChannel", correlation_id: str) -> None:
        self._channel = channel
        self._correlation_id = correlation_id

    async def emit(self, event) -> None:
        await self._channel.emit(event, correlation_id=self._correlation_id)


class ConversationChannel:
    def __init__(self, send, ctx: ProtocolContext, session_id: str, protocol) -> None:
        self._send = send                 # async callable(dict) -> None (roher WS-Sink)
        self.ctx = ctx
        self.session_id = session_id       # opake, interne Conversation-Session-ID
        self._protocol = protocol
        self._lock = asyncio.Lock()

    async def emit(self, event, *, correlation_id=None, event_id=None, timestamp=None) -> None:
        frame = self._protocol.encode_event(
            event, self.ctx, correlation_id=correlation_id,
            event_id=event_id, timestamp=timestamp)
        async with self._lock:            # serialisiert konkurrierende Sends
            await self._send(frame)

    def event_sink(self, correlation_id: str) -> EventSink:
        return EventSink(self, correlation_id)


class ConnectionRegistry:
    """Runtime-besessen (kein Modul-Global). Verwaltet Verbindungen + ProtocolContext."""

    def __init__(self, protocol, session_idgen=None) -> None:
        self._protocol = protocol
        self._session_idgen = session_idgen or UuidGen()
        self._channels: list[ConversationChannel] = []

    def register(self, send, offered):
        """Aushandeln + opake Session-ID + Channel anlegen.

        Rückgabe (channel, accepted_subprotocol). Bei ausschließlich nicht
        unterstütztem jarvis.vN -> (None, None) (Ablehnung vor accept).
        """
        neg = negotiate_ws(offered)
        if neg.rejected:
            return None, None
        session_id = self._session_idgen.new_id()
        ctx = (ProtocolContext.v1(session_id=session_id)
               if neg.context.is_v1 else ProtocolContext.legacy())
        ch = ConversationChannel(send, ctx, session_id, self._protocol)
        self._channels.append(ch)
        return ch, neg.accepted_subprotocol

    def unregister(self, channel) -> None:
        try:
            self._channels.remove(channel)
        except ValueError:
            pass

    def count(self) -> int:
        return len(self._channels)

    async def broadcast(self, event) -> None:
        event_id = self._protocol.new_event_id()   # EINE semantische Event-ID
        timestamp = self._protocol.now_iso()        # EIN Timestamp
        for ch in list(self._channels):
            try:
                await ch.emit(event, event_id=event_id, timestamp=timestamp)
            except Exception:
                self.unregister(ch)                 # tote Verbindung entfernen

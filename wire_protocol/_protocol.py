"""WireProtocol — die kleine, tiefe öffentliche Fassade (RFC-0005 §8)."""
from __future__ import annotations

from ._codecs import LegacyCodec, V1Codec
from ._decode import decode_legacy, decode_v1
from ._seams import SystemClock, UuidGen


class WireProtocol:
    def __init__(self, clock=None, idgen=None) -> None:
        self._clock = clock or SystemClock()
        self._idgen = idgen or UuidGen()
        self._legacy = LegacyCodec(self._clock)
        self._v1 = V1Codec(self._clock, self._idgen)

    def encode_event(self, event, ctx, *, correlation_id=None, event_id=None,
                     timestamp=None) -> dict:
        if ctx.is_v1:
            return self._v1.encode(event, ctx, correlation_id,
                                   event_id=event_id, timestamp=timestamp)
        return self._legacy.encode(event)

    def decode_command(self, raw, ctx):
        """Eingehende Nachricht -> SayText | Stop | ProtocolError | None (Legacy ignoriert)."""
        if ctx.is_v1:
            return decode_v1(raw, self._idgen)
        return decode_legacy(raw, self._idgen)

    def new_event_id(self) -> str:
        """Serverseitige Event-ID (für gemeinsame Broadcast-Event-ID)."""
        return self._idgen.new_id()

    def new_correlation_id(self) -> str:
        """Serverseitige Correlation-ID für spontane Events (D6)."""
        return self._idgen.new_id()

    def now_iso(self) -> str:
        return self._clock.now_iso()

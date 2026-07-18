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

    # ── REST-Presentation (RFC-0005 §10, A1.A) ───────────────────────────────
    def rest_envelope(self, result_type: str, sensitivity: str, payload,
                      *, correlation_id: str, event_id=None, timestamp=None) -> dict:
        """V1-REST-Envelope. session_id ist bei REST immer null (D6)."""
        return {
            "protocol_version": 1,
            "type": result_type,
            "event_id": event_id if event_id is not None else self._idgen.new_id(),
            "correlation_id": correlation_id,
            "session_id": None,
            "timestamp": timestamp if timestamp is not None else self._clock.now_iso(),
            "sensitivity": sensitivity,
            "payload": payload,
        }

    def rest_error(self, code: str, message: str, *, correlation_id: str,
                   hint: str = "", retryable: bool = False) -> dict:
        return self.rest_envelope(
            "error", "local",
            {"code": code, "message": message, "hint": hint, "retryable": retryable},
            correlation_id=correlation_id)

    def now_iso(self) -> str:
        return self._clock.now_iso()

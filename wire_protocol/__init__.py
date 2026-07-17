"""wire_protocol — typisierte, versionierte Wire-Contracts (RFC-0005).

Öffentliche Oberfläche. Interne Codec-/Validator-Helfer (`_codecs`, `_model`-Interna)
sind privat und dürfen von Anwendungscode/Tests NICHT importiert werden.
Import-sicher: kein I/O, keine Config, keine Netz-/Task-Nebenwirkungen.
"""
from ._decode import decode_legacy as _decode_legacy  # noqa: F401 (intern)
from ._model import (ActionLifecycle, AppEvent, ErrorEvent, Health, LauncherChanged,
                     MusicChanged, ProtocolContext, ProtocolError, SayText, Sensitivity,
                     SpokenResponse, Stop, StopAck)
from ._negotiation import RestNegotiation, WsNegotiation, negotiate_rest, negotiate_ws
from ._protocol import WireProtocol
from ._seams import FixedClock, SequenceIdGen, SystemClock, UuidGen

__all__ = [
    "WireProtocol", "ProtocolContext", "Sensitivity", "ProtocolError",
    # Server Events
    "Health", "SpokenResponse", "ActionLifecycle", "ErrorEvent", "StopAck",
    "MusicChanged", "AppEvent", "LauncherChanged",
    # Client Commands
    "SayText", "Stop",
    # Negotiation
    "negotiate_ws", "negotiate_rest", "WsNegotiation", "RestNegotiation",
    # Seams
    "SystemClock", "FixedClock", "UuidGen", "SequenceIdGen",
]

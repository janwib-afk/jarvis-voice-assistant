"""Reine Versionsaushandlung (RFC-0005 D4/A1.A/A1.C). Keine Transport-Nebenwirkungen."""
from __future__ import annotations

from dataclasses import dataclass

from ._model import ProtocolContext

_V1_SUBPROTOCOL = "jarvis.v1"
_V1_MEDIA_TYPE = "application/vnd.jarvis.v1+json"


@dataclass(frozen=True)
class WsNegotiation:
    context: ProtocolContext | None
    accepted_subprotocol: str | None
    rejected: bool  # nur nicht unterstütztes jarvis.vN -> Ablehnung vor accept


@dataclass(frozen=True)
class RestNegotiation:
    context: ProtocolContext | None
    not_acceptable: bool  # unbekannte Vendor-Version -> 406


def negotiate_ws(offered, session_id=None) -> WsNegotiation:
    offered = list(offered or [])
    if _V1_SUBPROTOCOL in offered:
        return WsNegotiation(ProtocolContext.v1(session_id), _V1_SUBPROTOCOL, False)
    jarvis_offers = [o for o in offered if o.startswith("jarvis.")]
    if jarvis_offers:
        # ausschließlich nicht unterstützte jarvis.vN -> Ablehnung vor accept
        return WsNegotiation(None, None, True)
    return WsNegotiation(ProtocolContext.legacy(), None, False)


def negotiate_rest(accept_header) -> RestNegotiation:
    accept = (accept_header or "")
    if _V1_MEDIA_TYPE in accept:
        return RestNegotiation(ProtocolContext.v1(None), False)
    # unbekannte Vendor-Version application/vnd.jarvis.vN+json (N != 1) -> 406
    if "application/vnd.jarvis.v" in accept:
        return RestNegotiation(None, True)
    return RestNegotiation(ProtocolContext.legacy(), False)

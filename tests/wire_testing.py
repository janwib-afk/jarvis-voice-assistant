"""Test-Hilfen für die Wire-Migration (Phase 4H).

`legacy_sink(send_json)` adaptiert einen bestehenden WS-artigen Stub (mit async
`send_json(dict)`) auf einen EventSink: der Legacy-Channel encodiert die semantischen
Events byte-/shape-exakt in dieselben Legacy-Dicts, die der Stub bisher sammelte. So
bleiben implementierungsnahe Alt-Tests gültig, ohne Verhaltensabdeckung zu verlieren.
"""
import wire_protocol as wp


def legacy_sink(send_json, correlation_id="test-corr"):
    """EventSink über einen Legacy-ConversationChannel auf `send_json` (async callable)."""
    channel = wp.ConversationChannel(
        send_json, wp.ProtocolContext.legacy(), "test-sess", wp.WireProtocol())
    return channel.event_sink(correlation_id)


class CollectingSink:
    """Direkter EventSink-Ersatz, der die encodierten Legacy-Frames sammelt."""

    def __init__(self):
        self.frames = []

    async def _send(self, frame):
        self.frames.append(frame)

    def sink(self, correlation_id="test-corr"):
        ch = wp.ConversationChannel(self._send, wp.ProtocolContext.legacy(),
                                    "test-sess", wp.WireProtocol())
        return ch.event_sink(correlation_id)


def turn_context(history=None, pending=None, on_confirm=None, correlation_id="test-corr"):
    """Oeffentlicher Seam-Helfer (RFC-0006 Phase 4J): baut einen TurnContext, wie ihn
    die Session an ``assistant_core`` uebergibt. Ersetzt die frueheren direkten
    Manipulationen der Modul-Globals ``conversations``/``pending_confirm``."""
    import conversation
    return conversation.TurnContext(
        history=history if history is not None else [],
        pending=pending,
        request_confirmation=on_confirm or (lambda action: None),
        correlation_id=correlation_id,
    )

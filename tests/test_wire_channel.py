"""Slice 3 (RFC-0005/Phase 4H) — ConversationChannel / EventSink / ConnectionRegistry.

SEAM-WIRE/SEAM-MIXED-WIRE: getestet über die öffentliche Schnittstelle mit einem
Fake-async-`send` (kein echter WebSocket nötig). Der EventSink kennt keine JSON-Dicts;
die Registry encodiert Broadcasts pro Empfänger mit EINER gemeinsamen Event-ID/Timestamp.
"""
import asyncio
import unittest

import wire_protocol as wp


def run(coro):
    return asyncio.run(coro)


class _Capture:
    def __init__(self):
        self.sent = []

    async def send(self, frame):
        self.sent.append(frame)


def _proto(ids=("evt-1", "evt-2", "evt-3")):
    return wp.WireProtocol(clock=wp.FixedClock("2026-07-18T00:00:00.000Z", epoch=1_700_000_000.0),
                           idgen=wp.SequenceIdGen(list(ids)))


class ConversationChannelTests(unittest.TestCase):
    def test_legacy_channel_emits_exact_legacy_frame(self):
        cap = _Capture()
        ch = wp.ConversationChannel(cap.send, wp.ProtocolContext.legacy(),
                                    session_id="sess-1", protocol=_proto())
        run(ch.emit(wp.Health(warnings=("w",))))
        self.assertEqual(cap.sent, [{"type": "health", "warnings": ["w"]}])

    def test_event_sink_binds_correlation_and_session(self):
        cap = _Capture()
        ch = wp.ConversationChannel(cap.send, wp.ProtocolContext.v1(session_id="sess-1"),
                                    session_id="sess-1", protocol=_proto())
        sink = ch.event_sink("corr-9")
        run(sink.emit(wp.SpokenResponse(text="hi", audio="")))
        env = cap.sent[0]
        self.assertEqual(env["correlation_id"], "corr-9")
        self.assertEqual(env["session_id"], "sess-1")
        self.assertEqual(env["type"], "response")

    def test_send_lock_serializes_concurrent_emits(self):
        # Worker vs. REST-Broadcast: der Send-Lock verhindert verschränkte send_json.
        order = []

        async def slow_send(frame):
            order.append(("start", frame["type"]))
            await asyncio.sleep(0.01)
            order.append(("end", frame["type"]))

        ch = wp.ConversationChannel(slow_send, wp.ProtocolContext.legacy(),
                                    session_id="s", protocol=_proto())

        async def both():
            await asyncio.gather(ch.emit(wp.Health(warnings=())), ch.emit(wp.StopAck()))

        run(both())
        # Serialisiert => start,end,start,end (nie start,start).
        self.assertEqual([o[0] for o in order], ["start", "end", "start", "end"])


class ConnectionRegistryTests(unittest.TestCase):
    def _registry(self):
        return wp.ConnectionRegistry(protocol=_proto(),
                                     session_idgen=wp.SequenceIdGen(["s1", "s2", "s3"]))

    def test_register_assigns_opaque_session_id(self):
        reg = self._registry()
        cap = _Capture()
        ch, accepted = reg.register(cap.send, [])  # kein Subprotocol -> Legacy
        self.assertEqual(ch.session_id, "s1")
        self.assertIsNone(accepted)

    def test_broadcast_reaches_all_and_drops_dead(self):
        reg = self._registry()
        good = _Capture()
        reg.register(good.send, [])

        class _Dead:
            async def send(self, frame):
                raise RuntimeError("closed")

        reg.register(_Dead().send, [])
        run(reg.broadcast(wp.MusicChanged(selected="s.mp3")))
        self.assertEqual(len(good.sent), 1)
        self.assertEqual(good.sent[0]["type"], "music_changed")
        self.assertEqual(reg.count(), 1)  # tote Verbindung entfernt

    def test_v1_broadcast_shares_event_id_but_own_session(self):
        # Zwei V1-Empfänger: gleiche event_id, aber je eigene session_id.
        reg = wp.ConnectionRegistry(
            protocol=_proto(ids=["shared-evt"]),
            session_idgen=wp.SequenceIdGen(["sa", "sb"]))
        a, b = _Capture(), _Capture()
        reg.register(a.send, ["jarvis.v1"])
        reg.register(b.send, ["jarvis.v1"])
        run(reg.broadcast(wp.MusicChanged(selected="s.mp3")))
        ea, eb = a.sent[0], b.sent[0]
        self.assertEqual(ea["event_id"], "shared-evt")
        self.assertEqual(eb["event_id"], "shared-evt")   # gemeinsame semantische Event-ID
        self.assertEqual(ea["session_id"], "sa")
        self.assertEqual(eb["session_id"], "sb")          # eigene Session-ID je Empfänger

    def test_rejected_offer_returns_rejection(self):
        reg = self._registry()
        ch, accepted = reg.register(_Capture().send, ["jarvis.v2"])
        self.assertIsNone(ch)  # nur nicht unterstütztes jarvis.vN -> Ablehnung vor accept


if __name__ == "__main__":
    unittest.main()

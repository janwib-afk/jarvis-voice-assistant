"""
Slice 3 (RFC-0006 / Phase 4J) — runtime-eigener Manager und Sessions.

Getestet wird die kleine oeffentliche Oberflaeche (§24): ``open``/``close`` am
Manager, ``submit``/``on``/``snapshot`` an der Session. Die Ausfuehrung der Effekte
(Turn-Task, Cancel, Emit) laeuft real; nur die Turn-Ausfuehrung selbst und der
Wire-Kanal sind kontrollierte Grenzen (Fake-Runner, Fake-Kanal).

Es wird NIE auf Tasks, Locks oder Queue-Objekte zugegriffen — nur auf Frames,
``snapshot()`` und beobachtbares Verhalten.

    python -m unittest discover -s tests
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import conversation  # noqa: E402


class _FakeSink:
    """Ersetzt den an eine Correlation gebundenen EventSink (RFC-0005)."""

    def __init__(self, channel, correlation_id):
        self._channel = channel
        self._correlation_id = correlation_id

    async def emit(self, event):
        await self._channel.emit(event, correlation_id=self._correlation_id)


class _FakeChannel:
    """Minimaler Ersatz fuer den RFC-0005-Transport: sammelt semantische Events."""

    def __init__(self):
        self.emitted = []
        self.session_id = "sess-fake"

    async def emit(self, event, correlation_id=None):
        self.emitted.append((type(event).__name__, correlation_id))

    def event_sink(self, correlation_id):
        return _FakeSink(self, correlation_id)

    def types(self):
        return [t for t, _ in self.emitted]


class _Runner:
    """Kontrollierte Turn-Ausfuehrung: haelt an, bis der Test sie freigibt."""

    def __init__(self):
        self.started = []
        self.cancelled = []
        self.release = asyncio.Event()

    async def __call__(self, text, correlation_id, sink):
        self.started.append(text)
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.append(text)
            raise


def _run(coro):
    return asyncio.run(coro)


class ManagerLifecycleTests(unittest.TestCase):
    def test_open_creates_session_and_close_removes_it(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            ch = _FakeChannel()
            sess = mgr.open(ch, run_turn=_Runner())
            self.assertEqual(mgr.session_count, 1)
            self.assertEqual(sess.snapshot()["lifecycle"], "open")
            await mgr.close(sess)
            self.assertEqual(mgr.session_count, 0)
            self.assertEqual(sess.snapshot()["lifecycle"], "closed")
        _run(scenario())

    def test_multiple_sessions_are_independent(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            r1, r2 = _Runner(), _Runner()
            a = mgr.open(_FakeChannel(), run_turn=r1)
            b = mgr.open(_FakeChannel(), run_turn=r2)
            self.assertEqual(mgr.session_count, 2)
            await a.submit(conversation.SayTextReceived("nur a", "c1"))
            await asyncio.sleep(0)
            self.assertEqual(r1.started, ["nur a"])
            self.assertEqual(r2.started, [])          # b bleibt unberuehrt
            self.assertTrue(b.snapshot()["ready"])
            await mgr.aclose()
        _run(scenario())

    def test_aclose_closes_all_sessions_without_task_leak(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            runners = [_Runner() for _ in range(3)]
            sessions = [mgr.open(_FakeChannel(), run_turn=r) for r in runners]
            for i, s in enumerate(sessions):
                await s.submit(conversation.SayTextReceived(f"lang{i}", f"c{i}"))
            await asyncio.sleep(0)
            self.assertEqual([r.started for r in runners], [["lang0"], ["lang1"], ["lang2"]])

            await mgr.aclose()

            self.assertEqual(mgr.session_count, 0)
            for s in sessions:
                self.assertEqual(s.snapshot()["lifecycle"], "closed")
            # Jede laufende Verarbeitung wurde abgebrochen (kein Task-Leak).
            for r in runners:
                self.assertEqual(len(r.cancelled), 1)
            self.assertEqual(
                [t for t in asyncio.all_tasks() if t is not asyncio.current_task()], [])
        _run(scenario())


class SessionBehaviourTests(unittest.TestCase):
    def test_submit_starts_turn_and_snapshot_reflects_it(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            runner = _Runner()
            sess = mgr.open(_FakeChannel(), run_turn=runner)
            await sess.submit(conversation.SayTextReceived("hallo", "c1"))
            await asyncio.sleep(0)
            self.assertEqual(runner.started, ["hallo"])
            snap = sess.snapshot()
            self.assertEqual(snap["turn"], "processing")
            self.assertFalse(snap["ready"])
            await mgr.aclose()
        _run(scenario())

    def test_second_message_waits_for_the_first(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            runner = _Runner()
            sess = mgr.open(_FakeChannel(), run_turn=runner)
            await sess.submit(conversation.SayTextReceived("eins", "c1"))
            await sess.submit(conversation.SayTextReceived("zwei", "c2"))
            await asyncio.sleep(0)
            self.assertEqual(runner.started, ["eins"])       # strikt sequenziell
            self.assertEqual(sess.snapshot()["queued"], 1)
            runner.release.set()
            await asyncio.sleep(0.02)
            self.assertEqual(runner.started, ["eins", "zwei"])
            await mgr.aclose()
        _run(scenario())

    def test_stop_emits_ack_and_cancels_running_turn(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            runner = _Runner()
            ch = _FakeChannel()
            sess = mgr.open(ch, run_turn=runner)
            await sess.submit(conversation.SayTextReceived("lang", "c1"))
            await asyncio.sleep(0)
            await sess.submit(conversation.StopReceived("c9"))
            await asyncio.sleep(0.02)
            # Charakterisierte Semantik: Ack + gesprochene Bestaetigung.
            self.assertEqual(ch.types(), ["StopAck", "SpokenResponse"])
            self.assertEqual(runner.cancelled, ["lang"])
            await mgr.aclose()
        _run(scenario())

    def test_stop_while_idle_emits_ack_only(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            ch = _FakeChannel()
            sess = mgr.open(ch, run_turn=_Runner())
            await sess.submit(conversation.StopReceived("c9"))
            await asyncio.sleep(0)
            self.assertEqual(ch.types(), ["StopAck"])   # KEIN 'Okay, gestoppt.'
            await mgr.aclose()
        _run(scenario())

    def test_closed_session_ignores_further_commands(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            runner = _Runner()
            sess = mgr.open(_FakeChannel(), run_turn=runner)
            await mgr.close(sess)
            await sess.submit(conversation.SayTextReceived("ignoriert", "c1"))
            await asyncio.sleep(0)
            self.assertEqual(runner.started, [])
            self.assertEqual(sess.snapshot()["lifecycle"], "closed")
        _run(scenario())


class ImportSafetyTests(unittest.TestCase):
    def test_manager_construction_is_io_free(self):
        """Konstruktion darf keinerlei I/O oder Event-Loop brauchen (RFC-0002)."""
        mgr = conversation.ConversationManager()
        self.assertEqual(mgr.session_count, 0)


if __name__ == "__main__":
    unittest.main()

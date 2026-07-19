"""
Slice 10 (RFC-0006 §21 + Amendment 1 / M3) — RACE-, STALE- UND CLEANUP-MATRIX.

Dies ist der in §21 vorgesehene EIGENE Testblock. Er faehrt die verbindlichen
Szenarien der Matrix ab; jeder Test traegt seine Szenarionummer im Namen, damit
Matrix und Suite eindeutig aufeinander zeigen.

Aufteilung nach dem in der Matrix dokumentierten Test-Seam:

    Szenario  1-10, 17   SEAM-CONVERSATION / SEAM-WS / SEAM-CONVERSATION-STATE
                         -> diese Datei
    Szenario 11-16       SEAM-VOICE / SEAM-BROWSER-UI
                         -> tests/browser/e2e_race_matrix.py
    Szenario 18          SEAM-JOB-CONTRACT, ausdruecklich erst Phase 6
                         -> hier bewusst NICHT getestet (siehe Schluss der Datei)

Geprueft wird ausschliesslich beobachtbares Verhalten ueber die vereinbarte
Oberflaeche: emittierte Frames, ``snapshot()`` und ob eine Ausfuehrung lief bzw.
abgebrochen wurde. NIE Tasks, Locks oder Queue-Interna (§24).

Determinismus: die Nebenlaeufigkeit wird ueber kontrollierte ``asyncio.Event``-
Freigaben und ``asyncio.sleep(0)``-Uebergabepunkte gesteuert, nicht ueber
Wartezeiten. Es gibt in dieser Datei keinen einzigen Sleep als Race-Loesung.

    python -m unittest tests.test_race_matrix -v
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import conversation  # noqa: E402


class _Sink:
    def __init__(self, channel, correlation_id):
        self._channel = channel
        self._correlation_id = correlation_id

    async def emit(self, event):
        await self._channel.emit(event, correlation_id=self._correlation_id)


class _Channel:
    """Minimaler RFC-0005-Transportersatz: sammelt die semantischen Frames."""

    def __init__(self):
        self.emitted = []
        self.session_id = "sess-race"

    async def emit(self, event, correlation_id=None):
        self.emitted.append((type(event).__name__, correlation_id))

    def event_sink(self, correlation_id):
        return _Sink(self, correlation_id)

    def types(self):
        return [t for t, _ in self.emitted]


class _Runner:
    """Kontrollierte Turn-Ausfuehrung.

    Der Turn haelt an einem Freigabepunkt an. Erst NACH der Freigabe wuerde er
    seine Abschluss-Frames senden — genau das macht ein spaeter Abschluss nach
    einem Stop nachweisbar: wird der Turn abgebrochen, darf nichts mehr kommen.
    """

    def __init__(self, late_frames=()):
        self.started = []
        self.cancelled = []
        self.contexts = []
        self.finished = []
        self.release = asyncio.Event()
        self._late_frames = tuple(late_frames)

    async def __call__(self, ctx, text, correlation_id, sink):
        self.contexts.append(ctx)
        self.started.append(text)
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.append(text)
            raise
        # Ab hier: der "spaete" Abschluss (LlmOk / ActionOk der Matrix).
        for frame in self._late_frames:
            await sink.emit(frame)
        self.finished.append(text)


class _LateFrame:
    """Platzhalter-Frame; nur der Typname wird beobachtet."""


class LlmOk(_LateFrame):
    pass


class ActionOk(_LateFrame):
    pass


def _run(coro):
    return asyncio.run(coro)


async def _settle():
    """Alle bereitstehenden Tasks bis zur Ruhe fahren — ohne Wartezeit.

    Deterministisch: gibt die Kontrolle so oft ab, bis kein Task mehr lauffaehig
    ist. Ersetzt bewusst jedes ``sleep(<zahl>)`` als Race-Loesung.
    """
    for _ in range(50):
        await asyncio.sleep(0)


class RaceMatrixServerTests(unittest.TestCase):
    """Szenarien 1-10 und 17 der Matrix aus RFC-0006 §21."""

    # ── 1 ──────────────────────────────────────────────────────────────────
    def test_szenario_01_stop_gleichzeitig_mit_turn_abschluss(self):
        """Stop trifft einen laufenden Turn: LlmOk wird verworfen."""
        async def scenario():
            mgr = conversation.ConversationManager()
            runner, ch = _Runner(late_frames=[LlmOk()]), _Channel()
            sess = mgr.open(ch, run_turn=runner)
            await sess.submit(conversation.SayTextReceived("lang", "c1"))
            await _settle()
            self.assertEqual(runner.started, ["lang"])

            await sess.submit(conversation.StopReceived("c9"))
            await _settle()

            # Legaler Folgezustand: abgebrochen, Session wieder bereit.
            self.assertEqual(runner.cancelled, ["lang"])
            self.assertEqual(runner.finished, [])
            # Effekte: Ack + gesprochene Bestaetigung. KEIN spaetes LlmOk.
            self.assertEqual(ch.types(), ["StopAck", "SpokenResponse"])
            self.assertNotIn("LlmOk", ch.types())
            self.assertTrue(sess.snapshot()["ready"])
            await mgr.aclose()
        _run(scenario())

    # ── 2 ──────────────────────────────────────────────────────────────────
    def test_szenario_02_stop_gleichzeitig_mit_action_abschluss(self):
        """Stop waehrend einer Aktion: ActionOk/ActionDone werden verworfen."""
        async def scenario():
            mgr = conversation.ConversationManager()
            runner, ch = _Runner(late_frames=[ActionOk()]), _Channel()
            sess = mgr.open(ch, run_turn=runner)
            await sess.submit(conversation.SayTextReceived("aktion", "c1"))
            await _settle()
            await sess.on(conversation.ExecutionEnded())   # Aktion laeuft
            await sess.submit(conversation.StopReceived("c9"))
            await _settle()

            self.assertNotIn("ActionOk", ch.types())
            self.assertEqual(runner.finished, [])
            await mgr.aclose()
        _run(scenario())

    # ── 3 ──────────────────────────────────────────────────────────────────
    def test_szenario_03_disconnect_waehrend_stop(self):
        """Disconnect im Zustand 'cancelling': Session schliesst vollstaendig."""
        async def scenario():
            mgr = conversation.ConversationManager()
            runner, ch = _Runner(), _Channel()
            sess = mgr.open(ch, run_turn=runner)
            await sess.submit(conversation.SayTextReceived("lang", "c1"))
            await _settle()
            await sess.submit(conversation.StopReceived("c9"))
            await sess.on(conversation.Disconnected())
            await _settle()

            self.assertEqual(sess.snapshot()["lifecycle"], "closed")
            self.assertEqual(runner.cancelled, ["lang"])
            await mgr.aclose()
            self.assertEqual(mgr.session_count, 0)
        _run(scenario())

    # ── 4 ──────────────────────────────────────────────────────────────────
    def test_szenario_04_disconnect_waehrend_verarbeitung_ohne_task_leak(self):
        """Disconnect waehrend LLM/TTS/Action: Abbruch garantiert, kein Leak."""
        async def scenario():
            mgr = conversation.ConversationManager()
            runner, ch = _Runner(late_frames=[LlmOk()]), _Channel()
            sess = mgr.open(ch, run_turn=runner)
            await sess.submit(conversation.SayTextReceived("lang", "c1"))
            await _settle()

            await sess.on(conversation.Disconnected())
            await _settle()

            self.assertEqual(sess.snapshot()["lifecycle"], "closed")
            self.assertEqual(runner.cancelled, ["lang"])
            self.assertNotIn("LlmOk", ch.types())        # alle Emits verworfen
            # Kein Task-Leak: ausser dem laufenden Test lebt nichts mehr.
            self.assertEqual(
                [t for t in asyncio.all_tasks() if t is not asyncio.current_task()], [])
            await mgr.aclose()
        _run(scenario())

    # ── 5 ──────────────────────────────────────────────────────────────────
    def test_szenario_05_zwei_schnelle_saytext_bleiben_sequenziell(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            runner = _Runner()
            sess = mgr.open(_Channel(), run_turn=runner)
            await sess.submit(conversation.SayTextReceived("eins", "c1"))
            await sess.submit(conversation.SayTextReceived("zwei", "c2"))
            await _settle()

            self.assertEqual(runner.started, ["eins"])     # strikt sequenziell
            snap = sess.snapshot()
            self.assertEqual(snap["turn"], "processing")
            self.assertEqual(snap["queued"], 1)

            runner.release.set()
            await _settle()
            self.assertEqual(runner.started, ["eins", "zwei"])
            await mgr.aclose()
        _run(scenario())

    # ── 6 ──────────────────────────────────────────────────────────────────
    def test_szenario_06_stop_verwirft_die_gesamte_queue(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            runner, ch = _Runner(), _Channel()
            sess = mgr.open(ch, run_turn=runner)
            for i in range(4):
                await sess.submit(conversation.SayTextReceived(f"m{i}", f"c{i}"))
            await _settle()
            self.assertEqual(sess.snapshot()["queued"], 3)

            await sess.submit(conversation.StopReceived("c9"))
            await _settle()
            runner.release.set()          # die Wartenden duerfen NICHT nachlaufen
            await _settle()

            self.assertEqual(sess.snapshot()["queued"], 0)
            self.assertEqual(runner.started, ["m0"])       # keine Nacharbeit
            self.assertEqual(ch.types(), ["StopAck", "SpokenResponse"])
            await mgr.aclose()
        _run(scenario())

    # ── 7 ──────────────────────────────────────────────────────────────────
    def test_szenario_07_stop_waehrend_awaiting_confirmation(self):
        """Rueckfrage verfaellt; kein 'Okay, gestoppt.' wenn nichts lief."""
        async def scenario():
            mgr = conversation.ConversationManager()
            runner, ch = _Runner(), _Channel()
            sess = mgr.open(ch, run_turn=runner)
            await sess.on(conversation.ConfirmationOpened(
                action="RISKANT", origin_correlation_id="c1"))
            self.assertTrue(sess.snapshot()["awaiting_confirmation"])

            await sess.submit(conversation.StopReceived("c9"))
            await _settle()

            self.assertFalse(sess.snapshot()["awaiting_confirmation"])
            self.assertEqual(ch.types(), ["StopAck"])      # KEIN SpokenResponse
            await mgr.aclose()
        _run(scenario())

    # ── 8 ──────────────────────────────────────────────────────────────────
    def test_szenario_08_normale_nachricht_statt_ja_nein(self):
        """Die Rueckfrage verfaellt STILL und wird dem neuen Turn uebergeben."""
        async def scenario():
            mgr = conversation.ConversationManager()
            runner, ch = _Runner(), _Channel()
            sess = mgr.open(ch, run_turn=runner)
            await sess.on(conversation.ConfirmationOpened(
                action="RISKANT", origin_correlation_id="c1"))

            await sess.submit(conversation.SayTextReceived("wie spaet ist es", "c2"))
            await _settle()

            # Still: kein Frame ueber das Verfallen.
            self.assertEqual(ch.types(), [])
            # Die Bestaetigung ist KONSUMIERT — genau eine Wahrheit.
            self.assertFalse(sess.snapshot()["awaiting_confirmation"])
            self.assertEqual(runner.started, ["wie spaet ist es"])
            self.assertEqual(runner.contexts[0].pending, "RISKANT")
            await mgr.aclose()
        _run(scenario())

    # ── 9 ──────────────────────────────────────────────────────────────────
    def test_szenario_09_wiederholter_stop_im_ready(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            ch = _Channel()
            sess = mgr.open(ch, run_turn=_Runner())
            await sess.submit(conversation.StopReceived("c1"))
            await sess.submit(conversation.StopReceived("c2"))
            await _settle()

            self.assertEqual(ch.types(), ["StopAck", "StopAck"])
            self.assertNotIn("SpokenResponse", ch.types())   # was_busy = false
            self.assertTrue(sess.snapshot()["ready"])
            await mgr.aclose()
        _run(scenario())

    # ── 10 ─────────────────────────────────────────────────────────────────
    def test_szenario_10_neue_nachricht_direkt_nach_stopack(self):
        async def scenario():
            mgr = conversation.ConversationManager()
            runner, ch = _Runner(), _Channel()
            sess = mgr.open(ch, run_turn=runner)
            await sess.submit(conversation.SayTextReceived("erst", "c1"))
            await _settle()
            await sess.submit(conversation.StopReceived("c9"))
            await _settle()

            await sess.submit(conversation.SayTextReceived("danach", "c2"))
            await _settle()

            self.assertEqual(runner.started, ["erst", "danach"])
            self.assertEqual(sess.snapshot()["turn"], "processing")
            await mgr.aclose()
        _run(scenario())

    # ── 17 ─────────────────────────────────────────────────────────────────
    def test_szenario_17_runtime_shutdown_mit_aktiven_sessions(self):
        """Alle Sessions schliessen; kein Task- und kein Channel-Leak."""
        async def scenario():
            mgr = conversation.ConversationManager()
            runners = [_Runner(late_frames=[LlmOk()]) for _ in range(3)]
            channels = [_Channel() for _ in range(3)]
            sessions = [mgr.open(c, run_turn=r) for c, r in zip(channels, runners)]
            for i, s in enumerate(sessions):
                await s.submit(conversation.SayTextReceived(f"lang{i}", f"c{i}"))
            await _settle()

            await mgr.aclose()

            self.assertEqual(mgr.session_count, 0)
            for s in sessions:
                self.assertEqual(s.snapshot()["lifecycle"], "closed")
            for r in runners:
                self.assertEqual(len(r.cancelled), 1)      # Abbruch garantiert
            for c in channels:
                self.assertNotIn("LlmOk", c.types())       # alle Emits verworfen
            self.assertEqual(
                [t for t in asyncio.all_tasks() if t is not asyncio.current_task()], [])
        _run(scenario())


class PhaseSixOutOfScopeTests(unittest.TestCase):
    """Szenario 18 gehoert laut Matrix ausdruecklich zu Phase 6."""

    def test_szenario_18_ist_kein_teil_dieser_phase(self):
        """SEAM-JOB-CONTRACT existiert bewusst noch nicht.

        Der Test haelt das Nicht-Ziel fest, damit die Luecke belegt und nicht
        versehentlich ist: gibt es eines Tages ein Job-Modul, faellt dieser Test
        auf und die Matrixzeile 18 muss echte Abdeckung bekommen.
        """
        self.assertNotIn("jobs", sys.modules)
        with self.assertRaises(ImportError):
            __import__("jobs")


if __name__ == "__main__":
    unittest.main()

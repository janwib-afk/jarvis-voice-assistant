"""
Slice 2 (RFC-0006 / Phase 4J) — SEAM-CONVERSATION-STATE.

Der reine Transitionskern: ``state + event -> (state, effects)``. Vollstaendig
deterministisch, ohne I/O, ohne Tasks, ohne Locks, ohne Wire-Codec. Getestet wird
ausschliesslich ueber die oeffentliche Oberflaeche des Kerns — keine privaten Helfer.

Verbindliche Quellen: RFC-0006 §9/§10/§15.1/§15.2/§16/§19/§20 und die in Slice 1
charakterisierte Ist-Framefolge.

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conversation import (  # noqa: E402
    CancelActive, CloseSession, EmitStopAck, EmitStopped, SessionState, StartTurn,
    ConfirmationOpened, Disconnected, ExecutionEnded, SayTextReceived, StopReceived,
    TurnFailed, TurnFinished, initial_session_state, step,
)


def _effect_types(effects):
    return [type(e).__name__ for e in effects]


class InitialStateTests(unittest.TestCase):
    def test_initial_state_is_open_and_ready(self):
        s = initial_session_state()
        self.assertIsInstance(s, SessionState)
        self.assertEqual(s.lifecycle, "open")
        self.assertIsNone(s.active)
        self.assertEqual(s.queue, ())
        self.assertIsNone(s.suspended)
        # 'ready' ist KEIN Zustand, sondern abgeleitet (D5).
        self.assertTrue(s.is_ready)

    def test_state_is_immutable(self):
        s = initial_session_state()
        with self.assertRaises(Exception):
            s.lifecycle = "closed"


class TurnLifecycleTests(unittest.TestCase):
    def test_first_message_starts_turn_immediately(self):
        s, eff = step(initial_session_state(), SayTextReceived("hallo", "c1"))
        self.assertEqual(s.active.state, "processing")
        self.assertEqual(s.active.correlation_id, "c1")
        self.assertEqual(s.queue, ())
        self.assertEqual(_effect_types(eff), ["StartTurn"])
        self.assertEqual(eff[0].text, "hallo")
        self.assertEqual(eff[0].correlation_id, "c1")

    def test_second_message_is_queued_not_started(self):
        s, _ = step(initial_session_state(), SayTextReceived("eins", "c1"))
        s, eff = step(s, SayTextReceived("zwei", "c2"))
        self.assertEqual(s.active.correlation_id, "c1")   # erster Turn bleibt aktiv
        self.assertEqual(len(s.queue), 1)
        self.assertEqual(eff, ())                          # kein zweiter StartTurn
        self.assertFalse(s.is_ready)

    def test_finished_turn_starts_next_queued(self):
        s, _ = step(initial_session_state(), SayTextReceived("eins", "c1"))
        s, _ = step(s, SayTextReceived("zwei", "c2"))
        s, eff = step(s, TurnFinished())
        self.assertEqual(s.active.correlation_id, "c2")
        self.assertEqual(s.queue, ())
        self.assertEqual(_effect_types(eff), ["StartTurn"])
        self.assertEqual(eff[0].text, "zwei")

    def test_finished_turn_without_queue_becomes_ready(self):
        s, _ = step(initial_session_state(), SayTextReceived("eins", "c1"))
        s, eff = step(s, TurnFinished())
        self.assertIsNone(s.active)
        self.assertTrue(s.is_ready)
        self.assertEqual(eff, ())

    def test_failed_turn_is_terminal_and_frees_the_session(self):
        s, _ = step(initial_session_state(), SayTextReceived("eins", "c1"))
        s, eff = step(s, TurnFailed())
        self.assertIsNone(s.active)
        self.assertTrue(s.is_ready)
        self.assertEqual(eff, ())


class StopTests(unittest.TestCase):
    def test_stop_while_idle_acks_only(self):
        """Charakterisiert (Slice 1): Stop im Leerlauf bestaetigt nur — KEIN
        'Okay, gestoppt.'."""
        s, eff = step(initial_session_state(), StopReceived("c9"))
        self.assertEqual(_effect_types(eff), ["EmitStopAck"])
        self.assertEqual(eff[0].correlation_id, "c9")
        self.assertTrue(s.is_ready)

    def test_stop_while_busy_cancels_and_confirms(self):
        """Charakterisiert (Slice 1): CancelActive, dann StopAck, dann
        'Okay, gestoppt.' — in dieser Reihenfolge."""
        s, _ = step(initial_session_state(), SayTextReceived("lang", "c1"))
        s, eff = step(s, StopReceived("c9"))
        self.assertEqual(_effect_types(eff), ["CancelActive", "EmitStopAck", "EmitStopped"])
        self.assertEqual(eff[1].correlation_id, "c9")
        self.assertEqual(eff[2].correlation_id, "c9")
        self.assertEqual(s.active.state, "cancelling")

    def test_stop_clears_the_queue(self):
        s, _ = step(initial_session_state(), SayTextReceived("lang", "c1"))
        s, _ = step(s, SayTextReceived("wartet", "c2"))
        s, _ = step(s, StopReceived("c9"))
        self.assertEqual(s.queue, ())

    def test_repeated_stop_is_idempotent(self):
        s, _ = step(initial_session_state(), SayTextReceived("lang", "c1"))
        s, _ = step(s, StopReceived("c9"))
        s, eff = step(s, StopReceived("c10"))
        # Zweiter Stop: nur noch Ack, kein zweites Cancel/'Okay, gestoppt.'.
        self.assertEqual(_effect_types(eff), ["EmitStopAck"])
        self.assertEqual(s.active.state, "cancelling")

    def test_message_during_cancellation_is_queued_not_started(self):
        """Praezisierung 5: neuer Command sofort annehmbar, aber kein zweiter Turn
        parallel — er startet erst nach ExecutionEnded."""
        s, _ = step(initial_session_state(), SayTextReceived("lang", "c1"))
        s, _ = step(s, StopReceived("c9"))
        s, eff = step(s, SayTextReceived("neu", "c2"))
        self.assertEqual(eff, ())                        # NICHT gestartet
        self.assertEqual(len(s.queue), 1)
        self.assertEqual(s.active.state, "cancelling")

        s, eff = step(s, ExecutionEnded())
        self.assertEqual(_effect_types(eff), ["StartTurn"])
        self.assertEqual(eff[0].text, "neu")

    def test_execution_ended_without_queue_becomes_ready(self):
        s, _ = step(initial_session_state(), SayTextReceived("lang", "c1"))
        s, _ = step(s, StopReceived("c9"))
        s, eff = step(s, ExecutionEnded())
        self.assertIsNone(s.active)
        self.assertTrue(s.is_ready)
        self.assertEqual(eff, ())


class ConfirmationTests(unittest.TestCase):
    def test_confirmation_suspends_and_turn_completes(self):
        s, _ = step(initial_session_state(), SayTextReceived("vergiss X", "c1"))
        s, eff = step(s, ConfirmationOpened(action="ACTION-X", origin_correlation_id="c1"))
        self.assertIsNotNone(s.suspended)
        self.assertEqual(s.suspended.action, "ACTION-X")
        self.assertEqual(s.suspended.origin_correlation_id, "c1")
        self.assertEqual(eff, ())
        # Der ausloesende Turn selbst ist beendet (heutiges Verhalten).
        s, _ = step(s, TurnFinished())
        self.assertTrue(s.is_ready)
        self.assertIsNotNone(s.suspended)   # Bestaetigung ueberlebt den Turn

    def test_stop_discards_open_confirmation(self):
        s, _ = step(initial_session_state(), SayTextReceived("vergiss X", "c1"))
        s, _ = step(s, ConfirmationOpened(action="ACTION-X", origin_correlation_id="c1"))
        s, _ = step(s, TurnFinished())
        s, _ = step(s, StopReceived("c9"))
        self.assertIsNone(s.suspended)

    def test_disconnect_discards_open_confirmation(self):
        s, _ = step(initial_session_state(), SayTextReceived("vergiss X", "c1"))
        s, _ = step(s, ConfirmationOpened(action="ACTION-X", origin_correlation_id="c1"))
        s, _ = step(s, TurnFinished())
        s, _ = step(s, Disconnected())
        self.assertIsNone(s.suspended)


class LifecycleTests(unittest.TestCase):
    def test_disconnect_moves_to_closing_and_cancels(self):
        s, _ = step(initial_session_state(), SayTextReceived("lang", "c1"))
        s, eff = step(s, Disconnected())
        self.assertEqual(s.lifecycle, "closing")
        self.assertIn("CancelActive", _effect_types(eff))
        self.assertIn("CloseSession", _effect_types(eff))

    def test_disconnect_while_idle_closes_without_cancel(self):
        s, eff = step(initial_session_state(), Disconnected())
        self.assertEqual(s.lifecycle, "closing")
        self.assertEqual(_effect_types(eff), ["CloseSession"])

    def test_closing_ignores_new_commands(self):
        """I4: closing/closed nehmen keine neuen Commands an."""
        s, _ = step(initial_session_state(), Disconnected())
        s2, eff = step(s, SayTextReceived("ignoriert", "c2"))
        self.assertEqual(eff, ())
        self.assertEqual(s2.queue, ())
        s3, eff = step(s2, StopReceived("c3"))
        self.assertEqual(eff, ())

    def test_cleanup_completes_to_closed(self):
        s, _ = step(initial_session_state(), Disconnected())
        s, eff = step(s, ExecutionEnded())
        self.assertEqual(s.lifecycle, "closed")
        self.assertEqual(eff, ())


class InvalidTransitionTests(unittest.TestCase):
    def test_unknown_event_is_total_no_op(self):
        """I19: ungueltige Uebergaenge sind totale No-Ops (kein Wurf)."""
        s0 = initial_session_state()
        s1, eff = step(s0, object())
        self.assertIs(s1, s0)
        self.assertEqual(eff, ())

    def test_turn_finished_without_active_turn_is_no_op(self):
        s0 = initial_session_state()
        s1, eff = step(s0, TurnFinished())
        self.assertIs(s1, s0)
        self.assertEqual(eff, ())


class SnapshotTests(unittest.TestCase):
    def test_view_exposes_only_semantic_state(self):
        s, _ = step(initial_session_state(), SayTextReceived("eins", "c1"))
        s, _ = step(s, SayTextReceived("zwei", "c2"))
        view = s.view()
        self.assertEqual(view["lifecycle"], "open")
        self.assertEqual(view["turn"], "processing")
        self.assertEqual(view["queued"], 1)          # Laenge = Daten, kein Zustand
        self.assertFalse(view["awaiting_confirmation"])
        self.assertFalse(view["ready"])
        # Keine Interna nach aussen.
        for forbidden in ("task", "lock", "queue", "worker"):
            self.assertNotIn(forbidden, view)


if __name__ == "__main__":
    unittest.main()

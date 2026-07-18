"""Slice 2 (RFC-0005/Phase 4H) — SEAM-WIRE: der reine, transportneutrale Typed Core.

Getestet wird NUR die öffentliche `wire_protocol`-Schnittstelle und der VOLLSTÄNDIG
serialisierte Output (Dicts), nie private Codec-/Validator-Helfer. Clock und ID werden
über injizierbare Seams eingefroren, damit Golden-Erwartungen feste Literale sind.
"""
import unittest

import wire_protocol as wp


_TS_ISO = "2026-07-18T00:00:00.000Z"
_TS_EPOCH = 1_700_000_000.0


def _proto(ids=("evt-1", "evt-2", "evt-3")):
    return wp.WireProtocol(
        clock=wp.FixedClock(_TS_ISO, epoch=_TS_EPOCH),
        idgen=wp.SequenceIdGen(list(ids)))


class HealthTracerTests(unittest.TestCase):
    def test_health_legacy_is_exact_legacy_shape(self):
        frame = _proto().encode_event(wp.Health(warnings=("w1", "w2")),
                                      wp.ProtocolContext.legacy())
        self.assertEqual(frame, {"type": "health", "warnings": ["w1", "w2"]})

    def test_health_v1_is_nested_envelope(self):
        frame = _proto().encode_event(
            wp.Health(warnings=("w1",)),
            wp.ProtocolContext.v1(session_id="sess-1"),
            correlation_id="corr-1")
        self.assertEqual(frame, {
            "protocol_version": 1,
            "type": "health",
            "event_id": "evt-1",
            "correlation_id": "corr-1",
            "session_id": "sess-1",
            "timestamp": "2026-07-18T00:00:00.000Z",
            "sensitivity": "public",
            "payload": {"warnings_count": 1},
        })


class EventLegacyShapeTests(unittest.TestCase):
    """Legacy-Encode = exakte heutige Shape (Feldnamen/Reihenfolge/Typen/Werte)."""

    def enc(self, event):
        return _proto().encode_event(event, wp.ProtocolContext.legacy())

    def test_response(self):
        self.assertEqual(self.enc(wp.SpokenResponse(text="Hallo", audio="QUJD")),
                         {"type": "response", "text": "Hallo", "audio": "QUJD"})

    def test_action_has_epoch_ts_last(self):
        frame = self.enc(wp.ActionLifecycle(phase="start", action="SEARCH",
                                            label="Suche", detail="x"))
        self.assertEqual(frame, {"type": "action", "phase": "start", "action": "SEARCH",
                                 "label": "Suche", "detail": "x", "ts": _TS_EPOCH})
        self.assertIsInstance(frame["ts"], float)

    def test_error_uses_text_field(self):
        self.assertEqual(
            self.enc(wp.ErrorEvent(component="llm", message="Kaputt", hint="später",
                                   code="llm_failed", retryable=True)),
            {"type": "error", "component": "llm", "text": "Kaputt", "hint": "später"})

    def test_stop(self):
        self.assertEqual(self.enc(wp.StopAck()), {"type": "stop"})

    def test_music_changed(self):
        self.assertEqual(self.enc(wp.MusicChanged(selected="song.mp3")),
                         {"type": "music_changed", "selected": "song.mp3", "ts": _TS_EPOCH})

    def test_app_event(self):
        self.assertEqual(
            self.enc(wp.AppEvent(ok=False, app=None, name="", message="unbekannt")),
            {"type": "app_event", "ok": False, "app": None, "name": "",
             "message": "unbekannt", "ts": _TS_EPOCH})

    def test_launcher_changed(self):
        self.assertEqual(
            self.enc(wp.LauncherChanged(kind="activated", active_profile="default")),
            {"type": "launcher_changed", "kind": "activated",
             "active_profile": "default", "ts": _TS_EPOCH})


class EventV1EnvelopeTests(unittest.TestCase):
    """V1-Encode = nested Envelope mit Metadaten + Sensitivität; keine Legacy-Epoch-ts."""

    def enc(self, event, corr="corr-1"):
        return _proto().encode_event(event, wp.ProtocolContext.v1(session_id="s1"),
                                     correlation_id=corr)

    def test_response_is_personal(self):
        env = self.enc(wp.SpokenResponse(text="Hi", audio=""))
        self.assertEqual(env["sensitivity"], "personal")
        self.assertEqual(env["type"], "response")
        self.assertEqual(env["payload"], {"text": "Hi", "audio": ""})
        self.assertEqual(env["timestamp"], _TS_ISO)
        self.assertEqual(env["event_id"], "evt-1")
        self.assertEqual(env["session_id"], "s1")
        self.assertNotIn("ts", env["payload"])  # kein Legacy-Epoch im V1

    def test_action_payload_has_no_epoch_ts(self):
        env = self.enc(wp.ActionLifecycle(phase="done", action="SEARCH",
                                          label="Suche", detail="x"))
        self.assertEqual(env["payload"],
                         {"phase": "done", "action": "SEARCH", "label": "Suche", "detail": "x"})
        self.assertEqual(env["sensitivity"], "personal")

    def test_error_is_structured(self):
        env = self.enc(wp.ErrorEvent(component="llm", message="Kaputt", hint="später",
                                     code="llm_failed", retryable=True))
        self.assertEqual(env["type"], "error")
        self.assertEqual(env["payload"], {"component": "llm", "code": "llm_failed",
                                          "message": "Kaputt", "hint": "später",
                                          "retryable": True})

    def test_broadcasts_are_local(self):
        for ev in (wp.MusicChanged(selected="s.mp3"),
                   wp.AppEvent(ok=True, app="editor", name="Editor", message="ok"),
                   wp.LauncherChanged(kind="activated", active_profile="default")):
            env = self.enc(ev)
            self.assertEqual(env["sensitivity"], "local")
            self.assertNotIn("ts", env["payload"])


_UUID = "123e4567-e89b-42d3-a456-426614174000"


class DecodeLegacyCommandTests(unittest.TestCase):
    def dec(self, raw):
        return _proto().decode_command(raw, wp.ProtocolContext.legacy())

    def test_text_becomes_saytext_with_server_correlation(self):
        cmd = self.dec({"text": "hallo welt"})
        self.assertIsInstance(cmd, wp.SayText)
        self.assertEqual(cmd.text, "hallo welt")
        self.assertTrue(cmd.correlation_id)  # serverseitig erzeugt

    def test_stop_frame_becomes_stop(self):
        self.assertIsInstance(self.dec({"type": "stop"}), wp.Stop)

    def test_empty_or_unknown_is_ignored(self):
        self.assertIsNone(self.dec({"text": "   "}))
        self.assertIsNone(self.dec({"type": "irgendwas"}))


class DecodeV1CommandTests(unittest.TestCase):
    def dec(self, raw):
        return _proto().decode_command(raw, wp.ProtocolContext.v1(session_id="s1"))

    def test_say_text_ok(self):
        cmd = self.dec({"protocol_version": 1, "type": "say_text",
                        "correlation_id": _UUID, "payload": {"text": "hi"}})
        self.assertIsInstance(cmd, wp.SayText)
        self.assertEqual(cmd.text, "hi")
        self.assertEqual(cmd.correlation_id, _UUID)  # gültige Client-ID gespiegelt

    def test_stop_ok(self):
        cmd = self.dec({"protocol_version": 1, "type": "stop", "payload": {}})
        self.assertIsInstance(cmd, wp.Stop)
        self.assertTrue(cmd.correlation_id)  # fehlend -> serverseitig

    def test_server_field_spoofing_rejected(self):
        err = self.dec({"protocol_version": 1, "type": "say_text",
                        "event_id": "x", "payload": {"text": "hi"}})
        self.assertIsInstance(err, wp.ProtocolError)
        self.assertEqual(err.code, "reserved_field")

    def test_wrong_major_rejected_close_1002(self):
        err = self.dec({"protocol_version": 2, "type": "say_text", "payload": {"text": "hi"}})
        self.assertIsInstance(err, wp.ProtocolError)
        self.assertEqual(err.code, "unsupported_version")
        self.assertEqual(err.close_code, 1002)

    def test_missing_text_rejected(self):
        err = self.dec({"protocol_version": 1, "type": "say_text", "payload": {}})
        self.assertIsInstance(err, wp.ProtocolError)
        self.assertEqual(err.code, "invalid_command")

    def test_unknown_command_rejected(self):
        err = self.dec({"protocol_version": 1, "type": "fliegen", "payload": {}})
        self.assertIsInstance(err, wp.ProtocolError)
        self.assertEqual(err.code, "unknown_command")

    def test_additive_field_ignored(self):
        cmd = self.dec({"protocol_version": 1, "type": "say_text",
                        "payload": {"text": "hi"}, "kuenftig": {"x": 1}})
        self.assertIsInstance(cmd, wp.SayText)

    def test_oversize_text_rejected(self):
        err = self.dec({"protocol_version": 1, "type": "say_text",
                        "payload": {"text": "a" * (16 * 1024 + 1)}})
        self.assertIsInstance(err, wp.ProtocolError)
        self.assertEqual(err.code, "too_large")

    def test_bad_root_rejected(self):
        err = self.dec(["nicht", "dict"])
        self.assertIsInstance(err, wp.ProtocolError)
        self.assertEqual(err.code, "bad_root")


class FaultMatrixUnitTests(unittest.TestCase):
    """Slice 9 (SEAM-WIRE): Timestamp-Format, Event-ID-Eindeutigkeit,
    action.detail-Minimierung, keine Rohwerte in Fehlermeldungen."""

    def test_timestamp_is_rfc3339_utc_millis(self):
        proto = wp.WireProtocol()  # echte SystemClock
        env = proto.encode_event(wp.StopAck(), wp.ProtocolContext.v1("s"), correlation_id="c")
        self.assertRegex(env["timestamp"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")

    def test_event_ids_are_unique(self):
        proto = wp.WireProtocol()  # echte UuidGen
        ctx = wp.ProtocolContext.v1("s")
        a = proto.encode_event(wp.StopAck(), ctx, correlation_id="c")
        b = proto.encode_event(wp.StopAck(), ctx, correlation_id="c")
        self.assertNotEqual(a["event_id"], b["event_id"])

    def test_action_detail_minimized_for_sensitive_action_in_v1(self):
        env = _proto().encode_event(
            wp.ActionLifecycle(phase="start", action="CLIPBOARD", label="Zwischenablage",
                               detail="GEHEIME-KONTONUMMER-1234"),
            wp.ProtocolContext.v1("s"), correlation_id="c")
        self.assertEqual(env["payload"]["detail"], "")  # minimiert

    def test_action_detail_kept_for_benign_action_in_v1(self):
        env = _proto().encode_event(
            wp.ActionLifecycle(phase="start", action="NEWS", label="News", detail="Sport"),
            wp.ProtocolContext.v1("s"), correlation_id="c")
        self.assertEqual(env["payload"]["detail"], "Sport")

    def test_legacy_action_detail_stays_exact(self):
        # Legacy bleibt byte-exakt — auch bei sensiblen Actions.
        frame = _proto().encode_event(
            wp.ActionLifecycle(phase="start", action="CLIPBOARD", label="Z", detail="ROH"),
            wp.ProtocolContext.legacy())
        self.assertEqual(frame["detail"], "ROH")

    def test_decode_error_message_has_no_raw_input(self):
        # ProtocolError-Meldungen sind statisch — kein Echo des Rohwerts.
        err = _proto().decode_command(
            {"protocol_version": 1, "type": "say_text",
             "payload": {"text": "SENTINEL-GEHEIM-NIE-ECHO"}, "event_id": "x"},
            wp.ProtocolContext.v1("s"))
        self.assertIsInstance(err, wp.ProtocolError)
        self.assertNotIn("SENTINEL", err.message)


class NegotiationTests(unittest.TestCase):
    def test_ws_offers_v1(self):
        neg = wp.negotiate_ws(["jarvis.v1"])
        self.assertTrue(neg.context.is_v1)
        self.assertEqual(neg.accepted_subprotocol, "jarvis.v1")
        self.assertFalse(neg.rejected)

    def test_ws_no_subprotocol_is_legacy(self):
        neg = wp.negotiate_ws([])
        self.assertFalse(neg.context.is_v1)
        self.assertIsNone(neg.accepted_subprotocol)
        self.assertFalse(neg.rejected)

    def test_ws_only_unsupported_jarvis_rejected(self):
        neg = wp.negotiate_ws(["jarvis.v2"])
        self.assertTrue(neg.rejected)

    def test_ws_mixed_picks_v1(self):
        neg = wp.negotiate_ws(["chat", "jarvis.v1"])
        self.assertTrue(neg.context.is_v1)

    def test_rest_vendor_media_type_is_v1(self):
        self.assertTrue(wp.negotiate_rest("application/vnd.jarvis.v1+json").context.is_v1)

    def test_rest_default_is_legacy(self):
        self.assertFalse(wp.negotiate_rest("application/json").context.is_v1)

    def test_rest_unsupported_vendor_is_406(self):
        neg = wp.negotiate_rest("application/vnd.jarvis.v2+json")
        self.assertTrue(neg.not_acceptable)


if __name__ == "__main__":
    unittest.main()

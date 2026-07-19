"""Prompt 20A §7 — ``get_weather_sync`` schliesst seine HTTP-Responses.

Belegt, dass die Response auf allen Wegen geschlossen wird (Erfolg, read()/JSON-
Fehler, und beide ``HTTPError``-Versuche). Kein echter Netzaufruf: ``urlopen`` wird
durch eine geschlossen-verfolgende Attrappe ersetzt.

Unveraendert bleiben: genau zwei Versuche, 5s Timeout, bestehendes Logging,
``None``-Fallback, keine zusaetzliche Retry-Schicht.
"""
import io
import json
import unittest
import urllib.error
import urllib.request
from unittest import mock

import tests  # noqa: F401

import assistant_core

_OK_BODY = json.dumps({
    "current_condition": [{
        "temp_C": "12", "FeelsLikeC": "10",
        "weatherDesc": [{"value": "wolkig"}], "humidity": "80", "windspeedKmph": "9",
    }]
}).encode()


class _TrackedResponse(io.BytesIO):
    """Response-Attrappe mit Schliess-Verfolgung + Context-Manager."""

    def __init__(self, body=b"", closes=None):
        super().__init__(body)
        self._closes = closes if closes is not None else []
        self.closed_flag = False

    def close(self):
        self.closed_flag = True
        self._closes.append(1)
        super().close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


class WeatherResourceTests(unittest.TestCase):
    def setUp(self):
        # Deterministisch: 5s-Retry-sleep nicht real warten.
        self._sleep = mock.patch("assistant_core.time.sleep", lambda *_: None)
        self._sleep.start()
        self.addCleanup(self._sleep.stop)

    def test_successful_response_is_closed(self):
        resp = _TrackedResponse(_OK_BODY)
        with mock.patch("urllib.request.urlopen", return_value=resp) as uo:
            result = assistant_core.get_weather_sync()
        self.assertIsNotNone(result)
        self.assertEqual("12", result["temp"])
        self.assertTrue(resp.closed_flag, "erfolgreiche Response nicht geschlossen")
        # 5s-Timeout unveraendert.
        self.assertEqual(5, uo.call_args.kwargs.get("timeout", uo.call_args[1].get("timeout")))

    def test_read_or_json_error_closes_the_response(self):
        # Gueltige Verbindung, aber kaputter Body -> json.loads wirft.
        responses = [_TrackedResponse(b"kein json"), _TrackedResponse(b"auch nicht")]
        with mock.patch("urllib.request.urlopen", side_effect=list(responses)):
            result = assistant_core.get_weather_sync()
        self.assertIsNone(result, "kaputter Body muss zum None-Fallback fuehren")
        for i, r in enumerate(responses):
            self.assertTrue(r.closed_flag, f"Response {i} bei JSON-Fehler nicht geschlossen")

    def test_both_httperror_responses_are_closed(self):
        import gc
        import warnings

        def _raise_httperror(req, *a, **k):
            # Echtes HTTPError — es traegt einen zu schliessenden Body und meldet
            # sonst beim impliziten Aufraeumen ein ResourceWarning.
            fp = _TrackedResponse(b"fehlerseite")
            raise urllib.error.HTTPError(
                "https://wttr.in/x", 503, "Service Unavailable", {}, fp)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with mock.patch("urllib.request.urlopen", side_effect=_raise_httperror):
                result = assistant_core.get_weather_sync()
            # Etwaige implizite Aufraeumung erzwingen, damit ein Leck SICHTBAR wird.
            gc.collect()
        self.assertIsNone(result)
        leaks = [w for w in caught if issubclass(w.category, ResourceWarning)]
        self.assertEqual([], leaks,
                         f"HTTPError-Response nicht explizit geschlossen: "
                         f"{[str(w.message) for w in leaks]}")

    def test_exactly_two_attempts(self):
        calls = []

        def _count(req, *a, **k):
            calls.append(1)
            raise urllib.error.URLError("weg")

        with mock.patch("urllib.request.urlopen", side_effect=_count):
            assistant_core.get_weather_sync()
        self.assertEqual(2, len(calls), "es muessen genau zwei Versuche bleiben")

    def test_logs_on_failure_but_no_second_retry_layer(self):
        events = []
        with mock.patch("assistant_core.obslog.event",
                        lambda name, **f: events.append((name, f))), \
                mock.patch("urllib.request.urlopen",
                           side_effect=urllib.error.URLError("weg")):
            assistant_core.get_weather_sync()
        stages = [f.get("stage") for n, f in events if n == "context.refresh_failed"]
        self.assertEqual(["weather", "weather"], stages,
                         "bestehendes Logging (je Versuch) veraendert")


if __name__ == "__main__":
    unittest.main()

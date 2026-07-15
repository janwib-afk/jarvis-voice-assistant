"""
Tests fuer tts.py — Chunking und Fehlerpfade mit gemocktem HTTP-Client.
Kein echter ElevenLabs-Aufruf, kein Serverstart noetig.

    python -m unittest discover -s tests
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tts


class _FakeResponse:
    def __init__(self, status_code=200, content=b"", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


class _FakeClient:
    """Gibt vorbereitete Antworten der Reihe nach zurueck (oder wirft sie)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        item = self.responses.pop(0) if self.responses else _FakeResponse(500)
        if isinstance(item, Exception):
            raise item
        return item


def _run(text, client):
    return asyncio.run(tts.synthesize_speech(
        text, api_key="test-key", voice_id="test-voice", client=client
    ))


class SplitIntoChunksTests(unittest.TestCase):
    def test_short_text_single_chunk(self):
        self.assertEqual(tts.split_into_chunks("Hallo."), ["Hallo."])

    def test_long_text_splits_at_sentences(self):
        text = ("Erster Satz mit einigem Inhalt. " * 25).strip()  # > MAX_CHUNK_CHARS
        chunks = tts.split_into_chunks(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), tts.MAX_CHUNK_CHARS + 40)
        self.assertEqual(" ".join(chunks), text)

    def test_empty(self):
        self.assertEqual(tts.split_into_chunks(""), [""])

    def test_long_sentence_without_punctuation_capped(self):
        # Ein einziger "Satz" ohne Satzzeichen, deutlich laenger als max_chars.
        text = ("Wort " * 200).strip()
        chunks = tts.split_into_chunks(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), tts.MAX_CHUNK_CHARS)
            self.assertTrue(chunk)  # keine Leerstrings

    def test_single_word_longer_than_max_hard_cut(self):
        word = "a" * (tts.MAX_CHUNK_CHARS * 2 + 5)
        chunks = tts.split_into_chunks(word)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), tts.MAX_CHUNK_CHARS)
            self.assertTrue(chunk)
        # Hartschnitt ist verlustfrei (kein Trennzeichen eingefuegt).
        self.assertEqual("".join(chunks), word)

    def test_custom_max_chars_respected(self):
        text = "Satz eins ist hier. Satz zwei folgt jetzt. Und ein dritter Satz kommt."
        chunks = tts.split_into_chunks(text, max_chars=20)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 20)
            self.assertTrue(chunk)


class SynthesizeSpeechTests(unittest.TestCase):
    def test_empty_text_no_call(self):
        client = _FakeClient([])
        audio, err = _run("   ", client)
        self.assertEqual(audio, b"")
        self.assertIsNone(err)
        self.assertEqual(client.calls, [])

    def test_success_returns_audio(self):
        client = _FakeClient([_FakeResponse(200, b"MP3DATA")])
        audio, err = _run("Hallo Jan.", client)
        self.assertEqual(audio, b"MP3DATA")
        self.assertIsNone(err)
        self.assertEqual(len(client.calls), 1)
        # Voice-ID steckt in der URL, Key im Header.
        url, kwargs = client.calls[0]
        self.assertIn("test-voice", url)
        self.assertEqual(kwargs["headers"]["xi-api-key"], "test-key")

    def test_multi_chunk_audio_concatenated(self):
        text = ("Langer Satz Nummer eins mit vielen Worten drin. " * 15).strip()
        n_chunks = len(tts.split_into_chunks(text))
        self.assertGreater(n_chunks, 1)  # Verkettung mehrerer MP3-Parts wird geprueft
        client = _FakeClient([_FakeResponse(200, b"A")] * n_chunks)
        audio, err = _run(text, client)
        self.assertEqual(audio, b"A" * n_chunks)
        self.assertIsNone(err)

    def test_auth_error_no_retry(self):
        client = _FakeClient([_FakeResponse(401, text="unauthorized")])
        audio, err = _run("Hallo.", client)
        self.assertEqual(audio, b"")
        self.assertIn("API-Key", err)
        self.assertEqual(len(client.calls), 1)  # 4xx ist nicht transient

    def test_unknown_voice_hint(self):
        client = _FakeClient([_FakeResponse(404, text="voice not found")])
        audio, err = _run("Hallo.", client)
        self.assertEqual(audio, b"")
        self.assertIn("Voice-ID", err)

    def test_rate_limit_hint(self):
        client = _FakeClient([_FakeResponse(429, text="quota")])
        audio, err = _run("Hallo.", client)
        self.assertEqual(audio, b"")
        self.assertIn("Rate-Limit", err)

    def test_network_error_retries_then_reports(self):
        client = _FakeClient([ConnectionError("kaputt"), ConnectionError("immer noch")])
        audio, err = _run("Hallo.", client)
        self.assertEqual(audio, b"")
        self.assertIn("Netzwerkfehler", err)
        self.assertEqual(len(client.calls), 2)  # genau 1 Retry

    def test_server_error_retries_then_succeeds(self):
        client = _FakeClient([_FakeResponse(500), _FakeResponse(200, b"OK")])
        audio, err = _run("Hallo.", client)
        self.assertEqual(audio, b"OK")
        self.assertIsNone(err)

    def test_partial_success_is_no_error(self):
        # Chunk 1 ok, Chunk 2 scheitert => Audio kommt, kein Fehlerhinweis.
        text = ("Satz eins ist hier ziemlich lang und redet weiter. " * 15).strip()
        n_chunks = len(tts.split_into_chunks(text))
        self.assertGreaterEqual(n_chunks, 2)
        responses = [_FakeResponse(200, b"X")] + [_FakeResponse(429)] * (n_chunks - 1)
        client = _FakeClient(responses)
        audio, err = _run(text, client)
        self.assertEqual(audio, b"X")
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()

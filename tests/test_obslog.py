"""Contract-Tests des strukturierten Operational-Logging-Moduls (RFC-0004).

Getestet wird ausschliesslich das oeffentliche Interface und der VOLLSTAENDIG
FORMATIERTE Sink-Output — nie private Regex-/Filter-/Formatter-Helfer, nie ein
unbearbeiteter LogRecord.

    sink = obslog.MemorySink()
    obslog.configure(sink=sink, fmt="text")     # bzw. fmt="jsonl"
    obslog.event("action.finished", action="CLIPBOARD", result_len=412)
    lines = sink.lines                           # die tatsaechlich gerenderten Zeilen

Alle Werte sind synthetische Sentinels. Keine echten Provider, keine echte Config,
keine echten Logdateien.
"""
import json
import unittest

import obslog

# Synthetische Sentinels — duerfen in KEINEM Sink-Output erscheinen.
S_SECRET = "SENTINEL-SECRET-sk-ant-xyz-NEVER"
S_TOKEN = "SENTINEL-TOKEN-bearer-abc-NEVER"
S_CLIP = "SENTINEL-CLIPBOARD-Kontonummer-NEVER"
S_QUERY = "SENTINEL-QUERY-Krankheit-NEVER"
S_PATH = "SENTINEL-PATH-C-Users-Geheim-NEVER"
S_FIELD = "SENTINEL-UNKNOWNFIELD-VALUE-NEVER"


class _SinkTestCase(unittest.TestCase):
    """Basis: jeder Test bekommt einen frischen In-Memory-Sink."""

    def configure(self, fmt="text"):
        self.sink = obslog.MemorySink()
        obslog.configure(sink=self.sink, fmt=fmt, level="DEBUG")
        return self.sink

    def tearDown(self):
        obslog.reset()

    @property
    def text(self):
        return "\n".join(self.sink.lines)


class TextOutputTests(_SinkTestCase):
    def test_event_name_and_allowed_metadata_appear(self):
        self.configure("text")
        obslog.event("action.finished", action="CLIPBOARD", result_len=412)
        self.assertIn("action.finished", self.text)
        self.assertIn("CLIPBOARD", self.text)
        self.assertIn("412", self.text)

    def test_output_is_a_single_line_per_event(self):
        self.configure("text")
        obslog.event("action.finished", action="SEARCH", result_len=10)
        self.assertEqual(len(self.sink.lines), 1)


class JsonlOutputTests(_SinkTestCase):
    def test_each_line_is_valid_json(self):
        self.configure("jsonl")
        obslog.event("action.finished", action="CLIPBOARD", result_len=412)
        parsed = json.loads(self.sink.lines[0])
        self.assertEqual(parsed["event"], "action.finished")
        self.assertEqual(parsed["action"], "CLIPBOARD")
        self.assertEqual(parsed["result_len"], 412)

    def test_text_and_jsonl_carry_the_same_semantic_fields(self):
        self.configure("jsonl")
        obslog.event("app.launched", app="obsidian")
        js = json.loads(self.sink.lines[0])
        obslog.reset()
        self.configure("text")
        obslog.event("app.launched", app="obsidian")
        # Beide Formate speisen sich aus denselben Feldern.
        self.assertEqual(js["app"], "obsidian")
        self.assertIn("obsidian", self.text)
        self.assertIn("app.launched", self.text)


class UnknownFieldTests(_SinkTestCase):
    def test_unknown_field_disappears_and_only_count_remains(self):
        self.configure("text")
        obslog.event("action.finished", action="CLIPBOARD", result_len=1,
                     clipboard_text=S_CLIP)
        self.assertNotIn(S_CLIP, self.text)
        self.assertNotIn("clipboard_text", self.text)
        self.assertIn("dropped_fields", self.text)
        self.assertIn("1", self.text)

    def test_nested_sentinel_in_unknown_field_disappears(self):
        self.configure("jsonl")
        obslog.event("action.finished", action="SEARCH", result_len=1,
                     bag={"deep": {"deeper": S_CLIP}})
        line = self.sink.lines[0]
        self.assertNotIn(S_CLIP, line)
        self.assertEqual(json.loads(line)["dropped_fields"], 1)

    def test_wrong_typed_allowed_field_is_dropped_without_str(self):
        class Hostile:
            def __str__(self):
                raise RuntimeError(S_FIELD)
            def __repr__(self):
                raise RuntimeError(S_FIELD)

        self.configure("text")
        # result_len erwartet int; ein feindliches Objekt darf NICHT ge-str()-t werden.
        obslog.event("action.finished", action="SEARCH", result_len=Hostile())
        self.assertNotIn(S_FIELD, self.text)
        self.assertIn("dropped_fields", self.text)

    def test_safe_metadata_survives_alongside_dropped_field(self):
        self.configure("text")
        obslog.event("action.finished", action="NEWS", result_len=99,
                     secret_field=S_SECRET)
        self.assertIn("NEWS", self.text)
        self.assertIn("99", self.text)
        self.assertNotIn(S_SECRET, self.text)


class UnknownEventNameTests(_SinkTestCase):
    def test_unknown_event_name_cannot_emit_its_input_text(self):
        self.configure("text")
        # Ein unbekannter Eventname koennte sensible Daten tragen -> nie ausgeben.
        obslog.event(f"stolen.{S_SECRET}", action="X")
        self.assertNotIn(S_SECRET, self.text)

    def test_unknown_event_is_reported_without_leaking_name(self):
        self.configure("jsonl")
        obslog.event(f"weird.{S_QUERY}")
        # Es darf hoechstens ein neutraler Marker erscheinen, nie der Rohname.
        self.assertNotIn(S_QUERY, self.text)


class UrlRedactionTests(_SinkTestCase):
    def test_url_loses_path_query_fragment_and_userinfo(self):
        self.configure("text")
        url = f"https://user:pw@duckduckgo.com/html/?q={S_QUERY}#frag-{S_PATH}"
        obslog.event("browser.fallback", url=url)
        self.assertIn("duckduckgo.com", self.text)
        self.assertNotIn(S_QUERY, self.text)
        self.assertNotIn(S_PATH, self.text)
        self.assertNotIn("user", self.text)
        self.assertNotIn("pw", self.text)

    def test_url_keeps_scheme_and_host_only(self):
        self.configure("jsonl")
        obslog.event("browser.fallback", url="https://api.elevenlabs.io/v1/x?k=secret")
        self.assertEqual(json.loads(self.sink.lines[0])["url"], "https://api.elevenlabs.io")


class SecretsAreUnrepresentableTests(_SinkTestCase):
    def test_no_field_can_carry_a_secret_or_free_text(self):
        self.configure("text")
        # Es gibt keine erlaubten Freitext-/Secret-Felder — sie fallen alle raus.
        obslog.event("settings.saved", changed=2, token=S_TOKEN, backup_path=S_PATH,
                     message=S_CLIP)
        self.assertIn("settings.saved", self.text)
        self.assertIn("2", self.text)
        for s in (S_TOKEN, S_PATH, S_CLIP):
            self.assertNotIn(s, self.text)


class StartupWiringTests(unittest.TestCase):
    """Slice 2: Konfiguration am Startpfad, nicht beim Import; beide Startwege
    geschuetzt; Test-Sinks werden nicht ungefragt ueberschrieben."""

    def tearDown(self):
        obslog.reset()

    def _fresh_import(self, code):
        import subprocess, sys, os
        env = dict(os.environ); env["PYTHONUTF8"] = "1"
        env.pop("JARVIS_CONFIG_PATH", None)
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=env, capture_output=True, text=True, timeout=90)

    def test_importing_server_installs_no_root_handler(self):
        # Rot bis basicConfig aus dem Import raus ist: basicConfig haengt einen
        # StreamHandler an den Root-Logger. Nach Slice 2 darf der Import KEINEN
        # Handler installieren (Import-Sicherheit, D9).
        r = self._fresh_import(
            "import logging, server; "
            "n = len(logging.getLogger().handlers); "
            "print('ROOT_HANDLERS', n)")
        self.assertIn("ROOT_HANDLERS 0", r.stdout,
                      f"server-Import installierte Root-Handler.\nstderr:\n{r.stderr}")

    def test_importing_server_does_not_configure_obslog(self):
        r = self._fresh_import(
            "import obslog, server; "
            "assert obslog._sink is None, 'server-Import hat obslog konfiguriert'; "
            "print('OBSLOG_UNSET')")
        self.assertIn("OBSLOG_UNSET", r.stdout, r.stderr)

    def test_format_from_env_defaults_to_text(self):
        self.assertEqual(obslog.format_from_env({}), "text")
        self.assertEqual(obslog.format_from_env({"JARVIS_LOG_FORMAT": "jsonl"}), "jsonl")
        self.assertEqual(obslog.format_from_env({"JARVIS_LOG_FORMAT": "bogus"}), "text")
        self.assertEqual(obslog.format_from_env({"JARVIS_LOG_FORMAT": "JSONL"}), "jsonl")

    def test_configure_is_idempotent_no_duplicate_lines(self):
        sink = obslog.MemorySink()
        obslog.configure(sink=sink, fmt="text", level="INFO")
        obslog.configure(sink=sink, fmt="text", level="INFO")  # erneut
        obslog.event("server.started")
        self.assertEqual(len(sink.lines), 1, "wiederholte Konfiguration darf nicht doppeln")

    def test_reconfigure_replaces_sink_cleanly(self):
        a = obslog.MemorySink(); b = obslog.MemorySink()
        obslog.configure(sink=a); obslog.event("server.started")
        obslog.configure(sink=b); obslog.event("server.started")
        self.assertEqual(len(a.lines), 1)
        self.assertEqual(len(b.lines), 1)


if __name__ == "__main__":
    unittest.main()

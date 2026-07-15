"""
Tests fuer die Musik-API (GET /music/files, POST /music/selection) und den
statischen Guard fuer den Musikpfad in launch-session.ps1.

WICHTIG: wie in test_settings_api wird ``server.CONFIG_PATH`` auf eine
Temp-Kopie gepatcht und ``assistant_core.refresh_data`` auf einen No-Op —
die Tests duerfen NIEMALS die echte config.json beschreiben oder Netzaufrufe
ausloesen. Der Musikordner ist ein Temp-Verzeichnis mit Dummy-Dateien.

    python -m unittest discover -s tests
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LAUNCH_PS1 = os.path.join(_ROOT, "scripts", "launch-session.ps1")

try:
    import server
    import app_launcher
    import assistant_core
    import memory
    from fastapi.testclient import TestClient
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    app_launcher = None
    assistant_core = None
    memory = None
    TestClient = None
    _IMPORT_ERROR = e

_TEST_CONFIG = {
    "anthropic_api_key": "sk-ant-test-secret-111",
    "elevenlabs_api_key": "el-test-secret-222",
    "user_name": "TestUser",
    "city": "Hamburg",
    "apps": ["obsidian://open"],
    "music_folder": "",           # wird in setUp auf den Temp-Ordner gesetzt
    "selected_music_file": "",
}

_SERVER_GLOBALS = ("config", "STARTUP_WARNINGS", "CONFIG_PATH")
_CORE_GLOBALS = (
    "USER_NAME", "USER_ADDRESS", "USER_ROLE", "CITY",
    "ELEVENLABS_VOICE_ID", "refresh_data",
)


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class MusicApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.headers = {"X-Jarvis-Token": server.SESSION_TOKEN}

        # Temp-Musikordner: 2 MP3s, Nicht-MP3s und ein Ordner mit .mp3-Namen.
        self.music_dir = tempfile.mkdtemp(prefix="jarvis_music_")
        for name in ("b-track.mp3", "A-Track.mp3", "notes.txt", "clip.wav"):
            with open(os.path.join(self.music_dir, name), "w", encoding="utf-8") as f:
                f.write("x")
        os.makedirs(os.path.join(self.music_dir, "ordner.mp3"))  # Dir wird ignoriert

        cfg = dict(_TEST_CONFIG)
        cfg["music_folder"] = self.music_dir

        fd, self.cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)

        self._saved = {name: getattr(server, name) for name in _SERVER_GLOBALS}
        self._saved_core = {name: getattr(assistant_core, name) for name in _CORE_GLOBALS}
        self._saved_memory = (memory.VAULT_PATH, memory.INBOX_PATH)
        self._saved_apps = (app_launcher.APPS, app_launcher.PROFILES,
                            app_launcher.ACTIVE_PROFILE)
        server.CONFIG_PATH = self.cfg_path
        assistant_core.refresh_data = lambda: None  # kein wttr.in/Vault-Scan im Test
        server.config = cfg
        assistant_core.CITY = cfg["city"]
        assistant_core.USER_NAME = cfg["user_name"]
        memory.configure(vault_path="", inbox_path="")

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(server, name, value)
        for name, value in self._saved_core.items():
            setattr(assistant_core, name, value)
        memory.configure(*self._saved_memory)
        app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE = \
            self._saved_apps
        if os.path.exists(self.cfg_path):
            os.remove(self.cfg_path)
        shutil.rmtree(self.music_dir, ignore_errors=True)

    def _on_disk(self) -> dict:
        with open(self.cfg_path, encoding="utf-8") as f:
            return json.load(f)

    # ── Auth ────────────────────────────────────────────────────────────────
    def test_files_requires_token(self):
        self.assertEqual(self.client.get("/music/files").status_code, 403)

    def test_selection_requires_token(self):
        resp = self.client.post("/music/selection", json={"file": "A-Track.mp3"})
        self.assertEqual(resp.status_code, 403)

    # ── GET /music/files ────────────────────────────────────────────────────
    def test_files_lists_only_mp3_sorted(self):
        resp = self.client.get("/music/files", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["folder"], self.music_dir)
        self.assertEqual(data["selected"], "")
        names = [f["name"] for f in data["files"]]
        # Nur echte .mp3-DATEIEN, stabil alphabetisch (case-insensitiv).
        self.assertEqual(names, ["A-Track.mp3", "b-track.mp3"])
        for f in data["files"]:
            self.assertIn("size", f)
            self.assertIn("modified", f)

    def test_files_missing_folder_controlled_error(self):
        server.config["music_folder"] = os.path.join(
            tempfile.gettempdir(), "jarvis_nope_musik")
        resp = self.client.get("/music/files", headers=self.headers)
        self.assertEqual(resp.status_code, 200)  # Zustandsbericht, kein Crash
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("Musikordner", data["error"])
        self.assertEqual(data["files"], [])

    def test_files_no_folder_configured(self):
        server.config["music_folder"] = ""
        data = self.client.get("/music/files", headers=self.headers).json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["files"], [])

    # ── POST /music/selection ───────────────────────────────────────────────
    def test_selection_saves_valid_file(self):
        resp = self.client.post("/music/selection", headers=self.headers,
                                json={"file": "A-Track.mp3"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True, "selected": "A-Track.mp3"})
        # Persistiert (nur der Dateiname) + live uebernommen + in GET sichtbar.
        self.assertEqual(self._on_disk()["selected_music_file"], "A-Track.mp3")
        self.assertEqual(server.config["selected_music_file"], "A-Track.mp3")
        data = self.client.get("/music/files", headers=self.headers).json()
        self.assertEqual(data["selected"], "A-Track.mp3")

    def test_selection_empty_deselects(self):
        self.client.post("/music/selection", headers=self.headers,
                         json={"file": "A-Track.mp3"})
        resp = self.client.post("/music/selection", headers=self.headers,
                                json={"file": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._on_disk()["selected_music_file"], "")

    def test_selection_rejects_invalid(self):
        for bad in ("clip.wav",                 # keine .mp3
                    "..\\A-Track.mp3",          # Traversal
                    "sub/A-Track.mp3",          # Separator
                    "C:\\Musik\\song.mp3",      # absoluter Pfad
                    "gibtsnicht.mp3"):          # existiert nicht im Ordner
            resp = self.client.post("/music/selection", headers=self.headers,
                                    json={"file": bad})
            self.assertEqual(resp.status_code, 400, repr(bad))
            self.assertEqual(self._on_disk()["selected_music_file"], "", repr(bad))

    def test_selection_directory_named_mp3_rejected(self):
        # "ordner.mp3" existiert, ist aber ein Verzeichnis — isfile lehnt ab.
        resp = self.client.post("/music/selection", headers=self.headers,
                                json={"file": "ordner.mp3"})
        self.assertEqual(resp.status_code, 400)

    def test_selection_missing_field_400(self):
        resp = self.client.post("/music/selection", headers=self.headers, json={})
        self.assertEqual(resp.status_code, 400)

    def test_selection_missing_folder_rejected(self):
        server.config["music_folder"] = os.path.join(
            tempfile.gettempdir(), "jarvis_nope_musik")
        resp = self.client.post("/music/selection", headers=self.headers,
                                json={"file": "A-Track.mp3"})
        self.assertEqual(resp.status_code, 400)

    def test_selection_broadcasts_music_changed(self):
        # Muster launcher_changed: alle WS-Clients werden nach einer
        # Auswahlaenderung nachgezogen. broadcast_json wird aufgezeichnet.
        events = []

        async def record(payload):
            events.append(payload)

        original = server.broadcast_json
        server.broadcast_json = record
        try:
            resp = self.client.post("/music/selection", headers=self.headers,
                                    json={"file": "A-Track.mp3"})
            self.assertEqual(resp.status_code, 200)
        finally:
            server.broadcast_json = original
        music_events = [e for e in events if e.get("type") == "music_changed"]
        self.assertEqual(len(music_events), 1)
        self.assertEqual(music_events[0]["selected"], "A-Track.mp3")


class PowerShellMusicTests(unittest.TestCase):
    """Statischer Guard fuer launch-session.ps1 — es gibt keine PS-Testsuite,
    daher pruefen wir die Musik-Logik auf Textebene (kein Hardcode, Config-
    Felder gelesen, .mp3-/Dateiname-/Existenz-Pruefung vor dem Abspielen)."""

    @classmethod
    def setUpClass(cls):
        with open(_LAUNCH_PS1, "r", encoding="utf-8") as f:
            cls.ps1 = f.read()

    def test_no_hardcoded_music_path(self):
        self.assertNotIn("D:\\AI\\Musik", self.ps1)
        self.assertNotIn('$MUSIC_PATH = "', self.ps1)

    def test_reads_config_fields(self):
        self.assertIn("music_folder", self.ps1)
        self.assertIn("selected_music_file", self.ps1)
        self.assertIn("music_volume", self.ps1)

    def test_enforces_filename_and_mp3(self):
        # Reiner Dateiname + .mp3-Endung + Existenz als Datei vor dem Abspielen.
        self.assertIn("[System.IO.Path]::GetFileName($f) -ne $f", self.ps1)
        self.assertIn(".EndsWith('.mp3')", self.ps1)
        self.assertIn("Test-Path -LiteralPath $candidate -PathType Leaf", self.ps1)

    def test_plays_only_resolved_path(self):
        # Abspiel-Block haengt am Ergebnis von Get-SelectedMusicPath —
        # kein eigener Test-Path auf einen Hardcode mehr.
        self.assertIn("Get-SelectedMusicPath $config", self.ps1)
        self.assertIn("if ($music.Path) {", self.ps1)
        self.assertIn("Start-BackgroundMusic", self.ps1)

    def test_helpers_loadable_via_functions_only(self):
        # Beide Helfer stehen VOR dem FunctionsOnly-Gate — nur so laedt
        # ". launch-session.ps1 -FunctionsOnly" sie fuer Tests.
        gate = self.ps1.find("if ($FunctionsOnly) { return }")
        self.assertNotEqual(gate, -1)
        for fn in ("function Get-SelectedMusicPath",
                   "function Start-BackgroundMusic",
                   "function Get-MusicVolume"):
            pos = self.ps1.find(fn)
            self.assertNotEqual(pos, -1, fn)
            self.assertLess(pos, gate, fn + " muss vor dem FunctionsOnly-Gate stehen")

    def test_logs_skip_cases(self):
        # Skip-Faelle werden geloggt (mit Begruendung aus Get-SelectedMusicPath).
        self.assertIn("Musik uebersprungen", self.ps1)


@unittest.skipUnless(
    sys.platform == "win32" and shutil.which("powershell"),
    "PowerShell nicht verfuegbar",
)
class PowerShellMusicFunctionalTests(unittest.TestCase):
    """Funktionaler End-to-End-Test der REINEN Aufloesung: laedt die Helfer
    per ``. launch-session.ps1 -FunctionsOnly`` in einer echten PowerShell und
    prueft Get-SelectedMusicPath/Get-MusicVolume gegen einen Temp-Musikordner.
    Seiteneffektfrei — Get-SelectedMusicPath startet/loggt nichts."""

    def test_resolution_and_volume(self):
        import subprocess

        music_dir = tempfile.mkdtemp(prefix="jarvis_psmusic_")
        self.addCleanup(shutil.rmtree, music_dir, ignore_errors=True)
        mp3 = os.path.join(music_dir, "track.mp3")
        for name in ("track.mp3", "clip.wav"):
            with open(os.path.join(music_dir, name), "w", encoding="utf-8") as f:
                f.write("x")

        def q(s):  # PowerShell-Single-Quote-Escaping
            return s.replace("'", "''")

        # Ein einziger PS-Aufruf prueft alle Faelle (eine Ausgabezeile pro Fall).
        driver = "\n".join([
            ". '%s' -FunctionsOnly" % q(_LAUNCH_PS1),
            "$folder = '%s'" % q(music_dir),
            "$cases = @('track.mp3', '', 'clip.wav', '..\\track.mp3', 'sub/track.mp3', '%s', 'fehlt.mp3')" % q(mp3),
            "foreach ($f in $cases) {",
            "    $cfg = [pscustomobject]@{ music_folder = $folder; selected_music_file = $f }",
            "    $r = Get-SelectedMusicPath $cfg",
            "    if ($r.Path) { Write-Output \"PATH:$($r.Path)\" } else { Write-Output 'NULL' }",
            "}",
            "foreach ($v in @('0.5', '', 'quatsch', '2')) {",
            "    $cfg = [pscustomobject]@{ music_volume = $v }",
            "    Write-Output \"VOL:$((Get-MusicVolume $cfg).ToString([System.Globalization.CultureInfo]::InvariantCulture))\"",
            "}",
        ])
        fd, script = tempfile.mkstemp(suffix=".ps1")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(script) and os.remove(script))
        with open(script, "w", encoding="utf-8-sig") as f:
            f.write(driver)

        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 11, proc.stdout)

        # Fall 1: gueltige Auswahl -> voller Pfad im Musikordner.
        self.assertTrue(lines[0].startswith("PATH:"), lines[0])
        self.assertEqual(os.path.normcase(lines[0][5:]), os.path.normcase(mp3))
        # Faelle 2-7: leer, .wav, Traversal, Separator, absoluter Pfad
        # (obwohl die Datei existiert!), nicht vorhanden -> alle NULL.
        self.assertEqual(lines[1:7], ["NULL"] * 6, lines)
        # Volume: gueltig, leer (Default), unparsebar (Default), geklemmt.
        self.assertEqual(lines[7:], ["VOL:0.5", "VOL:0.25", "VOL:0.25", "VOL:1"], lines)


if __name__ == "__main__":
    unittest.main()

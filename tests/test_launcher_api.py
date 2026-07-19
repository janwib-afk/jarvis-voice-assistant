"""
Tests fuer die Launcher-API (Apps, Placement, Monitore, Session-Profile)
gegen die echte App.

WICHTIG: alles laeuft ueber die Runtime-Seam (eigene Temp-Config) und
``assistant_core.refresh_data`` auf einen No-Op — die Tests duerfen NIEMALS
die echte config.json beschreiben oder Netzaufrufe (wttr.in) ausloesen.

``LauncherApiTests`` faehrt den MIGRATIONSPFAD (Alt-Config ohne launcher-Block,
Profil wird abgeleitet und bei der ersten Mutation materialisiert),
``ProfileApiTests`` den Profil-Pfad (launcher-Block vorhanden).

    python -m unittest discover -s tests
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'
from tests import wire_testing as wt

try:
    import server
    import actions
    import app_launcher
    import assistant_core
    import memory
    import runtime as runtime_mod
    from fastapi.testclient import TestClient
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    app_launcher = None
    assistant_core = None
    TestClient = None
    _IMPORT_ERROR = e

# Alt-Config OHNE launcher: Migrationspfad (Legacy-String + Objektform).
_TEST_CONFIG = {
    "anthropic_api_key": "sk-ant-test-secret-111",
    "elevenlabs_api_key": "el-test-secret-222",
    "user_name": "TestUser",
    "city": "Hamburg",
    # Nicht UI-editierbar — muss ein Toggle unangetastet lassen:
    "workspace_path": "C:\\test-workspace",
    "apps": [
        "obsidian://open",
        {"id": "vscode", "name": "VS Code", "command": "code", "type": "process", "autostart": True,
         "placement": {"monitor": "left", "zone": "left_half"}},
    ],
}

# Neu-Config MIT launcher-Block: Profil-Pfad.
_PROFILED_CONFIG = {
    "anthropic_api_key": "sk-ant-test-secret-111",
    "elevenlabs_api_key": "el-test-secret-222",
    "user_name": "TestUser",
    "city": "Hamburg",
    "workspace_path": "C:\\test-workspace",
    "apps": [
        {"id": "obsidian", "name": "Obsidian", "command": "obsidian://open", "type": "url"},
        {"id": "vscode", "name": "VS Code", "command": "code", "type": "process"},
    ],
    "launcher": {
        "active_profile": "coding",
        "profiles": [
            {"id": "coding", "name": "Coding", "apps": {
                "vscode": {"autostart": True,
                           "placement": {"monitor": "left", "zone": "left_half"}}}},
            {"id": "writing", "name": "Writing", "apps": {"vscode": {"autostart": False}}},
        ],
    },
}

# Globals, die apply_settings veraendert — werden pro Test gesichert.
_CORE_GLOBALS = (
    "USER_NAME", "USER_ADDRESS", "USER_ROLE", "CITY",
    "ELEVENLABS_VOICE_ID", "refresh_data",
)


class _ApiTestBase(unittest.TestCase):
    """Gemeinsames Geruest: Temp-Config, gepatchte Globals, saubere Restauration."""

    _CONFIG: dict = {}

    def setUp(self):
        # Seam (RFC-0003): eigene Runtime + Temp-Config + lifespan-fahrender
        # TestClient — keine server.CONFIG_PATH/config-Patches.
        os.environ["JARVIS_SKIP_STARTUP_REFRESH"] = "1"
        fd, self.cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(dict(self._CONFIG, schema_version=1), f, ensure_ascii=False)

        self._saved_core = {name: getattr(assistant_core, name) for name in _CORE_GLOBALS}
        self._saved_memory = (memory.VAULT_PATH, memory.INBOX_PATH)
        self._saved_launcher = (app_launcher.APPS, app_launcher.PROFILES,
                                app_launcher.ACTIVE_PROFILE)
        assistant_core.refresh_data = lambda: None  # kein wttr.in/Vault-Scan im Test
        memory.configure(vault_path="", inbox_path="")

        self.runtime = runtime_mod.Runtime.for_production(
            config_path=self.cfg_path, environ={}, ai=object(), http=object())
        self.app = server.create_app(self.runtime)
        self._client_cm = TestClient(self.app)
        self.client = self._client_cm.__enter__()
        self.headers = {"X-Jarvis-Token": self.runtime.session_token}

    def tearDown(self):
        self._client_cm.__exit__(None, None, None)
        for name, value in self._saved_core.items():
            setattr(assistant_core, name, value)
        memory.configure(*self._saved_memory)
        app_launcher.APPS, app_launcher.PROFILES, app_launcher.ACTIVE_PROFILE = \
            self._saved_launcher
        if os.path.exists(self.cfg_path):
            os.remove(self.cfg_path)

    def _read_cfg(self):
        with open(self.cfg_path, encoding="utf-8") as f:
            return json.load(f)

    def _profile_states(self, profile_id=None):
        """App-States eines Profils aus der Temp-Datei lesen."""
        launcher = self._read_cfg()["launcher"]
        pid = profile_id or launcher["active_profile"]
        profile = next(p for p in launcher["profiles"] if p["id"] == pid)
        return profile["apps"]

    def _effective(self):
        return {a["id"]: a for a in app_launcher.list_apps()}


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class LauncherApiTests(_ApiTestBase):
    """Migrationspfad: Alt-Config ohne launcher-Block."""

    _CONFIG = _TEST_CONFIG

    # ── Auth ────────────────────────────────────────────────────────────────
    def test_endpoints_require_token(self):
        self.assertEqual(self.client.get("/launcher/apps").status_code, 403)
        resp = self.client.get("/launcher/apps", headers={"X-Jarvis-Token": "falsch"})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post("/launcher/apps/vscode/toggle", json={"autostart": False})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post(
            "/launcher/apps/vscode/placement", json={"monitor": "left", "zone": "center"}
        )
        self.assertEqual(resp.status_code, 403)

    # ── GET ─────────────────────────────────────────────────────────────────
    def test_get_lists_apps_without_command(self):
        resp = self.client.get("/launcher/apps", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["active_profile"], "default")  # abgeleitet
        self.assertEqual(len(data["apps"]), 2)
        for app in data["apps"]:
            self.assertEqual(set(app), {"id", "name", "type", "autostart", "placement"})

    def test_get_includes_placement(self):
        data = self.client.get("/launcher/apps", headers=self.headers).json()
        by_id = {a["id"]: a for a in data["apps"]}
        # App-Level-placement wandert in das abgeleitete Default-Profil.
        self.assertEqual(by_id["vscode"]["placement"], {"monitor": "left", "zone": "left_half"})
        # Legacy-String ohne placement → normalisierter Default (reine Anzeige).
        self.assertEqual(by_id["obsidian"]["placement"], {"monitor": "primary", "zone": "fullscreen"})

    # ── Toggle: materialisiert den launcher-Block (Migration) ──────────────
    def test_toggle_materializes_launcher_and_persists(self):
        resp = self.client.post(
            "/launcher/apps/vscode/toggle", headers=self.headers, json={"autostart": False}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        by_id = {a["id"]: a for a in data["apps"]}
        self.assertFalse(by_id["vscode"]["autostart"])

        on_disk = self._read_cfg()
        self.assertEqual(on_disk["launcher"]["active_profile"], "default")
        states = self._profile_states()
        self.assertFalse(states["vscode"]["autostart"])
        # Migriertes explizites placement bleibt erhalten.
        self.assertEqual(states["vscode"]["placement"], {"monitor": "left", "zone": "left_half"})
        # Secrets + nicht-editierbare Felder bleiben erhalten.
        self.assertEqual(on_disk["anthropic_api_key"], "sk-ant-test-secret-111")
        self.assertEqual(on_disk["workspace_path"], "C:\\test-workspace")

    def test_toggle_pins_legacy_string_id_without_placement(self):
        # Pitfall-Regression: das Pinnen darf KEIN Default-placement schreiben —
        # weder am apps-Eintrag noch im Profil-State.
        resp = self.client.post(
            "/launcher/apps/obsidian/toggle", headers=self.headers, json={"autostart": False}
        )
        self.assertEqual(resp.status_code, 200)
        entry = self._read_cfg()["apps"][0]
        self.assertIsInstance(entry, dict)
        self.assertEqual(entry["command"], "obsidian://open")
        self.assertEqual(entry["id"], "obsidian")
        self.assertNotIn("placement", entry)
        states = self._profile_states()
        self.assertFalse(states["obsidian"]["autostart"])
        self.assertNotIn("placement", states["obsidian"])

    def test_toggle_live_applies(self):
        self.client.post(
            "/launcher/apps/vscode/toggle", headers=self.headers, json={"autostart": False}
        )
        self.assertFalse(self._effective()["vscode"]["autostart"])

    def test_toggle_back_on(self):
        self.client.post(
            "/launcher/apps/vscode/toggle", headers=self.headers, json={"autostart": False}
        )
        resp = self.client.post(
            "/launcher/apps/vscode/toggle", headers=self.headers, json={"autostart": True}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self._profile_states()["vscode"]["autostart"])

    # ── Fehlerfaelle ────────────────────────────────────────────────────────
    def test_toggle_unknown_id_404(self):
        resp = self.client.post(
            "/launcher/apps/photoshop/toggle", headers=self.headers, json={"autostart": True}
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()["ok"])

    def test_toggle_bad_body_400(self):
        for body in ({}, {"autostart": "ja"}, {"autostart": 1}, ["liste"]):
            resp = self.client.post(
                "/launcher/apps/vscode/toggle", headers=self.headers, json=body
            )
            self.assertEqual(resp.status_code, 400, f"Body {body!r} muss 400 liefern")
        # Datei unveraendert: kein Fehlerfall darf schreiben.
        on_disk = self._read_cfg()
        self.assertEqual(on_disk["apps"][0], "obsidian://open")
        self.assertNotIn("launcher", on_disk)

    def test_toggle_response_contains_no_command(self):
        resp = self.client.post(
            "/launcher/apps/obsidian/toggle", headers=self.headers, json={"autostart": False}
        )
        self.assertNotIn("obsidian://open", resp.text)

    # ── Placement (wirkt auf das abgeleitete/aktive Profil) ────────────────
    def test_placement_persists_to_profile(self):
        resp = self.client.post(
            "/launcher/apps/vscode/placement", headers=self.headers,
            json={"monitor": "rightmost", "zone": "top_half"},
        )
        self.assertEqual(resp.status_code, 200)
        by_id = {a["id"]: a for a in resp.json()["apps"]}
        self.assertEqual(by_id["vscode"]["placement"], {"monitor": "rightmost", "zone": "top_half"})
        states = self._profile_states()
        self.assertEqual(states["vscode"]["placement"], {"monitor": "rightmost", "zone": "top_half"})

    def test_placement_live_applies(self):
        self.client.post(
            "/launcher/apps/vscode/placement", headers=self.headers,
            json={"monitor": "right", "zone": "center"},
        )
        self.assertEqual(self._effective()["vscode"]["placement"],
                         {"monitor": "right", "zone": "center"})

    def test_placement_on_legacy_string(self):
        resp = self.client.post(
            "/launcher/apps/obsidian/placement", headers=self.headers,
            json={"monitor": "left", "zone": "right_half"},
        )
        self.assertEqual(resp.status_code, 200)
        # ID gepinnt, placement lebt im Profil — nicht am apps-Eintrag.
        entry = self._read_cfg()["apps"][0]
        self.assertEqual(entry["id"], "obsidian")
        self.assertNotIn("placement", entry)
        self.assertEqual(self._profile_states()["obsidian"]["placement"],
                         {"monitor": "left", "zone": "right_half"})

    def test_placement_unknown_id_404(self):
        resp = self.client.post(
            "/launcher/apps/photoshop/placement", headers=self.headers,
            json={"monitor": "left", "zone": "center"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_placement_bad_body_400(self):
        bodies = (
            {},                                            # beide fehlen
            {"monitor": "left"},                           # zone fehlt
            {"monitor": "mars", "zone": "fullscreen"},     # ungueltiger monitor
            {"monitor": "left", "zone": "diagonal"},       # ungueltige zone
            {"monitor": "left", "zone": "center", "x": 1}, # unbekanntes Feld
            ["liste"],                                     # kein Objekt
        )
        for body in bodies:
            resp = self.client.post(
                "/launcher/apps/vscode/placement", headers=self.headers, json=body
            )
            self.assertEqual(resp.status_code, 400, f"Body {body!r} muss 400 liefern")
        self.assertNotIn("launcher", self._read_cfg())

    def test_placement_response_contains_no_command(self):
        resp = self.client.post(
            "/launcher/apps/obsidian/placement", headers=self.headers,
            json={"monitor": "left", "zone": "right_half"},
        )
        self.assertNotIn("obsidian://open", resp.text)

    # ── Monitors ────────────────────────────────────────────────────────────
    def test_monitors_requires_token(self):
        self.assertEqual(self.client.get("/launcher/monitors").status_code, 403)

    def test_monitors_shape(self):
        fake = [
            {"id": "left", "label": "Linker Monitor", "x": 0, "y": 0,
             "width": 1920, "height": 1080, "primary": True},
            {"id": "right", "label": "Rechter Monitor", "x": 1920, "y": 0,
             "width": 1920, "height": 1080, "primary": False},
        ]
        with mock.patch.object(server.monitors, "detect_monitors", return_value=fake):
            resp = self.client.get("/launcher/monitors", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["monitors"], fake)

    def test_monitors_detection_failure_returns_empty(self):
        # Leere Liste = Frontend zeigt die virtuelle Standardansicht.
        with mock.patch.object(server.monitors, "detect_monitors", return_value=[]):
            resp = self.client.get("/launcher/monitors", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True, "monitors": []})


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class ProfileApiTests(_ApiTestBase):
    """Profil-Pfad: launcher-Block vorhanden (coding aktiv, writing daneben)."""

    _CONFIG = _PROFILED_CONFIG

    def test_profiles_require_token(self):
        self.assertEqual(self.client.get("/launcher/profiles").status_code, 403)
        self.assertEqual(
            self.client.post("/launcher/profiles", json={"name": "X"}).status_code, 403)
        self.assertEqual(
            self.client.post("/launcher/profiles/writing/activate").status_code, 403)
        self.assertEqual(self.client.delete("/launcher/profiles/writing").status_code, 403)

    def test_get_profiles_shape(self):
        resp = self.client.get("/launcher/profiles", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["active_profile"], "coding")
        self.assertEqual([p["id"] for p in data["profiles"]], ["coding", "writing"])
        for profile in data["profiles"]:
            self.assertEqual(set(profile), {"id", "name", "apps"})
        self.assertEqual(len(data["apps"]), 2)
        self.assertNotIn("obsidian://open", resp.text)  # kein command-Leak

    # ── Aktivieren ──────────────────────────────────────────────────────────
    def test_activate_persists_and_switches_effective_state(self):
        resp = self.client.post("/launcher/profiles/writing/activate", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["active_profile"], "writing")
        self.assertEqual(self._read_cfg()["launcher"]["active_profile"], "writing")
        # Effective Apps folgen dem Profil: vscode ist in writing deaktiviert.
        self.assertFalse(self._effective()["vscode"]["autostart"])

    def test_activate_unknown_404(self):
        resp = self.client.post("/launcher/profiles/nope/activate", headers=self.headers)
        self.assertEqual(resp.status_code, 404)

    # ── Profil-Isolation: Toggle/Placement treffen nur das aktive Profil ───
    def test_toggle_isolated_per_profile(self):
        self.client.post(
            "/launcher/apps/obsidian/toggle", headers=self.headers, json={"autostart": False}
        )
        self.assertFalse(self._profile_states("coding")["obsidian"]["autostart"])
        self.assertNotIn("obsidian", self._profile_states("writing"))
        # Wechsel nach writing: obsidian dort weiterhin aktiv (Default true).
        self.client.post("/launcher/profiles/writing/activate", headers=self.headers)
        self.assertTrue(self._effective()["obsidian"]["autostart"])
        # Zurueck nach coding: Toggle-Zustand blieb erhalten.
        self.client.post("/launcher/profiles/coding/activate", headers=self.headers)
        self.assertFalse(self._effective()["obsidian"]["autostart"])

    def test_placement_isolated_per_profile(self):
        self.client.post(
            "/launcher/apps/obsidian/placement", headers=self.headers,
            json={"monitor": "right", "zone": "top_half"},
        )
        self.assertEqual(self._profile_states("coding")["obsidian"]["placement"],
                         {"monitor": "right", "zone": "top_half"})
        self.assertNotIn("obsidian", self._profile_states("writing"))

    # ── Anlegen / Duplizieren / Umbenennen / Loeschen ───────────────────────
    def test_create_profile_defaults_not_activated(self):
        resp = self.client.post("/launcher/profiles", headers=self.headers,
                                json={"name": "Research"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["active_profile"], "coding")  # anlegen != wechseln
        research = next(p for p in data["profiles"] if p["id"] == "research")
        self.assertEqual(research["apps"],
                         {"obsidian": {"autostart": True}, "vscode": {"autostart": True}})
        self.assertIn("research", [p["id"] for p in self._read_cfg()["launcher"]["profiles"]])

    def test_create_profile_bad_requests(self):
        resp = self.client.post("/launcher/profiles", headers=self.headers, json={})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/launcher/profiles", headers=self.headers,
                                json={"name": "Coding 2", "id": "coding"})
        self.assertEqual(resp.status_code, 400)  # ID-Kollision

    def test_duplicate_copies_states(self):
        resp = self.client.post("/launcher/profiles/coding/duplicate", headers=self.headers,
                                json={"name": "Coding Copy"})
        self.assertEqual(resp.status_code, 200)
        copy = next(p for p in resp.json()["profiles"] if p["id"] == "coding-copy")
        self.assertEqual(copy["apps"]["vscode"]["placement"],
                         {"monitor": "left", "zone": "left_half"})
        resp = self.client.post("/launcher/profiles/nope/duplicate", headers=self.headers,
                                json={"name": "X"})
        self.assertEqual(resp.status_code, 404)

    def test_rename_profile(self):
        resp = self.client.post("/launcher/profiles/writing/rename", headers=self.headers,
                                json={"name": "Deep Writing"})
        self.assertEqual(resp.status_code, 200)
        launcher = self._read_cfg()["launcher"]
        writing = next(p for p in launcher["profiles"] if p["id"] == "writing")
        self.assertEqual(writing["name"], "Deep Writing")
        resp = self.client.post("/launcher/profiles/nope/rename", headers=self.headers,
                                json={"name": "X"})
        self.assertEqual(resp.status_code, 404)

    def test_delete_profile_and_guards(self):
        # Aktives Profil ist geschuetzt.
        resp = self.client.delete("/launcher/profiles/coding", headers=self.headers)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("aktive", resp.json()["errors"][0])
        # Nicht-aktives Profil loeschen klappt.
        resp = self.client.delete("/launcher/profiles/writing", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([p["id"] for p in self._read_cfg()["launcher"]["profiles"]],
                         ["coding"])
        # Letztes Profil ist geschuetzt.
        resp = self.client.delete("/launcher/profiles/coding", headers=self.headers)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("letzte", resp.json()["errors"][0])

    def test_delete_unknown_404(self):
        resp = self.client.delete("/launcher/profiles/nope", headers=self.headers)
        self.assertEqual(resp.status_code, 404)

    # ── Sprachsteuerung (Phase 5): echter Persist-Pfad ──────────────────────
    def test_voice_autostart_persists_to_disk(self):
        result = asyncio.run(assistant_core.execute_action(
            actions.Action("APP_AUTOSTART_OFF", "VS Code"), wt.turn_context(),
            mutate_launcher=server._launcher_hook(self.runtime)))
        self.assertEqual(result, "VS Code ist aus dem Clap-Start raus.")
        self.assertFalse(self._profile_states("coding")["vscode"]["autostart"])
        # Live-Apply: effective Apps spiegeln die Sprachaenderung sofort.
        self.assertFalse(self._effective()["vscode"]["autostart"])

    def test_voice_place_persists_to_disk(self):
        result = asyncio.run(assistant_core.execute_action(
            actions.Action("APP_PLACE", "Obsidian | rechts | Vollbild"), wt.turn_context(),
            mutate_launcher=server._launcher_hook(self.runtime)))
        self.assertEqual(result, "Obsidian liegt jetzt im Vollbild auf dem rechten Monitor.")
        self.assertEqual(self._profile_states("coding")["obsidian"]["placement"],
                         {"monitor": "right", "zone": "fullscreen"})

    def test_voice_profile_activate_persists(self):
        result = asyncio.run(assistant_core.execute_action(
            actions.Action("PROFILE_ACTIVATE", "Writing"), wt.turn_context(),
            mutate_launcher=server._launcher_hook(self.runtime)))
        self.assertEqual(result, "Writing ist jetzt aktiv.")
        self.assertEqual(self._read_cfg()["launcher"]["active_profile"], "writing")

    def test_toggle_broadcasts_launcher_changed(self):
        # Der Broadcast-Pfad ist derselbe fuer API- und Sprach-Aenderungen.
        with self.client.websocket_connect(
            f"/ws?token={server.SESSION_TOKEN}", headers={"origin": "http://127.0.0.1:8340"}
        ) as websocket:
            self.assertEqual(websocket.receive_json()["type"], "health")
            resp = self.client.post(
                "/launcher/apps/vscode/toggle", headers=self.headers,
                json={"autostart": False},
            )
            self.assertEqual(resp.status_code, 200)
            event = None
            for _ in range(5):  # apply_settings broadcastet vorher noch health
                frame = websocket.receive_json()
                if frame["type"] == "launcher_changed":
                    event = frame
                    break
            self.assertIsNotNone(event)
            self.assertEqual(event["kind"], "autostart")
            self.assertEqual(event["active_profile"], "coding")

    # ── Settings-Textarea darf Apps entfernen, ohne dass Profile blocken ───
    def test_settings_apps_edit_with_stale_profile_refs_ok(self):
        resp = self.client.post(
            "/settings", headers=self.headers,
            json={"apps": [{"id": "obsidian", "name": "Obsidian",
                            "command": "obsidian://open", "type": "url"}]},
        )
        self.assertEqual(resp.status_code, 200)
        # Stale vscode-Referenzen in den Profilen werden toleriert (Prune bei
        # der Normalisierung) — effective Apps kennen nur noch obsidian.
        self.assertEqual(set(self._effective()), {"obsidian"})


if __name__ == "__main__":
    unittest.main()

"""
Tests fuer app_launcher.py: Normalisierung (Legacy-Strings + Objekte),
App-Suche (case-insensitiv) und den Allowlist-Launch.

WICHTIG: ``_start_url``/``_start_process`` werden IMMER gepatcht — die Tests
starten niemals echte Programme oder URL-Handler.

    python -m unittest discover -s tests
"""
import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests  # noqa: F401  waehlt synthetische Test-Config (tests/__init__.py) vor 'import server'

import app_launcher

try:
    import server  # verdrahtet assistant_core (configure/init_clients)
    import assistant_core
    import actions
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    assistant_core = None
    actions = None
    _IMPORT_ERROR = e

_APPS = [
    {"id": "obsidian", "name": "Obsidian", "command": "obsidian://open", "type": "url"},
    {"id": "vscode", "name": "VS Code", "command": "code", "type": "process"},
]


class _RegistryMixin:
    """Registry + Profile pro Test setzen und garantiert wiederherstellen."""

    def _use_apps(self, raw, launcher=None):
        self._saved_apps = app_launcher.APPS
        self._saved_profiles = app_launcher.PROFILES
        self._saved_active = app_launcher.ACTIVE_PROFILE
        self.addCleanup(lambda: setattr(app_launcher, "APPS", self._saved_apps))
        self.addCleanup(lambda: setattr(app_launcher, "PROFILES", self._saved_profiles))
        self.addCleanup(lambda: setattr(app_launcher, "ACTIVE_PROFILE", self._saved_active))
        app_launcher.configure(raw, launcher)


class NormalizeTests(unittest.TestCase):
    def test_legacy_url_string(self):
        app = app_launcher.normalize_app_entry("obsidian://open")
        self.assertEqual(app["type"], "url")
        self.assertEqual(app["id"], "obsidian")
        self.assertEqual(app["command"], "obsidian://open")
        self.assertTrue(app["autostart"])  # Legacy = Autostart (bisheriges Verhalten)

    def test_legacy_process_string(self):
        app = app_launcher.normalize_app_entry("C:\\Tools\\Notepad++.exe")
        self.assertEqual(app["type"], "process")
        self.assertEqual(app["command"], "C:\\Tools\\Notepad++.exe")
        self.assertTrue(app["autostart"])

    def test_dict_minimal_command_only(self):
        app = app_launcher.normalize_app_entry({"command": "code"})
        self.assertEqual(app["type"], "process")
        self.assertTrue(app["id"])
        self.assertTrue(app["name"])
        self.assertTrue(app["autostart"])

    def test_dict_full_passthrough(self):
        app = app_launcher.normalize_app_entry({
            "id": "vscode", "name": "VS Code", "command": "code",
            "type": "process", "autostart": False,
        })
        self.assertEqual(app["id"], "vscode")
        self.assertEqual(app["name"], "VS Code")
        self.assertFalse(app["autostart"])

    def test_dict_type_inferred_from_command(self):
        self.assertEqual(app_launcher.normalize_app_entry({"command": "slack://open"})["type"], "url")

    def test_invalid_entries_skipped(self):
        self.assertIsNone(app_launcher.normalize_app_entry(""))
        self.assertIsNone(app_launcher.normalize_app_entry({"name": "ohne Befehl"}))
        self.assertIsNone(app_launcher.normalize_app_entry(42))
        self.assertIsNone(app_launcher.normalize_app_entry({"command": "x", "type": "shell"}))

    def test_normalize_apps_filters_and_keeps_valid(self):
        apps = app_launcher.normalize_apps(["obsidian://open", "", {"command": "code"}, 7])
        self.assertEqual(len(apps), 2)

    # ── placement + process_name ────────────────────────────────────────────
    def test_string_entry_gets_default_placement(self):
        app = app_launcher.normalize_app_entry("obsidian://open")
        self.assertEqual(app["placement"], {"monitor": "primary", "zone": "fullscreen"})

    def test_dict_without_placement_gets_default(self):
        app = app_launcher.normalize_app_entry({"command": "code"})
        self.assertEqual(app["placement"], {"monitor": "primary", "zone": "fullscreen"})

    def test_explicit_placement_passthrough(self):
        app = app_launcher.normalize_app_entry(
            {"command": "code", "placement": {"monitor": "left", "zone": "left_half"}}
        )
        self.assertEqual(app["placement"], {"monitor": "left", "zone": "left_half"})

    def test_partial_placement_filled(self):
        app = app_launcher.normalize_app_entry(
            {"command": "code", "placement": {"zone": "center"}}
        )
        self.assertEqual(app["placement"], {"monitor": "primary", "zone": "center"})

    def test_garbage_placement_falls_back_to_default(self):
        # Kein Absturz, kein Drop des Eintrags — nur Default + Warnung.
        for bad in ("links", 5, {"monitor": "mars"}, {"zone": 7}):
            app = app_launcher.normalize_app_entry({"command": "code", "placement": bad})
            self.assertIsNotNone(app, repr(bad))
            self.assertEqual(app["placement"], {"monitor": "primary", "zone": "fullscreen"}, repr(bad))

    def test_process_name_passthrough_and_absent(self):
        app = app_launcher.normalize_app_entry(
            {"command": "https://calendar.google.com", "process_name": "chrome"}
        )
        self.assertEqual(app["process_name"], "chrome")
        self.assertNotIn("process_name", app_launcher.normalize_app_entry({"command": "code"}))


class FindAppTests(_RegistryMixin, unittest.TestCase):
    def setUp(self):
        self._use_apps(_APPS)

    def test_find_by_id_case_insensitive(self):
        self.assertEqual(app_launcher.find_app("OBSIDIAN")["id"], "obsidian")

    def test_find_by_name_case_insensitive(self):
        self.assertEqual(app_launcher.find_app("vs code")["id"], "vscode")

    def test_whitespace_stripped(self):
        self.assertEqual(app_launcher.find_app("  Obsidian  ")["id"], "obsidian")

    def test_unknown_returns_none(self):
        self.assertIsNone(app_launcher.find_app("photoshop"))
        self.assertIsNone(app_launcher.find_app(""))


class LaunchTests(_RegistryMixin, unittest.TestCase):
    def setUp(self):
        self._use_apps(_APPS)

    def test_launch_url_uses_start_url(self):
        with mock.patch.object(app_launcher, "_start_url") as start_url, \
             mock.patch.object(app_launcher, "_start_process") as start_process:
            result = app_launcher.launch("Obsidian")
        start_url.assert_called_once_with("obsidian://open")
        start_process.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertEqual(result["app"], "obsidian")

    def test_launch_process_uses_start_process(self):
        with mock.patch.object(app_launcher, "_start_url") as start_url, \
             mock.patch.object(app_launcher, "_start_process") as start_process:
            result = app_launcher.launch("vs code")
        start_process.assert_called_once_with("code")
        start_url.assert_not_called()
        self.assertTrue(result["ok"])

    def test_unknown_app_lists_available(self):
        with mock.patch.object(app_launcher, "_start_url"), \
             mock.patch.object(app_launcher, "_start_process"):
            result = app_launcher.launch("photoshop")
        self.assertFalse(result["ok"])
        self.assertIsNone(result["app"])
        self.assertIn("Obsidian", result["message"])
        self.assertIn("VS Code", result["message"])

    def test_empty_registry_message(self):
        app_launcher.configure([])
        result = app_launcher.launch("obsidian")
        self.assertFalse(result["ok"])
        self.assertIn("keine Apps konfiguriert", result["message"])

    def test_start_failure_returns_ok_false(self):
        with mock.patch.object(app_launcher, "_start_url", side_effect=OSError("kaputt")):
            result = app_launcher.launch("obsidian")
        self.assertFalse(result["ok"])
        self.assertEqual(result["app"], "obsidian")
        self.assertIn("OSError", result["message"])

    def test_result_shape_keys(self):
        with mock.patch.object(app_launcher, "_start_url"):
            result = app_launcher.launch("obsidian")
        self.assertEqual(set(result), {"ok", "app", "name", "message"})


class ResolveCommandTests(unittest.TestCase):
    """Der VS-Code-Resolver: ``code`` -> ``Code.exe``, alles andere unveraendert.
    Kein echter Programmstart — nur Pfad-Aufloesung (Popen/isfile/which gemockt)."""

    # ── _resolve_vscode: Shim-Ableitung, well-known-Fallback, None ─────────────
    def test_resolve_vscode_derives_exe_from_shim(self):
        shim = os.path.join("C:\\VSC", "bin", "code.cmd")
        exe = os.path.join("C:\\VSC", "Code.exe")
        with mock.patch.object(app_launcher.shutil, "which", return_value=shim), \
             mock.patch("os.path.isfile", side_effect=lambda p: p == exe):
            self.assertEqual(app_launcher._resolve_vscode(), exe)

    def test_resolve_vscode_falls_back_to_well_known(self):
        # Shim vorhanden, aber Code.exe daneben fehlt -> well-known greift.
        fake = os.path.join("C:\\Program Files", "Microsoft VS Code", "Code.exe")
        with mock.patch.object(app_launcher.shutil, "which", return_value=None), \
             mock.patch.object(app_launcher, "_VSCODE_WELL_KNOWN", (r"%NICHT_GESETZT%\a", fake)), \
             mock.patch("os.path.isfile", side_effect=lambda p: p == fake):
            # Der %VAR%-Eintrag bleibt unexpandiert (enthaelt '%') und wird uebersprungen.
            self.assertEqual(app_launcher._resolve_vscode(), fake)

    def test_resolve_vscode_none_when_absent(self):
        with mock.patch.object(app_launcher.shutil, "which", return_value=None), \
             mock.patch.object(app_launcher, "_VSCODE_WELL_KNOWN", ()), \
             mock.patch("os.path.isfile", return_value=False):
            self.assertIsNone(app_launcher._resolve_vscode())

    # ── _resolve_command: nur das Token 'code' wird gemappt ───────────────────
    def test_resolve_command_maps_code_case_and_whitespace(self):
        with mock.patch.object(app_launcher, "_resolve_vscode", return_value="X\\Code.exe"):
            self.assertEqual(app_launcher._resolve_command("code"), "X\\Code.exe")
            self.assertEqual(app_launcher._resolve_command("  CODE  "), "X\\Code.exe")

    def test_resolve_command_leaves_others_untouched_no_injection(self):
        # Absolute Pfade, URLs UND Injektionsversuche bleiben woertlich — nur das
        # exakte Token 'code' wird aufgeloest, sonst nichts.
        with mock.patch.object(app_launcher, "_resolve_vscode",
                               return_value="X\\Code.exe") as resolve:
            for cmd in ("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                        "obsidian://open",
                        "code; rm -rf /",
                        "notepad code",
                        "code.exe"):
                self.assertEqual(app_launcher._resolve_command(cmd), cmd, repr(cmd))
            resolve.assert_not_called()

    def test_resolve_command_code_unresolved_returns_token(self):
        # Kein VS Code installiert -> 'code' bleibt 'code' (Popen liefert dann den
        # freundlichen FileNotFoundError-Pfad in launch()).
        with mock.patch.object(app_launcher, "_resolve_vscode", return_value=None):
            self.assertEqual(app_launcher._resolve_command("code"), "code")

    # ── _start_process: Liste, keine Shell, Auflösung wirkt ───────────────────
    def test_start_process_resolves_code_and_uses_list_no_shell(self):
        with mock.patch.object(app_launcher, "_resolve_vscode", return_value="X\\Code.exe"), \
             mock.patch.object(app_launcher.subprocess, "Popen") as popen:
            app_launcher._start_process("code")
        args, kwargs = popen.call_args
        self.assertEqual(args[0], ["X\\Code.exe"])     # aufgeloest + als Liste
        self.assertNotEqual(kwargs.get("shell"), True)  # niemals shell=True

    def test_start_process_passes_other_command_unchanged(self):
        with mock.patch.object(app_launcher.subprocess, "Popen") as popen:
            app_launcher._start_process("C:\\Tools\\Notepad++.exe")
        self.assertEqual(popen.call_args.args[0], ["C:\\Tools\\Notepad++.exe"])


class NormalizeLauncherTests(unittest.TestCase):
    def test_missing_launcher_derives_default_profile(self):
        raw = [
            {"id": "vscode", "command": "code", "autostart": False,
             "placement": {"monitor": "left", "zone": "left_half"}},
            "obsidian://open",
        ]
        launcher = app_launcher.normalize_launcher(raw, None)
        self.assertEqual(launcher["active_profile"], "default")
        self.assertEqual(len(launcher["profiles"]), 1)
        states = launcher["profiles"][0]["apps"]
        self.assertFalse(states["vscode"]["autostart"])
        self.assertEqual(states["vscode"]["placement"], {"monitor": "left", "zone": "left_half"})
        # Pitfall-Erbe: kein explizites placement am Eintrag -> keins im Profil.
        self.assertTrue(states["obsidian"]["autostart"])
        self.assertNotIn("placement", states["obsidian"])

    def test_unknown_active_profile_falls_back_to_first(self):
        launcher = app_launcher.normalize_launcher([], {
            "active_profile": "nope",
            "profiles": [{"id": "coding", "name": "Coding", "apps": {}}],
        })
        self.assertEqual(launcher["active_profile"], "coding")

    def test_unknown_profile_app_keys_pruned(self):
        launcher = app_launcher.normalize_launcher(
            [{"id": "vscode", "command": "code"}],
            {"active_profile": "a", "profiles": [
                {"id": "a", "name": "A",
                 "apps": {"vscode": {"autostart": False}, "geist": {"autostart": True}}},
            ]},
        )
        self.assertEqual(set(launcher["profiles"][0]["apps"]), {"vscode"})

    def test_missing_name_defaults_from_id(self):
        launcher = app_launcher.normalize_launcher([], {
            "active_profile": "focus", "profiles": [{"id": "focus", "apps": {}}],
        })
        self.assertEqual(launcher["profiles"][0]["name"], "Focus")

    def test_empty_profiles_derives_default(self):
        launcher = app_launcher.normalize_launcher(["obsidian://open"],
                                                   {"active_profile": "x", "profiles": []})
        self.assertEqual(launcher["active_profile"], "default")


class EffectiveAppsTests(_RegistryMixin, unittest.TestCase):
    _LAUNCHER = {"active_profile": "coding", "profiles": [
        {"id": "coding", "name": "Coding", "apps": {
            "vscode": {"autostart": True,
                       "placement": {"monitor": "left", "zone": "left_half"}}}},
        {"id": "writing", "name": "Writing", "apps": {"vscode": {"autostart": False}}},
    ]}

    def test_effective_shape_and_profile_state(self):
        self._use_apps(_APPS, self._LAUNCHER)
        by_id = {a["id"]: a for a in app_launcher.list_apps()}
        self.assertEqual(set(by_id["vscode"]),
                         {"id", "name", "type", "autostart", "placement"})
        self.assertEqual(by_id["vscode"]["placement"], {"monitor": "left", "zone": "left_half"})
        # App ohne Profil-Eintrag: autostart true + Anzeige-Default.
        self.assertTrue(by_id["obsidian"]["autostart"])
        self.assertEqual(by_id["obsidian"]["placement"],
                         {"monitor": "primary", "zone": "fullscreen"})

    def test_effective_apps_other_profile(self):
        self._use_apps(_APPS, self._LAUNCHER)
        by_id = {a["id"]: a for a in app_launcher.effective_apps("writing")}
        self.assertFalse(by_id["vscode"]["autostart"])
        # Aktives Profil bleibt unveraendert.
        self.assertEqual(app_launcher.ACTIVE_PROFILE, "coding")


class PinAppIdsTests(unittest.TestCase):
    def test_legacy_string_pinned_without_placement(self):
        # Pitfall-Erbe: Pinnen darf das Default-placement nicht materialisieren.
        entry = app_launcher.pin_app_ids(["obsidian://open"])[0]
        self.assertEqual(entry["id"], "obsidian")
        self.assertEqual(entry["command"], "obsidian://open")
        self.assertNotIn("placement", entry)
        self.assertNotIn("process_name", entry)

    def test_dict_without_id_gets_id_other_fields_preserved(self):
        raw = [{"name": "VS Code", "command": "code", "process_name": "Code"}]
        result = app_launcher.pin_app_ids(raw)
        self.assertEqual(result[0]["id"], "vs-code")
        self.assertEqual(result[0]["process_name"], "Code")
        self.assertNotIn("id", raw[0])  # Eingabe unmutiert

    def test_existing_id_untouched(self):
        raw = [{"id": "vscode", "command": "code"}]
        self.assertIs(app_launcher.pin_app_ids(raw)[0], raw[0])

    def test_unusable_entry_kept_as_is(self):
        self.assertEqual(app_launcher.pin_app_ids([42, ""]), [42, ""])


class LauncherMutationTests(_RegistryMixin, unittest.TestCase):
    def setUp(self):
        self._use_apps(_APPS, {"active_profile": "coding", "profiles": [
            {"id": "coding", "name": "Coding", "apps": {"vscode": {"autostart": True}}},
            {"id": "writing", "name": "Writing", "apps": {}},
        ]})

    @staticmethod
    def _profile(launcher, pid):
        return next(p for p in launcher["profiles"] if p["id"] == pid)

    def test_app_state_toggle_hits_active_profile_only(self):
        launcher = app_launcher.launcher_with_app_state("vscode", autostart=False)
        self.assertFalse(self._profile(launcher, "coding")["apps"]["vscode"]["autostart"])
        self.assertNotIn("vscode", self._profile(launcher, "writing")["apps"])

    def test_app_state_placement_sets_default_autostart(self):
        launcher = app_launcher.launcher_with_app_state(
            "obsidian", placement={"monitor": "left", "zone": "right_half"})
        state = self._profile(launcher, "coding")["apps"]["obsidian"]
        self.assertEqual(state["placement"], {"monitor": "left", "zone": "right_half"})
        self.assertTrue(state["autostart"])

    def test_app_state_unknown_app_returns_none(self):
        self.assertIsNone(app_launcher.launcher_with_app_state("photoshop", autostart=True))

    def test_module_state_not_mutated(self):
        app_launcher.launcher_with_app_state("vscode", autostart=False)
        self.assertTrue(app_launcher.PROFILES[0]["apps"]["vscode"]["autostart"])

    def test_new_profile_defaults_and_not_activated(self):
        launcher = app_launcher.launcher_with_new_profile("research", "Research")
        profile = self._profile(launcher, "research")
        self.assertEqual(profile["apps"],
                         {"obsidian": {"autostart": True}, "vscode": {"autostart": True}})
        self.assertEqual(launcher["active_profile"], "coding")

    def test_new_profile_id_slugged_from_name(self):
        launcher = app_launcher.launcher_with_new_profile(None, "Deep Work")
        self.assertTrue(any(p["id"] == "deep-work" for p in launcher["profiles"]))

    def test_new_profile_collision_returns_none(self):
        self.assertIsNone(app_launcher.launcher_with_new_profile("coding", "Coding 2"))
        self.assertIsNone(app_launcher.launcher_with_new_profile("x", ""))

    def test_duplicate_copies_states(self):
        launcher = app_launcher.launcher_with_new_profile("coding-2", "Coding 2",
                                                          copy_from="coding")
        self.assertEqual(self._profile(launcher, "coding-2")["apps"],
                         {"vscode": {"autostart": True}})
        self.assertIsNone(app_launcher.launcher_with_new_profile("x", "X", copy_from="nope"))

    def test_rename(self):
        launcher = app_launcher.launcher_with_renamed("writing", "Deep Writing")
        self.assertEqual(self._profile(launcher, "writing")["name"], "Deep Writing")
        self.assertIsNone(app_launcher.launcher_with_renamed("nope", "X"))
        self.assertIsNone(app_launcher.launcher_with_renamed("writing", "  "))

    def test_activate(self):
        self.assertEqual(app_launcher.launcher_with_active("writing")["active_profile"],
                         "writing")
        self.assertIsNone(app_launcher.launcher_with_active("nope"))

    def test_delete_and_guards(self):
        launcher, err = app_launcher.launcher_without_profile("writing")
        self.assertIsNone(err)
        self.assertEqual([p["id"] for p in launcher["profiles"]], ["coding"])
        # Aktives Profil ist geschuetzt.
        launcher, err = app_launcher.launcher_without_profile("coding")
        self.assertIsNone(launcher)
        self.assertIn("aktive", err)
        # Unbekanntes Profil: (None, None) -> 404 im Server.
        launcher, err = app_launcher.launcher_without_profile("nope")
        self.assertIsNone(launcher)
        self.assertIsNone(err)

    def test_delete_last_profile_guard(self):
        self._use_apps(_APPS, {"active_profile": "solo",
                               "profiles": [{"id": "solo", "name": "Solo", "apps": {}}]})
        launcher, err = app_launcher.launcher_without_profile("solo")
        self.assertIsNone(launcher)
        self.assertIn("letzte", err)


class ListAppsTests(_RegistryMixin, unittest.TestCase):
    def test_list_apps_exposes_no_command(self):
        self._use_apps(_APPS)
        for app in app_launcher.list_apps():
            self.assertNotIn("command", app)
            self.assertNotIn("process_name", app)
            self.assertEqual(set(app), {"id", "name", "type", "autostart", "placement"})
            self.assertEqual(set(app["placement"]), {"monitor", "zone"})

    def test_list_apps_placement_is_copy(self):
        # Mutation der Rueckgabe darf den Registry-Zustand nicht veraendern.
        self._use_apps(_APPS)
        app_launcher.list_apps()[0]["placement"]["zone"] = "center"
        self.assertEqual(app_launcher.APPS[0]["placement"]["zone"], "fullscreen")


class ExecuteActionAppOpenTests(_RegistryMixin, unittest.TestCase):
    """APP_OPEN ueber die oeffentliche Action-Seam (RFC-0001)."""

    def test_app_open_returns_launcher_message(self):
        self._use_apps(_APPS)
        with mock.patch.object(app_launcher, "_start_url") as start_url:
            result = asyncio.run(actions.spec_for("APP_OPEN").execute(
                "Obsidian", actions.ActionContext()))
        start_url.assert_called_once_with("obsidian://open")
        self.assertEqual(result, "Obsidian wird geöffnet.")


if __name__ == "__main__":
    unittest.main()

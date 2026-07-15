"""
Tests fuer scripts/clap-trigger.py — der workspace_path-Fallback in
``resolve_script_path``. Kein echtes Mikrofon/Audio noetig: die sounddevice-/
numpy-Imports liegen in main(), der Modul-Import bleibt leichtgewichtig.

    python -m unittest discover -s tests
"""
import importlib.util
import json
import os
import tempfile
import unittest

_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "clap-trigger.py",
)


def _load_clap_module():
    # Bindestrich im Dateinamen -> normales import geht nicht, per Pfad laden.
    spec = importlib.util.spec_from_file_location("clap_trigger", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


clap = _load_clap_module()

_REPO_ROOT = r"C:\repo-root"
_EXPECTED_TAIL = os.path.join("scripts", "launch-session.ps1")


class ResolveScriptPathTests(unittest.TestCase):
    def _write(self, data) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_uses_workspace_path_when_present(self):
        cfg = self._write({"workspace_path": r"C:\jarvis-workspace"})
        result = clap.resolve_script_path(config_path=cfg, repo_root=_REPO_ROOT)
        self.assertEqual(
            result, os.path.join(r"C:\jarvis-workspace", "scripts", "launch-session.ps1")
        )

    def test_falls_back_to_repo_root_when_key_missing(self):
        # config_loader.REQUIRED_KEYS verlangt kein workspace_path -> darf fehlen.
        cfg = self._write({"anthropic_api_key": "x", "elevenlabs_api_key": "y"})
        result = clap.resolve_script_path(config_path=cfg, repo_root=_REPO_ROOT)
        self.assertEqual(result, os.path.join(_REPO_ROOT, _EXPECTED_TAIL))

    def test_falls_back_when_workspace_path_empty(self):
        cfg = self._write({"workspace_path": ""})
        result = clap.resolve_script_path(config_path=cfg, repo_root=_REPO_ROOT)
        self.assertEqual(result, os.path.join(_REPO_ROOT, _EXPECTED_TAIL))

    def test_falls_back_when_config_missing(self):
        missing = os.path.join(tempfile.gettempdir(), "jarvis_nope_clap_config.json")
        result = clap.resolve_script_path(config_path=missing, repo_root=_REPO_ROOT)
        self.assertEqual(result, os.path.join(_REPO_ROOT, _EXPECTED_TAIL))

    def test_falls_back_on_invalid_json(self):
        cfg = self._write("{ das ist kein gueltiges json ")
        result = clap.resolve_script_path(config_path=cfg, repo_root=_REPO_ROOT)
        self.assertEqual(result, os.path.join(_REPO_ROOT, _EXPECTED_TAIL))


if __name__ == "__main__":
    unittest.main()

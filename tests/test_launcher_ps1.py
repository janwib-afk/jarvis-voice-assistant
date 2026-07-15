"""
Statischer Guard fuer den VS-Code-Start in scripts/launch-session.ps1.

Es gibt keine PowerShell-Testsuite; wie ``PowerShellMusicTests`` in
test_music_api.py pruefen wir die VS-Code-Logik auf Textebene: der Resolver ist
definiert, prueft die typischen Windows-Pfade, uebergibt den Workspace und
ueberspringt fehlendes VS Code mit einer Warnung statt die Startsequenz zu werfen.

    python -m unittest discover -s tests
"""
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LAUNCH_PS1 = os.path.join(_ROOT, "scripts", "launch-session.ps1")


class PowerShellVSCodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_LAUNCH_PS1, "r", encoding="utf-8") as f:
            cls.ps1 = f.read()

    def test_resolver_defined_before_functions_only_guard(self):
        # Muss VOR `if ($FunctionsOnly) { return }` stehen, damit -FunctionsOnly
        # (Dry-Run) die Funktion laedt.
        self.assertIn("function Resolve-VSCodeCommand", self.ps1)
        self.assertLess(
            self.ps1.index("function Resolve-VSCodeCommand"),
            self.ps1.index("if ($FunctionsOnly) { return }"),
        )

    def test_resolver_checks_well_known_install_paths(self):
        # Fallback deckt User- und System-Installationen (32/64-Bit) ab.
        self.assertIn("$env:LOCALAPPDATA", self.ps1)
        self.assertIn("$env:ProgramFiles", self.ps1)
        self.assertIn("${env:ProgramFiles(x86)}", self.ps1)
        self.assertIn("Microsoft VS Code\\Code.exe", self.ps1)

    def test_resolver_derives_exe_from_code_shim(self):
        # 'code' im PATH ist der .cmd-Shim; Code.exe liegt eine Ebene darueber.
        self.assertIn("Get-Command code", self.ps1)
        self.assertIn('"Code.exe"', self.ps1)

    def test_start_passes_workspace_to_vscode(self):
        # Schritt 3 loest ueber den Resolver auf und uebergibt $WORKSPACE_PATH.
        self.assertIn("$vscodeCmd = Resolve-VSCodeCommand", self.ps1)
        self.assertIn('Start-Process -FilePath $vscodeCmd -ArgumentList', self.ps1)
        self.assertIn('& $vscodeCmd $WORKSPACE_PATH', self.ps1)

    def test_missing_vscode_logged_and_skipped_not_thrown(self):
        # Fehlt VS Code, wird geloggt und uebersprungen — kein throw/Abbruch.
        self.assertIn("VS Code nicht gefunden", self.ps1)
        self.assertNotIn("throw", self.ps1)


if __name__ == "__main__":
    unittest.main()

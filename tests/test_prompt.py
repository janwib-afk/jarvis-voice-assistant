"""
Tests fuer build_system_prompt(): Persona kommt aus der Config, nicht aus
hartcodierten Literalen (Regression fuer den frueheren "Jan"/"Sir"-Hardcode).

    python -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import server
    _IMPORT_ERROR = None
except BaseException as e:  # auch SystemExit (ConfigError -> sys.exit) abfangen
    server = None
    _IMPORT_ERROR = e


@unittest.skipIf(server is None, f"server import nicht moeglich: {_IMPORT_ERROR!r}")
class SystemPromptTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            name: getattr(server, name)
            for name in ("USER_NAME", "USER_ADDRESS", "USER_ROLE")
        }

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(server, name, value)

    def test_persona_uses_config_values(self):
        server.USER_NAME = "Unit-Tester"
        server.USER_ADDRESS = "Mylady"
        server.USER_ROLE = "Qualitätssicherung"
        prompt = server.build_system_prompt()
        self.assertIn("der persoenliche KI-Assistent von Unit-Tester, Qualitätssicherung.", prompt)
        self.assertIn('mit "Mylady" angesprochen', prompt)
        self.assertIn('WENN Unit-Tester "Jarvis activate" sagt', prompt)

    def test_no_hardcoded_persona_remains(self):
        server.USER_NAME = "Unit-Tester"
        server.USER_ADDRESS = "Mylady"
        server.USER_ROLE = ""
        prompt = server.build_system_prompt()
        self.assertNotIn("Dienstherr ist Jan", prompt)
        self.assertNotIn('"Sir"', prompt)
        self.assertNotIn("Softwareentwickler", prompt)

    def test_empty_role_renders_cleanly(self):
        server.USER_NAME = "Unit-Tester"
        server.USER_ROLE = ""
        prompt = server.build_system_prompt()
        self.assertIn("der persoenliche KI-Assistent von Unit-Tester.", prompt)


if __name__ == "__main__":
    unittest.main()

"""
Tests fuer clipboard_tools.py — subprocess wird gemockt, kein echter
Zwischenablage-Zugriff.

    python -m unittest discover -s tests
"""
import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import clipboard_tools


def _completed(stdout: bytes = b"", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=b"")


class GetClipboardTextTests(unittest.TestCase):
    def test_returns_trimmed_text(self):
        with mock.patch("clipboard_tools.subprocess.run", return_value=_completed(b"Hallo Welt\r\n")):
            self.assertEqual(clipboard_tools.get_clipboard_text(), "Hallo Welt")

    def test_empty_clipboard(self):
        with mock.patch("clipboard_tools.subprocess.run", return_value=_completed(b"")):
            self.assertEqual(clipboard_tools.get_clipboard_text(), "")

    def test_nonzero_exit_returns_empty(self):
        with mock.patch("clipboard_tools.subprocess.run", return_value=_completed(b"x", returncode=1)):
            self.assertEqual(clipboard_tools.get_clipboard_text(), "")

    def test_timeout_returns_empty(self):
        with mock.patch(
            "clipboard_tools.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="powershell", timeout=5),
        ):
            self.assertEqual(clipboard_tools.get_clipboard_text(), "")

    def test_long_text_capped(self):
        with mock.patch("clipboard_tools.subprocess.run", return_value=_completed(b"a" * 10000)):
            self.assertEqual(len(clipboard_tools.get_clipboard_text(max_chars=4000)), 4000)

    def test_utf8_umlauts(self):
        with mock.patch("clipboard_tools.subprocess.run", return_value=_completed("Grüße".encode("utf-8"))):
            self.assertEqual(clipboard_tools.get_clipboard_text(), "Grüße")


if __name__ == "__main__":
    unittest.main()

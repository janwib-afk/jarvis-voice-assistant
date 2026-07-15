"""
Tests fuer monitors.py — semantische ID-Vergabe (pur) und die
Nie-werfen-Garantie von detect_monitors.

    python -m unittest discover -s tests
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import monitors


def _mon(x, width=1920, height=1080, primary=False):
    return {"x": x, "y": 0, "width": width, "height": height, "primary": primary}


class AssignIdsTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(monitors._assign_ids([]), [])

    def test_single_monitor_is_primary(self):
        result = monitors._assign_ids([_mon(0, primary=True)])
        self.assertEqual(result[0]["id"], "primary")
        self.assertEqual(result[0]["label"], "Primärer Monitor")

    def test_two_monitors_left_right(self):
        result = monitors._assign_ids([_mon(1920), _mon(0, primary=True)])
        # Sortierung nach x: der bei x=0 ist links.
        self.assertEqual([m["id"] for m in result], ["left", "right"])
        self.assertEqual(result[0]["label"], "Linker Monitor")
        self.assertEqual(result[1]["label"], "Rechter Monitor")
        # primary-Flag wird durchgereicht.
        self.assertTrue(result[0]["primary"])
        self.assertFalse(result[1]["primary"])

    def test_three_monitors_middle_unassignable(self):
        result = monitors._assign_ids([_mon(0), _mon(1920, primary=True), _mon(3840)])
        self.assertEqual([m["id"] for m in result], ["left", None, "right"])
        self.assertEqual(result[1]["label"], "Monitor 2")

    def test_input_not_mutated(self):
        raw = [_mon(0)]
        snapshot = dict(raw[0])
        monitors._assign_ids(raw)
        self.assertEqual(raw[0], snapshot)

    def test_geometry_passthrough(self):
        result = monitors._assign_ids([_mon(100, width=2560, height=1440)])
        self.assertEqual(
            (result[0]["x"], result[0]["width"], result[0]["height"]), (100, 2560, 1440)
        )


class DetectMonitorsTests(unittest.TestCase):
    def test_failure_returns_empty_list(self):
        # Nie-werfen-Garantie: jeder Fehler wird zu [] (Frontend-Fallback).
        with mock.patch.object(monitors, "_enum_monitors_raw", side_effect=OSError("kaputt")):
            self.assertEqual(monitors.detect_monitors(), [])

    @unittest.skipUnless(sys.platform == "win32", "Windows-Monitor-API")
    def test_real_detection_shape(self):
        result = monitors.detect_monitors()
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 1)
        for mon in result:
            self.assertLessEqual(
                {"id", "label", "x", "y", "width", "height", "primary"}, set(mon)
            )
            self.assertGreater(mon["width"], 0)
            self.assertGreater(mon["height"], 0)
        self.assertEqual(sum(1 for m in result if m["primary"]), 1)


if __name__ == "__main__":
    unittest.main()

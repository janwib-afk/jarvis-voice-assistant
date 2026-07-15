"""
Tests fuer actions.py — Action-Parsing, URL-Validierung, Origin-Check.

Laufen ohne Serverstart/Config/Netzwerk:
    python -m unittest discover -s tests
"""
import os
import sys
import unittest

# Projektwurzel importierbar machen (tests/ liegt darunter).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import actions
import app_launcher
from actions import (
    Action,
    normalize_url,
    parse_action,
    parse_place_payload,
    is_allowed_origin,
    is_origin_acceptable,
    is_confirmation,
    is_stop_command,
    split_inbox_category,
)


class ParseLauncherActionTests(unittest.TestCase):
    """Phase 5: Launcher-Sprachaktionen sind in der Registry und parsen sauber."""

    def test_profile_activate(self):
        spoken, action, err = parse_action("Mach ich. [ACTION:PROFILE_ACTIVATE] Coding")
        self.assertIsNone(err)
        self.assertEqual(spoken, "Mach ich.")
        self.assertEqual(action, Action("PROFILE_ACTIVATE", "Coding"))

    def test_profile_activate_requires_payload(self):
        _, action, err = parse_action("[ACTION:PROFILE_ACTIVATE]")
        self.assertIsNone(action)
        self.assertIsNotNone(err)

    def test_profile_status_optional_payload(self):
        _, action, err = parse_action("[ACTION:PROFILE_STATUS]")
        self.assertIsNone(err)
        self.assertEqual(action, Action("PROFILE_STATUS", ""))
        _, action, err = parse_action("[ACTION:PROFILE_STATUS] Research")
        self.assertIsNone(err)
        self.assertEqual(action.payload, "Research")

    def test_autostart_on_off(self):
        _, action, err = parse_action("[ACTION:APP_AUTOSTART_ON] Obsidian")
        self.assertIsNone(err)
        self.assertEqual(action, Action("APP_AUTOSTART_ON", "Obsidian"))
        _, action, err = parse_action("[ACTION:APP_AUTOSTART_OFF] Chrome")
        self.assertIsNone(err)
        self.assertEqual(action, Action("APP_AUTOSTART_OFF", "Chrome"))
        _, action, err = parse_action("[ACTION:APP_AUTOSTART_ON]")
        self.assertIsNone(action)
        self.assertIsNotNone(err)

    def test_app_place_parses_as_action(self):
        _, action, err = parse_action("[ACTION:APP_PLACE] Obsidian | left | right_half")
        self.assertIsNone(err)
        self.assertEqual(action, Action("APP_PLACE", "Obsidian | left | right_half"))

    def test_speak_result_actions_cover_launcher(self):
        expected = {"APP_OPEN", "PROFILE_ACTIVATE", "PROFILE_STATUS",
                    "APP_AUTOSTART_ON", "APP_AUTOSTART_OFF", "APP_PLACE"}
        self.assertEqual(actions.SPEAK_RESULT_ACTIONS, frozenset(expected))

    def test_no_confirm_needed_for_launcher_actions(self):
        # Keine der neuen Aktionen ist destruktiv — kein Bestaetigungs-Flow.
        self.assertEqual(actions.CONFIRM_ACTIONS & actions.SPEAK_RESULT_ACTIONS, frozenset())


class ParsePlacePayloadTests(unittest.TestCase):
    def test_happy_path(self):
        parsed, err = parse_place_payload("Obsidian | left | right_half")
        self.assertIsNone(err)
        self.assertEqual(parsed, ("Obsidian", "left", "right_half"))

    def test_german_aliases(self):
        parsed, err = parse_place_payload("Obsidian | links | rechte Hälfte")
        self.assertIsNone(err)
        self.assertEqual(parsed, ("Obsidian", "left", "right_half"))
        parsed, _ = parse_place_payload("VS Code | Hauptmonitor | Vollbild")
        self.assertEqual(parsed, ("VS Code", "primary", "fullscreen"))
        parsed, _ = parse_place_payload("VS Code | ganz rechts | Mitte")
        self.assertEqual(parsed, ("VS Code", "rightmost", "center"))

    def test_case_insensitive_canonical(self):
        parsed, err = parse_place_payload("code | LEFT | Top_Half")
        self.assertIsNone(err)
        self.assertEqual(parsed, ("code", "left", "top_half"))

    def test_wrong_part_count(self):
        for payload in ("Obsidian | left", "a | b | c | d", "Obsidian", "", " | left | center"):
            parsed, err = parse_place_payload(payload)
            self.assertIsNone(parsed, payload)
            self.assertIn("app | monitor | zone", err)

    def test_invalid_monitor_and_zone(self):
        parsed, err = parse_place_payload("Obsidian | mars | center")
        self.assertIsNone(parsed)
        self.assertIn("primary", err)  # nennt die erlaubten Werte
        parsed, err = parse_place_payload("Obsidian | left | diagonal")
        self.assertIsNone(parsed)
        self.assertIn("fullscreen", err)

    def test_constants_in_sync_with_app_launcher(self):
        # Drift-Guard fuer die bewusste Konstanten-Kopie.
        self.assertEqual(actions.PLACE_MONITORS, app_launcher.PLACEMENT_MONITORS)
        self.assertEqual(actions.PLACE_ZONES, app_launcher.PLACEMENT_ZONES)


class ParseActionValidTests(unittest.TestCase):
    def test_search(self):
        spoken, action, err = parse_action("Ich schaue nach. [ACTION:SEARCH] wetter hamburg")
        self.assertIsNone(err)
        self.assertEqual(spoken, "Ich schaue nach.")
        self.assertEqual(action, Action("SEARCH", "wetter hamburg"))

    def test_open_with_scheme(self):
        _, action, err = parse_action("[ACTION:OPEN] https://example.com/pfad")
        self.assertIsNone(err)
        self.assertEqual(action, Action("OPEN", "https://example.com/pfad"))

    def test_open_bare_domain_gets_https(self):
        _, action, err = parse_action("Wird geoeffnet. [ACTION:OPEN] google.com")
        self.assertIsNone(err)
        self.assertEqual(action.type, "OPEN")
        self.assertEqual(action.payload, "https://google.com")

    def test_screen_no_payload(self):
        spoken, action, err = parse_action("[ACTION:SCREEN]")
        self.assertIsNone(err)
        self.assertEqual(spoken, "")
        self.assertEqual(action, Action("SCREEN", ""))

    def test_screen_keeps_trailing_text_as_question(self):
        # SCREEN hat jetzt einen optionalen Payload: die Kontextfrage.
        _, action, err = parse_action("[ACTION:SCREEN] Was ist das Problem?")
        self.assertIsNone(err)
        self.assertEqual(action, Action("SCREEN", "Was ist das Problem?"))

    def test_news_no_payload(self):
        _, action, err = parse_action("Ich schaue nach den Nachrichten. [ACTION:NEWS]")
        self.assertIsNone(err)
        self.assertEqual(action, Action("NEWS", ""))

    def test_inbox_write(self):
        _, action, err = parse_action("Notiert. [ACTION:INBOX_WRITE] Milch kaufen")
        self.assertIsNone(err)
        self.assertEqual(action, Action("INBOX_WRITE", "Milch kaufen"))

    def test_lowercase_action_type_normalized(self):
        _, action, err = parse_action("[ACTION:search] katzenvideos")
        self.assertIsNone(err)
        self.assertEqual(action, Action("SEARCH", "katzenvideos"))

    def test_research_with_payload(self):
        _, action, err = parse_action("Ich recherchiere. [ACTION:RESEARCH] beste ssd 2026")
        self.assertIsNone(err)
        self.assertEqual(action, Action("RESEARCH", "beste ssd 2026"))

    def test_research_requires_payload(self):
        _, action, err = parse_action("[ACTION:RESEARCH]")
        self.assertIsNone(action)
        self.assertIsNotNone(err)

    def test_clipboard_payload_optional(self):
        _, action, err = parse_action("[ACTION:CLIPBOARD]")
        self.assertIsNone(err)
        self.assertEqual(action, Action("CLIPBOARD", ""))
        _, action, err = parse_action("[ACTION:CLIPBOARD] uebersetze ins Englische")
        self.assertIsNone(err)
        self.assertEqual(action, Action("CLIPBOARD", "uebersetze ins Englische"))

    def test_no_payload_actions(self):
        for action_type in ("CLIPBOARD_NOTE", "NOTES_RECENT", "SESSION_SUMMARY"):
            with self.subTest(action_type=action_type):
                _, action, err = parse_action(f"Moment. [ACTION:{action_type}] Rest wird verworfen")
                self.assertIsNone(err)
                self.assertEqual(action, Action(action_type, ""))

    def test_inbox_write_with_category(self):
        _, action, err = parse_action("Notiert. [ACTION:INBOX_WRITE] [Termin] Zahnarzt Dienstag 9 Uhr")
        self.assertIsNone(err)
        self.assertEqual(action, Action("INBOX_WRITE", "[Termin] Zahnarzt Dienstag 9 Uhr"))

    def test_memory_read_no_payload(self):
        _, action, err = parse_action("Ich schaue nach. [ACTION:MEMORY_READ]")
        self.assertIsNone(err)
        self.assertEqual(action, Action("MEMORY_READ", ""))

    def test_memory_forget_with_payload(self):
        _, action, err = parse_action("[ACTION:MEMORY_FORGET] Kaffeevorliebe")
        self.assertIsNone(err)
        self.assertEqual(action, Action("MEMORY_FORGET", "Kaffeevorliebe"))

    def test_memory_forget_requires_payload(self):
        _, action, err = parse_action("[ACTION:MEMORY_FORGET]")
        self.assertIsNone(action)
        self.assertIsNotNone(err)

    def test_project_context_with_payload(self):
        spoken, action, err = parse_action("Ich schaue in deine Notizen. [ACTION:PROJECT_CONTEXT] Jarvis Voice Assistant")
        self.assertIsNone(err)
        self.assertEqual(spoken, "Ich schaue in deine Notizen.")
        self.assertEqual(action, Action("PROJECT_CONTEXT", "Jarvis Voice Assistant"))


class ConfirmActionRegistryTests(unittest.TestCase):
    def test_memory_forget_requires_confirmation(self):
        self.assertIn("MEMORY_FORGET", actions.CONFIRM_ACTIONS)

    def test_memory_read_needs_no_confirmation(self):
        self.assertNotIn("MEMORY_READ", actions.CONFIRM_ACTIONS)


class ParseActionInvalidTests(unittest.TestCase):
    def test_no_action_returns_text(self):
        spoken, action, err = parse_action("Nur eine normale Antwort, Sir.")
        self.assertEqual(spoken, "Nur eine normale Antwort, Sir.")
        self.assertIsNone(action)
        self.assertIsNone(err)

    def test_unknown_action_type(self):
        spoken, action, err = parse_action("Text. [ACTION:DELETE_ALL] /")
        self.assertIsNone(action)
        self.assertIsNotNone(err)
        self.assertEqual(spoken, "Text.")

    def test_missing_payload_for_search(self):
        _, action, err = parse_action("[ACTION:SEARCH]")
        self.assertIsNone(action)
        self.assertIsNotNone(err)

    def test_missing_payload_for_open(self):
        _, action, err = parse_action("[ACTION:OPEN]   ")
        self.assertIsNone(action)
        self.assertIsNotNone(err)

    def test_missing_payload_for_project_context(self):
        _, action, err = parse_action("[ACTION:PROJECT_CONTEXT]")
        self.assertIsNone(action)
        self.assertIn("fehlender Payload fuer PROJECT_CONTEXT", err)

    def test_dangerous_scheme_javascript(self):
        _, action, err = parse_action("[ACTION:OPEN] javascript:alert(1)")
        self.assertIsNone(action)
        self.assertIsNotNone(err)

    def test_dangerous_scheme_file(self):
        _, action, err = parse_action("[ACTION:OPEN] file:///C:/Windows/System32")
        self.assertIsNone(action)
        self.assertIsNotNone(err)

    def test_dangerous_scheme_data(self):
        _, action, err = parse_action("[ACTION:BROWSE] data:text/html,<h1>x</h1>")
        self.assertIsNone(action)
        self.assertIsNotNone(err)


class NormalizeUrlTests(unittest.TestCase):
    def test_adds_https(self):
        self.assertEqual(normalize_url("example.com"), "https://example.com")

    def test_keeps_http(self):
        self.assertEqual(normalize_url("http://example.com"), "http://example.com")

    def test_rejects_empty(self):
        self.assertIsNone(normalize_url(""))
        self.assertIsNone(normalize_url("   "))

    def test_rejects_javascript(self):
        self.assertIsNone(normalize_url("javascript:alert(1)"))

    def test_rejects_file(self):
        self.assertIsNone(normalize_url("file:///etc/passwd"))


class SplitInboxCategoryTests(unittest.TestCase):
    def test_known_category(self):
        self.assertEqual(
            split_inbox_category("[Termin] Zahnarzt Dienstag 9 Uhr"),
            ("Termin", "Zahnarzt Dienstag 9 Uhr"),
        )

    def test_category_case_insensitive(self):
        self.assertEqual(split_inbox_category("[idee] Podcast starten"), ("Idee", "Podcast starten"))
        self.assertEqual(split_inbox_category("[AUFGABE] Reifen wechseln"), ("Aufgabe", "Reifen wechseln"))

    def test_unknown_category_keeps_full_text(self):
        # Unbekannte Klammern gehoeren zum Text — nichts geht verloren.
        self.assertEqual(
            split_inbox_category("[Wichtig] Server neu starten"),
            ("Notiz", "[Wichtig] Server neu starten"),
        )

    def test_no_category(self):
        self.assertEqual(split_inbox_category("Milch kaufen"), ("Notiz", "Milch kaufen"))

    def test_category_without_text_keeps_payload(self):
        self.assertEqual(split_inbox_category("[Idee]"), ("Notiz", "[Idee]"))

    def test_empty(self):
        self.assertEqual(split_inbox_category(""), ("Notiz", ""))


class IsConfirmationTests(unittest.TestCase):
    def test_yes(self):
        for text in ("Ja", "ja bitte", "Jawohl", "Mach das", "Okay", "Ja, tu es"):
            with self.subTest(text=text):
                self.assertIs(is_confirmation(text), True)

    def test_no(self):
        for text in ("Nein", "nein danke", "Abbrechen", "Stopp", "Lieber nicht", "Vergiss es"):
            with self.subTest(text=text):
                self.assertIs(is_confirmation(text), False)

    def test_negation_wins_over_yes_word(self):
        self.assertIs(is_confirmation("Nein, mach das nicht"), False)
        self.assertIs(is_confirmation("Ja nicht loeschen!"), False)

    def test_unrelated_text_is_none(self):
        self.assertIsNone(is_confirmation("Wie wird das Wetter morgen in Hamburg?"))
        self.assertIsNone(is_confirmation(""))

    def test_long_sentence_with_buried_yes_is_none(self):
        # "ja" tief in einem langen Satz ist keine Bestaetigung.
        self.assertIsNone(is_confirmation("Ich habe mich gefragt ob das damals ja so richtig war"))


class IsStopCommandTests(unittest.TestCase):
    def test_plain_stop_words(self):
        for text in ("Stopp", "stop", "Stopp!", "abbrechen", "Halt", "Abbruch", "stoppen"):
            with self.subTest(text=text):
                self.assertTrue(is_stop_command(text))

    def test_stop_with_filler(self):
        for text in ("Jarvis, stopp", "bitte stopp", "Okay, stopp jetzt", "Jarvis, sei still", "hör auf"):
            with self.subTest(text=text):
                self.assertTrue(is_stop_command(text))

    def test_questions_about_stopping_are_not_stop(self):
        for text in (
            "Wie stoppe ich einen Docker-Container",
            "stoppe die Recherche zu SSDs",
            "Kannst du kurz stoppen und was anderes machen",
            "Was bedeutet Abbruch bei einem Build",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_stop_command(text))

    def test_normal_text_and_empty(self):
        self.assertFalse(is_stop_command("Wie ist das Wetter morgen?"))
        self.assertFalse(is_stop_command(""))
        self.assertFalse(is_stop_command("   "))


class ActionRegistryTests(unittest.TestCase):
    """Konsistenz der zentralen Registry (actions.REGISTRY)."""

    def test_every_action_has_label_and_positive_timeout(self):
        for action_type, spec in actions.REGISTRY.items():
            with self.subTest(action_type=action_type):
                self.assertEqual(spec.type, action_type)
                self.assertTrue(spec.label.strip())
                self.assertGreater(spec.timeout, 0)
                self.assertGreater(spec.summary_max_tokens, 0)
                self.assertIn(spec.payload, ("required", "optional", "none"))
                self.assertIn(spec.risk, ("low", "confirm"))

    def test_derived_views_match_registry(self):
        self.assertEqual(actions.ALLOWED_ACTIONS, frozenset(actions.REGISTRY))
        self.assertEqual(
            actions.PAYLOAD_ACTIONS | actions.NO_PAYLOAD_ACTIONS | actions.OPTIONAL_PAYLOAD_ACTIONS,
            actions.ALLOWED_ACTIONS,
        )
        # URL-Aktionen brauchen zwingend einen Payload.
        self.assertTrue(actions.URL_ACTIONS <= actions.PAYLOAD_ACTIONS)
        # Confirm-Aktionen kommen ausschliesslich aus risk="confirm".
        for action_type in actions.CONFIRM_ACTIONS:
            self.assertEqual(actions.REGISTRY[action_type].risk, "confirm")

    def test_spec_and_label_lookup(self):
        self.assertEqual(actions.spec_for("RESEARCH").timeout, 180)
        self.assertEqual(actions.label_for("SEARCH"), "Websuche")
        # Unbekannter Typ faellt aufs Typ-Kuerzel zurueck (Anzeige darf nie crashen).
        self.assertEqual(actions.label_for("UNBEKANNT"), "UNBEKANNT")

    def test_unknown_action_not_executable(self):
        _, action, err = parse_action("[ACTION:SHUTDOWN] jetzt")
        self.assertIsNone(action)
        self.assertIsNotNone(err)

    def test_app_open_spec(self):
        spec = actions.spec_for("APP_OPEN")
        self.assertEqual(spec.label, "App öffnen")
        self.assertEqual(spec.payload, "required")
        self.assertEqual(spec.risk, "low")
        # Kein URL-Zwang: Payload ist ein App-Name, keine Adresse.
        self.assertFalse(spec.is_url)
        self.assertFalse(spec.is_browser)

    def test_parse_app_open(self):
        spoken, action, err = parse_action("Ich oeffne Obsidian. [ACTION:APP_OPEN] Obsidian")
        self.assertIsNone(err)
        self.assertEqual(action.type, "APP_OPEN")
        self.assertEqual(action.payload, "Obsidian")
        self.assertEqual(spoken, "Ich oeffne Obsidian.")

    def test_parse_app_open_without_payload_fails(self):
        _, action, err = parse_action("[ACTION:APP_OPEN]")
        self.assertIsNone(action)
        self.assertIsNotNone(err)


class IsAllowedOriginTests(unittest.TestCase):
    def test_localhost_allowed(self):
        self.assertTrue(is_allowed_origin("http://localhost:8340"))

    def test_loopback_ip_allowed(self):
        self.assertTrue(is_allowed_origin("http://127.0.0.1:8340"))

    def test_ipv6_loopback_allowed(self):
        self.assertTrue(is_allowed_origin("http://[::1]:8340"))

    def test_https_localhost_allowed(self):
        self.assertTrue(is_allowed_origin("https://localhost"))

    def test_foreign_host_denied(self):
        self.assertFalse(is_allowed_origin("http://evil.example.com"))

    def test_none_denied(self):
        self.assertFalse(is_allowed_origin(None))

    def test_empty_denied(self):
        self.assertFalse(is_allowed_origin(""))

    def test_non_http_scheme_denied(self):
        self.assertFalse(is_allowed_origin("file://localhost"))

    def test_localhost_subdomain_spoof_denied(self):
        # "localhost.evil.com" darf NICHT als localhost durchgehen.
        self.assertFalse(is_allowed_origin("http://localhost.evil.com"))


class IsOriginAcceptableTests(unittest.TestCase):
    """WS-Handshake-Policy: 'null' nur mit Token, fremde/fehlende Origins abgelehnt."""

    def test_local_origin_allowed_regardless_of_token(self):
        # Lokaler Origin passiert das Origin-Gate; der Token wird separat geprueft.
        self.assertTrue(is_origin_acceptable("http://127.0.0.1:8340", False))
        self.assertTrue(is_origin_acceptable("http://localhost:8340", True))

    def test_null_origin_allowed_only_with_token(self):
        self.assertTrue(is_origin_acceptable("null", True))
        self.assertFalse(is_origin_acceptable("null", False))

    def test_missing_origin_denied_even_with_token(self):
        self.assertFalse(is_origin_acceptable(None, True))
        self.assertFalse(is_origin_acceptable("", True))

    def test_foreign_origin_denied_even_with_token(self):
        self.assertFalse(is_origin_acceptable("http://evil.example.com", True))


if __name__ == "__main__":
    unittest.main()

"""
Statischer Regressions-Guard fuers Frontend. Es gibt keine JS-Teststruktur,
daher pruefen wir hier nur, dass die WebSocket-URL protokoll-abhaengig gebaut
wird (wss:// unter HTTPS) und kein hart kodiertes ws:// zurueckkommt.

Manuelle Pruefung (nicht automatisierbar ohne Browser): Seite ueber https://
oeffnen und in der Konsole pruefen, dass die WS-Verbindung mit "wss://" startet;
ueber http://localhost mit "ws://".

    python -m unittest discover -s tests
"""
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAIN_JS = os.path.join(_ROOT, "frontend", "main.js")
_SETTINGS_JS = os.path.join(_ROOT, "frontend", "settings.js")
_STYLE_CSS = os.path.join(_ROOT, "frontend", "style.css")
_INDEX_HTML = os.path.join(_ROOT, "frontend", "index.html")
_LAUNCHER = os.path.join(_ROOT, "jarvis-launcher.pyw")


def _read(path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_main_js() -> str:
    return _read(_MAIN_JS)


class WebSocketProtocolTests(unittest.TestCase):
    def test_ws_url_is_protocol_aware(self):
        js = _read_main_js()
        self.assertIn("location.protocol === 'https:' ? 'wss:' : 'ws:'", js)

    def test_no_hardcoded_ws_scheme(self):
        js = _read_main_js()
        self.assertNotIn("new WebSocket(`ws://", js)


class WindowModeTests(unittest.TestCase):
    """Regressions-Guard fuer die Drei-Wege-Fenstergroesse. Start immer im
    Vollbild (auf der Jarvis-Seite), kein localStorage-Restore."""

    def test_index_boots_fullscreen(self):
        html = _read(_INDEX_HTML)
        self.assertIn("page-jarvis mode-fullscreen", html)

    def test_index_does_not_read_ui_mode_from_localstorage(self):
        html = _read(_INDEX_HTML)
        self.assertNotIn("jarvis.uiMode", html)

    def test_index_has_three_way_switch(self):
        html = _read(_INDEX_HTML)
        self.assertIn("window-mode-switch", html)
        for mode in ("fullscreen", "focus", "panel"):
            self.assertIn('data-window-mode="%s"' % mode, html)

    def test_main_js_defines_three_modes(self):
        js = _read_main_js()
        self.assertIn("['fullscreen', 'focus', 'panel']", js)

    def test_main_js_drops_ui_mode_localstorage(self):
        js = _read_main_js()
        self.assertNotIn("jarvis.uiMode", js)

    def test_launcher_handles_all_three_modes(self):
        py = _read(_LAUNCHER)
        start = py.find("def set_window_mode")
        self.assertNotEqual(start, -1, "set_window_mode nicht gefunden")
        # Bis zur naechsten Top-Level-Klasse/Def bzw. Dateiende betrachten.
        body = py[start:start + 2000]
        self.assertIn('mode == "panel"', body)
        self.assertIn('mode == "fullscreen"', body)
        self.assertIn("focus", body)  # else-Zweig, im Docstring benannt


class PageNavigationTests(unittest.TestCase):
    """Regressions-Guard fuer die Seiten-Ebene (Phase 1): Jarvis-Seite und
    Kontrollzentrum sind getrennte Bereiche, unabhaengig von der Fenstergroesse."""

    def test_index_has_main_navigation(self):
        html = _read(_INDEX_HTML)
        self.assertIn('id="page-nav"', html)
        for page in ("jarvis", "control"):
            self.assertIn('data-app-page="%s"' % page, html)

    def test_boot_class_contains_jarvis_page(self):
        # Startklasse im Pre-Paint-Skript: Jarvis-Seite, nicht das Kontrollzentrum.
        html = _read(_INDEX_HTML)
        self.assertIn("className = 'page-jarvis mode-fullscreen'", html)
        self.assertNotIn("className = 'mode-focus", html)

    def test_main_js_defines_all_page_symbols(self):
        # Keine kaputten Referenzen: alles, was applyAppPage nutzt, ist definiert.
        js = _read_main_js()
        self.assertIn("const APP_PAGES = ['jarvis', 'control']", js)
        for fn in ("applyAppPage", "isControlPage", "rootClass",
                   "updatePageButton", "shouldLoadControlData"):
            self.assertIn("function %s(" % fn, js)

    def test_control_data_loaded_only_when_control_visible(self):
        # Dashboard-/Kontrollzentrum-Daten haengen an der Seite, nicht mehr an
        # der Fenstergroesse.
        js = _read_main_js()
        self.assertIn("if (shouldLoadControlData()) loadDashboardState();", js)
        self.assertIn("if (!shouldLoadControlData()) return;", js)
        self.assertNotIn("isDashboardMode", js)

    def test_panel_switches_to_focus_for_control_page(self):
        # Aus "Klein" ins Kontrollzentrum: automatisch auf "Mitte" wechseln —
        # und "Klein" bleibt umgekehrt immer die kompakte Jarvis-Ansicht.
        js = _read_main_js()
        self.assertIn("if (isControlPage() && uiMode === 'panel')", js)
        self.assertIn("applyUiMode('focus');", js)
        self.assertIn("if (mode === 'panel' && isControlPage()) appPage = 'jarvis';", js)


class ControlCenterSettingsTests(unittest.TestCase):
    """Phase-2-Guards: Einstellungen leben inline im Kontrollzentrum
    (Sub-View Übersicht/Einstellungen), die Jarvis-Seite und die Titelleiste
    tragen keine Verwaltungselemente mehr."""

    def test_settings_anchored_in_control_center(self):
        html = _read(_INDEX_HTML)
        self.assertIn('id="cc-shell"', html)
        self.assertIn('id="cc-subnav"', html)
        for view in ("overview", "settings"):
            self.assertIn('data-cc-view="%s"' % view, html)
        self.assertIn('id="settings-form"', html)
        # Das Formular liegt im Kontrollzentrum-Shell, nicht mehr am Body-Ende.
        self.assertLess(html.find('id="settings-view"'), html.find('id="mute-btn"'))

    def test_settings_gear_removed_from_title_bar(self):
        html = _read(_INDEX_HTML)
        self.assertNotIn('id="btn-settings"', html)
        # Kein Modal mehr: weder hidden-Klasse noch Dialog-Attribute.
        self.assertNotIn("aria-modal", html)
        js = _read(_SETTINGS_JS)
        self.assertNotIn("btn-settings')", js)

    def test_css_hides_management_outside_control_center(self):
        css = _read(_STYLE_CSS)
        # Grundzustand: Sub-Nav und Einstellungen versteckt — nur das
        # Kontrollzentrum (mode-focus) blendet sie ein.
        self.assertIn("#cc-subnav {\n    display: none;", css)
        self.assertIn("#settings-view {\n    display: none;\n}", css)
        self.assertIn("html.mode-focus.cc-view-settings #settings-view", css)
        self.assertIn("html.mode-focus #cc-subnav", css)
        # Das alte Vollbild-Overlay ist weg.
        self.assertNotIn("#settings-view.hidden", css)

    def test_main_js_defines_control_view_symbols(self):
        js = _read_main_js()
        self.assertIn("const CONTROL_VIEWS = ['overview', 'settings', 'music']", js)
        for fn in ("applyControlView", "updateControlViewButton"):
            self.assertIn("function %s(" % fn, js)
        # settings.js kehrt darueber zur Übersicht zurueck.
        self.assertIn("window.applyControlView = applyControlView;", js)


class MusicViewTests(unittest.TestCase):
    """Phase-3-Guards: Musikverwaltung (MP3-Auswahl fuer den Sessionstart)
    lebt als Sub-View im Kontrollzentrum; die Jarvis-Seite traegt nur den
    kleinen "Nächste Musik"-Status."""

    def test_music_view_anchored_in_control_center(self):
        html = _read(_INDEX_HTML)
        self.assertIn('data-cc-view="music"', html)
        self.assertIn('id="music-view"', html)
        self.assertIn('id="music-list"', html)
        self.assertIn('id="btn-music-clear"', html)
        self.assertIn("/static/music.js", html)
        # Die Verwaltung liegt im cc-shell (nach dessen Beginn im Markup) …
        self.assertGreater(html.find('id="music-view"'), html.find('id="cc-shell"'))

    def test_jarvis_page_only_small_status(self):
        html = _read(_INDEX_HTML)
        # … waehrend die Jarvis-Hauptspalte nur den Status traegt (vor cc-shell).
        self.assertIn('id="music-status"', html)
        self.assertLess(html.find('id="music-status"'), html.find('id="cc-shell"'))
        css = _read(_STYLE_CSS)
        # Grundzustand versteckt — nur der Musik-Sub-View blendet die Verwaltung ein.
        self.assertIn("#music-view {\n    display: none;\n}", css)
        self.assertIn("html.mode-focus.cc-view-music #music-view", css)

    def test_main_js_dispatches_music_view(self):
        js = _read_main_js()
        self.assertIn("view === 'music'", js)
        self.assertIn("window.loadMusic", js)

    def test_main_js_handles_music_changed_event(self):
        # WS-Event vom Server (POST /music/selection): Liste + Status nachziehen.
        js = _read_main_js()
        self.assertIn("data.type === 'music_changed'", js)

    def test_music_js_uses_music_api(self):
        music_js = _read(os.path.join(_ROOT, "frontend", "music.js"))
        self.assertIn("/music/files", music_js)
        self.assertIn("/music/selection", music_js)
        self.assertIn("window.loadMusic = loadMusic", music_js)

    def test_settings_form_saves_music_folder(self):
        html = _read(_INDEX_HTML)
        self.assertIn('name="music_folder"', html)
        settings_js = _read(_SETTINGS_JS)
        self.assertIn("'music_folder'", settings_js)


if __name__ == "__main__":
    unittest.main()


class MotionTests(unittest.TestCase):
    """Phase-5-Guards: Motion-Tokens, Orb-Glow-Layer, Reduced-Motion-Abdeckung
    und die JS-Hooks der Bewegungsschicht (rein additiv)."""

    def test_motion_tokens_present(self):
        css = _read(os.path.join(_ROOT, "frontend", "design-tokens.css"))
        for token in ("--motion-duration-standard", "--motion-duration-ambient-listen",
                      "--motion-ease-enter", "--motion-scale-press"):
            self.assertIn(token, css)

    def test_orb_glow_layer_and_new_keyframes(self):
        css = _read(_STYLE_CSS)
        self.assertIn("#orb::after", css)
        for kf in ("orb-breathe", "orb-listen", "orb-think", "orb-speak",
                   "glow-pulse", "run-dot", "sweep"):
            self.assertIn("@keyframes " + kf, css)
        # Alt-Puls-Keyframes sind abgeloest.
        self.assertNotIn("@keyframes pulse-listen", css)

    def test_reduced_motion_covers_orb_and_sweep(self):
        css = _read(_STYLE_CSS)
        idx = css.find("prefers-reduced-motion")
        self.assertGreater(idx, -1)
        block = css[idx:]
        for sel in ("#orb", "luenette-sweep", "msg-new", "view-enter"):
            self.assertIn(sel, block)

    def test_main_js_motion_hooks(self):
        js = _read_main_js()
        self.assertIn("classList.add('msg-new')", js)
        self.assertIn("'action-running'", js)
        self.assertIn("playViewEnter", js)
        self.assertIn("function removeBanner", js)


class DelightTests(unittest.TestCase):
    """Phase-6-Guards: die zwei gezielten Delight-Momente (Instrument erwacht,
    Chip landet) samt Reduced-Motion-Abdeckung und JS-Hooks (rein additiv)."""

    def test_delight_keyframes_present(self):
        css = _read(_STYLE_CSS)
        for kf in ("orb-awaken", "chip-land"):
            self.assertIn("@keyframes " + kf, css)
        self.assertIn("#orb-container.awakening #orb::after", css)
        self.assertIn(".map-chip.chip-landed", css)

    def test_delight_covered_by_reduced_motion(self):
        css = _read(_STYLE_CSS)
        block = css[css.find("prefers-reduced-motion"):]
        for sel in ("awakening", "chip-landed"):
            self.assertIn(sel, block)

    def test_main_js_delight_hooks(self):
        js = _read_main_js()
        self.assertIn("function awakenInstrument", js)
        self.assertIn("awakenInstrument()", js)
        self.assertIn("justPlacedAppId", js)
        self.assertIn("chip-landed", js)


class Phase7AuditTests(unittest.TestCase):
    """Phase-7-Guards: Web-Interface-Guidelines-Fixes (color-scheme, Icon-Button-
    Labels, Heading-Hierarchie, Banner-Rolle, Formular-Attribute) — rein additiv."""

    def test_color_scheme_dark_declared(self):
        html = _read(_INDEX_HTML)
        css = _read(os.path.join(_ROOT, "frontend", "design-tokens.css"))
        self.assertIn("color-scheme: dark", html)   # Boot-Style vor externer CSS
        self.assertIn("color-scheme: dark", css)     # Token-Layer

    def test_icon_glyph_buttons_have_aria_label(self):
        html = _read(_INDEX_HTML)
        self.assertIn('id="btn-min"', html)
        self.assertIn('id="btn-close"', html)
        # Beide Glyph-Buttons brauchen einen Accessible Name jenseits des Glyphs.
        for marker in ('aria-label="Minimieren"', 'aria-label="Fenster ausblenden"'):
            self.assertIn(marker, html)
        js = _read_main_js()
        self.assertIn("aria-label", js)              # .eb-close Schließen-Label

    def test_control_center_heading_hierarchy(self):
        html = _read(_INDEX_HTML)
        # Heute-Streifen hat einen h2-Elternknoten (kein h1->h3-Sprung mehr).
        self.assertIn('<h2 id="cc-today-heading" class="sr-only">Heute</h2>', html)
        # Blöcke bleiben h2, Heute-Gruppen h3.
        for h2 in ("<h2>Apps</h2>", "<h2>Aktionen</h2>", "<h2>System</h2>"):
            self.assertIn(h2, html)
        for h3 in ("<h3>Offene Aufgaben</h3>", "<h3>Inbox heute</h3>"):
            self.assertIn(h3, html)

    def test_error_banner_roles(self):
        js = _read_main_js()
        # Warnungen höflich (status), echte Störungen assertiv (alert).
        self.assertIn("isWarning ? 'status' : 'alert'", js)

    def test_settings_form_autocomplete_off(self):
        html = _read(_INDEX_HTML)
        self.assertIn('id="settings-form" autocomplete="off" spellcheck="false"', html)

    def test_single_h1_per_page(self):
        # Nur die aktive Seite exponiert ihre Bereichs-h1 (sonst zwei h1 im Tree).
        css = _read(_STYLE_CSS)
        self.assertIn("html.page-jarvis #control-heading", css)
        self.assertIn("html.page-control #jarvis-heading", css)

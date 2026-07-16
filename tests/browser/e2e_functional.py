"""Funktionale Jarvis-Browser-E2E-Suite (Playwright, Python).

Faehrt die ECHTE Jarvis-Anwendung (echte REST-/WS-Pfade, echter Action-Parser,
echte Queue-/Stop-Logik) gegen kontrollierte Provider-/Desktop-Adapter. Jeder
Flow laeuft in einem frischen Server-Subprozess UND frischem Browserkontext
(volle Isolation, keine geteilte Conversation-/Config-Mutation).

Fehlerpolitik (BROWSER_TEST_STRATEGY.md): jeder Flow endet mit
``collectors.assert_clean`` — 0 console.error, 0 pageerror, 0 fehlgeschlagene
lokale Requests, 0 unerwartete externe Hosts.

Nutzung:
  python tests/browser/e2e_functional.py                # einmal
  python tests/browser/e2e_functional.py --repeat 5     # Flake-Gate
  python tests/browser/e2e_functional.py --only stop_action

Exit 0 = alle Flows grün.
"""
import os
import re
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright, expect  # noqa: E402
from e2e_harness import JarvisServer, browser_context, open_jarvis, INIT_WS_BLOCK  # noqa: E402

CRITICAL = {"connect", "text_input", "stop_action", "mute", "reconnect",
            "settings", "settings_conflict", "monitor_keyboard"}


def jarvis_said(page, text):
    """Antwort im Transcript (nicht im hidden #panel-answer-Spiegel)."""
    return page.locator("#transcript").get_by_text(text)


# ── Flows ────────────────────────────────────────────────────────────────────

def flow_connect(pw):
    """1. Start & Verbindung: App laedt, echte WS-Verbindung, verbundener Status."""
    with JarvisServer("connect") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        expect(page.get_by_text("Server verbunden")).to_be_visible()
        # Echte WS-Verbindung (der steuerbare Wrapper hat genau einmal verbunden).
        assert page.evaluate("window.__wsConnectCount") >= 1
        assert page.evaluate("window.__lastWs && window.__lastWs.readyState") == 1  # OPEN
        col.assert_clean("connect")


def flow_text_input(pw):
    """2. Texteingabe: senden -> thinking -> Antwort -> Transcript -> Eingabe nutzbar."""
    with JarvisServer("text") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        # llm_delay hält den 'thinking'-Zustand deterministisch beobachtbar: der
        # Fake-LLM antwortet sonst mit null Latenz und der Client springt
        # thinking->idle, bevor der Poller 'thinking' sieht (sonst ~20% flaky).
        # Gleiches Muster wie action_delay in flow_stop_action.
        srv.scenario(replies=["Verstanden, Chef — erledigt."], llm_delay=0.4)
        page.get_by_label("Textnachricht an Jarvis").fill("Wie ist der Status?")
        page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
        # thinking wird clientseitig sofort beim Senden gesetzt.
        page.wait_for_function("document.getElementById('orb').className === 'thinking'")
        # Nutzer-Nachricht + Antwort erscheinen im Transcript.
        expect(jarvis_said(page, "Wie ist der Status?")).to_be_visible()
        expect(jarvis_said(page, "Verstanden, Chef — erledigt.")).to_be_visible()
        # Zurueck auf Bereit, Eingabe geleert und weiter nutzbar.
        page.wait_for_function("document.getElementById('status').textContent === 'Bereit'")
        assert page.get_by_label("Textnachricht an Jarvis").input_value() == ""
        expect(page.get_by_label("Textnachricht an Jarvis")).to_be_enabled()
        col.assert_clean("text_input")


def flow_stop_action(pw):
    """3. Stop waehrend Action: verzoegerte Aktion startet, Stop beendet sie."""
    with JarvisServer("stop") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        # RESEARCH mit kuenstlich langer Quellen-Suche (abbrechbar).
        srv.scenario(replies=["Ich recherchiere das. [ACTION:RESEARCH] Elektroautos"],
                     action_delay=30.0)
        page.get_by_label("Textnachricht an Jarvis").fill("recherchiere Elektroautos")
        page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
        # Laufende Aktion sichtbar (Statuszeile zeigt die Aktion).
        page.wait_for_function(
            "document.getElementById('status-action').textContent.includes('Recherche')")
        # Stop ueber den Button.
        page.get_by_role("button", name="Wiedergabe und laufende Aktion stoppen").click()
        # Aktion endet kontrolliert (Aktionszeile leert sich), Verbindung bleibt offen.
        page.wait_for_function(
            "document.getElementById('status-action').textContent === ''")
        assert page.evaluate("window.__lastWs.readyState") == 1  # OPEN
        # Verbindung weiter nutzbar: naechste Nachricht wird normal beantwortet.
        srv.scenario(replies=["Alles klar, weiter geht's."])
        page.get_by_label("Textnachricht an Jarvis").fill("weiter")
        page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
        expect(jarvis_said(page, "Alles klar, weiter geht's.")).to_be_visible()
        col.assert_clean("stop_action")


def flow_mute(pw):
    """5. Mute/Unmute: aria-pressed + sichtbarer Statuswechsel, ohne Extra-Request."""
    with JarvisServer("mute") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        mute = page.get_by_role("button", name="Mikrofon stummschalten")
        expect(mute).to_have_attribute("aria-pressed", "false")
        mute.click()
        muted = page.get_by_role("button", name="Mikrofon wieder aktivieren")
        expect(muted).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#status")).to_have_text("Mikrofon stumm")
        muted.click()
        expect(page.get_by_role("button", name="Mikrofon stummschalten")).to_have_attribute(
            "aria-pressed", "false")
        col.assert_clean("mute")


def flow_error(pw):
    """15. Fehler: LLM-Fehler -> sichtbares Fehlerbanner, Nutzer kann weiterarbeiten."""
    with JarvisServer("error") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        srv.scenario(replies=[{"raise": True}])
        page.get_by_label("Textnachricht an Jarvis").fill("loese einen Fehler aus")
        page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
        banner = page.locator("#error-stack .error-banner")
        expect(banner).to_be_visible()
        expect(banner.locator(".eb-label")).to_have_text("KI")
        # Weiterarbeiten: naechste Nachricht wird normal beantwortet.
        srv.scenario(replies=["Jetzt wieder alles gut."])
        page.get_by_label("Textnachricht an Jarvis").fill("und jetzt?")
        page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
        expect(jarvis_said(page, "Jetzt wieder alles gut.")).to_be_visible()
        col.assert_clean("error")


def flow_offline(pw):
    """15. Offline: WS verbindet nie -> klarer Getrennt-Zustand, keine Endlosschleife."""
    with JarvisServer("offline") as srv, \
            browser_context(pw, srv.base_url, ws_init=INIT_WS_BLOCK) as (page, col):
        page.goto(srv.base_url)
        page.wait_for_selector("body.jarvis-ready")
        expect(page.get_by_text("Getrennt")).to_be_visible()
        # Senden im Offline-Zustand meldet einen Fehler statt zu haengen.
        page.get_by_label("Textnachricht an Jarvis").fill("bist du da?")
        page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
        # Kein pageerror/console.error; Eingabe bleibt nutzbar.
        expect(page.get_by_label("Textnachricht an Jarvis")).to_be_enabled()
        col.assert_clean("offline")


def flow_reconnect(pw):
    """6. Disconnect/Reconnect: WS-Abbruch -> Getrennt -> automatischer Reconnect."""
    with JarvisServer("reconnect") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        assert page.evaluate("window.__wsConnectCount") == 1
        # Verbindung gezielt kappen (Server bleibt oben -> Token gueltig).
        page.evaluate("window.__lastWs.close()")
        expect(page.get_by_text("Getrennt")).to_be_visible()
        # Automatischer Reconnect (Backoff ~3s): zweite Verbindung + verbundener Status.
        page.wait_for_function(
            "window.__wsConnectCount >= 2 && "
            "document.getElementById('sc-conn-text').textContent === 'Server verbunden'",
            timeout=15000,
        )
        col.assert_clean("reconnect")


def flow_settings(pw):
    """7. Settings: oeffnen, synthetische Werte, Aenderung/Dirty, Speichern, keine Secrets."""
    with JarvisServer("settings") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        page.get_by_role("button", name="Kontrollzentrum").click()
        page.get_by_role("tab", name="Einstellungen").click()
        name = page.locator('#settings-form [name="user_name"]')
        expect(name).to_have_value("Testnutzer")  # synthetischer Wert
        # Secrets erscheinen nie im Einstellungs-UI.
        settings_text = page.locator("#settings-view").inner_text()
        assert "anthropic" not in settings_text.lower()
        assert "e2e-dummy" not in settings_text.lower()
        expect(page.get_by_text("API-Schlüssel werden aus Sicherheitsgründen nur in config.json")
               ).to_be_visible()
        # Aenderung -> Dirty-Zustand sichtbar.
        page.locator('#settings-form [name="city"]').fill("Bremen")
        expect(page.locator("#settings-dirty")).to_be_visible()
        # Speichern -> bestaetigte Rueckmeldung.
        page.get_by_role("button", name="Speichern").click()
        expect(page.locator("#settings-msg")).to_contain_text("Gespeichert")
        col.assert_clean("settings")


def flow_settings_conflict(pw):
    """7b. Stale Settings-UI: konkurrierende Aenderung -> sichtbarer Konflikt + Reload.

    Sichtbares Nutzerverhalten (RFC-0003 D6): die UI behauptet NICHT gespeichert zu
    haben, laedt den Serverstand neu und meldet den Konflikt verstaendlich.
    """
    with JarvisServer("settings-conflict") as srv, browser_context(pw, srv.base_url) as (page, col):
        # Der 409 wird hier ABSICHTLICH provoziert; Chromium loggt jede Nicht-2xx-
        # Ressource selbsttaetig. Alles andere bleibt unter der strengen Politik.
        col.allow_console_error("409")
        open_jarvis(page, srv.base_url)
        page.get_by_role("button", name="Kontrollzentrum").click()
        page.get_by_role("tab", name="Einstellungen").click()
        expect(page.locator('#settings-form [name="user_name"]')).to_have_value("Testnutzer")

        # Der Nutzer tippt — seine Basis ist ab jetzt veraltet.
        page.locator('#settings-form [name="city"]').fill("Bremen")

        # Zwischenzeitlich aendert jemand anders die Settings (zweiter Client mit
        # demselben Token) — das ist der reale Fall "zweiter Tab / Voice-Aktion".
        page.evaluate(
            """async () => {
                const token = window.JARVIS_TOKEN;
                await fetch('/settings', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'X-Jarvis-Token': token},
                    body: JSON.stringify({user_role: 'zwischendurch geaendert'}),
                });
            }"""
        )

        page.get_by_role("button", name="Speichern").click()
        # Kein falsches "Gespeichert": stattdessen verstaendliche Konfliktmeldung.
        expect(page.locator("#settings-msg")).to_contain_text("zwischenzeitlich geändert")
        expect(page.locator("#settings-msg")).not_to_contain_text("Gespeichert ✓")
        # Formular wurde mit dem frischen Serverstand neu geladen.
        expect(page.locator('#settings-form [name="user_role"]')
               ).to_have_value("zwischendurch geaendert")
        col.assert_clean("settings-conflict")


def flow_monitor_keyboard(pw):
    """11. Monitorzuweisung (Tastaturpfad): App waehlen, Zone per Enter, kein Fenster-Move."""
    with JarvisServer("monitor") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        page.get_by_role("button", name="Kontrollzentrum").click()
        page.wait_for_selector("#cc-app-grid .app-module")
        page.wait_for_selector("#cc-map-stage .map-zone")
        # App selektieren (Klick auf den Modul-Kopf, nicht auf Buttons).
        page.locator('.app-module[data-app="obsidian"]').click(position={"x": 6, "y": 6})
        expect(page.locator('.app-module[data-app="obsidian"]')).to_have_class(
            re.compile(r".*selected.*"))
        # Zone semantisch fokussieren und per Tastatur (Enter) zuweisen.
        zone = page.get_by_role("button", name="Linker Monitor: Zentriert")
        zone.focus()
        page.keyboard.press("Enter")
        # Sichtbare Bestaetigung: Platzierungs-Label der App aktualisiert sich.
        expect(page.locator('.app-module[data-app="obsidian"] .app-module-place')
               ).to_contain_text("Zentriert")
        col.assert_clean("monitor_keyboard")


def flow_window_modes(pw):
    """13. Fenstermodi: Vollbild/Mitte/Klein mit aria-pressed + Layout-Marker."""
    with JarvisServer("window") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        full = page.get_by_role("button", name="Vollbild")
        mitte = page.get_by_role("button", name="Mitte")
        klein = page.get_by_role("button", name="Klein")
        expect(full).to_have_attribute("aria-pressed", "true")
        mitte.click()
        expect(mitte).to_have_attribute("aria-pressed", "true")
        expect(full).to_have_attribute("aria-pressed", "false")
        klein.click()
        expect(klein).to_have_attribute("aria-pressed", "true")
        page.wait_for_function(
            "document.documentElement.className.includes('mode-panel')")
        col.assert_clean("window_modes")


def flow_transcript(pw):
    """12. Transcript: mehrere Nachrichten, Suche (Trefferzahl), Kopieren (Feedback)."""
    with JarvisServer("transcript") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)
        srv.scenario(replies=["Antwort ueber Orbzustaende.", "Antwort ueber Screenshots.",
                              "Antwort ueber Farben."])
        for i, msg in enumerate(["Frage Orb", "Frage Screenshots", "Frage Farben"], start=2):
            page.get_by_label("Textnachricht an Jarvis").fill(msg)
            page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
            page.wait_for_function(
                f"document.querySelectorAll('#transcript .msg.jarvis').length >= {i}")
        # Suche filtert live und meldet die Trefferzahl.
        page.get_by_label("Verlauf durchsuchen").fill("Orbzustaende")
        expect(page.locator("#search-count")).to_contain_text("von")
        expect(jarvis_said(page, "Antwort ueber Orbzustaende.")).to_be_visible()
        page.get_by_label("Verlauf durchsuchen").fill("")
        # Kopieren: Feedback-Klasse belegt die Interaktion (Clipboard kontrolliert).
        last = page.locator("#transcript .msg").last
        last.hover()
        last.get_by_role("button", name="kopieren").click()
        expect(last.get_by_role("button", name="kopieren")).to_have_class(
            re.compile(r".*copied.*"))
        col.assert_clean("transcript")


FLOWS = {
    "connect": flow_connect,
    "text_input": flow_text_input,
    "stop_action": flow_stop_action,
    "mute": flow_mute,
    "reconnect": flow_reconnect,
    "settings": flow_settings,
    "settings_conflict": flow_settings_conflict,
    "monitor_keyboard": flow_monitor_keyboard,
    "window_modes": flow_window_modes,
    "transcript": flow_transcript,
    "error": flow_error,
    "offline": flow_offline,
}


SMOKE = ["connect", "text_input", "stop_action", "error"]


def main():
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    repeat = 1
    if "--repeat" in sys.argv:
        repeat = int(sys.argv[sys.argv.index("--repeat") + 1])

    if only:
        names = [only]
    elif "--smoke" in sys.argv:
        names = SMOKE
    else:
        names = list(FLOWS)
    all_ok = True
    with sync_playwright() as pw:
        for rep in range(1, repeat + 1):
            if repeat > 1:
                print(f"\n=== Wiederholung {rep}/{repeat} ===")
            for name in names:
                tag = " [kritisch]" if name in CRITICAL else ""
                try:
                    FLOWS[name](pw)
                    print(f"  [OK ] {name}{tag}")
                except Exception as e:
                    all_ok = False
                    print(f"  [FAIL] {name}{tag}: {e}")
                    traceback.print_exc()

    print("\n[verify] " + ("ALLE FLOWS GRÜN" if all_ok else "FEHLER — siehe oben"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

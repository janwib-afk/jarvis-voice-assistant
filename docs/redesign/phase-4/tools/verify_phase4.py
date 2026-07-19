# -*- coding: utf-8 -*-
"""Phase-4-Endabnahme gegen das Baseline-Harness (8341, Fake-LLM/TTS).

Portiert die R-/Flow-Checks aus docs/ux/tools/capture_ux.py auf die echte
produktive UI und ergaenzt die Pflicht-Screenshots (200 %, kleine Hoehe).
Exit 1 bei Fails oder Konsolenfehlern.
"""
import os
import sys

from playwright.sync_api import sync_playwright

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "screenshots"))
URL = "http://127.0.0.1:8341"

INIT_MIC = """
navigator.mediaDevices.getUserMedia = () => Promise.resolve({
    getTracks: () => [{ stop: () => {} }],
});
localStorage.setItem('jarvis.micMode', 'ptt');
"""

results, console_errors = [], []


def check(name, ok, note=""):
    results.append((name, ok))
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{' — ' + note if note else ''}")


def shot(page, name):
    page.screenshot(path=os.path.join(OUT, name))
    print(f"  [shot] {name}")


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                                  permissions=["microphone"], locale="de-DE")
        ctx.add_init_script(INIT_MIC)
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append("PAGEERROR " + str(e)))
        page.goto(URL)
        page.wait_for_timeout(1500)

        fonts = page.evaluate("() => ['15px Fraunces', \"13px 'IBM Plex Sans'\", \"11px 'IBM Plex Mono'\"].map(f => document.fonts.check(f))")
        check("AP1: Fraunces/Plex Sans/Plex Mono geladen", all(fonts), str(fonts))

        # R1: Kopfzeile + Stop gemeinsam im Viewport — alle drei Modi.
        def frame_check(label):
            head = page.locator("#win-bar").bounding_box()
            stop = page.locator("#stop-btn").bounding_box()
            vp = page.viewport_size
            ok = (head and stop and head["y"] >= -1
                  and stop["y"] + stop["height"] <= vp["height"] + 1)
            check(f"R1 {label}: Kopfzeile + Stop im Frame", bool(ok))

        frame_check("Vollbild")
        page.evaluate("applyUiMode('focus')")
        page.set_viewport_size({"width": 1000, "height": 800})
        page.wait_for_timeout(200)
        frame_check("Fokus")
        page.evaluate("applyUiMode('panel')")
        page.set_viewport_size({"width": 420, "height": 560})
        page.wait_for_timeout(200)
        frame_check("Panel")
        check("R4 Panel: Modus-Schalter sichtbar",
              page.locator("#window-mode-switch").is_visible())
        check("R4 Panel: Klartext-Status sichtbar",
              "verbunden" in page.locator("#sc-conn-text").inner_text())
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.evaluate("applyUiMode('fullscreen')")
        page.wait_for_timeout(200)

        # Zustandswort-Map (STATE_MODEL): Wort + Zeilenklasse je Zustand.
        words = {"idle": "Bereit", "listening": "Hört zu", "thinking": "Denkt nach",
                 "speaking": "Spricht", "error": "Störung — Details im Banner"}
        ok_words = True
        for st, word in words.items():
            page.evaluate("(function(w){var D=function(e){return dispatchVoice(Object.assign({epoch:window.__voice.state.epoch},e));};D({type:'StopRequested'});D({type:'StopAck'});if(window.__voice.state.capture==='muted')D({type:'MuteToggled'});if(window.__voice.state.capture==='listening')D({type:'RecognitionEnd'});D({type:'ErrorDismissed',overlay:'fatal-error'});D({type:'ErrorDismissed',overlay:'recoverable-error'});if(w==='listening')D({type:'StartListening'});else if(w==='thinking')D({type:'SayTextSent'});else if(w==='speaking'){D({type:'UserGesture'});D({type:'AudioReceived',audio:'x'});}else if(w==='muted')D({type:'MuteToggled'});else if(w==='error')D({type:'ErrorEvent',fatal:true});renderVoice();})('%s')" % st)
            got = page.locator("#status").inner_text()
            cls = page.evaluate("document.getElementById('status-row').className")
            if got != word or f"s-{st}" not in cls:
                ok_words = False
                print(f"    {st}: '{got}' / {cls}")
        check("AP11: Zustandswort + Statuszeilen-Klasse je Zustand", ok_words)
        page.evaluate("(function(w){var D=function(e){return dispatchVoice(Object.assign({epoch:window.__voice.state.epoch},e));};D({type:'StopRequested'});D({type:'StopAck'});if(window.__voice.state.capture==='muted')D({type:'MuteToggled'});if(window.__voice.state.capture==='listening')D({type:'RecognitionEnd'});D({type:'ErrorDismissed',overlay:'fatal-error'});D({type:'ErrorDismissed',overlay:'recoverable-error'});if(w==='listening')D({type:'StartListening'});else if(w==='thinking')D({type:'SayTextSent'});else if(w==='speaking'){D({type:'UserGesture'});D({type:'AudioReceived',audio:'x'});}else if(w==='muted')D({type:'MuteToggled'});else if(w==='error')D({type:'ErrorEvent',fatal:true});renderVoice();})('idle')")

        # Mute: aria-pressed + Klartext + Orb.
        page.click("#mute-btn")
        page.wait_for_timeout(150)
        check("Flow 8: Mute → aria-pressed + Klartext + Zustandswort",
              page.locator("#mute-btn").get_attribute("aria-pressed") == "true"
              and "stumm" in page.locator("#sc-mic-text").inner_text()
              and page.locator("#status").inner_text() == "Mikrofon stumm")
        shot(page, "zustand--muted-fussleiste.png")
        page.click("#mute-btn")

        # Laufende Aktion in der Statuszeile — ueber denselben Codepfad wie der
        # WS-Handler (addActionEntry ist die eine Darstellungsfunktion).
        page.fill("#text-input", "Recherchiere bitte die Reichweite von Elektroautos")
        page.keyboard.press("Control+Enter")
        page.wait_for_timeout(400)
        page.evaluate("addActionEntry({phase:'start', action:'RESEARCH', label:'Recherche', detail:'Elektroautos Reichweite', ts: Date.now()/1000})")
        page.wait_for_timeout(150)
        check("AP4: laufende Aktion erscheint in der Statuszeile",
              "Recherche" in page.locator("#status-action").inner_text())
        check("AP4: Esc-Hinweis sichtbar", page.locator("#status-esc").is_visible())
        check("AP4: Stop visuell primär während Aktion",
              "primary-now" in (page.locator("#stop-btn").get_attribute("class") or ""))
        shot(page, "zustand--action-running-statuszeile.png")
        page.evaluate("addActionEntry({phase:'done', action:'RESEARCH', label:'Recherche', ts: Date.now()/1000})")
        page.wait_for_timeout(150)
        check("AP4: Statuszeile leert sich nach Abschluss",
              page.locator("#status-action").inner_text().strip() == "")
        page.keyboard.press("Escape")
        page.wait_for_timeout(2200)

        check("AP5: Sprecher-Element statt Präfix",
              page.locator("#transcript .msg-speaker").first.inner_text() in ("Du", "Jarvis"))
        page.fill("#transcript-search", "Reichweite")
        page.wait_for_timeout(200)
        cnt = page.locator("#search-count").inner_text()
        check("Flow 11: Trefferzahl", "von" in cnt, cnt)
        shot(page, "flow--suche-treffer.png")
        page.fill("#transcript-search", "")
        page.wait_for_timeout(200)
        copy_btn = page.locator("#transcript .msg-copy").first
        copy_btn.focus()
        check("Flow 12: Copy-Button bei Tastaturfokus sichtbar",
              copy_btn.evaluate("el => getComputedStyle(el).opacity") == "1")

        # KZ: Selects (Weg B) + Karte + Bucht-Feedback.
        page.click('.pn-btn[data-app-page="control"]')
        page.wait_for_timeout(1200)
        check("Flow 16: Fokus auf KZ-Überschrift",
              page.evaluate("document.activeElement.id") == "control-heading")
        module = page.locator(".app-module").first
        module.click()
        page.wait_for_timeout(200)
        sel = page.locator(".app-module.selected .app-position select").first
        check("AP8: Positions-Selects im ausgewählten Modul sichtbar", sel.is_visible())
        page.locator(".app-module.selected .app-position select >> nth=1").select_option("bottom_left")
        page.locator(".app-module.selected .ap-save").click()
        saved = False
        for _ in range(20):
            page.wait_for_timeout(150)
            if "espeicher" in page.locator("#cc-map-status").inner_text():
                saved = True
                break
        check("Flow 19B: Position per Selects gespeichert (Bucht-Feedback)", saved,
              page.locator("#cc-map-status").inner_text())
        shot(page, "flow--position-selects.png")

        # Settings: dirty → Confirm → Weiter/Verwerfen; Fehlerfokus-Mechanik.
        page.click('.cc-tab[data-cc-view="settings"]')
        page.wait_for_timeout(600)
        page.fill('#settings-form input[name="user_name"]', "Jan W.")
        check("AP9: Ungespeichert-Pill", page.locator("#settings-dirty").is_visible())
        page.click("#btn-settings-cancel")
        check("AP9: Verwerfen-Rückfrage erscheint", page.locator("#settings-confirm").is_visible())
        shot(page, "flow--settings-confirm.png")
        page.click("#btn-keep")
        check("AP9: Weiter bearbeiten → Fokus im Formular",
              page.evaluate("document.activeElement.name || ''") != "")
        page.click("#btn-settings-cancel")
        page.click("#btn-discard")
        page.wait_for_timeout(300)
        check("AP9: Verwerfen kehrt zur Übersicht zurück",
              page.evaluate("document.documentElement.className").find("cc-view-settings") < 0)

        # Musik-Status-Wortlaut
        page.click('.cc-tab[data-cc-view="music"]')
        page.wait_for_timeout(600)
        page.locator(".music-item").first.click()
        page.wait_for_timeout(600)
        check("AP10: Musik-Status neuer Wortlaut",
              "nächsten Start" in page.locator("#music-status").inner_text())

        # Tastatur: Skip-Link zuerst.
        page.click('.pn-btn[data-app-page="jarvis"]')
        page.reload()
        page.wait_for_timeout(1200)
        page.keyboard.press("Tab")
        check("AP3: Skip-Link ist erstes Tab-Ziel",
              page.evaluate("document.activeElement.id") == "skip-link")
        page.keyboard.press("Enter")
        check("AP3: Skip-Link fokussiert Eingabe",
              page.evaluate("document.activeElement.id") == "text-input")
        shot(page, "zustand--tastaturfokus-eingabe.png")

        # Stress: kleine Hoehe + Zoom-200%-Naeherung.
        page.set_viewport_size({"width": 1280, "height": 640})
        page.wait_for_timeout(300)
        shot(page, "stress--kleine-hoehe-1280x640.png")
        frame_check("kleine Höhe")
        page.set_viewport_size({"width": 760, "height": 540})
        page.wait_for_timeout(300)
        no_h = page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        check("AP12: Zoom-200%-Näherung ohne H-Scroll + Stop sichtbar",
              bool(no_h and page.locator('#stop-btn').is_visible()))
        shot(page, "stress--zoom200-naeherung.png")
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.emulate_media(reduced_motion="reduce")
        shot(page, "zustand--reduced-motion.png")

        browser.close()

    ok = sum(1 for _, o in results if o)
    print(f"\n[verify] {ok}/{len(results)} Prüfungen erfolgreich")
    real_errors = [e for e in console_errors if "favicon" not in e]
    if real_errors:
        print(f"[warn] Konsolenfehler: {real_errors[:6]}")
    fails = [n for n, o in results if not o]
    if fails:
        print("[FAIL] " + "; ".join(fails))
    return 1 if (fails or real_errors) else 0


if __name__ == "__main__":
    sys.exit(main())

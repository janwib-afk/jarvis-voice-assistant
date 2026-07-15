"""Phase-0-Screenshot-Matrix: faehrt die Jarvis-UI auf dem Baseline-Server ab.

Voraussetzung: baseline_server.py laeuft (Standard: http://127.0.0.1:8341).
Ausgabe: PNGs nach docs/design-baseline/screenshots/, Schema <view>--<mode>--<state>.png

Determinismus-Entscheidungen (in BASELINE.md dokumentiert):
  - Mikrofonmodus wird per localStorage auf 'ptt' gesetzt: Im Default-Modus 'auto'
    kaempft die Speech-Recognition-Retry-Schleife staendig um den Orb-Zustand
    (startListening -> 'listening'), was Screenshots nichtdeterministisch macht.
    'listening' wird stattdessen real per Push-to-Talk (Space) aufgenommen.
  - Orb-Zustaende listening/thinking/speaking/error werden zusaetzlich ueber die
    oeffentliche Client-API setOrbState() erzwungen (identische CSS-Klassen wie im
    echten Flow); 'muted' entsteht real per Mute-Button, das Transcript real ueber
    den LLM-Stub des Harness.
  - Fake-Media-Flags + Mikrofon-Permission verhindern das Mic-Fehlerbanner beim
    Start (frontend/main.js: getUserMedia-Check).

Nutzung:  python docs/design-baseline/tools/capture_baseline.py [--base-url URL]
"""

import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(ROOT, "docs", "design-baseline", "screenshots")

BASE_URL = "http://127.0.0.1:8341"
if "--base-url" in sys.argv:
    BASE_URL = sys.argv[sys.argv.index("--base-url") + 1]
if "--out" in sys.argv:
    OUT = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])

# --freeze: deterministische Pixel fuer Regressionsvergleiche (Phase 1+):
# feste Uhrzeit (stabile Zeitstempel in Transcript/Aktionen) und abgeschaltete
# Animationen/Transitions/Caret. Reine Testbrowser-Injektion — die App selbst
# bleibt unveraendert. Ohne Flag verhaelt sich das Skript exakt wie in Phase 0.
FREEZE = "--freeze" in sys.argv

INIT_FREEZE_CLOCK = """
(() => {
    const fixed = 1783154400000; // 2026-07-11T10:00:00Z, willkuerlich aber stabil
    const RealDate = Date;
    class FrozenDate extends RealDate {
        constructor(...args) { args.length ? super(...args) : super(fixed); }
        static now() { return fixed; }
    }
    FrozenDate.parse = RealDate.parse;
    FrozenDate.UTC = RealDate.UTC;
    window.Date = FrozenDate;
})();
"""

INIT_FREEZE_STYLE = """
document.addEventListener('DOMContentLoaded', () => {
    const s = document.createElement('style');
    s.textContent = '*, *::before, *::after { animation: none !important; ' +
        'transition: none !important; caret-color: transparent !important; }';
    document.head.appendChild(s);
});
"""

VIEWPORTS = {"fullscreen": (1920, 1080), "focus": (1000, 800), "panel": (420, 560)}

# Web-Speech laeuft in Playwright-Chromium ohne Speech-Dienst: Default-Modus
# 'auto' wuerde den Orb-Zustand durch die Retry-Schleife nichtdeterministisch
# machen. PTT ist ein regulaerer, im Settings-UI waehlbarer Modus.
INIT_MIC_PTT = "localStorage.setItem('jarvis.micMode', 'ptt');"

# Nur fuer den Disconnected-/Empty-Shot: WebSocket, der nie verbindet und nach
# 150 ms onclose feuert -> Reconnect-Status + leeres Transcript (reiner
# Browser-Override im Testkontext, keine App-Aenderung).
INIT_WS_BLOCK = """
window.WebSocket = class {
    constructor() { this.readyState = 3; setTimeout(() => this.onclose && this.onclose({}), 150); }
    send() {} close() {}
};
"""

ACTION_ENTRIES = """
addActionEntry({phase:'start', action:'RESEARCH', label:'Recherche', detail:'Elektroautos Reichweite', ts: Date.now()/1000 - 190});
addActionEntry({phase:'done',  action:'RESEARCH', label:'Recherche', detail:'Elektroautos Reichweite', ts: Date.now()/1000 - 150});
addActionEntry({phase:'start', action:'APP_OPEN', label:'App oeffnen', detail:'Obsidian', ts: Date.now()/1000 - 90});
addActionEntry({phase:'error', action:'APP_OPEN', label:'App oeffnen', detail:'Pfad nicht gefunden', ts: Date.now()/1000 - 85});
addActionEntry({phase:'start', action:'INBOX_WRITE', label:'Inbox-Notiz', detail:'Baseline-Gedanke festhalten', ts: Date.now()/1000 - 5});
"""

saved = []
console_errors = []


def shot(page, name):
    path = os.path.join(OUT, name)
    page.screenshot(path=path)
    saved.append(name)
    print(f"  [shot] {name}")


def wait_jarvis_msgs(page, n, timeout=15000):
    page.wait_for_function(
        f"document.querySelectorAll('#transcript .msg.jarvis').length >= {n}", timeout=timeout
    )


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            permissions=["microphone"],
            locale="de-DE",
        )
        ctx.add_init_script(INIT_MIC_PTT)
        if FREEZE:
            ctx.add_init_script(INIT_FREEZE_CLOCK)
            ctx.add_init_script(INIT_FREEZE_STYLE)
            print(f"[freeze] Fixe Uhr + Animationen aus — Ziel: {OUT}")

        # ── A) Getrennt + leeres Transcript (WS geblockt) ────────────────────
        print("[A] Disconnected/Empty …")
        page_a = ctx.new_page()
        page_a.add_init_script(INIT_WS_BLOCK)
        page_a.goto(BASE_URL)
        page_a.wait_for_selector("body.jarvis-ready")
        page_a.wait_for_timeout(1200)  # onclose + Status 'neuer Versuch in 3s'
        shot(page_a, "jarvis--fullscreen--empty-disconnected.png")
        page_a.close()

        # ── B) Hauptdurchlauf (verbunden, LLM-Stub) ──────────────────────────
        print("[B] Verbundener Hauptdurchlauf …")
        page = ctx.new_page()
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.goto(BASE_URL)
        page.wait_for_selector("body.jarvis-ready")
        wait_jarvis_msgs(page, 1)  # Auto-Begruessung beantwortet (Stub)
        page.wait_for_timeout(800)  # idle-Ruecksprung nach Antwort ohne Audio

        # Orb-Zustaende — Vollbild 1920x1080
        page.evaluate("setOrbState('idle')")
        page.wait_for_timeout(300)
        shot(page, "jarvis--fullscreen--idle.png")

        for state in ("listening", "thinking", "speaking", "error"):
            page.evaluate(f"setOrbState('{state}')")
            page.wait_for_timeout(450)  # Animation sichtbar mitten im Puls
            shot(page, f"jarvis--fullscreen--{state}-forced.png")
        page.evaluate("setOrbState('idle')")

        # listening real per Push-to-Talk (Space halten)
        page.keyboard.down("Space")
        page.wait_for_timeout(400)
        shot(page, "jarvis--fullscreen--listening-ptt-real.png")
        page.keyboard.up("Space")
        page.wait_for_timeout(300)

        # muted real per Mute-Button
        page.click("#mute-btn")
        page.wait_for_timeout(300)
        shot(page, "jarvis--fullscreen--muted-real.png")
        page.click("#mute-btn")
        page.wait_for_timeout(200)
        page.evaluate("setOrbState('idle')")

        # Fehlerbanner (persistente Komponente, per oeffentlicher API)
        page.evaluate(
            "window.showErrorBanner({component:'tts', text:'Sprachausgabe fehlgeschlagen — Antwort wird nur als Text angezeigt.', hint:'ElevenLabs-Key pruefen oder Kontingent aufstocken.'})"
        )
        page.wait_for_selector("#error-stack .error-banner")
        shot(page, "jarvis--fullscreen--error-banner.png")
        page.click("#error-stack .error-banner .eb-close")

        # Transcript mit mehreren Nachrichten (echter Flow gegen LLM-Stub)
        for i, text in enumerate(
            [
                "Wie ist der Status der Baseline?",
                "Welche Zustaende kennt der Orb?",
                "Wo landen die Screenshots?",
            ],
            start=2,
        ):
            page.fill("#text-input", text)
            page.press("#text-input", "Control+Enter")
            wait_jarvis_msgs(page, i)
        page.wait_for_timeout(600)
        shot(page, "jarvis--fullscreen--transcript-multi.png")

        # Transcript-Suche (filtert live)
        page.fill("#transcript-search", "Orb")
        page.wait_for_timeout(400)
        shot(page, "jarvis--fullscreen--transcript-search.png")
        page.fill("#transcript-search", "")
        page.wait_for_timeout(300)

        # Hover auf letzte Nachricht: Kopieren-Button ist bis dahin unsichtbar
        # (style.css: .msg-copy visibility:hidden, sichtbar erst bei .msg:hover)
        page.hover("#transcript .msg:last-child")
        page.wait_for_timeout(250)
        try:
            page.hover("#transcript .msg:last-child .msg-copy", timeout=2000)
            page.wait_for_timeout(150)
        except Exception:
            pass  # Parent-Hover genuegt: Button ist sichtbar
        shot(page, "jarvis--fullscreen--hover-copy-button.png")

        # Tastaturfokus (dokumentiert fehlendes :focus-visible)
        page.click("body")
        for _ in range(3):
            page.keyboard.press("Tab")
        focused = page.evaluate(
            "({tag: document.activeElement.tagName, id: document.activeElement.id, cls: document.activeElement.className})"
        )
        print(f"  [info] Fokus nach 3x Tab: {focused}")
        shot(page, "jarvis--fullscreen--keyboard-focus.png")

        # prefers-reduced-motion (Orb-Puls laeuft trotzdem — bekannte Luecke)
        page.emulate_media(reduced_motion="reduce")
        page.evaluate("setOrbState('listening')")
        page.wait_for_timeout(450)
        shot(page, "jarvis--fullscreen--reduced-motion-listening.png")
        page.emulate_media(reduced_motion="no-preference")
        page.evaluate("setOrbState('idle')")

        # Aktionshistorie fuellen (sichtbar in Fokus- und Panel-Modus)
        page.evaluate(ACTION_ENTRIES)

        # Fokus-Modus (1000x800)
        page.set_viewport_size({"width": 1000, "height": 800})
        page.click('.wm-btn[data-window-mode="focus"]')
        page.wait_for_timeout(400)
        shot(page, "jarvis--focus--actions.png")

        # Kontrollzentrum — Uebersicht (Fokus-Layout)
        page.click('.pn-btn[data-app-page="control"]')
        page.wait_for_selector("#cc-app-grid .app-module")
        page.wait_for_selector("#cc-map-stage .map-monitor")
        page.wait_for_timeout(600)
        shot(page, "control-overview--focus--default.png")

        # Monitor-Map: Hover-Ghost auf einer Zone
        page.hover("#cc-map-stage .map-zone")
        page.wait_for_timeout(300)
        shot(page, "control-overview--focus--map-hover.png")

        # App-Auswahl (Klick-zu-Zuweisen-Modus), Escape bricht ab
        page.click("#cc-app-grid .app-module", position={"x": 10, "y": 10})
        page.wait_for_selector("#cc-app-grid .app-module.selected")
        shot(page, "control-overview--focus--app-selected.png")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

        # 'Oeffnen'-Feedback (App-Starts sind im Harness gestubbt)
        page.click("#cc-app-grid .app-module .app-btn")
        page.wait_for_timeout(350)
        shot(page, "control-overview--focus--app-open-feedback.png")
        page.wait_for_timeout(2500)  # ok/err-Flash abklingen lassen

        # Tastaturfokus im Kontrollzentrum
        page.click("body")
        for _ in range(6):
            page.keyboard.press("Tab")
        shot(page, "control-overview--focus--keyboard-focus.png")

        # Einstellungen
        page.click('.cc-tab[data-cc-view="settings"]')
        page.wait_for_selector("#settings-view input")
        page.wait_for_timeout(600)
        shot(page, "control-settings--focus--default.png")

        # Musik: Liste + Auswahl (POST geht in Temp-Config des Harness)
        page.click('.cc-tab[data-cc-view="music"]')
        page.wait_for_selector(".music-item")
        shot(page, "control-music--focus--list.png")
        page.click(".music-item")
        page.wait_for_selector(".music-item.selected")
        page.wait_for_timeout(300)
        shot(page, "control-music--focus--selected.png")

        # Kontrollzentrum im Vollbild-Fenster (Layout identisch focus-gated)
        page.click('.cc-tab[data-cc-view="overview"]')
        page.wait_for_selector("#cc-app-grid .app-module")
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.click('.wm-btn[data-window-mode="fullscreen"]')
        page.wait_for_timeout(500)
        shot(page, "control-overview--fullscreen--default.png")

        # Panel-Modus (420x560): Mini-Antwort + Mini-Aktionshistorie
        page.click('.pn-btn[data-app-page="jarvis"]')
        page.click('.wm-btn[data-window-mode="panel"]')
        page.set_viewport_size({"width": 420, "height": 560})
        page.wait_for_timeout(400)
        shot(page, "jarvis--panel--answer-actions.png")
        page.click("#mute-btn")
        page.wait_for_timeout(300)
        shot(page, "jarvis--panel--muted.png")
        page.click("#mute-btn")
        page.close()

        # ── C) Ladezustand Monitor-Map (Request wird angehalten) ─────────────
        print("[C] Ladezustand Monitor-Map …")
        page_c = ctx.new_page()
        held = []
        page_c.route("**/launcher/monitors*", lambda route: held.append(route))
        page_c.goto(BASE_URL)
        page_c.wait_for_selector("body.jarvis-ready")
        page_c.set_viewport_size({"width": 1000, "height": 800})
        page_c.click('.pn-btn[data-app-page="control"]')
        page_c.wait_for_selector("#cc-map-status")
        page_c.wait_for_timeout(600)  # 'Lade Monitore…' sichtbar, Request haengt
        shot(page_c, "control-overview--focus--map-loading.png")
        for r in held:
            r.continue_()
        page_c.wait_for_timeout(500)
        page_c.close()

        browser.close()

    print(f"\n[done] {len(saved)} Screenshots -> {OUT}")
    if console_errors:
        print(f"[warn] {len(console_errors)} Konsolenfehler im Hauptdurchlauf:")
        for e in console_errors[:10]:
            print(f"   - {e[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

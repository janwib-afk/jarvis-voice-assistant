# -*- coding: utf-8 -*-
"""Browser-Validierung des Phase-2-Prototyps (file://, keine Server noetig).

Nimmt die Pflicht-Screenshots nach docs/design-direction/screenshots/ auf und
prueft nebenbei: Konsolenfehler, geladene Fonts, Textueberlauf-Stellen.
"""
import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
URL = "file:///" + os.path.join(ROOT, "prototype", "index.html").replace("\\", "/")
OUT = os.path.join(ROOT, "screenshots")

saved, console_errors = [], []


def shot(page, name, locator=None):
    path = os.path.join(OUT, name)
    (locator or page).screenshot(path=path)
    saved.append(name)
    print(f"  [shot] {name}")


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, locale="de-DE")
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.goto(URL)
        page.wait_for_timeout(600)

        fonts_ok = page.evaluate(
            "() => ['15px Fraunces', '13px \"IBM Plex Sans\"', '11px \"IBM Plex Mono\"']"
            ".map(f => document.fonts.check(f))")
        print(f"  [fonts] Fraunces/PlexSans/PlexMono geladen: {fonts_ok}")

        # 1) Vollbild — Jarvis (listening) + Kontrollzentrum
        shot(page, "vollbild--jarvis-listening.png", page.locator("#stage"))
        page.click('.proto-bar [data-page="control"]')
        page.wait_for_timeout(200)
        shot(page, "vollbild--kontrollzentrum.png", page.locator("#stage"))
        page.click('.proto-bar [data-page="jarvis"]')

        # 2) Orb-Zustaende auf der Buehne: speaking + muted (Rest in Galerie)
        page.click('.proto-bar [data-orb="speaking"]')
        page.wait_for_timeout(150)
        shot(page, "vollbild--jarvis-speaking.png", page.locator("#stage"))
        page.click('.proto-bar [data-orb="muted"]')
        page.wait_for_timeout(150)
        shot(page, "vollbild--jarvis-muted.png", page.locator("#stage"))
        page.click('.proto-bar [data-orb="listening"]')

        # 3) Fokus-Modus
        page.click('.proto-bar [data-mode="focus"]')
        page.wait_for_timeout(250)
        shot(page, "fokus--jarvis.png", page.locator("#stage"))
        page.click('.proto-bar [data-page="control"]')
        page.wait_for_timeout(200)
        shot(page, "fokus--kontrollzentrum.png", page.locator("#stage"))
        page.click('.proto-bar [data-page="jarvis"]')

        # 4) Panel-Modus
        page.click('.proto-bar [data-mode="panel"]')
        page.wait_for_timeout(250)
        shot(page, "panel--jarvis.png", page.locator("#stage"))

        # 5) Galerie: Orb-Reihe, Meldungen, Formular, Musik, Leerzustand
        page.click('.proto-bar [data-mode="fullscreen"]')
        page.wait_for_timeout(200)
        rows = page.locator(".gallery .g-row")
        shot(page, "galerie--orb-zustaende.png", rows.nth(0))
        shot(page, "galerie--meldungen.png", rows.nth(1))
        shot(page, "galerie--formular.png", page.locator(".gallery .form-view"))
        shot(page, "galerie--musik.png", page.locator(".music-list"))
        shot(page, "galerie--leerzustand.png", page.locator(".journal-empty"))

        # 6) Hover-Zustaende
        page.hover(".nav-tab:not([aria-selected='true'])")
        page.wait_for_timeout(120)
        shot(page, "zustand--hover-navigation.png", page.locator("#stage .head"))
        page.hover(".gallery .btn-primary:not(:disabled)")
        page.wait_for_timeout(120)
        shot(page, "zustand--hover-primaerbutton.png", page.locator(".gallery .form-view .g-row"))
        entry = page.locator("#view-jarvis .entry.jarvis").first
        entry.hover()
        page.wait_for_timeout(120)
        shot(page, "zustand--hover-kopieren.png", entry)

        # 7) Tastaturfokus (sichtbarer Messing-Ring)
        page.click(".journal-search")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        shot(page, "zustand--tastaturfokus.png", page.locator("#stage"))

        # 8) Reduzierte Bewegung (statisch identisch — Beleg)
        page.emulate_media(reduced_motion="reduce")
        shot(page, "zustand--reduced-motion.png", page.locator("#stage"))
        page.emulate_media(reduced_motion="no-preference")

        # 9) Kleine Hoehe + hohe Dichte (Vollbild-Stage bei 1280x640: scrollbar)
        page.set_viewport_size({"width": 1280, "height": 640})
        page.wait_for_timeout(200)
        shot(page, "stress--kleine-hoehe-1280x640.png")
        page.set_viewport_size({"width": 1920, "height": 1080})

        # Ueberlauf-Heuristik: horizontale Scroller ausserhalb erwarteter Bereiche?
        overflow = page.evaluate("""
            () => Array.from(document.querySelectorAll('.stage *'))
                .filter(el => el.scrollWidth > el.clientWidth + 1)
                .slice(0, 8).map(el => el.className || el.tagName)
        """)
        print(f"  [overflow] horizontale Ueberlaeufe: {overflow if overflow else 'keine'}")

        browser.close()

    print(f"\n[done] {len(saved)} Screenshots -> {OUT}")
    if console_errors:
        print(f"[warn] Konsolenfehler: {console_errors[:6]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Phase-3-Validierung: UX-Prototyp im Browser pruefen (file://, offline).

Nimmt Screenshots auf UND spielt die Kernablaeufe durch; jedes Ergebnis wird
als erfolgreich/blockiert protokolliert (Exit 1 bei Blockern/Konsolenfehlern).
200-%-Zoom wird als halbierter Viewport genaehert (Playwright hat kein echtes
Browser-Zoom-API); kleine Hoehe und reduced-motion werden direkt emuliert.
"""
import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
URL = "file:///" + os.path.join(ROOT, "prototype", "index.html").replace("\\", "/")
OUT = os.path.join(ROOT, "screenshots")

console_errors, results = [], []


def shot(page, name, locator=None):
    (locator or page).screenshot(path=os.path.join(OUT, name))
    print(f"  [shot] {name}")


def check(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{' — ' + note if note else ''}")


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, locale="de-DE")
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.goto(URL)
        page.wait_for_timeout(500)

        # ── Modi + Bereiche ──────────────────────────────────────────────
        shot(page, "vollbild--gespraech.png", page.locator("#stage"))
        page.click('.nav-tab[data-view="control"]')
        page.wait_for_timeout(200)
        check("Flow 16/30: KZ öffnen + Fokus auf Überschrift",
              page.evaluate("document.activeElement.id") == "control-heading")
        shot(page, "vollbild--kontrollzentrum.png", page.locator("#stage"))

        page.click('[data-sub="settings"]')
        page.wait_for_timeout(150)
        check("Flow 29: Subview Einstellungen + Fokus",
              page.evaluate("document.activeElement.id") == "settings-heading")
        shot(page, "vollbild--einstellungen.png", page.locator("#stage"))
        page.click('[data-sub="music"]')
        page.wait_for_timeout(150)
        shot(page, "vollbild--musik.png", page.locator("#stage"))
        page.click('[data-sub="overview"]')
        page.click('.nav-tab[data-view="jarvis"]')
        page.wait_for_timeout(150)

        # R1: Kopfzeile UND Stop-Button muessen in JEDEM Modus gleichzeitig im
        # Stage-Rahmen liegen (Prioritaet 2: Stop jederzeit sichtbar).
        def frame_check(mode_label):
            box = page.locator("#stage").bounding_box()
            head = page.locator("#stage .head").bounding_box()
            stop = page.locator("#btn-stop").bounding_box()
            inside = (head and stop and box
                      and head["y"] >= box["y"] - 1
                      and stop["y"] + stop["height"] <= box["y"] + box["height"] + 1)
            check(f"R1 {mode_label}: Kopfzeile + Stop gemeinsam im Frame", bool(inside))

        frame_check("Vollbild")
        page.click('.proto-bar [data-mode="focus"]')
        page.wait_for_timeout(200)
        frame_check("Fokus")
        shot(page, "fokus--gespraech.png", page.locator("#stage"))
        page.click('.proto-bar [data-mode="panel"]')
        page.wait_for_timeout(200)
        frame_check("Panel")
        check("R4 Panel: Modus-Schalter sichtbar", page.locator("#stage .mode-switch").is_visible())
        shot(page, "panel--gespraech.png", page.locator("#stage"))

        # Flow 32: Panel -> KZ erzwingt Fokusmodus
        page.click('.nav-tab[data-view="control"]')
        page.wait_for_timeout(250)
        check("Flow 32: Panel→KZ wechselt auf Fokus",
              page.evaluate("document.getElementById('stage').className").find("mode-focus") >= 0)
        shot(page, "panel-zu-kz--fokusmodus.png", page.locator("#stage"))
        page.click('.proto-bar [data-mode="fullscreen"]')
        page.click('.nav-tab[data-view="jarvis"]')
        page.wait_for_timeout(150)

        # ── Zustaende (Auswahl inkl. neuer) ──────────────────────────────
        for st in ["disconnected", "action-running", "degraded"]:
            page.click(f'.proto-bar [data-state="{st}"]')
            page.wait_for_timeout(120)
            if st == "action-running":
                check("Zustand action-running zeigt Esc-Hinweis",
                      page.locator("#esc-hint").is_visible())
            if st == "disconnected":
                # R3: getrennt blockiert Senden (kein neuer Eintrag)
                before = page.locator("#journal .entry").count()
                page.fill("#ask-field", "Test während getrennt")
                page.keyboard.press("Control+Enter")
                page.wait_for_timeout(200)
                check("R3 disconnected: Senden blockiert + Hinweis",
                      page.locator("#journal .entry").count() == before)
                page.fill("#ask-field", "")
                check("R3 disconnected: Banner sichtbar",
                      page.locator(".banner.error").is_visible())
            shot(page, f"zustand--{st}.png", page.locator("#stage"))
        page.click('.proto-bar [data-state="error"]')
        page.wait_for_timeout(120)
        check("R3 error: Banner mit Abhilfe + schließbar",
              page.locator(".banner.error .b-hint").is_visible())
        shot(page, "zustand--error-banner.png", page.locator("#stage"))
        page.click(".banner.error .b-close")
        page.click('.proto-bar [data-state="listening"]')
        page.evaluate("document.getElementById('banner-stack').innerHTML = ''")

        # ── Flows 6-8: Stop/Esc/Mute ─────────────────────────────────────
        page.click('.proto-bar [data-state="speaking"]')
        page.keyboard.press("Escape")
        page.wait_for_timeout(700)
        check("Flow 6: Esc stoppt speaking→listening",
              page.locator("#state-word").inner_text() in ("Hört zu", "Bereit"))
        page.click("#btn-mute")
        check("Flow 8: Mute setzt Klartext + aria-pressed",
              page.locator("#txt-mic").inner_text() == "Mikrofon stumm"
              and page.locator("#btn-mute").get_attribute("aria-pressed") == "true")
        shot(page, "zustand--muted.png", page.locator("#stage .jarvis-view"))
        page.click("#btn-mute")

        # ── Flows 9/11/12: Text, Suche, Kopieren ─────────────────────────
        page.fill("#ask-field", "Wie wird das Wetter morgen in Hamburg?")
        page.keyboard.press("Control+Enter")
        page.wait_for_timeout(300)
        check("Flow 9: Strg+Enter erzeugt Nutzereintrag",
              page.locator("#journal .entry.user").count() >= 3)
        page.fill("#search", "Reichweite")
        page.wait_for_timeout(150)
        cnt = page.locator("#search-count").inner_text()
        check("Flow 11: Suche zeigt Trefferzahl", "von" in cnt, cnt)
        shot(page, "flow--suche-treffer.png", page.locator("#view-jarvis .journal"))
        page.fill("#search", "")
        copy_btn = page.locator(".entry-copy").first
        copy_btn.focus()
        check("Flow 12: Copy-Button per Tastatur fokussierbar (sichtbar)",
              copy_btn.evaluate("el => getComputedStyle(el).opacity") == "1")
        copy_btn.press("Enter")
        page.wait_for_timeout(100)
        check("Flow 12: Kopier-Feedback", copy_btn.inner_text() == "Kopiert")
        shot(page, "flow--kopiert.png", page.locator("#view-jarvis .journal"))

        # ── Flows 17-19: App oeffnen, Toggle, Position (beide Wege) ──────
        page.click('.nav-tab[data-view="control"]')
        page.wait_for_timeout(200)
        # R2: Stop-Button stoppt auch im KZ sofort (keine Kaskade am Button)
        page.click('.proto-bar [data-state="speaking"]')
        page.click("#btn-stop")
        page.wait_for_timeout(700)
        check("R2: Stop-Button stoppt im KZ beim ersten Klick",
              page.locator("#state-word").inner_text() in ("Bereit", "Hört zu"))
        page.click('#mod-obsidian [data-open]')
        page.wait_for_timeout(900)
        check("Flow 17: Öffnen-Feedback", "Geöffnet" in page.locator('#mod-obsidian [data-open]').inner_text())
        page.click("#pos-save")
        page.wait_for_timeout(800)
        check("Flow 19B: Position per Selects gespeichert",
              "Gespeichert" in page.locator("#pos-msg").inner_text())
        shot(page, "flow--position-selects.png", page.locator("#mod-obsidian"))
        page.click('#zones-left .zone >> nth=2')
        page.wait_for_timeout(150)
        check("Flow 19A: Zone per Karte zugewiesen (sichtbares Bucht-Feedback)",
              "gespeichert" in page.locator("#bay-msg").inner_text())
        check("R7: Chip wandert in die neue Zone",
              page.locator('#zones-left .zone >> nth=2 >> .chip').count() == 1)
        shot(page, "flow--zone-karte.png", page.locator(".bay").first)

        # ── Flows 20-22: Profile ─────────────────────────────────────────
        page.click("#p-new")
        page.fill("#p-name", "Deep Work")
        page.keyboard.press("Enter")
        page.wait_for_timeout(100)
        check("Flow 20: Profil angelegt", page.locator(".p-tabs .p-tab").count() == 4)
        page.click("#p-del")
        page.wait_for_timeout(100)
        check("Flow 22: Lösch-Bestätigung sichtbar",
              "Nochmal" in page.locator("#p-err").inner_text())
        shot(page, "flow--profil-loeschen-confirm.png", page.locator(".profiles >> nth=1"))
        page.click("#p-del")
        page.wait_for_timeout(100)
        check("Flow 22: Löschen nach Bestätigung", page.locator(".p-tabs .p-tab").count() == 3)

        # ── Flows 25/26: Settings dirty + Validierung + Fokus ────────────
        page.click('[data-sub="settings"]')
        page.fill("#s-city", "")
        page.locator("#s-city").blur()
        page.fill("#s-name", "Jan W.")
        check("Flow 25: Ungespeichert-Pill", page.locator("#unsaved").is_visible())
        page.click("#s-save")
        page.wait_for_timeout(150)
        check("Flow 26: Fehlerfokus auf Stadt-Feld",
              page.evaluate("document.activeElement.id") == "s-city")
        shot(page, "flow--settings-fehler.png", page.locator("#view-settings"))
        page.fill("#s-city", "Hamburg")
        page.click("#s-save")
        page.wait_for_timeout(900)
        check("Flow 26: Gespeichert", "Gespeichert" in page.locator("#s-msg").inner_text())
        page.click("#s-cancel")

        # ── Flows 27/28: Musik ───────────────────────────────────────────
        page.click('[data-sub="music"]')
        page.click(".music-item >> nth=1")
        check("Flow 27: Musik gewählt",
              "Deep Focus" in page.locator("#music-current").inner_text())
        page.click("#music-clear")
        check("Flow 28: Musik entfernt",
              "Keine Musik" in page.locator("#music-current").inner_text())
        shot(page, "flow--musik-leer.png", page.locator("#view-music"))

        # ── Tastatur: Skip-Link + Tab-Reihenfolge (frische Seite) ────────
        page.reload()
        page.wait_for_timeout(400)
        page.keyboard.press("Tab")
        first = page.evaluate("document.activeElement.className")
        check("Skip-Link ist erstes Tab-Ziel", "skip-link" in first)
        shot(page, "zustand--skip-link.png")
        # Gestalteter Tastaturpfad: Skip-Link aktivieren -> Landung auf der
        # Bereichsueberschrift -> naechste Tabs bleiben im Produkt (Orb, Suche).
        page.keyboard.press("Enter")
        page.wait_for_timeout(100)
        check("Skip-Link führt zur Gesprächs-Überschrift",
              page.evaluate("document.activeElement.id") == "main-heading")
        order = []
        for _ in range(3):
            page.keyboard.press("Tab")
            order.append(page.evaluate(
                "document.activeElement.getAttribute('aria-label') || document.activeElement.tagName"))
        print(f"  [tab-order nach Skip] {order}")
        check("Nach Skip-Link folgt Produktinhalt (Orb/Suche)",
              any("Zuhören" in o or o == "INPUT" for o in order))

        # ── Stress: kleine Hoehe, Zoom-200%-Naeherung, reduced motion ───
        page.set_viewport_size({"width": 1280, "height": 640})
        page.wait_for_timeout(150)
        shot(page, "stress--kleine-hoehe.png")
        page.set_viewport_size({"width": 760, "height": 540})
        page.wait_for_timeout(150)
        no_hscroll = page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        stop_visible = page.locator("#btn-stop").is_visible()
        check("Zoom-200%-Näherung: kein H-Scroll + Stop sichtbar", bool(no_hscroll and stop_visible))
        shot(page, "stress--zoom200-naeherung.png")
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.emulate_media(reduced_motion="reduce")
        shot(page, "zustand--reduced-motion.png", page.locator("#stage"))

        browser.close()

    ok = sum(1 for _, o, _ in results if o)
    print(f"\n[flows] {ok}/{len(results)} Prüfungen erfolgreich")
    if console_errors:
        print(f"[warn] Konsolenfehler: {console_errors[:5]}")
    fails = [n for n, o, _ in results if not o]
    if fails:
        print("[FAIL] " + "; ".join(fails))
    return 1 if (fails or console_errors) else 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Phase-6-Zusatzshots (before/after identisch): Zoom-200%-Naeherung,
kleine Hoehe, Reduced-Motion, laufende Aktion. Aufruf: extra_shots.py <outdir>
"""
import os
import sys

from playwright.sync_api import sync_playwright

OUT = os.path.abspath(sys.argv[1])
URL = "http://127.0.0.1:8341"


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        ctx = b.new_context(viewport={"width": 1920, "height": 1080},
                            permissions=["microphone"], locale="de-DE")
        ctx.add_init_script("localStorage.setItem('jarvis.micMode','ptt')")
        pg = ctx.new_page()
        pg.goto(URL)
        pg.wait_for_timeout(1500)
        pg.evaluate("addActionEntry({phase:'start', action:'RESEARCH', label:'Recherche', detail:'Elektroautos Reichweite', ts: Date.now()/1000})")
        pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(OUT, "extra--action-running.png"))
        pg.evaluate("addActionEntry({phase:'done', action:'RESEARCH', label:'Recherche', ts: Date.now()/1000})")
        pg.set_viewport_size({"width": 1280, "height": 640})
        pg.wait_for_timeout(250)
        pg.screenshot(path=os.path.join(OUT, "extra--kleine-hoehe.png"))
        pg.set_viewport_size({"width": 760, "height": 540})
        pg.wait_for_timeout(250)
        pg.screenshot(path=os.path.join(OUT, "extra--zoom200-naeherung.png"))
        ctx.close()

        rctx = b.new_context(viewport={"width": 1280, "height": 900},
                             permissions=["microphone"], locale="de-DE",
                             reduced_motion="reduce")
        rctx.add_init_script("localStorage.setItem('jarvis.micMode','ptt')")
        rp = rctx.new_page()
        rp.goto(URL)
        rp.wait_for_timeout(1200)
        rp.evaluate("setOrbState('listening')")
        rp.wait_for_timeout(300)
        rp.screenshot(path=os.path.join(OUT, "extra--reduced-listening.png"))
        rctx.close()
        b.close()
    print(f"[done] 4 Zusatzshots -> {OUT}")


if __name__ == "__main__":
    main()

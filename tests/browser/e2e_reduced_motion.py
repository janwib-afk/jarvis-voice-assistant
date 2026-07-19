"""Reduced-Motion-Suite: prueft das App-Verhalten unter
``prefers-reduced-motion: reduce`` in einem eigenen Browserkontext.

Wichtig: KEIN eigenes Animation-Aus-Override (freeze=False) — getestet werden die
echten @media(prefers-reduced-motion)-Regeln der App, nicht eine Testinjektion.

Erwartung (Phase 5 / verify_phase5): keine Loop-Animationen (Orb/Sweep), Zustand
bleibt ueber Klasse + statischen Glow + Statuswort erkennbar, volle Funktion.

Nutzung:  python tests/browser/e2e_reduced_motion.py [--repeat N]
Exit 0 = alle Checks grün.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402
from e2e_harness import force_presentation, JarvisServer, browser_context, open_jarvis  # noqa: E402

RESULTS = []

STATE_WORDS = {
    "listening": "Hört zu", "thinking": "Denkt nach",
    "speaking": "Spricht", "error": "Störung — Details im Banner",
}


def check(name, ok, note=""):
    RESULTS.append((name, bool(ok)))
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{' — ' + note if note else ''}")


def anim_name(page, selector):
    return page.evaluate(
        f"(() => {{ const el = document.querySelector('{selector}'); "
        f"return el ? getComputedStyle(el).animationName : 'MISSING'; }})()")


def run(pw):
    with JarvisServer("rmotion") as srv, \
            browser_context(pw, srv.base_url, reduced_motion="reduce", freeze=False) as (page, col):
        open_jarvis(page, srv.base_url)

        # Loop-Animationen aus: Orb + Luenette-Sweep in allen Zustaenden.
        force_presentation(page, "idle")
        check("Orb idle: keine Animation", anim_name(page, "#orb") == "none",
              anim_name(page, "#orb"))
        check("Luenette-Sweep: keine Animation",
              anim_name(page, ".luenette-sweep") == "none", anim_name(page, ".luenette-sweep"))

        for state, word in STATE_WORDS.items():
            force_presentation(page, state)
            check(f"Orb {state}: keine Loop-Animation",
                  anim_name(page, "#orb") == "none", anim_name(page, "#orb"))
            # Zustand bleibt erkennbar: Klasse gesetzt + Statuswort im Klartext.
            check(f"Orb {state}: Zustand ueber Klasse erkennbar",
                  page.locator("#orb").get_attribute("class") == state)
            check(f"Orb {state}: Statuswort '{word}' sichtbar",
                  page.locator("#status").inner_text().strip() == word)
        force_presentation(page, "idle")

        # Volle Funktion trotz Reduced Motion: Nachricht senden funktioniert.
        srv.scenario(replies=["Reduced-Motion-Antwort erhalten."])
        page.get_by_label("Textnachricht an Jarvis").fill("test unter reduced motion")
        page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
        page.wait_for_function(
            "[...document.querySelectorAll('#transcript .msg.jarvis .msg-words')]"
            ".some(e => e.textContent.includes('Reduced-Motion-Antwort erhalten.'))")
        check("Kernfunktion (Senden) verfuegbar unter Reduced Motion", True)

        # Mute funktioniert und bleibt erkennbar (kein Informationsverlust).
        page.get_by_role("button", name="Mikrofon stummschalten").click()
        check("Mute unter Reduced Motion: Statuswort erhalten",
              page.locator("#status").inner_text().strip() == "Mikrofon stumm")

        col.assert_clean("reduced_motion")


def main():
    repeat = 1
    if "--repeat" in sys.argv:
        repeat = int(sys.argv[sys.argv.index("--repeat") + 1])
    ok_all = True
    with sync_playwright() as pw:
        for rep in range(1, repeat + 1):
            if repeat > 1:
                print(f"\n=== Wiederholung {rep}/{repeat} ===")
            RESULTS.clear()
            try:
                run(pw)
            except Exception:
                import traceback
                traceback.print_exc()
                ok_all = False
            if any(not ok for _, ok in RESULTS):
                ok_all = False
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n[verify] {passed}/{len(RESULTS)} Reduced-Motion-Checks erfolgreich")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Phase-5-Motion-Validierung am Harness (8341): Zustands-Animationen,
Unterbrechbarkeit, Spam-Festigkeit, Reduced Motion, Konsole — plus
Video-Evidence einer Kernsequenz nach docs/motion/evidence/.
"""
import os
import shutil
import sys

from playwright.sync_api import sync_playwright

EVID = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "evidence"))
URL = "http://127.0.0.1:8341"
results, console_errors = [], []

ORB_ANIMS = ("document.getElementById('orb').getAnimations({subtree:true})"
             ".filter(a => 'animationName' in a).map(a => a.animationName)")
SWEEP_ANIMS = ("document.querySelector('.luenette-sweep').getAnimations()"
               ".filter(a => 'animationName' in a).map(a => a.animationName)")


def check(name, ok, note=""):
    results.append((name, ok))
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{' — ' + note if note else ''}")


def orb_names(page):
    return page.evaluate(ORB_ANIMS)


def main():
    os.makedirs(EVID, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])

        # ── Hauptlauf (normal motion) ────────────────────────────────────
        ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                  permissions=["microphone"], locale="de-DE")
        ctx.add_init_script("localStorage.setItem('jarvis.micMode','ptt')")
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append("PAGEERROR " + str(e)))
        page.goto(URL)
        page.wait_for_timeout(1500)

        # Zustandsmatrix: erwartete Animationsnamen je Zustand.
        expect = {
            "idle": {"orb-breathe"},
            "listening": {"orb-listen", "glow-breathe"},
            "thinking": {"orb-think", "glow-focus"},
            "speaking": {"orb-speak", "glow-pulse"},
            "muted": set(),
        }
        ok_states = True
        for st, names in expect.items():
            if st == "muted":
                page.evaluate("isMuted = true; setOrbState('idle')")
            else:
                page.evaluate("isMuted = false; setOrbState('%s')" % st)
            page.wait_for_timeout(320)
            got = set(orb_names(page))
            if got != names:
                ok_states = False
                print(f"    {st}: {sorted(got)}")
        check("Orb: exakt die vorgesehenen Animationen je Zustand", ok_states)
        # Mute-Flag aus der Matrix zuruecksetzen — Folgechecks laufen entstummt.
        page.evaluate("isMuted = false; updateMuteButton(); setOrbState('idle')")
        page.wait_for_timeout(150)

        # error: 2 Pulse, endet statisch (nur Glow-Layer statisch an).
        page.evaluate("setOrbState('error')")
        page.wait_for_timeout(300)
        during = set(orb_names(page))
        page.wait_for_timeout(2300)
        after = set(orb_names(page))
        check("error: Impuls läuft (flash-error) und endet statisch",
              "flash-error" in during and after == set(), f"{sorted(during)} → {sorted(after)}")
        page.evaluate("setOrbState('idle')")

        # Wechsel ersetzt sofort (kein Alt-Loop überlebt).
        page.evaluate("setOrbState('listening')")
        page.wait_for_timeout(120)
        page.evaluate("setOrbState('speaking')")
        page.wait_for_timeout(250)
        got = set(orb_names(page))
        check("Zustandswechsel ersetzt Animationen sofort",
              got == {"orb-speak", "glow-pulse"}, str(sorted(got)))

        # action-running: Sweep an der Lünette, endet mit done.
        page.evaluate("addActionEntry({phase:'start', action:'RESEARCH', label:'Recherche', ts: Date.now()/1000})")
        page.wait_for_timeout(250)
        sweep_on = page.evaluate(SWEEP_ANIMS)
        page.evaluate("addActionEntry({phase:'done', action:'RESEARCH', label:'Recherche', ts: Date.now()/1000})")
        page.wait_for_timeout(350)
        sweep_off = page.evaluate(SWEEP_ANIMS)
        check("action-running: Lünetten-Sweep läuft und endet",
              sweep_on == ["sweep"] and sweep_off == [], f"{sweep_on} → {sweep_off}")

        # Stop unterbricht sofort (Esc während speaking/thinking).
        for st in ("speaking", "thinking"):
            page.evaluate(f"setOrbState('{st}')")
            page.wait_for_timeout(150)
            page.keyboard.press("Escape")
            page.wait_for_timeout(600)
            word = page.locator("#status").inner_text()
            names = set(orb_names(page))
            check(f"Esc während {st}: Zustand + Animation sofort ersetzt",
                  word in ("Bereit", "Hört zu") and names.issubset({"orb-breathe", "orb-listen", "glow-breathe"}),
                  f"{word} / {sorted(names)}")

        # Spam-Festigkeit: 6× Mute — keine Animationsschlange, Endzustand korrekt.
        for _ in range(6):
            page.click("#mute-btn", delay=10)
        page.wait_for_timeout(400)
        pressed = page.locator("#mute-btn").get_attribute("aria-pressed")
        cnt = len(orb_names(page))
        check("6×-Mute-Spam: konsistenter Endzustand, keine Queue",
              pressed == "false" and cnt <= 2, f"pressed={pressed}, anims={cnt}")

        # View-Enter: einmalig, selbstaufräumend, Fokus korrekt.
        page.click('.pn-btn[data-app-page="control"]')
        has_now = page.evaluate("document.getElementById('cc-shell').classList.contains('view-enter')")
        page.wait_for_timeout(500)
        has_later = page.evaluate("document.getElementById('cc-shell').classList.contains('view-enter')")
        check("Ansichtswechsel: Enter-Klasse läuft und räumt sich auf",
              has_now and not has_later)
        check("Fokus nach Wechsel unverändert korrekt",
              page.evaluate("document.activeElement.id") == "control-heading")
        page.click('.pn-btn[data-app-page="jarvis"]')
        page.wait_for_timeout(300)

        # msg-new nur am neuen Eintrag, räumt sich auf.
        page.fill("#text-input", "Kurzer Motion-Test")
        page.keyboard.press("Control+Enter")
        page.wait_for_timeout(60)
        fresh = page.evaluate("document.querySelectorAll('#transcript .msg-new').length")
        page.wait_for_timeout(400)
        gone = page.evaluate("document.querySelectorAll('#transcript .msg-new').length")
        check("Transcript: nur neuer Eintrag animiert, Klasse räumt sich auf",
              fresh == 1 and gone == 0, f"{fresh}→{gone}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(2300)

        # Banner: Enter-Animation + WAAPI-Exit entfernt Element.
        page.evaluate("showErrorBanner({component:'action', text:'Motion-Testmeldung', hint:'Verschwindet gleich.'})")
        page.wait_for_timeout(120)
        page.click(".error-banner .eb-close")
        page.wait_for_timeout(350)
        check("Banner: Exit via WAAPI entfernt Element",
              page.locator(".error-banner").count() == 0)

        shot = os.path.join(EVID, "normal--listening-glow.png")
        page.evaluate("setOrbState('listening')")
        page.wait_for_timeout(400)
        page.locator("#orb-container").screenshot(path=shot)
        print(f"  [shot] {os.path.basename(shot)}")
        ctx.close()

        # ── Reduced Motion: 0 laufende Animationen, Funktionen intakt ────
        rctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                   permissions=["microphone"], locale="de-DE",
                                   reduced_motion="reduce")
        rctx.add_init_script("localStorage.setItem('jarvis.micMode','ptt')")
        rpage = rctx.new_page()
        rpage.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        rpage.goto(URL)
        rpage.wait_for_timeout(1200)
        ok_reduced = True
        for st in ("idle", "listening", "thinking", "speaking", "error"):
            rpage.evaluate(f"setOrbState('{st}')")
            rpage.wait_for_timeout(250)
            n = rpage.evaluate(ORB_ANIMS)
            if n:
                ok_reduced = False
                print(f"    reduced {st}: {n}")
        rpage.evaluate("addActionEntry({phase:'start', action:'X', label:'X', ts:1})")
        rpage.wait_for_timeout(150)
        sweep_r = rpage.evaluate(SWEEP_ANIMS)
        check("Reduced Motion: 0 Orb-/Sweep-Animationen in allen Zuständen",
              ok_reduced and sweep_r == [], str(sweep_r))
        glow = rpage.evaluate(
            "getComputedStyle(document.getElementById('orb'), '::after').opacity")
        rpage.evaluate("setOrbState('listening')")
        rpage.wait_for_timeout(200)
        glow = rpage.evaluate(
            "getComputedStyle(document.getElementById('orb'), '::after').opacity")
        check("Reduced Motion: Zustands-Glow bleibt statisch sichtbar",
              float(glow) > 0.5, glow)
        rpage.locator("#orb-container").screenshot(path=os.path.join(EVID, "reduced--listening-static.png"))
        rctx.close()

        # ── Video-Evidence: Kernsequenz ──────────────────────────────────
        vctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                   permissions=["microphone"], locale="de-DE",
                                   record_video_dir=EVID,
                                   record_video_size={"width": 1280, "height": 900})
        vctx.add_init_script("localStorage.setItem('jarvis.micMode','ptt')")
        vpage = vctx.new_page()
        vpage.goto(URL)
        vpage.wait_for_timeout(1200)
        for st, ms in (("idle", 1500), ("listening", 2000), ("thinking", 1500), ("speaking", 1500)):
            vpage.evaluate(f"setOrbState('{st}')")
            vpage.wait_for_timeout(ms)
        vpage.evaluate("addActionEntry({phase:'start', action:'RESEARCH', label:'Recherche', detail:'Elektroautos', ts: Date.now()/1000})")
        vpage.wait_for_timeout(2500)
        vpage.keyboard.press("Escape")
        vpage.wait_for_timeout(1000)
        vpage.evaluate("setOrbState('error')")
        vpage.wait_for_timeout(2600)
        vpage.evaluate("setOrbState('idle')")
        vpage.click('.pn-btn[data-app-page="control"]')
        vpage.wait_for_timeout(1200)
        video_path = vpage.video.path()
        vctx.close()
        target = os.path.join(EVID, "sequenz--zustaende-stop-error-wechsel.webm")
        if os.path.exists(target):
            os.remove(target)
        shutil.move(video_path, target)
        print(f"  [video] {os.path.basename(target)} ({os.path.getsize(target)//1024} KB)")

        browser.close()

    ok = sum(1 for _, o in results if o)
    print(f"\n[verify] {ok}/{len(results)} Prüfungen erfolgreich")
    real = [e for e in console_errors if "favicon" not in e]
    if real:
        print(f"[warn] Konsolenfehler: {real[:5]}")
    fails = [n for n, o in results if not o]
    if fails:
        print("[FAIL] " + "; ".join(fails))
    return 1 if (fails or real) else 0


if __name__ == "__main__":
    sys.exit(main())

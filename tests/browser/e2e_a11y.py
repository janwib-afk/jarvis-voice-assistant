"""Accessibility- und Tastatur-Suite (semantische DOM-/Keyboard-Pruefung).

Keine WCAG-Vollkonformitaets- oder echte-Screenreader-Behauptung — geprueft wird
der Accessibility-Tree/semantisches DOM plus Tastaturbedienbarkeit gegen die
eingefrorene UI-Baseline. Bei einem echten Baseline-Defekt wird gemeldet, NICHT
die UI geaendert.

Nutzung:  python tests/browser/e2e_a11y.py [--repeat N]
Exit 0 = alle Checks grün.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402
from e2e_harness import JarvisServer, browser_context, open_jarvis  # noqa: E402

RESULTS = []


def check(name, ok, note=""):
    RESULTS.append((name, bool(ok)))
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{' — ' + note if note else ''}")


def run(pw):
    with JarvisServer("a11y") as srv, browser_context(pw, srv.base_url) as (page, col):
        open_jarvis(page, srv.base_url)

        # ── Landmarken ──────────────────────────────────────────────────────
        check("Landmark banner", page.get_by_role("banner").count() >= 1)
        check("Landmark main", page.get_by_role("main").count() >= 1)
        check("Landmark contentinfo (footer)", page.locator("footer#device-bar").count() == 1)
        check("Landmark navigation 'Bereich'",
              page.get_by_role("navigation", name="Bereich").count() == 1)

        # ── Genau eine EXPONIERTE H1 im aktiven Bereich (Jarvis) ────────────
        check("Genau eine exponierte H1 im Jarvis-Bereich",
              page.get_by_role("heading", level=1).count() == 1)
        check("H1 Jarvis = 'Gespräch mit Jarvis'",
              page.get_by_role("heading", level=1, name="Gespräch mit Jarvis").count() == 1)

        # ── Skip-Link ───────────────────────────────────────────────────────
        check("Skip-Link zielt auf #text-input",
              page.locator("#skip-link").get_attribute("href") == "#text-input")

        # ── Zugaengliche Namen aller Icon-Buttons ───────────────────────────
        for label in ["Wiedergabe und laufende Aktion stoppen", "Mikrofon stummschalten",
                      "Minimieren", "Fenster ausblenden"]:
            check(f"Icon-Button hat Namen: '{label}'",
                  page.get_by_role("button", name=label).count() == 1)

        # ── Status-/Alert-Live-Region ───────────────────────────────────────
        check("Status Live-Region (role=status)",
              page.locator("#status-row[role='status']").count() == 1)

        # ── aria-pressed-Zustaende ──────────────────────────────────────────
        check("Vollbild aria-pressed=true",
              page.get_by_role("button", name="Vollbild").get_attribute("aria-pressed") == "true")
        check("Mute aria-pressed=false initial",
              page.get_by_role("button", name="Mikrofon stummschalten").get_attribute("aria-pressed") == "false")

        # ── Erster Tab landet auf dem Skip-Link, mit sichtbarem Fokus ────────
        page.keyboard.press("Tab")
        active = page.evaluate("document.activeElement && document.activeElement.id")
        check("Erster Tab -> Skip-Link fokussiert", active == "skip-link", f"aktiv={active}")
        outline = page.evaluate(
            "(() => { const s = getComputedStyle(document.activeElement); "
            "return s.outlineStyle + '/' + s.outlineWidth; })()")
        check("Sichtbarer Tastaturfokus (Outline)",
              outline not in ("none/0px", "none/", ""), f"outline={outline}")

        # ── Mausfreie Kernbedienung: Nachricht nur per Tastatur senden ──────
        srv.scenario(replies=["Nur-Tastatur-Antwort erhalten."])
        page.get_by_label("Textnachricht an Jarvis").focus()
        page.keyboard.type("nur mit tastatur")
        page.keyboard.press("Control+Enter")
        page.wait_for_function(
            "[...document.querySelectorAll('#transcript .msg.jarvis .msg-words')]"
            ".some(e => e.textContent.includes('Nur-Tastatur-Antwort erhalten.'))")
        check("Kernbedienung ohne Maus (Senden per Tastatur)", True)

        # ── Escape stoppt eine laufende Aktion ──────────────────────────────
        srv.scenario(replies=["Ich recherchiere. [ACTION:RESEARCH] Thema"], action_delay=30.0)
        page.get_by_label("Textnachricht an Jarvis").fill("recherchiere")
        page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
        page.wait_for_function(
            "document.getElementById('status-action').textContent.includes('Recherche')")
        page.keyboard.press("Escape")
        page.wait_for_function("document.getElementById('status-action').textContent === ''")
        check("Escape stoppt laufende Aktion", True)

        # ── Keine Tastaturfalle: Fokus wandert ueber viele Tabs ─────────────
        seen = set()
        for _ in range(14):
            page.keyboard.press("Tab")
            seen.add(page.evaluate(
                "document.activeElement.id || document.activeElement.tagName + '.' + "
                "document.activeElement.className"))
        check("Keine Tastaturfalle (Fokus wandert)", len(seen) >= 6, f"{len(seen)} distinkte Stops")

        # ── Bereichswechsel: genau eine exponierte H1 im Kontrollzentrum ────
        page.get_by_role("button", name="Kontrollzentrum").click()
        page.wait_for_function(
            "document.getElementById('control-heading') === document.activeElement "
            "|| document.documentElement.className.includes('page-control')")
        check("Genau eine exponierte H1 im Kontrollzentrum-Bereich",
              page.get_by_role("heading", level=1).count() == 1)
        check("H1 Kontrollzentrum = 'Kontrollzentrum'",
              page.get_by_role("heading", level=1, name="Kontrollzentrum").count() == 1)

        # ── Settings: jedes Feld hat einen zugaenglichen Namen ──────────────
        page.get_by_role("tab", name="Einstellungen").click()
        page.wait_for_selector('#settings-form [name="user_name"]')
        unnamed = page.evaluate("""() => {
            const fields = document.querySelectorAll(
                '#settings-form input:not([type=radio]), #settings-form textarea');
            let missing = 0;
            for (const f of fields) {
                const hasLabel = f.labels && f.labels.length > 0;
                const hasAria = f.getAttribute('aria-label');
                if (!hasLabel && !hasAria) missing++;
            }
            return missing;
        }""")
        check("Alle Settings-Felder haben ein Label", unnamed == 0, f"{unnamed} ohne Label")

        col.assert_clean("a11y")


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
            except Exception as e:
                import traceback
                traceback.print_exc()
                ok_all = False
            if any(not ok for _, ok in RESULTS):
                ok_all = False
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n[verify] {passed}/{len(RESULTS)} Accessibility-/Tastatur-Checks erfolgreich")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())

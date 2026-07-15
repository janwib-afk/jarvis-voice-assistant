"""Visual-Regression-Suite (Python Playwright + Pillow/numpy).

Nimmt eine kleine, hochwertige Menge deterministischer UI-Zustaende der AKTUELLEN
(freigegebenen) Jarvis-UI auf und vergleicht sie pixelweise gegen eine bestaetigte
Baseline unter ``tests/browser/visual_baseline/``.

Determinismus: feste Uhr + Animationen aus (Harness-Init-Skripte), lokale Fonts
vollstaendig geladen, definierter Viewport/Device-Scale, synthetische Daten aus
dem E2E-Stub, 0 externe Assets. Funktionale Assertions bleiben zusaetzlich in
e2e_functional.py — Visual ersetzt sie nie.

WICHTIG: ``docs/design-baseline/screenshots`` ist die **Phase-0-Baseline VOR dem
Redesign** und wird NICHT ueberschrieben und NICHT als Vergleichsziel genutzt.

Modi:
  --update   Baseline (neu) aufnehmen -> tests/browser/visual_baseline/
  (default)  aktuelle Aufnahme gegen die Baseline diffen (Regressionsschutz)

Nutzung:
  python tests/browser/e2e_visual.py --update     # Baseline erzeugen (nach Freigabe)
  python tests/browser/e2e_visual.py              # Regression pruefen
Exit 0 = keine Regression über der Toleranz.
"""
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402
from e2e_harness import JarvisServer, browser_context, open_jarvis  # noqa: E402

BASELINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visual_baseline")
DIFF_THRESHOLD = 16       # Kanal-Differenz je Pixel, ab der ein Pixel "anders" zaehlt
TOLERANCE_RATIO = 0.002   # max. Anteil abweichender Pixel (0.2 %)

# (name, viewport) — Zustaende werden in EINER Session der Reihe nach aufgenommen.
STATES = [
    ("jarvis-fullscreen-idle", (1920, 1080)),
    ("jarvis-fullscreen-listening", (1920, 1080)),
    ("jarvis-fullscreen-thinking", (1920, 1080)),
    ("jarvis-fullscreen-speaking", (1920, 1080)),
    ("jarvis-fullscreen-error", (1920, 1080)),
    ("jarvis-fullscreen-muted", (1920, 1080)),
    ("jarvis-fullscreen-error-banner", (1920, 1080)),
    ("jarvis-fullscreen-transcript-multi", (1920, 1080)),
    ("control-overview-focus", (1000, 800)),
    ("control-settings-focus", (1000, 800)),
    ("control-music-focus", (1000, 800)),
    ("jarvis-panel", (420, 560)),
]


def _wait_fonts(page):
    page.wait_for_function("document.fonts && document.fonts.status === 'loaded'", timeout=15000)


def capture_all(page, srv, outdir):
    """Alle Zustaende deterministisch aufnehmen; Rueckgabe: {name: pfad}."""
    os.makedirs(outdir, exist_ok=True)
    saved = {}

    def shot(name):
        path = os.path.join(outdir, name + ".png")
        page.screenshot(path=path)
        saved[name] = path

    open_jarvis(page, srv.base_url)
    _wait_fonts(page)

    # Orb-Zustaende (Vollbild) — erzwungen ueber die oeffentliche Client-API.
    page.evaluate("setOrbState('idle')")
    shot("jarvis-fullscreen-idle")
    for state in ("listening", "thinking", "speaking", "error"):
        page.evaluate(f"setOrbState('{state}')")
        shot(f"jarvis-fullscreen-{state}")
    page.evaluate("setOrbState('idle')")

    # Muted (echter Button), dann zurueck.
    page.get_by_role("button", name="Mikrofon stummschalten").click()
    shot("jarvis-fullscreen-muted")
    page.get_by_role("button", name="Mikrofon wieder aktivieren").click()
    page.evaluate("setOrbState('idle')")

    # Fehlerbanner (persistente Komponente).
    page.evaluate("window.showErrorBanner({component:'tts', "
                  "text:'Sprachausgabe fehlgeschlagen — Antwort wird nur als Text angezeigt.', "
                  "hint:'ElevenLabs-Key pruefen.'})")
    page.wait_for_selector("#error-stack .error-banner")
    shot("jarvis-fullscreen-error-banner")
    page.click("#error-stack .error-banner .eb-close")

    # Transcript mit mehreren Nachrichten (echter Flow gegen den Stub).
    srv.scenario(replies=["Antwort eins.", "Antwort zwei.", "Antwort drei."])
    for i, msg in enumerate(["Frage eins", "Frage zwei", "Frage drei"], start=2):
        page.get_by_label("Textnachricht an Jarvis").fill(msg)
        page.get_by_label("Textnachricht an Jarvis").press("Control+Enter")
        page.wait_for_function(
            f"document.querySelectorAll('#transcript .msg.jarvis').length >= {i}")
    page.evaluate("setOrbState('idle')")
    shot("jarvis-fullscreen-transcript-multi")

    # Kontrollzentrum (Fokus 1000x800).
    page.set_viewport_size({"width": 1000, "height": 800})
    page.get_by_role("button", name="Kontrollzentrum").click()
    page.wait_for_selector("#cc-app-grid .app-module")
    page.wait_for_selector("#cc-map-stage .map-monitor")
    shot("control-overview-focus")

    page.get_by_role("tab", name="Einstellungen").click()
    page.wait_for_selector('#settings-form [name="user_name"]')
    shot("control-settings-focus")

    page.get_by_role("tab", name="Musik").click()
    page.wait_for_selector(".music-item")
    shot("control-music-focus")

    # Panel (420x560).
    page.get_by_role("tab", name="Übersicht").click()
    page.get_by_role("button", name="Jarvis", exact=True).click()
    page.get_by_role("button", name="Klein").click()
    page.set_viewport_size({"width": 420, "height": 560})
    page.wait_for_function("document.documentElement.className.includes('mode-panel')")
    shot("jarvis-panel")

    return saved


def diff_ratio(path_a, path_b):
    a = Image.open(path_a).convert("RGB")
    b = Image.open(path_b).convert("RGB")
    if a.size != b.size:
        return 1.0, f"Groesse {a.size} != {b.size}"
    arr_a = np.asarray(a, dtype=np.int16)
    arr_b = np.asarray(b, dtype=np.int16)
    maxdiff = np.abs(arr_a - arr_b).max(axis=2)
    changed = int((maxdiff > DIFF_THRESHOLD).sum())
    ratio = changed / (a.size[0] * a.size[1])
    return ratio, f"{changed} Pixel > {DIFF_THRESHOLD}"


def main():
    update = "--update" in sys.argv
    tmp_out = os.path.join(os.environ.get("TEMP", "/tmp"), "jarvis-visual-capture")
    shutil.rmtree(tmp_out, ignore_errors=True)

    with sync_playwright() as pw:
        with JarvisServer("visual") as srv, browser_context(
                pw, srv.base_url, freeze=True) as (page, col):
            saved = capture_all(page, srv, tmp_out)
            col.assert_clean("visual-capture")

    if update:
        os.makedirs(BASELINE_DIR, exist_ok=True)
        for name, path in saved.items():
            shutil.copy(path, os.path.join(BASELINE_DIR, name + ".png"))
        print(f"[update] {len(saved)} Baseline-Bilder -> {BASELINE_DIR}")
        for name, vp in STATES:
            print(f"   - {name}.png  ({vp[0]}x{vp[1]})")
        return 0

    # Vergleichsmodus
    if not os.path.isdir(BASELINE_DIR):
        print(f"[FAIL] Keine bestaetigte Baseline unter {BASELINE_DIR} — "
              f"erst 'python tests/browser/e2e_visual.py --update' nach Freigabe.")
        return 1
    ok_all = True
    for name, _vp in STATES:
        cur = saved.get(name)
        base = os.path.join(BASELINE_DIR, name + ".png")
        if not cur or not os.path.exists(base):
            print(f"  [FAIL] {name}: Baseline oder Aufnahme fehlt")
            ok_all = False
            continue
        ratio, note = diff_ratio(base, cur)
        ok = ratio <= TOLERANCE_RATIO
        ok_all = ok_all and ok
        print(f"  [{'OK ' if ok else 'FAIL'}] {name}: Diff {ratio*100:.4f}% ({note})")
    print(f"\n[verify] Visual-Regression {'grün' if ok_all else 'FEHLER'} "
          f"(Toleranz {TOLERANCE_RATIO*100:.2f}%)")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())

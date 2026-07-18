"""
Slice 10 (RFC-0006 §21 + Amendment 1 / M3) — RACE-MATRIX, BROWSER-SEITE.

Szenarien 11-16 der Matrix an den dort dokumentierten Seams SEAM-VOICE und
SEAM-BROWSER-UI. Die Server-Szenarien 1-10 und 17 liegen in
``tests/test_race_matrix.py``.

Geprueft wird gegen die ECHTE Seite, nicht gegen den Reducer allein: ein Test,
der nur ``reduce`` befragt, wuerde die Epoch-Guards in den Adaptern
(``scheduleListen``, ``orbErrorRevert``, ``audio.onended``) gar nicht beruehren —
und genau dort entstehen die Races.

JEDES Stale-Szenario hat eine GEGENPROBE: derselbe Ablauf ohne Epoch-Wechsel muss
wirken. Ohne diese Gegenprobe koennte ein Test gruen sein, weil schlicht nichts
passiert — er wuerde nichts beweisen.

Determinismus ohne willkuerliche Sleeps: beobachtet wird per ``wait_for_function``
auf den sichtbaren Zustand. Wo auf ein FEHLEN gewartet werden muss, wird zuerst per
Gegenprobe die tatsaechliche Wirkdauer des Vorgangs abgewartet und danach das
Ausbleiben geprueft — nicht geraten.

    python tests/browser/e2e_race_matrix.py

Exit 0 = alle Szenarien gruen.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402

from e2e_harness import JarvisServer, browser_context, open_jarvis  # noqa: E402

# Kleine Helfer in der Seite: Ereignisse mit AKTUELLER oder mit ALTER Epoch
# zustellen. `dAt` ist der Kern der Matrix — ein Callback, der beim Planen eine
# Epoch gemerkt hat und verspaetet ankommt.
HELPERS = """
() => {
    window.__rm = {
        ep: () => window.__voice.state.epoch,
        st: () => window.__voice.state,
        d: (e) => dispatchVoice(Object.assign({ epoch: window.__voice.state.epoch }, e)),
        dAt: (ep, e) => dispatchVoice(Object.assign({}, e, { epoch: ep })),
        // Echter Kontextwechsel ueber den normalen Stop-Pfad (erhoeht die Epoch).
        bump: () => {
            dispatchVoice({ type: 'StopRequested', epoch: window.__voice.state.epoch });
            dispatchVoice({ type: 'StopAck', epoch: window.__voice.state.epoch });
            renderVoice();
        },
        orb: () => document.getElementById('orb').className
    };
}
"""

results = []


def check(name, ok, note=""):
    results.append((name, ok))
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{' — ' + note if note else ''}")


def _prepare(page, base_url):
    open_jarvis(page, base_url)
    page.evaluate(HELPERS)


# ── Szenario 11 ────────────────────────────────────────────────────────────
def szenario_11_reconnect_mit_alten_timern(page, base_url):
    """WS-Reconnect mit alten Timern: der geplante Listen-Restart ist stale."""
    _prepare(page, base_url)

    # GEGENPROBE: ohne Kontextwechsel wirkt der geplante Restart.
    page.evaluate("() => { window.__rm.d({type:'RecognitionEnd'}); scheduleListen(30); }")
    page.wait_for_function("window.__voice.state.capture === 'listening'", timeout=5000)
    check("11 Gegenprobe: geplanter Listen-Restart wirkt normal", True)

    # STALE: Restart planen, dann WsOpen -> Epoch steigt -> Timer wirkungslos.
    page.evaluate("""() => {
        window.__rm.d({type:'RecognitionEnd'});
        scheduleListen(30);
        window.__rm.d({type:'WsOpen'});      // echter Kontextwechsel, Epoch++
        renderVoice();
    }""")
    # Wirkdauer des Timers sicher verstreichen lassen (30 ms geplant).
    page.wait_for_timeout(300)
    st = page.evaluate("window.__rm.st()")
    check("11 stale: alter Reconnect-Timer springt nicht auf 'listening'",
          st["capture"] != "listening", f"capture={st['capture']}")


# ── Szenario 12 ────────────────────────────────────────────────────────────
def szenario_12_audio_ende_nach_stop(page, base_url):
    """Audio-Ende nach Stop: das verspaetete AudioEnded wird verworfen."""
    _prepare(page, base_url)

    # GEGENPROBE: AudioEnded mit AKTUELLER Epoch beendet die Wiedergabe.
    page.evaluate("""() => {
        window.__rm.d({type:'UserGesture'});
        window.__rm.d({type:'AudioReceived', audio:'a'});
        renderVoice();
    }""")
    playing = page.evaluate("window.__rm.st().playback") == "playing"
    page.evaluate("() => { window.__rm.d({type:'AudioEnded'}); renderVoice(); }")
    ended = page.evaluate("window.__rm.st().playback") != "playing"
    check("12 Gegenprobe: AudioEnded beendet die Wiedergabe", playing and ended)

    # STALE — und zwar so, dass die Epoch WIRKLICH das Entscheidende ist:
    # Audio A laeuft, Stop beendet es (Epoch++), danach startet Audio B mit
    # FRISCHER Epoch. Trifft jetzt das verspaetete onended von A ein, wuerde es
    # ohne Guard das laufende B beenden. Ein Test, der das alte Ende nur auf einen
    # bereits leeren Playback wirft, beweist nichts — dort ist AudioEnded ohnehin
    # ein No-Op, und die Epoch waere gar nicht noetig.
    st = page.evaluate("""() => {
        window.__rm.d({type:'AudioReceived', audio:'a'});
        const alt = window.__rm.ep();          // Epoch, die A's Handler gemerkt hat
        window.__rm.bump();                    // Stop -> Epoch++, A endet
        window.__rm.d({type:'AudioReceived', audio:'b'});   // B laeuft, neue Epoch
        const vorB = window.__rm.st().playback;
        window.__rm.dAt(alt, {type:'AudioEnded'});          // A's verspaetetes Ende
        renderVoice();
        return { vorB: vorB, jetzt: window.__rm.st().playback, orb: window.__rm.orb() };
    }""")
    check("12 stale: altes Audio-Ende beendet die NEUE Wiedergabe nicht",
          st["vorB"] == "playing" and st["jetzt"] == "playing",
          f"B war {st['vorB']}, jetzt {st['jetzt']}, orb={st['orb']}")


# ── Szenario 13 ────────────────────────────────────────────────────────────
def szenario_13_recognition_end_nach_mute(page, base_url):
    """RecognitionEnd nach Mute bzw. Disconnect: kein Ruecksprung auf 'listening'.

    Die Matrix nennt beide Auslauser. Sie sind unterschiedlich abgesichert, und das
    wird hier bewusst getrennt geprueft:

      Mute       — schuetzt der REDUCER: 'StartListening' ist unter Mute ein No-Op.
                   Der Epoch-Guard ist hier gar nicht noetig.
      Disconnect — schuetzt die EPOCH: ohne Guard wuerde der geplante Restart nach
                   dem Verbindungsverlust weiterlaufen.
    """
    _prepare(page, base_url)

    page.evaluate("""() => {
        window.__rm.d({type:'RecognitionEnd'});
        scheduleListen(30);
        window.__rm.d({type:'MuteToggled'});   // Mute -> Epoch++
        renderVoice();
    }""")
    page.wait_for_timeout(300)
    st = page.evaluate("window.__rm.st()")
    orb = page.evaluate("window.__rm.orb()")
    check("13a stale nach Mute: kein Ruecksprung auf 'listening' (Reducer-Regel)",
          st["capture"] == "muted" and orb == "muted", f"capture={st['capture']}, orb={orb}")

    # Gegenprobe: entstummen laesst Capture wieder normal arbeiten.
    page.evaluate("() => { window.__rm.d({type:'MuteToggled'}); renderVoice(); }")
    st2 = page.evaluate("window.__rm.st()")
    check("13 Gegenprobe: Entstummen stellt Capture wieder her",
          st2["capture"] != "muted", f"capture={st2['capture']}")

    # Disconnect-Variante: hier traegt allein die Epoch.
    page.evaluate("""() => {
        window.__rm.d({type:'RecognitionEnd'});
        scheduleListen(30);
        window.__rm.d({type:'WsClosed'});      // Verbindungsverlust -> Epoch++
        renderVoice();
    }""")
    page.wait_for_timeout(300)
    st3 = page.evaluate("window.__rm.st()")
    check("13b stale nach Disconnect: geplanter Restart wirkt nicht (Epoch)",
          st3["capture"] != "listening", f"capture={st3['capture']}")


# ── Szenario 14 ────────────────────────────────────────────────────────────
def szenario_14_verspaeteter_error_revert(page, base_url):
    """Verspaeteter Error-Revert-Timer nach neuer Interaktion: verworfen.

    Das ist der in der Matrix genannte 'heutige Stale-Revert': der 2500-ms-Timer
    aus ``flashOrbError`` durfte frueher einen inzwischen NEUEREN Zustand
    ueberschreiben.

    Hier wirken ZWEI unabhaengige Guards: der Timer prueft ``isStale`` selbst, und
    der Reducer verwirft zusaetzlich jedes Ereignis mit veralteter Epoch. Der Test
    prueft das beobachtbare Ergebnis; er kann nicht unterscheiden, welcher der
    beiden Guards gegriffen hat. Der Mutationsnachweis zeigt entsprechend erst
    dann Rot, wenn BEIDE entfernt werden — das ist gewollte Redundanz, keine
    Testschwaeche.
    """
    _prepare(page, base_url)

    # GEGENPROBE: ohne Kontextwechsel raeumt der Revert das Overlay nach 2500 ms.
    page.evaluate("() => { flashOrbError(); }")
    hat_overlay = page.evaluate(
        "window.__rm.st().overlays.indexOf('fatal-error') !== -1")
    page.wait_for_function(
        "window.__voice.state.overlays.indexOf('fatal-error') === -1", timeout=6000)
    check("14 Gegenprobe: Error-Revert raeumt das Overlay normal ab", hat_overlay)

    # STALE: Fehler zeigen, dann Kontextwechsel -> der geplante Revert ist stale.
    page.evaluate("() => { flashOrbError(); window.__rm.bump(); renderVoice(); }")
    vorher = page.evaluate("window.__rm.st().overlays")
    # Die Wirkdauer ist oben gemessen worden (2500 ms) — hier sicher darueber.
    page.wait_for_timeout(3200)
    nachher = page.evaluate("window.__rm.st().overlays")
    check("14 stale: verspaeteter Revert veraendert den neueren Zustand nicht",
          "fatal-error" in vorher and nachher == vorher,
          f"{vorher} -> {nachher}")


# ── Szenario 15 ────────────────────────────────────────────────────────────
def szenario_15_action_und_playback_gleichzeitig(page, base_url):
    """Aktion und Wiedergabe gleichzeitig: beide gueltig, Anzeige = speaking."""
    _prepare(page, base_url)

    st = page.evaluate("""() => {
        window.__rm.d({type:'ActionStart'});
        window.__rm.d({type:'UserGesture'});
        window.__rm.d({type:'AudioReceived', audio:'a'});
        renderVoice();
        return { s: window.__rm.st(), orb: window.__rm.orb(),
                 pres: JarvisVoice.presentation(window.__voice.state) };
    }""")
    check("15 beide Regionen sind gleichzeitig gueltig",
          st["s"]["interaction"] == "action-running" and st["s"]["playback"] == "playing",
          f"interaction={st['s']['interaction']}, playback={st['s']['playback']}")
    check("15 Anzeige folgt Prioritaet 3 vor 5 (speaking)",
          st["pres"] == "speaking" and st["orb"] == "speaking",
          f"pres={st['pres']}, orb={st['orb']}")

    # Nach dem Audio-Ende wird die noch laufende Aktion sichtbar.
    st2 = page.evaluate("""() => {
        window.__rm.d({type:'AudioEnded'});
        renderVoice();
        return { pres: JarvisVoice.presentation(window.__voice.state),
                 orb: window.__rm.orb() };
    }""")
    check("15 nach Audio-Ende bleibt die Aktion sichtbar",
          st2["pres"] == "action-running", f"pres={st2['pres']}, orb={st2['orb']}")


# ── Szenario 16 ────────────────────────────────────────────────────────────
def szenario_16_autoplay_blockiert(page, base_url):
    """Autoplay blockiert: Banner lokal, Server erfaehrt nichts (I12)."""
    _prepare(page, base_url)

    vorher = page.evaluate("window.__wsSentCount")
    page.evaluate("() => { window.__rm.d({type:'AutoplayBlocked'}); renderVoice(); }")
    st = page.evaluate("window.__rm.st()")
    check("16 Autoplay-Block setzt ein behebbares Overlay",
          "recoverable-error" in st["overlays"], str(st["overlays"]))
    check("16 Wiedergabe bleibt nicht faelschlich 'playing'",
          st["playback"] != "playing", f"playback={st['playback']}")

    nachher = page.evaluate("window.__wsSentCount")
    check("16 I12: der Server erfaehrt vom Autoplay-Block NICHTS",
          nachher == vorher, f"gesendete Frames {vorher} -> {nachher}")

    # UserGesture raeumt das Overlay wieder ab.
    page.evaluate("() => { window.__rm.d({type:'UserGesture'}); renderVoice(); }")
    st2 = page.evaluate("window.__rm.st()")
    check("16 Nutzergeste raeumt das Overlay ab",
          "recoverable-error" not in st2["overlays"], str(st2["overlays"]))


SZENARIEN = [
    ("11 WS-Reconnect mit alten Timern", szenario_11_reconnect_mit_alten_timern),
    ("12 Audio-Ende nach Stop", szenario_12_audio_ende_nach_stop),
    ("13 RecognitionEnd nach Mute", szenario_13_recognition_end_nach_mute),
    ("14 Verspaeteter Error-Revert", szenario_14_verspaeteter_error_revert),
    ("15 Aktion und Playback gleichzeitig", szenario_15_action_und_playback_gleichzeitig),
    ("16 Autoplay blockiert", szenario_16_autoplay_blockiert),
]


def main():
    with sync_playwright() as pw, JarvisServer("race") as srv:
        for name, fn in SZENARIEN:
            print(f"[szenario] {name}")
            # `freeze=False`: diese Matrix braucht ECHTE Timer — eine eingefrorene
            # Uhr wuerde genau die Races unsichtbar machen, um die es hier geht.
            with browser_context(pw, srv.base_url, freeze=False) as (page, col):
                try:
                    fn(page, srv.base_url)
                except Exception as exc:            # noqa: BLE001
                    check(f"{name}: Ausnahme", False, str(exc)[:200])
                col.assert_clean(f"race-{name.split()[0]}")

    failed = [n for n, ok in results if not ok]
    print()
    if failed:
        print(f"[verify] {len(failed)} von {len(results)} Race-Matrix-Pruefungen ROT")
        for n in failed:
            print(f"  [FAIL] {n}")
        return 1
    print(f"[verify] {len(results)}/{len(results)} Race-Matrix-Pruefungen erfolgreich")
    return 0


if __name__ == "__main__":
    sys.exit(main())

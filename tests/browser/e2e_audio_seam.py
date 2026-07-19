"""
Slice 10 / Phase 4J — DETERMINISTISCHER AUDIO-SEAM.

WARUM ES DIESEN SEAM GIBT (ehrlich benannt):

    Playwright-Chromium ist ein Open-Source-Build OHNE verwendbaren MP3-Codec.
    ``audio.play()`` lehnt dort mit ``NotSupportedError`` ab — unabhaengig von
    jeder Autoplay-Richtlinie. Der ERFOLGSPFAD der Wiedergabe war deshalb im
    Browser-Gate nie ausfuehrbar und damit ungetestet.

    Dieser Test taeuscht KEINEN Codec und KEIN echtes Chromium-Verhalten vor. Er
    ersetzt vor dem App-Start das ``Audio``-Element durch eine kontrollierbare
    Testimplementierung und prueft damit ausschliesslich das, was uns gehoert:
    die ADAPTER- UND ZUSTANDSSEMANTIK von ``playNext``/``onAudioFinished``/
    ``stopPlaybackLocal`` gegen den Reducer. Ob Chromium MP3 dekodiert, ist damit
    ausdruecklich NICHT geprueft und bleibt eine offene Umgebungsgrenze.

Der Seam liegt REIN AUF DER TESTSEITE: ``window.Audio`` wird per Init-Skript
ersetzt. Im Produktionscode gibt es dafuer keine Setter-, Inject- oder
Test-Modus-API — das Frontend weiss von diesem Test nichts.

    python tests/browser/e2e_audio_seam.py

Exit 0 = alle Pruefungen gruen.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402

from e2e_harness import JarvisServer, browser_context, open_jarvis  # noqa: E402

# Kontrollierbares Audio-Element. Bewusst minimal: nur was der Adapter benutzt
# (Konstruktor, play, pause, onended, onerror).
#
# WICHTIG (Prompt 20A): Der Fake spiegelt jetzt die ECHTE Chromium-/Edge-Realitaet.
# Eine ``data:audio/mp3``-URL — die alte stille Freischaltprobe — lehnt IMMER mit
# ``NotSupportedError`` ab (empirisch belegt: `canPlayType('audio/mpeg')` meldet
# 'probably', `play()` scheitert trotzdem). Der fruehere Fake loeste diese Probe
# faelschlich auf und MASKIERTE damit den Freischaltfehler.
#
# ``mode`` steuert nur die ECHTEN (blob:/data:audio/wav) Wiedergaben:
#   'ok'      -> loest auf
#   'blocked' -> NotAllowedError (echte, per Geste behebbare Autoplay-Sperre)
#   'unsupported' -> NotSupportedError (Format-/Codecfehler)
#   'pending' -> Promise bleibt offen; der Test loest/lehnt es spaeter selbst auf
INIT_FAKE_AUDIO = """
(() => {
    window.__audio = { instances: [], mode: 'ok', playCalls: 0 };
    function isProbe(src) { return String(src).startsWith('data:audio/mp3'); }
    class FakeAudio {
        constructor(src) {
            this.src = src;
            this.playing = false;
            this.paused = false;
            this.onended = null;
            this.onerror = null;
            this._pending = null;
            window.__audio.instances.push(this);
        }
        play() {
            window.__audio.playCalls++;
            // Die alte stille MP3-Probe ist ungueltig — echtes Chromium/Edge lehnt ab.
            if (isProbe(this.src)) {
                return Promise.reject(new DOMException('no supported source', 'NotSupportedError'));
            }
            const mode = window.__audio.mode;
            if (mode === 'blocked') {
                return Promise.reject(new DOMException('blocked', 'NotAllowedError'));
            }
            if (mode === 'unsupported') {
                return Promise.reject(new DOMException('no supported source', 'NotSupportedError'));
            }
            if (mode === 'pending') {
                const self = this;
                return new Promise((res, rej) => { self._pending = { res, rej }; });
            }
            this.playing = true;
            return Promise.resolve();
        }
        pause() { this.playing = false; this.paused = true; }
    }
    window.Audio = FakeAudio;
    // Testseitige Ausloeser — NICHT Teil des Produktionscodes.
    window.__audio.last = () => window.__audio.instances[window.__audio.instances.length - 1];
    window.__audio.real = () => window.__audio.instances.filter(a => !isProbe(a.src));
    window.__audio.end = (a) => { const t = a || window.__audio.last(); if (t.onended) t.onended(); };
    window.__audio.fail = (a) => { const t = a || window.__audio.last(); if (t.onerror) t.onerror(); };
    // Verzoegerte Aufloesung/Ablehnung fuer Stop-/Epoch-Rennen (§5.8/§5.9).
    window.__audio.resolvePlay = (a) => { const t = a || window.__audio.last();
        if (t._pending) { t.playing = true; t._pending.res(); t._pending = null; } };
    window.__audio.rejectPlay = (a, name) => { const t = a || window.__audio.last();
        if (t._pending) { t._pending.rej(new DOMException('x', name || 'AbortError')); t._pending = null; } };
})();
"""

results = []


def check(name, ok, note=""):
    results.append((name, ok))
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{' — ' + note if note else ''}")


def _prepare(page, base_url, srv):
    """Seite oeffnen und die Wiedergabe ueber eine echte Nutzergeste freischalten.

    Die Auto-Begruessung wird bewusst OHNE Audio beantwortet. Sonst laege beim
    Freischalten bereits ein gepuffertes Begruessungsaudio bereit, das sofort
    startet — jeder Fall begaenne dann mitten in einer laufenden Wiedergabe und
    saehe seine eigenen Elemente und Queue-Staende nicht mehr sauber.
    """
    srv.scenario(replies=[], audio=False)
    open_jarvis(page, base_url)
    page.mouse.click(5, 5)                      # echter Klick -> unlockAudio()
    page.wait_for_function("window.__voice.state.playback !== 'locked'", timeout=5000)
    page.wait_for_function("window.__voice.state.audioQueue.length === 0", timeout=5000)


def _say(page, text="hallo"):
    """Eine Nachricht ueber die echte Eingabe senden; der Stub antwortet mit Audio."""
    feld = page.get_by_label("Textnachricht an Jarvis")
    feld.fill(text)
    feld.press("Control+Enter")


def _wait_playing(page):
    page.wait_for_function("window.__voice.state.playback === 'playing'", timeout=10000)


# ── 1 Erfolgreicher play()-Pfad ────────────────────────────────────────────
def fall_play_erfolg(page, base_url, srv):
    _prepare(page, base_url, srv)
    srv.scenario(replies=["Antwort eins"], audio=True)
    vorher = page.evaluate("window.__audio.real().length")
    _say(page)
    _wait_playing(page)

    st = page.evaluate("""() => ({
        real: window.__audio.real().length,
        playing: window.__audio.last().playing,
        playback: window.__voice.state.playback,
        orb: document.getElementById('orb').className
    })""")
    check("play(): ein Audio-Element wurde erzeugt und gestartet",
          st["real"] == vorher + 1 and st["playing"] is True,
          f"elemente={st['real']}, playing={st['playing']}")
    check("play(): Zustand ist 'playing', Anzeige 'speaking'",
          st["playback"] == "playing" and st["orb"] == "speaking",
          f"playback={st['playback']}, orb={st['orb']}")


# ── 2 AudioEnded ───────────────────────────────────────────────────────────
def fall_audio_ende(page, base_url, srv):
    _prepare(page, base_url, srv)
    srv.scenario(replies=["Antwort eins"], audio=True)
    _say(page)
    _wait_playing(page)

    page.evaluate("() => window.__audio.end()")
    page.wait_for_function("window.__voice.state.playback !== 'playing'", timeout=5000)
    st = page.evaluate("""() => ({
        playback: window.__voice.state.playback,
        queue: window.__voice.state.audioQueue.length,
        orb: document.getElementById('orb').className
    })""")
    check("AudioEnded: Wiedergabe endet, Queue leer",
          st["playback"] == "idle" and st["queue"] == 0,
          f"playback={st['playback']}, queue={st['queue']}")
    check("AudioEnded: Anzeige ist nicht mehr 'speaking'",
          st["orb"] != "speaking", f"orb={st['orb']}")


# ── 3 Queue-Fortschritt ────────────────────────────────────────────────────
def fall_queue_fortschritt(page, base_url, srv):
    """Zwei Audioteile: das zweite startet erst NACH dem Ende des ersten."""
    _prepare(page, base_url, srv)
    srv.scenario(replies=["Erste Antwort", "Zweite Antwort"], audio=True)

    _say(page, "eins")
    _wait_playing(page)
    erstes = page.evaluate("window.__audio.real().length")

    # Zweite Antwort trifft ein, waehrend die erste noch laeuft -> sie wartet.
    _say(page, "zwei")
    page.wait_for_function("window.__voice.state.audioQueue.length >= 2", timeout=10000)
    waehrend = page.evaluate("""() => ({
        elemente: window.__audio.real().length,
        queue: window.__voice.state.audioQueue.length
    })""")
    check("Queue: zweites Audio wartet, es wird KEIN zweites Element gestartet",
          waehrend["elemente"] == erstes and waehrend["queue"] >= 2,
          f"elemente={waehrend['elemente']}, queue={waehrend['queue']}")

    # Ende des ersten -> das zweite startet.
    page.evaluate("() => window.__audio.end()")
    page.wait_for_function(
        "window.__audio.real().length === %d" % (erstes + 1), timeout=5000)
    danach = page.evaluate("""() => ({
        elemente: window.__audio.real().length,
        playing: window.__audio.last().playing,
        playback: window.__voice.state.playback,
        queue: window.__voice.state.audioQueue.length,
        lokal: audioQueue.length
    })""")
    check("Queue: nach dem Ende startet genau das naechste Audio",
          danach["elemente"] == erstes + 1 and danach["playing"] is True
          and danach["playback"] == "playing",
          f"elemente={danach['elemente']}, playback={danach['playback']}")
    check("Queue: der Puffer ist um genau einen Eintrag geschrumpft",
          danach["queue"] == waehrend["queue"] - 1,
          f"{waehrend['queue']} -> {danach['queue']}")
    check("Queue: lokaler Puffer und Reducer-Queue bleiben symmetrisch",
          danach["lokal"] == danach["queue"],
          f"lokal={danach['lokal']}, reducer={danach['queue']}")


# ── 4 Stop waehrend der Wiedergabe ─────────────────────────────────────────
def fall_stop_waehrend_playback(page, base_url, srv):
    _prepare(page, base_url, srv)
    srv.scenario(replies=["Eine lange Antwort"], audio=True)
    _say(page)
    _wait_playing(page)

    st = page.evaluate("""() => {
        const a = window.__audio.last();
        stopPlaybackLocal();
        return {
            paused: a.paused, playing: a.playing,
            handlerWeg: a.onended === null && a.onerror === null,
            playback: window.__voice.state.playback,
            queue: window.__voice.state.audioQueue.length
        };
    }""")
    check("Stop: das laufende Element wird angehalten",
          st["paused"] is True and st["playing"] is False,
          f"paused={st['paused']}, playing={st['playing']}")
    check("Stop: die Handler werden geloest (kein spaeter Rueckruf)",
          st["handlerWeg"] is True)
    check("Stop: Zustand ist nicht mehr 'playing' und der Puffer ist leer",
          st["playback"] != "playing" and st["queue"] == 0,
          f"playback={st['playback']}, queue={st['queue']}")


# ── 5 Verspaetetes Audio-Ende nach Epoch-Wechsel ───────────────────────────
def fall_verspaetetes_ende_nach_epoch(page, base_url, srv):
    """Ein bereits 'unterwegs' befindlicher Rueckruf darf nichts mehr tun.

    Der Adapter loest die Handler beim Stop zwar, aber ein Rueckruf kann bereits
    in der Zustellung sein. Genau den halten wir hier fest und feuern ihn NACH
    dem Kontextwechsel — er traegt die alte Epoch.
    """
    _prepare(page, base_url, srv)
    srv.scenario(replies=["Erste", "Zweite"], audio=True)
    _say(page, "eins")
    _wait_playing(page)

    st = page.evaluate("""() => {
        // Rueckruf des laufenden Audios festhalten, als waere er schon unterwegs.
        const alterRueckruf = window.__audio.last().onended;
        stopPlaybackLocal();                     // Stop -> Epoch++
        const nachStop = window.__voice.state.playback;
        return { alterRueckrufDa: typeof alterRueckruf === 'function',
                 nachStop: nachStop,
                 gemerkt: (window.__spaet = alterRueckruf) !== undefined };
    }""")
    check("stale: der alte Rueckruf existierte und der Stop wirkte",
          st["alterRueckrufDa"] is True and st["nachStop"] != "playing",
          f"nachStop={st['nachStop']}")

    # Neue Wiedergabe mit FRISCHER Epoch starten.
    _say(page, "zwei")
    _wait_playing(page)
    neu = page.evaluate("window.__audio.real().length")

    # Jetzt der verspaetete Rueckruf der ALTEN Wiedergabe.
    danach = page.evaluate("""() => {
        window.__spaet();
        return { playback: window.__voice.state.playback,
                 elemente: window.__audio.real().length,
                 lokal: audioQueue.length,
                 queue: window.__voice.state.audioQueue.length,
                 orb: document.getElementById('orb').className };
    }""")
    check("stale: verspaetetes Ende beendet die NEUE Wiedergabe nicht",
          danach["playback"] == "playing" and danach["orb"] == "speaking",
          f"playback={danach['playback']}, orb={danach['orb']}")
    check("stale: es wird kein zusaetzliches Audio gestartet",
          danach["elemente"] == neu, f"{neu} -> {danach['elemente']}")
    # I10/§19: ein verspaeteter Rueckruf ist ein TOTALER No-Op. Er darf auch den
    # lokalen Puffer nicht anfassen — sonst verliert die neue Wiedergabe einen
    # Teil, waehrend die Reducer-Queue ihn noch fuehrt. Genau diese Asymmetrie
    # bleibt unsichtbar, wenn man nur den Zustand und nicht beide Puffer prueft.
    check("stale: lokaler Puffer und Reducer-Queue bleiben symmetrisch",
          danach["lokal"] == danach["queue"],
          f"lokal={danach['lokal']}, reducer={danach['queue']}")


# ── 6 Autoplay-Block (getrennt geprueft) ───────────────────────────────────
def fall_autoplay_block(page, base_url, srv):
    """Der Block ist ein EIGENER Pfad und wird nicht mit dem Erfolg vermischt."""
    _prepare(page, base_url, srv)
    srv.scenario(replies=["Antwort"], audio=True)

    # Ab jetzt lehnt play() ab — wie eine Autoplay-Sperre.
    page.evaluate("() => { window.__audio.mode = 'blocked'; }")
    _say(page)
    page.wait_for_function(
        "window.__voice.state.overlays.indexOf('recoverable-error') !== -1", timeout=10000)

    st = page.evaluate("""() => ({
        overlays: window.__voice.state.overlays,
        playback: window.__voice.state.playback,
        banner: !!document.querySelector('.error-banner'),
        queue: window.__voice.state.audioQueue.length
    })""")
    check("Autoplay-Block: behebbares Overlay statt Wiedergabe",
          "recoverable-error" in st["overlays"] and st["playback"] != "playing",
          f"overlays={st['overlays']}, playback={st['playback']}")
    check("Autoplay-Block: ein Banner ist sichtbar", st["banner"] is True)
    check("Autoplay-Block: das Audio bleibt gepuffert, es geht nichts verloren",
          st["queue"] >= 1, f"queue={st['queue']}")

    # Nutzergeste + wieder abspielbar -> die Wiedergabe holt nach.
    page.evaluate("() => { window.__audio.mode = 'ok'; }")
    page.mouse.click(400, 400)
    page.wait_for_function("window.__voice.state.playback === 'playing'", timeout=10000)
    st2 = page.evaluate("""() => ({
        playback: window.__voice.state.playback,
        playing: window.__audio.last().playing
    })""")
    check("Autoplay-Block: nach dem Klick laeuft die Wiedergabe nach",
          st2["playback"] == "playing" and st2["playing"] is True,
          f"playback={st2['playback']}")


# ── 7 Kaltstart OHNE _prepare(): Audio trifft vor der Geste ein ────────────
def fall_kaltstart_ohne_geste(page, base_url, srv):
    """§5.1/§5.2: der Pfad, den der alte Fake maskiert hat.

    Es wird NICHT vorab freigeschaltet. Echtes TTS-Audio trifft ein, waehrend
    ``playback === 'locked'`` — es muss gepuffert werden und einen zugaenglichen
    „Audio aktivieren"-Button zeigen (kein blosses „irgendwo klicken"). Ein echter
    Klick auf diesen Button schaltet frei und startet GENAU EIN Nutz-Audio; Banner
    und Overlay verschwinden.

    Vor dem Fix bleibt ``unlockAudio()`` an der ungueltigen MP3-Probe haengen, die
    Geste dispatcht nie ``UserGesture`` und der Zustand bleibt fuer immer 'locked'.
    """
    srv.scenario(replies=["Hallo, hier ist Jarvis."], audio=True)
    open_jarvis(page, base_url)
    # Antwort abwarten (Text sichtbar), Audio ist gepuffert, noch keine Geste.
    page.wait_for_function("window.__voice.state.audioQueue.length >= 1", timeout=10000)
    st = page.evaluate("""() => ({
        playback: window.__voice.state.playback,
        queue: window.__voice.state.audioQueue.length,
        real: window.__audio.real().length,
        orb: document.getElementById('orb').className,
        banner: !!document.querySelector('.error-banner'),
    })""")
    check("Kaltstart: Audio ist gepuffert, noch nichts abgespielt",
          st["playback"] == "locked" and st["queue"] >= 1 and st["real"] == 0,
          f"playback={st['playback']}, queue={st['queue']}, real={st['real']}")
    check("Kaltstart: kein falsches 'speaking' vor der Geste",
          st["orb"] != "speaking", f"orb={st['orb']}")

    # Der zugaengliche Recovery-Button muss existieren und fokussierbar sein.
    btn = page.query_selector("#audio-unlock-btn, [data-audio-unlock]")
    check("Kaltstart: sichtbarer, fokussierbarer 'Audio aktivieren'-Button",
          btn is not None and btn.is_visible(),
          "kein Button gefunden" if btn is None else "sichtbar")

    if btn is not None:
        btn.focus()
        btn.click()
    else:                                       # Fallback: generische Geste
        page.mouse.click(5, 5)
    page.wait_for_function("window.__voice.state.playback === 'playing'", timeout=8000)
    # Der Blockade-Banner blendet mit einer kurzen Animation aus — auf seinen
    # tatsaechlichen Wegfall warten (Zustands-Wait, kein fester Sleep).
    page.wait_for_function("!document.querySelector('.error-banner')", timeout=5000)
    st2 = page.evaluate("""() => ({
        playback: window.__voice.state.playback,
        real: window.__audio.real().length,
        playing: window.__audio.last().playing,
        banner: !!document.querySelector('.error-banner'),
        overlay: window.__voice.state.overlays.indexOf('recoverable-error'),
    })""")
    check("Kaltstart: die Geste startet GENAU EIN Nutz-Audio",
          st2["playback"] == "playing" and st2["real"] == 1 and st2["playing"] is True,
          f"playback={st2['playback']}, real={st2['real']}")
    check("Kaltstart: Banner und Overlay verschwinden nach Erfolg",
          st2["banner"] is False and st2["overlay"] == -1,
          f"banner={st2['banner']}, overlay={st2['overlay']}")


# ── 8 NotSupportedError: ehrlicher Formatfehler, kein „Klick benoetigt" ─────
def fall_not_supported(page, base_url, srv):
    """§5.5: ein echter Codec-/Formatfehler ist KEINE Autoplay-Sperre.

    Es darf keine „Klick benoetigt"-Endlosschleife entstehen; die Queue wird
    deterministisch fortgesetzt (der Kopf wird verworfen, kein Wiederholen).
    """
    _prepare(page, base_url, srv)
    srv.scenario(replies=["Antwort"], audio=True)
    page.evaluate("() => { window.__audio.mode = 'unsupported'; }")
    _say(page)
    page.wait_for_function(
        "window.__voice.state.playback !== 'playing' && window.__voice.state.audioQueue.length === 0",
        timeout=10000)
    st = page.evaluate("""() => ({
        playback: window.__voice.state.playback,
        queue: window.__voice.state.audioQueue.length,
        overlay: window.__voice.state.overlays.indexOf('recoverable-error'),
        lastError: (window.__voice.state.lastError || {}),
    })""")
    check("NotSupported: kein recoverable-error-Overlay (kein Klick-noetig-Banner)",
          st["overlay"] == -1, f"overlay={st['overlay']}")
    check("NotSupported: Queue deterministisch geleert, keine Endlosschleife",
          st["queue"] == 0 and st["playback"] != "playing",
          f"playback={st['playback']}, queue={st['queue']}")


# ── 9 Stop, waehrend play() noch aussteht (§5.8) ───────────────────────────
def fall_stop_waehrend_play_pending(page, base_url, srv):
    """Eine verspaetete Aufloesung ODER Ablehnung eines bereits abgeloesten
    play() darf den neuen Zustand nicht veraendern."""
    _prepare(page, base_url, srv)
    srv.scenario(replies=["Antwort"], audio=True)
    page.evaluate("() => { window.__audio.mode = 'pending'; }")   # play() bleibt offen
    _say(page)
    page.wait_for_function("window.__audio.real().length === 1", timeout=10000)

    # Stop, waehrend das play()-Promise noch offen ist -> Epoch++.
    page.evaluate("() => { window.__spaetAudio = window.__audio.last(); stopPlaybackLocal(); }")
    st = page.evaluate("() => window.__voice.state.playback")
    check("pending-stop: nach Stop nicht mehr 'playing'", st != "playing", f"playback={st}")

    # Jetzt die verspaetete Ablehnung DES ALTEN play() (AbortError) zustellen.
    danach = page.evaluate("""() => {
        window.__audio.rejectPlay(window.__spaetAudio, 'AbortError');
        return { playback: window.__voice.state.playback,
                 queue: window.__voice.state.audioQueue.length,
                 lokal: audioQueue.length,
                 banner: !!document.querySelector('.error-banner') };
    }""")
    check("pending-stop: verspaetetes Reject aendert den Zustand nicht",
          danach["playback"] != "playing" and danach["queue"] == 0,
          f"playback={danach['playback']}, queue={danach['queue']}")
    check("pending-stop: kein neuer Blockade-Banner durch den Abbruch",
          danach["banner"] is False)
    check("pending-stop: lokaler Puffer und Reducer-Queue symmetrisch",
          danach["lokal"] == danach["queue"], f"lokal={danach['lokal']}")


# ── 10 Mikrofon stumm blockiert TTS nicht (§5.11) ──────────────────────────
def fall_mic_mute_erlaubt_tts(page, base_url, srv):
    """Mikrofon-Mute betrifft nur den Capture-Pfad, nie die Wiedergabe."""
    _prepare(page, base_url, srv)
    # Mikrofon stumm schalten (echte Nutzergeste auf den Mute-Button).
    page.click("#mute-btn")
    page.wait_for_function("window.__voice.state.capture === 'muted'", timeout=5000)
    srv.scenario(replies=["Trotzdem Sprache"], audio=True)
    _say(page)
    _wait_playing(page)
    st = page.evaluate("""() => ({
        capture: window.__voice.state.capture,
        playback: window.__voice.state.playback,
        playing: window.__audio.last().playing,
    })""")
    check("Mute: Capture bleibt 'muted', TTS spielt trotzdem",
          st["capture"] == "muted" and st["playback"] == "playing"
          and st["playing"] is True,
          f"capture={st['capture']}, playback={st['playback']}")


FAELLE = [
    ("1 erfolgreicher play()-Pfad", fall_play_erfolg),
    ("2 AudioEnded", fall_audio_ende),
    ("3 Queue-Fortschritt", fall_queue_fortschritt),
    ("4 Stop waehrend der Wiedergabe", fall_stop_waehrend_playback),
    ("5 verspaetetes Ende nach Epoch-Wechsel", fall_verspaetetes_ende_nach_epoch),
    ("6 Autoplay-Block", fall_autoplay_block),
    ("7 Kaltstart ohne Geste", fall_kaltstart_ohne_geste),
    ("8 NotSupportedError", fall_not_supported),
    ("9 Stop waehrend play() pending", fall_stop_waehrend_play_pending),
    ("10 Mic-Mute erlaubt TTS", fall_mic_mute_erlaubt_tts),
]


def main():
    with sync_playwright() as pw, JarvisServer("audio-seam") as srv:
        for name, fn in FAELLE:
            print(f"[fall] {name}")
            with browser_context(pw, srv.base_url, freeze=False,
                                 extra_init=INIT_FAKE_AUDIO) as (page, col):
                try:
                    fn(page, srv.base_url, srv)
                except Exception as exc:            # noqa: BLE001
                    check(f"{name}: Ausnahme", False, str(exc)[:220])

    failed = [n for n, ok in results if not ok]
    print()
    if failed:
        print(f"[verify] {len(failed)} von {len(results)} Audio-Seam-Pruefungen ROT")
        for n in failed:
            print(f"  [FAIL] {n}")
        return 1
    print(f"[verify] {len(results)}/{len(results)} Audio-Seam-Pruefungen erfolgreich")
    print("[hinweis] Playwright-Chromium hat keinen verwendbaren MP3-Codec; geprueft "
          "ist die Adapter- und Zustandssemantik ueber den Test-Seam, NICHT die "
          "Dekodierung durch den Browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

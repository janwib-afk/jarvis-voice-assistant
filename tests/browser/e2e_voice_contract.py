"""SEAM-VOICE — ausfuehrbare Contract-Tests des REINEN Voice-Reducers.

Laedt ``frontend/voice.js`` in eine leere Chromium-Seite (kein DOM-Zugriff, kein
Netz, kein Audio) und prueft die vier oeffentlichen Funktionen ``initialVoiceState``,
``reduce``, ``presentation`` und ``isStale`` per ``page.evaluate``.

Bewusst KEINE Quelltext-/String-Assertions und keine npm-Runtime-Dependency: der
bereits garantierte Projektrunner (Playwright/Chromium aus dem Browser-Gate) fuehrt
den echten Code aus.

    python tests/browser/e2e_voice_contract.py

Exit 0 = alle Contract-Faelle gruen.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_VOICE_JS = os.path.join(_ROOT, "frontend", "voice.js")

# Jeder Fall: (Name, JS-Ausdruck der true liefern muss)
CASES = [
    # ── Initialer Zustand (Praezisierung 4) ────────────────────────────────
    ("initial: connection disconnected", "S().connection === 'disconnected'"),
    ("initial: capture unavailable", "S().capture === 'unavailable'"),
    ("initial: playback locked", "S().playback === 'locked'"),
    ("initial: interaction idle", "S().interaction === 'idle'"),
    ("initial: overlays leer", "S().overlays.length === 0"),
    ("initial: greeted false", "S().greeted === false"),
    ("initial: epoch 0", "S().epoch === 0"),
    ("initial: presentation disconnected", "P(S()) === 'disconnected'"),

    # ── Presentation-Prioritaet (§13) ──────────────────────────────────────
    ("prio 1: getrennt schlaegt alles",
     "P(M({connection:'reconnecting', playback:'playing'})) === 'disconnected'"),
    ("prio 2: fatal-error",
     "P(M({connection:'connected', overlays:['fatal-error'], playback:'playing'})) === 'error'"),
    ("prio 3: playing = speaking",
     "P(M({connection:'connected', playback:'playing'})) === 'speaking'"),
    ("prio 4: stopping",
     "P(M({connection:'connected', interaction:'stopping'})) === 'stopping'"),
    ("prio 5: action-running",
     "P(M({connection:'connected', interaction:'action-running'})) === 'action-running'"),
    ("prio 6: awaiting-response = thinking",
     "P(M({connection:'connected', interaction:'awaiting-response'})) === 'thinking'"),
    ("prio 7: listening",
     "P(M({connection:'connected', capture:'listening'})) === 'listening'"),
    ("prio 8: muted",
     "P(M({connection:'connected', capture:'muted'})) === 'muted'"),
    ("prio 9: sonst idle", "P(M({connection:'connected'})) === 'idle'"),

    # Overlays veraendern die Presentation NICHT (Praezisierung 3)
    ("overlay degraded aendert presentation nicht",
     "P(M({connection:'connected', overlays:['degraded']})) === 'idle'"),
    ("overlay recoverable aendert presentation nicht",
     "P(M({connection:'connected', overlays:['recoverable-error'], capture:'listening'})) === 'listening'"),

    # ── Orthogonalitaet (der Kernbefund des Audits) ────────────────────────
    ("muted UND playing gleichzeitig darstellbar",
     "(function(){var s=M({connection:'connected', capture:'muted', playback:'playing'});"
     "return s.capture==='muted' && s.playback==='playing' && P(s)==='speaking';})()"),
    ("action-running UND playing -> speaking",
     "P(M({connection:'connected', interaction:'action-running', playback:'playing'})) === 'speaking'"),

    # ── Playback locked (Amendment 1 / M1) ─────────────────────────────────
    ("locked: Audio wird gepuffert statt abgespielt",
     "(function(){var r=R(M({connection:'connected'}),{type:'AudioReceived',audio:'a'});"
     "return r.state.playback==='locked' && r.state.audioQueue.length===1 &&"
     " r.effects.indexOf('PlayAudio')===-1 && r.effects.indexOf('AwaitUserGesture')!==-1;})()"),
    ("UserGesture schaltet frei und spielt Gepuffertes",
     "(function(){var s=R(M({connection:'connected'}),{type:'AudioReceived',audio:'a'}).state;"
     "var r=R(s,{type:'UserGesture'});"
     "return r.state.playback==='playing' && r.effects.indexOf('PlayAudio')!==-1;})()"),
    ("UserGesture ohne Puffer -> idle",
     "(function(){var r=R(M({connection:'connected'}),{type:'UserGesture'});"
     "return r.state.playback==='idle' && r.effects.indexOf('PlayAudio')===-1;})()"),
    ("AutoplayBlocked faellt zurueck nach locked",
     "(function(){var s=M({connection:'connected', playback:'playing'});"
     "var r=R(s,{type:'AutoplayBlocked'});"
     "return r.state.playback==='locked' && r.state.overlays.indexOf('recoverable-error')!==-1"
     " && P(r.state)!=='error';})()"),

    # ── Greeting-Latch (Amendment 1 / M2) ──────────────────────────────────
    ("erstes WsOpen sendet Begruessung",
     "(function(){var r=R(S(),{type:'WsOpen'});"
     "return r.state.greeted===true && r.effects.indexOf('SendGreeting')!==-1;})()"),
    ("Reconnect sendet KEINE zweite Begruessung",
     "(function(){var s=R(S(),{type:'WsOpen'}).state;"
     "s=R(s,{type:'WsClosed',epoch:s.epoch}).state;"
     "var r=R(s,{type:'WsOpen',epoch:s.epoch});"
     "return r.state.greeted===true && r.effects.indexOf('SendGreeting')===-1;})()"),
    ("Greeting ueberlebt drei Reconnects",
     "(function(){var s=R(S(),{type:'WsOpen'}).state, n=0;"
     "for(var i=0;i<3;i++){s=R(s,{type:'WsClosed',epoch:s.epoch}).state;"
     "var r=R(s,{type:'WsOpen',epoch:s.epoch}); if(r.effects.indexOf('SendGreeting')!==-1)n++; s=r.state;}"
     "return n===0;})()"),
    ("Stop setzt den Greeting-Latch nicht zurueck",
     "(function(){var s=R(S(),{type:'WsOpen'}).state;"
     "s=R(s,{type:'StopRequested',epoch:s.epoch}).state;"
     "return s.greeted===true;})()"),
    ("Mute setzt den Greeting-Latch nicht zurueck",
     "(function(){var s=R(S(),{type:'WsOpen'}).state;"
     "s=R(s,{type:'MuteToggled',epoch:s.epoch}).state;"
     "return s.greeted===true;})()"),

    # ── Epoch-Guard (Amendment 1 / M3) ─────────────────────────────────────
    ("Stop erhoeht die Epoch",
     "(function(){var s=M({connection:'connected'});"
     "return R(s,{type:'StopRequested',epoch:s.epoch}).state.epoch === s.epoch+1;})()"),
    ("Mute erhoeht die Epoch",
     "(function(){var s=M({connection:'connected'});"
     "return R(s,{type:'MuteToggled',epoch:s.epoch}).state.epoch === s.epoch+1;})()"),
    ("WsClosed erhoeht die Epoch",
     "(function(){var s=M({connection:'connected'});"
     "return R(s,{type:'WsClosed',epoch:s.epoch}).state.epoch === s.epoch+1;})()"),
    ("isStale erkennt veraltete Epoch",
     "(function(){var s=M({epoch:5}); return I(s,4)===true && I(s,5)===false;})()"),
    ("stale Reconnect-Timer veraendert nichts",
     "(function(){var s=M({connection:'connected', epoch:7});"
     "var r=R(s,{type:'WsOpen', epoch:3});"
     "return r.state===s && r.effects.length===0;})()"),
    ("Audio-Ende nach Stop wird verworfen",
     "(function(){var s=M({connection:'connected', playback:'playing', epoch:2});"
     "var afterStop=R(s,{type:'StopRequested',epoch:2}).state;"
     "var r=R(afterStop,{type:'AudioEnded', epoch:2});"   # alte Epoch
     "return r.effects.length===0 && r.state===afterStop;})()"),
    ("Recognition-Ende nach Mute wird verworfen",
     "(function(){var s=M({connection:'connected', capture:'listening', epoch:1});"
     "var afterMute=R(s,{type:'MuteToggled',epoch:1}).state;"
     "var r=R(afterMute,{type:'RecognitionEnd', epoch:1});"
     "return r.effects.length===0 && afterMute.capture==='muted';})()"),
    ("stale Error-Revert veraendert nichts",
     "(function(){var s=M({connection:'connected', epoch:4});"
     "var r=R(s,{type:'ErrorDismissed', epoch:1});"
     "return r.state===s && r.effects.length===0;})()"),

    # ── Mute-Semantik (Praezisierung 1) ────────────────────────────────────
    ("normale Sprache unter Mute wird ignoriert",
     "(function(){var s=M({connection:'connected', capture:'muted'});"
     "var r=R(s,{type:'RecognitionResult', text:'hallo'});"
     "return r.state===s && r.effects.length===0;})()"),
    ("Stop-Aeusserung unter Mute wirkt weiter",
     "(function(){var s=M({connection:'connected', capture:'muted'});"
     "var r=R(s,{type:'RecognitionResult', control:'stop'});"
     "return r.effects.indexOf('SendStopCommand')!==-1;})()"),
    ("Entstummen per Sprache wirkt weiter",
     "(function(){var s=M({connection:'connected', capture:'muted'});"
     "var r=R(s,{type:'RecognitionResult', control:'unmute'});"
     "return r.state.capture==='idle';})()"),
    ("StartListening unter Mute startet nichts",
     "(function(){var s=M({connection:'connected', capture:'muted'});"
     "var r=R(s,{type:'StartListening'});"
     "return r.effects.length===0 && r.state.capture==='muted';})()"),

    # ── Invalid transitions / Reinheit ─────────────────────────────────────
    ("unbekanntes Ereignis = totaler No-Op",
     "(function(){var s=M({connection:'connected'});"
     "var r=R(s,{type:'GibtEsNicht'}); return r.state===s && r.effects.length===0;})()"),
    ("Ereignis ohne type = No-Op",
     "(function(){var s=S(); var r=R(s,{}); return r.state===s && r.effects.length===0;})()"),
    ("Zustand ist eingefroren (unveraenderlich)",
     "Object.isFrozen(S()) === true"),
    # Reinheit VERHALTENSBASIERT (nicht per Quelltext-Grep): das Modul wird in einer
    # Sandbox neu ausgewertet, in der document/localStorage/WebSocket/Audio/fetch/
    # setTimeout beim kleinsten Zugriff werfen. Laeuft der Reducer dort vollstaendig
    # durch, benutzt er nachweislich kein DOM, kein Netz, kein Audio und keine Timer.
    ("Reducer ist rein (Sandbox ohne DOM/Netz/Audio/Timer)", "window.__purityOk()"),
]


def main():
    with open(_VOICE_JS, "r", encoding="utf-8") as f:
        src = f.read()

    failed = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto("about:blank")
        page.add_script_tag(content=src)
        page.evaluate("(s) => { window.__voiceSrc = s; }", src)
        # Kurze Helfer fuer die Faelle.
        page.evaluate("""() => {
            window.S = () => JarvisVoice.initialVoiceState();
            window.R = (s, e) => JarvisVoice.reduce(s, e);
            window.P = (s) => JarvisVoice.presentation(s);
            window.I = (s, e) => JarvisVoice.isStale(s, e);
            window.M = (patch) => Object.freeze(Object.assign(
                {}, JarvisVoice.initialVoiceState(), patch));
        }""")

        # Verhaltensbasierter Reinheitsnachweis: voice.js in einer Sandbox neu
        # auswerten, in der jeder DOM-/Netz-/Audio-/Timer-Zugriff wirft.
        page.evaluate("""() => {
            window.__purityOk = function () {
                const boom = new Proxy(function () {}, {
                    get() { throw new Error('impure: DOM/IO benutzt'); },
                    apply() { throw new Error('impure: DOM/IO aufgerufen'); },
                    construct() { throw new Error('impure: DOM/IO konstruiert'); }
                });
                const sandbox = {};
                new Function(
                    'document', 'localStorage', 'WebSocket', 'Audio', 'fetch',
                    'setTimeout', 'setInterval', 'XMLHttpRequest', 'navigator',
                    'window', 'module', 'exports', window.__voiceSrc
                )(boom, boom, boom, boom, boom, boom, boom, boom, boom,
                  sandbox, undefined, undefined);
                const V = sandbox.JarvisVoice;
                if (!V) return false;
                // Repraesentative Sequenz durch ALLE Regionen fahren.
                let s = V.initialVoiceState();
                const events = [
                    {type: 'WsConnecting'}, {type: 'WsOpen'}, {type: 'MicAvailable'},
                    {type: 'StartListening'}, {type: 'RecognitionResult', text: 'hi'},
                    {type: 'ActionStart'}, {type: 'AudioReceived', audio: 'a'},
                    {type: 'UserGesture'}, {type: 'AudioEnded'}, {type: 'ActionDone'},
                    {type: 'MuteToggled'}, {type: 'RecognitionResult', control: 'stop'},
                    {type: 'StopAck'}, {type: 'AutoplayBlocked'},
                    {type: 'ErrorEvent', fatal: false}, {type: 'Degraded'},
                    {type: 'ErrorDismissed'}, {type: 'WsClosed'}, {type: 'WsOpen'}
                ];
                for (const e of events) {
                    const r = V.reduce(s, Object.assign({}, e, {epoch: s.epoch}));
                    s = r.state;
                    V.presentation(s);
                    V.isStale(s, 0);
                }
                return true;
            };
        }""")

        for name, expr in CASES:
            try:
                ok = page.evaluate("() => !!(" + expr + ")")
            except Exception as e:
                ok, name = False, f"{name}  [JS-Fehler: {type(e).__name__}]"
            print(f"  [{'OK ' if ok else 'FAIL'}] {name}")
            if not ok:
                failed.append(name)

        browser.close()

    print()
    if failed:
        print(f"[verify] {len(failed)} von {len(CASES)} Voice-Contract-Faellen ROT")
        return 1
    print(f"[verify] {len(CASES)}/{len(CASES)} Voice-Contract-Faelle erfolgreich")
    return 0


if __name__ == "__main__":
    sys.exit(main())

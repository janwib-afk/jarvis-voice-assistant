"""Echter Medien-Codec-/Event-Smoke OHNE ``window.Audio``-Fake (Prompt 20A §5).

Der Audio-Seam (``e2e_audio_seam.py``) ersetzt ``window.Audio`` und kann deshalb
per Konstruktion KEINE echte Codec-Wiedergabe belegen. Dieser Test schliesst
genau diese Luecke: er benutzt ein ECHTES ``Audio``-Element in einem ECHTEN
Browser und belegt

  1. ``play()`` loest fuer ein GUELTIGES, rein lokales, synthetisches WAV auf,
  2. die nativen Ereignisse ``playing`` UND ``ended`` feuern wirklich.

WAV (PCM) braucht keinen proprietaeren Codec und laeuft auch im Open-Source-
Chromium — damit ist die echte Wiedergabe- und Ereignismaschinerie geprueft,
NICHT nur eine Fake-Zusage.

Wenn ein echtes Microsoft Edge (``channel='msedge'``) verfuegbar ist, wird es
bevorzugt — Edge/WebView2 tragen den MP3-Codec und melden ``audio/mpeg``-Support,
was die Produktionsformat-Realitaet (ElevenLabs liefert MP3) am naechsten kommt.

EHRLICHE GRENZE: Auch dieser Test behauptet NICHT, dass ein physischer Lautsprecher
hoerbar war. Die tatsaechliche Hoerbarkeit auf der echten pywebview-/WebView2-
Instanz des Nutzers bleibt eine einmalige manuelle Bestaetigung.

    python tests/browser/e2e_audio_codec.py

Exit 0 = echte Wiedergabe + native Ereignisse belegt.
"""
import base64
import struct
import sys

from playwright.sync_api import sync_playwright


def _valid_wav():
    """0.05 s Stille, 8 kHz mono 8-bit PCM — gueltiges, codecfreies WAV."""
    n = 400
    data = bytes([128]) * n
    hdr = b"RIFF" + struct.pack("<I", 36 + n) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8)
    hdr += b"data" + struct.pack("<I", n)
    return "data:audio/wav;base64," + base64.b64encode(hdr + data).decode()


# Spielt das WAV und meldet play()-Ausgang plus die NATIVEN Ereignisse.
PLAY = """
async (src) => {
  const a = new Audio(src);
  const seen = { playing: false, ended: false };
  a.addEventListener('playing', () => { seen.playing = true; });
  a.addEventListener('ended',   () => { seen.ended = true; });
  let played = false, err = null;
  try { await a.play(); played = true; } catch (e) { err = e.name; }
  // Auf das native 'ended' warten (kurzes WAV) — kein fester Sleep im Testcode,
  // sondern ein an das Ereignis gebundenes Promise mit Timeout-Fallback.
  await new Promise((res) => {
    if (a.ended) return res();
    a.addEventListener('ended', res, { once: true });
    setTimeout(res, 2000);
  });
  return { played, err, playing: seen.playing, ended: seen.ended,
           canMp3: a.canPlayType('audio/mpeg'), canWav: a.canPlayType('audio/wav') };
}
"""

results = []


def check(name, ok, note=""):
    results.append((name, ok))
    print(f"  [{'OK ' if ok else 'FAIL'}] {name}{' — ' + note if note else ''}")


def _launch(pw):
    """Echtes Edge bevorzugen; sonst der garantierte Chromium-Build."""
    try:
        b = pw.chromium.launch(channel="msedge")
        return b, "msedge (echtes Edge, MP3-Codec vorhanden)"
    except Exception:                              # noqa: BLE001
        return pw.chromium.launch(), "chromium (Open-Source, kein MP3-Codec)"


def main():
    with sync_playwright() as pw:
        browser, which = _launch(pw)
        print(f"[browser] {which}")
        page = browser.new_page()
        page.goto("about:blank")
        # Eine echte Nutzergeste erzeugen, damit keine Autoplay-Policy stoert.
        page.mouse.click(5, 5)
        res = page.evaluate(PLAY, _valid_wav())
        browser.close()

    print(f"[result] {res}")
    check("echtes play() loest fuer gueltiges WAV auf",
          res["played"] is True, f"err={res['err']}")
    check("natives 'playing'-Ereignis feuert", res["playing"] is True)
    check("natives 'ended'-Ereignis feuert", res["ended"] is True)
    # Nur informativ — belegt die MP3-Codec-Realitaet des Browsers.
    print(f"[info] canPlayType audio/mpeg={res['canMp3']!r}, audio/wav={res['canWav']!r}")

    failed = [n for n, ok in results if not ok]
    print()
    if failed:
        print(f"[verify] {len(failed)} von {len(results)} Codec-Smoke-Pruefungen ROT")
        return 1
    print(f"[verify] {len(results)}/{len(results)} echte Codec-/Event-Pruefungen erfolgreich")
    print("[hinweis] Belegt echte Wiedergabe + native Ereignisse in einem echten "
          "Browser. Die physische Hoerbarkeit auf der WebView2-Instanz des Nutzers "
          "bleibt eine einmalige manuelle Bestaetigung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

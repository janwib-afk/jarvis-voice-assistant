# Prompt 20A — Wartungsledger: Audio-Recovery und Projekthygiene

> Kleiner Red-Green-Nachweis je Slice. Basis: `origin/master`
> `ad6b71284c2171153214ae0e6b8175452bd8dc4f`. Branch
> `fix/post-phase5-audio-and-hygiene`. Kein Prompt 21, keine neue Masterplanphase.

## Slice 1+2+3+4 — Audio-Freischaltung, Recovery, Fehlermatrix, zugänglicher Button

**Reproduzierte Root-Cause (systematic-debugging Phase 1).** Eine Messung lud die
**exakte** eingebettete Freischaltprobe aus `unlockAudio()` gegen ein gültiges
synthetisches WAV im selben Chromium:

| Quelle | `play()` | `canPlayType('audio/mpeg')` |
|---|---|---|
| eingebettete stille MP3 (die Probe) | **NotSupportedError** — „no supported source" | `probably` (irreführend) |
| gültiges synthetisches WAV | **löst auf** | `maybe` |

Damit ist belegt: `unlockAudio()` dispatchte `UserGesture` **erst nach**
`silent.play().then()`. Die Probe ist ungültig → echtes Chromium/Edge lehnt mit
`NotSupportedError` ab → `.catch(() => {})` verschluckte es → `UserGesture` wurde
**nie** dispatcht → `playback` blieb für immer `locked`. Jedes echte TTS-Frame lief
danach in den `AudioReceived`-while-`locked`-Pfad → Puffer + Banner „Audio blockiert",
`playNext()`/`PlayAudio` wurde nie erreicht. Genau der Screenshot.

**Warum die CI das maskierte.** `e2e_audio_seam.py` ersetzte `window.Audio` durch
einen Fake, dessen `play()` **auch die ungültige Probe** auflöste — der Fake log.
`e2e_functional.py::flow_audio_playback` behauptete zudem, ein „Wiedergabeversuch"
habe stattgefunden, obwohl unter `locked` nur gepuffert wird. `--smoke` führt
`audio_playback` gar nicht aus.

**Erstes beobachtetes ROT.** Nachdem der Fake realistisch gemacht wurde (die
`data:audio/mp3`-Probe lehnt jetzt wie echtes Chromium ab), scheiterten **9 von 11**
Audio-Seam-Prüfungen: alle sechs Altfälle hingen an `_prepare()` (Freischaltung nie),
der neue Kaltstart-Fall fand keinen „Audio aktivieren"-Button, der NotSupported-Fall
loopte. Zusätzlich 2 rote Reducer-Contract-Fälle (Mute-Orthogonalität).

**Minimales GRÜN.**
* `unlockAudio()` → `activateAudio()`: dispatcht `UserGesture` **direkt** auf eine
  echte Nutzergeste, ohne stille MP3-Probe. Verbraucht die Reducer-Effekte
  (`DismissBanner`, `PlayAudio`). Der Reducer schaltet ohnehin ohne Probe frei.
* **Ein** kanonischer Recovery-Weg: die Nutzergeste (Klick/Taste/Button). Der
  frühere konkurrierende `document.addEventListener('click', retry)` in `playNext`
  ist entfernt — keine rekursiven `playNext`-Ketten, kein doppeltes Abspielen.
* **Fehlermatrix** in `handlePlayFailure`: `NotAllowedError` → behebbare Autoplay-
  Sperre (Banner + Button); `NotSupportedError`/Decode → ehrlicher Formatfehler,
  **kein** „Klick benötigt", Queue deterministisch geleert; `AbortError` → erwarteter
  Abbruch, keine Warnung; unbekannt → diagnostisch, keine Endlosschleife.
* **Epoch-Guard**: eine verspätete Ablehnung trägt ihre Ursprungs-Epoch; weicht sie
  von der aktuellen ab, wird nur aufgeräumt.
* **Exact-once-Cleanup** über `releaseAudio(audio, url)` mit Doppel-Revoke-Schutz —
  Erfolg, Fehler, Stop und stale laufen alle durch denselben Weg.
* **Zugänglicher Button** „Audio aktivieren": ein echtes `<button>` (`#audio-unlock-btn`,
  `data-audio-unlock`) im Blockade-Banner, fokussierbar und per Tastatur nutzbar,
  ruft dieselbe kanonische `activateAudio` in einer echten Geste.
* **Nur ungefährliche Metadaten** geloggt (`DOMException.name`, MIME, Byte-Länge,
  Epoch, Queue-Länge) — nie Base64-Audio, TTS-Text oder Secrets. `console.warn`,
  nicht `error` (stört `assert_clean` nicht).
* **Reducer-Orthogonalität** (§9): `AudioReceived` erhält `capture:'muted'` beim Start
  der Wiedergabe — Mikrofon-Mute ent-stummt nicht mehr durch TTS.

**Grüne Evidenz.** Voice-Contract **57/57** (2 neue Mute-Fälle), Audio-Seam **31/31**
(10 Fälle: Kaltstart ohne Geste, NotSupported, Stop-während-pending-`play()`, Mute
erlaubt TTS u.a.), Functional **alle Flows grün** (der Audio-Flow prüft jetzt ehrlich
Pufferung unter `locked` + echten MP3-`NotSupportedError` **ohne** Fake), A11y 22/22,
Reduced-Motion 16/16, Race-Matrix 16/16, Visual grün ohne Baseline-Update.

**Echter Codec-/Event-Nachweis.** Neuer `e2e_audio_codec.py` **ohne** `window.Audio`-
Fake: bevorzugt echtes Edge (`channel='msedge'`) und belegt `play()`-Erfolg für ein
gültiges WAV **plus** native `playing`/`ended`-Ereignisse. Auf dieser Maschine lief er
gegen **echtes Edge** (msedge, MP3-Codec `probably`). Die physische Hörbarkeit auf der
WebView2-Instanz des Nutzers bleibt eine einmalige manuelle Bestätigung.

**Rollback.** `git revert` dieses Commits stellt den alten (defekten) Audio-Pfad
wieder her; die realistische Fake-Härtung und die neuen Fälle würden mit
zurückgenommen.

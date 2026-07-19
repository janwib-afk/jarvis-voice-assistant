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

## Slice 5 — Test-Environment-Isolation

**Belegter Leak.** `tests/__init__.py` setzt `JARVIS_SKIP_STARTUP_REFRESH` per
`setdefault`. Sechs Testmodule **poppten** es im tearDown pauschal statt den
Ausgangswert wiederherzustellen — nach der Suite war es netto entfernt. Ein weiter
hinten sortierter Lifespan-Test hätte dann ohne Skip einen echten `wttr.in`-Zugriff
ausgelöst (reihenfolgeabhängig, kostenwirksam).

**Erstes beobachtetes ROT.** Der neue Env-Integritäts-Check im Smoke-Test wurde rot:
„die Suite hat verändert: JARVIS_SKIP_STARTUP_REFRESH".

**Minimales GRÜN.**
* `tests/env_guard.py`: `guard_env(test, *names)` schnappt den **exakten** Zustand
  (vorhanden-mit-Wert vs. fehlend) und stellt ihn über `addCleanup` wieder her —
  läuft bei Erfolg, Fehler **und** Setup-Abbruch, nie ein blanko `pop()`.
* Alle env-mutierenden Testmodule nutzen `guard_env` statt der pauschalen Pops.
* Smoke-Test vergleicht `JARVIS_SKIP_STARTUP_REFRESH`/`JARVIS_CONFIG_PATH` vor/nach
  der Suite und wird rot bei Netto-Drift.
* `tests/test_env_isolation.py`: fehlend→fehlend, Sentinel-Wert exakt, Restore trotz
  Ausnahme, Reihenfolge-Unabhängigkeit (Popper↔Setter beide Wege), und **§6.7**: mit
  gesetztem Skip löst der Serverstart keinen Refresh aus und eine
  `urllib.request.urlopen`-Tripwire fängt jeden echten `wttr.in`-Zugriff.

**Import-Robustheit.** `from tests.env_guard import guard_env` funktioniert sowohl
unter `discover -s tests` als auch unter `python -m unittest tests.<Modul>`.

**Grüne Evidenz.** Volle Suite 1248 OK; env-mutierende Module in umgekehrter und
gemischter Reihenfolge grün; Smoke-Env-Integrität grün.

**Rollback.** `git revert`; die Tests kehren zu den pauschalen Pops zurück (Leak).

## Slice 6 — Wetter-Response schliessen + ResourceWarnings

**Belegter Leak.** `assistant_core.get_weather_sync()` rief
`urllib.request.urlopen(...)` ohne jedes Schliessen: die Response leckte bei
Erfolg, bei `read()`/JSON-Fehler und — besonders — bei `HTTPError`, den `urlopen`
bereits beim Aufruf wirft (ein einfaches `with urlopen(...)` bindet dann nie).

**Erstes beobachtetes ROT.** Erfolgs- und JSON-Fehler-Response nicht geschlossen
(`closed_flag` False); zwei `ResourceWarning: Implicitly cleaning up <HTTPError 503>`.

**Minimales GRÜN.**
* Erfolg/`read()`/JSON: `with urllib.request.urlopen(...) as resp:`.
* `except urllib.error.HTTPError as e: e.close()` — separat, weil der Fehler die
  offene Response selbst ist.
* Unverändert: genau **zwei** Versuche, **5 s** Timeout, bestehendes Logging (je
  Versuch ein `context.refresh_failed`), `None`-Fallback, keine zweite Retry-Schicht.

**ResourceWarnings in `tests/test_action_deep_module.py`.** Drei
`open(...).read()`-Reads liefen ohne Context-Manager (unclosed file). Auf `with
open(...) as _f:` umgestellt — reine Ressourcenhygiene, keine Verhaltensänderung.

**Grüne Evidenz.** `test_weather_resource.py` 5/5; `test_action_deep_module.py` 64/64
unter `-W error::ResourceWarning`; volle Suite 1253 OK.

**Rollback.** `git revert`.

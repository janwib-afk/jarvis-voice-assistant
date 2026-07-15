# Jarvis – Windows-Native-Tests (Phase 3B)

> Trennung zwischen **automatisiert & sicher** (auf Hosted-Windows-Runnern),
> **Self-hosted** (echtes Fenster/Hardware auf einer betreuten Maschine) und
> **external-manual** (menschliche Prüfung). Keine Hardwareprüfung wird als
> automatisch grün ausgegeben, wenn sie nicht tatsächlich ausgeführt wurde.

## A. Automatisiert & sicher (Hosted-Windows-Runner)

Skript: `tests/native/windows_native_smoke.py` (kein Fenster, keine echte App,
keine Audiohardware). **Sicherheitsvorkehrungen:** Launcher wird nur
`py_compile`-kompiliert (nicht importiert — Import-Seiteneffekte: Logrotation,
stdout/stderr-Umleitung); App-Start über Fake-Adapter; Monitor-Daten aus dem
echten ctypes-Adapter, aber ohne Fensterbewegung.

| Test | Voraussetzung | Erwartetes Verhalten | Nachweis |
|---|---|---|---|
| Launcher kompiliert | Python 3.12 | `jarvis-launcher.pyw` parst ohne Ausführung | `py_compile` ok |
| Bridge-Deps importierbar | `webview`, `pystray`, `keyboard` installiert | Import ohne Fenster/Hook | 3× OK |
| Monitor-Adapter | Windows | `detect_monitors()` liefert Liste (leer = Fallback) | Liste (hier 2 Monitore) |
| Prozess-Adapter (Fake) | — | Allowlist-App „startet" nur über Fake; unbekannte App nicht | `ok`+kein echter Prozess |
| Placement-Allowlists | — | Monitor/Zone konsistent über `actions`/`config_loader`/`app_launcher` | Tupel-Gleichheit |

Ergänzend automatisiert & sicher (bestehende Suite, `python -m unittest`):
`tests/test_monitors.py` (Monitor-Adapter inkl. Fehlerpfad), `tests/test_app_launcher.py`
(Prozess-/URL-Adapter mit Fake, VS-Code-Auflösung), `tests/test_launcher_api.py`
(Monitor-Route, Placement/Autostart/Profile über REST), `tests/test_launcher_ps1.py`
(statische Prüfung von `scripts/launch-session.ps1`). Der **Window-Mode-Vertrag**
(fullscreen/focus/panel, `aria-pressed`, Root-Klassen) wird ohne echte Fenster-
mutation über den Browser-Flow `window_modes` (`e2e_functional.py`) geprüft.

## B. Self-hosted (betreute Windows-Maschine, echtes Fenster/Hardware)

Nur auf einer vertrauenswürdigen, betreuten Maschine ausführen — **nicht** auf
Hosted-Runnern (keine echte Desktopmutation, keine App-Starts, keine Audiohardware
dort). Start: `python jarvis-launcher.pyw` (Diagnose-Flags: `JARVIS_DEBUG`,
`JARVIS_NO_MICA`, `JARVIS_NO_HOTKEY`, `JARVIS_NO_TRAY`).

| Test | Voraussetzung | Erwartetes Verhalten | Nachweis | Sicherheitsvorkehrung |
|---|---|---|---|---|
| pywebview-Fenster | Windows 11, WebView2 | rahmenloses Fenster öffnet, Boot-Fallback verschwindet | Sichtprüfung/Screenshot | gegen Baseline-Harness (Port 8341), nie echte config |
| Tray-Icon + Menü | pystray | Icon erscheint, Menü öffnet/versteckt | Sichtprüfung | — |
| Win+J Hotkey | `keyboard`, Fokus | blendet Fenster ein/aus | Sichtprüfung | Hotkey nur lokal |
| Mica-Effekt | Win 11 + `win32mica` | transluzenter Hintergrund | Sichtprüfung | `JARVIS_NO_MICA` als Fallback |
| Panel/Fokus/Vollbild-Größe | pywebview `set_window_mode` | native Fenstergröße wechselt | Sichtprüfung | — |
| Echte App-Positionierung | `launch-session.ps1`, echte Apps | Fenster landen auf Monitor/Zone | Sichtprüfung | **startet echte Apps** — nur betreut |

## C. External-manual (menschliche Prüfung, echte Hardware/Dienste)

| Test | Voraussetzung | Erwartetes Verhalten | Nachweis | Sicherheitsvorkehrung |
|---|---|---|---|---|
| Doppelklatschen-Trigger | Mikrofon, `scripts/clap-trigger.py` | Clap startet Session/Profil | Beobachtung | startet echte Apps — bewusst |
| Echtes Mikrofon / STT | Chrome + Google-Speech | Sprache → Transcript | Beobachtung | gegen Harness, kein echtes LLM |
| Echte TTS-Wiedergabe | ElevenLabs-Key, Lautsprecher | Audio spielt | Hören | **echte API-Kosten** — nur bewusst |
| Echter Screenreader | NVDA/Narrator | Landmarken/Namen/Live-Regions vorgelesen | Hörprotokoll | — |
| Installer/Recovery | — | — | — | Phase 11/13, nicht hier |

## Klassifikations-Regel

- **A** läuft im schnellen PR-Gate (`windows_native_smoke.py`) — real, sicher.
- **B**/**C** werden **nicht** auf Hosted-Runnern grün gemeldet; sie sind als
  Self-hosted/manuell markiert und liefern Evidenz nur, wenn sie tatsächlich
  betreut ausgeführt wurden.

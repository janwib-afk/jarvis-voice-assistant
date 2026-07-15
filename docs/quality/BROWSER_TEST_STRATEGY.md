# Jarvis – Browser-Teststrategie (Phase 3B)

> Reproduzierbares Browser-/Windows-Testsystem für die eingefrorene, freigegebene
> Jarvis-UI. Runner-Entscheidung: [../adr/0006-browser-test-architecture-python-playwright.md](../adr/0006-browser-test-architecture-python-playwright.md).
> Seams: [TEST_SEAMS.md](TEST_SEAMS.md) (SEAM-BROWSER-UI, SEAM-WINDOWS).

## Ebenen (klar getrennt)

| Ebene | Datei | Zweck |
|---|---|---|
| Funktionale E2E | `tests/browser/e2e_functional.py` | echte REST-/WS-Pfade, kontrollierte Adapter |
| Accessibility/Keyboard | `tests/browser/e2e_a11y.py` | semantisches DOM + Tastaturbedienung |
| Reduced Motion | `tests/browser/e2e_reduced_motion.py` | `prefers-reduced-motion`-Verhalten |
| Visual Regression | `tests/browser/e2e_visual.py` | Pixeldiff gegen bestätigte Baseline |
| Windows-Native (sicher) | `tests/native/windows_native_smoke.py` | Adapter-Vertrag ohne echtes Fenster |
| Shared Harness | `tests/browser/e2e_harness.py`, `e2e_server.py` | Server-Lifecycle, Kontext, Sammler |
| Native (manuell) | [WINDOWS_NATIVE_TESTS.md](WINDOWS_NATIVE_TESTS.md) | Self-hosted/external-manual |

## Runner & Server-Lifecycle

- **Runner:** Python Playwright (`sync_api`), Chromium headless.
- **Server:** der ECHTE Jarvis-FastAPI-Server (`e2e_server.py`) als Subprozess,
  ausschließlich `127.0.0.1`, auf einem **dynamischen freien Port**
  (`e2e_harness.free_port`).
- **Readiness:** **nicht** `networkidle` (Jarvis hält den WS offen), sondern der
  sichtbare Zustand „Server verbunden" (`#sc-conn-text`) **plus** die beantwortete
  Auto-Begrüßung (`#transcript .msg.jarvis >= 1`) — siehe `open_jarvis`.
- **Start/Shutdown:** kontrolliert über `JarvisServer.__enter__/__exit__`
  (terminate → kill-Fallback → warten); kein Zombie-Prozess, kein belegter Port
  nach Testende (jeder Lauf nimmt einen neuen freien Port).
- **Logs:** ein eigenes Logfile pro Lauf unter `JARVIS_E2E_ARTIFACTS` (Default
  `%TEMP%/jarvis-e2e-artifacts`); bei Erfolg gelöscht, bei Fehler als Artefakt
  behalten. Keine Secrets (Dummy-Keys).

## Synthetische Config & Provideradapter (Teil C)

`e2e_server.py` schreibt eine Temp-`config.json` mit **Dummy-Keys** und
synthetischen Apps/Profilen/Musik; die echte `config.json` wird nie geladen.
Real bleiben: FastAPI-App, REST-Routing, WS-Endpunkt, Action-Parser, Queue-/
Stop-Logik, Config-Validierung, eigene Launcher-/Profilregeln, temporäre
Persistenz. **Kontrolliert ersetzt** (spezifische Adapter, kein generischer Fake):

| Grenze | Stub |
|---|---|
| Anthropic (`assistant_core.ai`) | steuerbare Antwort-Queue über `/__e2e__/scenario` |
| ElevenLabs (`synthesize_speech`) | `(b"", None)` — kein Audio, kein Netz |
| Wetter (`refresh_data`) | No-Op |
| externe Websites/Browser (`browser_tools.*`) | synthetische Treffer; `action_delay` für Stop-Tests |
| Clipboard, Screen | synthetische Strings |
| App-Start (`_start_url`/`_start_process`) | No-Op (kein echter Prozess) |
| Monitor-Hardware (`detect_monitors`) | feste 2-Monitor-Daten |

LLM-Szenarien: normale Antwort · Antwort mit Legacy-Action · verzögerte Action
(Stop) · Providerfehler (`{"raise": true}`) · Recherche-Antwort. Der Steuerkanal
`/__e2e__/*` ist reine Test-Infra (Loopback, ephemer) und berührt keinen
Produktionscode.

## Testisolation

- Browser-E2E laufen **sequenziell**; Parallelisierung erst nach einem expliziten
  Isolationsnachweis.
- **Frischer Server-Subprozess UND frischer Browserkontext pro Flow** — eigene
  Temp-Persistenz, keine geteilte Conversation-/Config-/Profil-/Musik-Mutation.
- Cleanup (Kontext + Server + Tempdir) läuft auch bei Testfehlern
  (Context-Manager `finally`).

## Netzwerk-Policy (Teil, Fehlerpolitik)

`attach_collectors` routet **jeden** Request: erlaubt nur die lokale Testorigin
und `data:`/`blob:`; jeder andere Host wird geblockt **und** als
`external_hosts` erfasst → Test schlägt fehl. Damit: keine CDN-Schrift, kein
Tracking, kein externer Audiostream, keine Providerdomain, keine echte Website.

## Locator-Strategie

Reihenfolge: `get_by_role` → `get_by_label` → `get_by_placeholder` → sichtbarer
stabiler Text → gezielter Marker. Verboten als primär: fragile CSS-Verschachtelung,
`nth-child`, Stil-/Zufallsklassen, DOM-Pfade. Wo nur eine ID/`data-*` eindeutig
ist (z. B. `#transcript`, `.app-module[data-app=…]`), wird **eng gescoped**
(App-Identität), nie über Layout-Klassen. Es wurde **kein** `data-testid` zur
Produktion hinzugefügt (die UI ist ausreichend semantisch).

## Waiting-Strategie

Playwright-Auto-Waiting + `expect`-Polling + `wait_for_function` auf sichtbare
Zustände/DOM-Ereignisse. **Keine** festen Sleeps/`wait_for_timeout` zur
Synchronisation. Timeouts werden nicht blind erhöht — Ursache zuerst verstehen.

## Fehlerpolitik (`Collectors.assert_clean`)

Ein Browsertest schlägt fehl bei: `pageerror`, unhandled Rejection, unerwartetem
`console.error`, fehlgeschlagenem lokalem Request, unerwartetem externen Request,
404 auf benötigte Assets, nicht geschlossenem Kontext, zurückbleibendem
Serverprozess. **Erlaubte Warnungen:** keine pauschale Unterdrückung; es werden
nur `console.error` gezählt (die App nutzt `console.log`/`console.warn` für
Betriebsmeldungen — z. B. „WebSocket connected", „Autoplay blocked" —, die keine
Fehler sind). Im Regelbetrieb (leeres Audio) tritt die Autoplay-Warnung nicht auf.

## Failure Artifacts (Teil G)

Serverlog pro Lauf (redigiert, Dummy-Keys) unter `JARVIS_E2E_ARTIFACTS`, in CI als
Failure-Artefakt hochgeladen. Screenshots/Trace/Video können pro Flow ergänzt
werden; Artefakte liegen in einem ignorierten Temp-Verzeichnis, ohne Secrets/
persönliche Inhalte, und werden nur bei Fehlern behalten.

## Visual Baselines (Teil F)

Deterministische Aufnahme (feste Uhr + Animationen aus via Harness-Init, lokale
Fonts `document.fonts.status==='loaded'`, definierter Viewport, Device-Scale 1,
synthetische Daten, 0 externe Assets) → Pixeldiff (Pillow/numpy) gegen
`tests/browser/visual_baseline/`. Toleranz 0.2 % abweichender Pixel
(Kanal-Schwelle 16). **Plattform:** Windows/Chromium (headless), gepinnt; keine
Linux-/macOS-Baselines mischen. Die Phase-0-Screenshots unter
`docs/design-baseline/screenshots` sind die **Vor-Redesign-Baseline** und werden
weder überschrieben noch als Vergleichsziel genutzt. Funktionale Assertions
bleiben zusätzlich bestehen — Visual ersetzt sie nie.

## Accessibility (Teil E)

Semantische/Keyboard-Pflichtprüfungen (unabhängig von Axe): Landmarken, genau eine
exponierte H1 je Bereich, zugängliche Namen aller Icon-Buttons, Live-Regions,
sichtbarer Tastaturfokus (`:focus-visible`-Outline), Skip-Link, mausfreie
Kernbedienung, Escape-Stopp, keine Tastaturfalle, `aria-pressed`, Settings-Labels,
Monitor-Zuweisung per Tastatur. **Keine** WCAG-Vollkonformitäts- oder
echte-Screenreader-Behauptung.

## Windows-Native-Abgrenzung

Sichere, automatisierbare Adapter-Smokes (`tests/native/windows_native_smoke.py`)
vs. Self-hosted/manuelle Hardware-/Fenster-Tests — vollständig klassifiziert in
[WINDOWS_NATIVE_TESTS.md](WINDOWS_NATIVE_TESTS.md).

## CI-Aufteilung & manuelle Gates

Schnelle PR-Gates + spätere Nightly/Release-Gates: siehe
[CI_PIPELINE.md](CI_PIPELINE.md). Visual-Vollmatrix, Native-Hardware, Soak, Fault
Injection, Installer/Rollback sind **nicht** im schnellen PR-Lauf (Phase 11/13).
